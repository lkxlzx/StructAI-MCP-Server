"""Infrastructure · Storage · LocalFilesystemStorage（`docs/02` §3.4 / §56；§30 / §84）。

权威来源
--------
- `docs/02` §3.4（LocalFilesystemStorage）—— Core Alpha 的第一实现：
  `./data/artifacts/<tenant_id>/<project_id>/<artifact_id>/payload`；「**禁止**直接使用
  用户提供的文件名作为最终路径」。
- `docs/02` §3.3（Storage Protocol）—— 流式 `put(storage_key, stream)` /
  `get(storage_key) -> BinaryIO` / `delete(storage_key)` / `exists(storage_key)`；
  本模块同时实现 P03 冻结的 Domain 契约 `ArtifactStorage`（`docs/02` §11 / §29 / §33）。
- `docs/02` §30（Document Service / Retry 语义）—— 删除 / 清理类操作必须**幂等**：
  重试不得因为「上一次已经删掉」而失败。
- `docs/02` §56（Definition of Done / Security Acceptance）—— `artifact path traversal
  protection` / `artifact filename sanitization`；`docs/07` §14.4「禁止无限 payload」
  ⇒ 读写必须分块。
- `docs/02` §84（Final Architecture）—— 完整性验证 = `checksum(original) ==
  checksum(read)`，故本模块提供 `checksum()`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **写路径 = `mkdir` → `<path>.tmp` → `os.replace`**：`docs/02` §3.4 只要求「不要用
   用户文件名」，未规定原子性；但 §30 的重试语义与「Artifact 写入中断」的恢复用例
   （`docs/02` §48）都要求「要么旧内容，要么新内容，不存在半截文件」。同目录
   `os.replace()` 是原子替换，`.tmp` 与目标同目录 ⇒ 同文件系统。
2. **阻塞 I/O 一律经 `asyncio.to_thread`**：`docs/02` §2.2 是全链路异步；同步文件
   I/O 直接跑在事件循环里会阻塞其它请求（`docs/07` §14.4「单实例失败不得让整个
   服务器不可用」同理）。
3. **构造器不做 I/O**：`__init__` 只 `resolve()` 根路径，**不**建目录（目录在首次写入时
   创建）。否则「配置了路径但还没用到产物」的进程会凭空产生目录，测试也无法区分
   「后端建了目录」与「调用方建了目录」。
4. **引用解析：存储键 OR 裸产物 id**：Domain 契约 `ArtifactStorage.get(artifact_id)`
   （`docs/02` §11）用的是产物 id，而 `docs/02` §3.3 / §3.5 用的是存储键。本实现两者
   都接受：含 `/`（或 `\\`）→ 按存储键走 `path_for()`；否则视为裸 id，在
   `<root>/*/*/<id>/payload` 中要求**恰好一条**命中。0 条 / 多条都落
   `reason="missing_payload"` —— 多条命中说明「用 id 定位」本身不成立，静默挑一条
   会让调用方读到**别的**产物。
5. **删除是幂等的，且向上剪掉空目录**：文件不存在不算错误（`docs/02` §30 的重试
   语义）；删除后把空掉的父目录一路 `rmdir` 到 `root`（不含 `root`），避免产物目录
   无限堆积空壳。裸 id 命中多条时**不**删除任何一条（同裁决 4：不猜）。
6. **`path_for()` 是公开的遍历守卫**：`relative_storage_path()` 先做词法守卫
   （绝对键 / `..` / 空段 / 反斜杠），再用 `Path.resolve()` 确认最终路径仍在 `root`
   之内（符号链接逃逸），失败落 `reason="path_traversal"`（`docs/02` §56）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / 同包的 `storage.base`：**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.application` / `app.interfaces`，
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import asyncio
import glob
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, BinaryIO, Final

from app.domain.errors import ArtifactError
from app.infrastructure.storage.base import (
    DEFAULT_CHUNK_SIZE,
    PAYLOAD_FILENAME,
    STORAGE_STAGE,
    relative_storage_path,
    sha256_stream,
    storage_key_for,
)

__all__ = ["BACKEND_NAME", "LocalFilesystemStorage"]

BACKEND_NAME: Final[str] = "local"
"""后端标识（`docs/02` §29「Core Alpha = 本地文件系统」；落 `artifacts.storage_backend`）。"""

TMP_SUFFIX: Final[str] = ".tmp"
"""原子写入的临时后缀（见模块裁决 1）。"""


class LocalFilesystemStorage:
    """本地文件系统存储后端（`docs/02` §3.4 / §29 / §33）。

    目录形状（`docs/02` §3.4）：

        <root>/<tenant_id>/<project_id>/<artifact_id>/payload

    ⚠️ 路径**只**由 `docs/02` §3.5 的存储键决定；用户提供的文件名最多经
    `sanitize_filename()` 变成标签，**绝不**进入路径（`docs/02` §3.4）。
    本类**不**持有事务、**不** `commit`（`docs/07` §14.4）。
    """

    def __init__(self, root: str | Path, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        """绑定存储根目录（**不**做 I/O，**不**建目录；见模块裁决 3）。

        Args:
            root: 存储根目录（`Settings.artifact_root`，`docs/02` §38）。
            chunk_size: 分块读写大小（`docs/02` §3.6 的 `1024 * 1024`）。

        Raises:
            ValueError: `chunk_size <= 0`（装配错误，**不**静默回落默认值）。
        """
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        self._root = Path(root).expanduser().resolve()
        self._chunk_size = chunk_size

    @property
    def root(self) -> Path:
        """存储根目录（已 `resolve()`）。"""
        return self._root

    @property
    def chunk_size(self) -> int:
        """分块读写大小（字节）。"""
        return self._chunk_size

    # ===== Domain 契约 `ArtifactStorage`（`docs/02` §11 / §29 / §33）+ `exists` =====

    async def put(self, data: bytes, metadata: Mapping[str, Any]) -> str:
        """写入字节流并返回存储键（`docs/02` §3.5 / §33）。

        Args:
            data: 产物字节（`docs/02` §3.6 已在调用方算出 `checksum`）。
            metadata: 至少含 `storage_key`，或含 `tenant_id` / `artifact_id`
                （可选 `project_id`）以便按 `docs/02` §3.5 生成键。

        Returns:
            实际使用的存储键（`docs/02` §3.5 形状）。

        Raises:
            ArtifactError: `STRUCTAI-6200`，`reason="invalid_metadata"`（元数据不足以
                定位一个键）或 `reason="invalid_storage_key"` / `"path_traversal"`。
        """
        key = self._key_from_metadata(metadata)
        path = self.path_for(key)
        await asyncio.to_thread(self._write_bytes, path, data)
        return key

    async def put_stream(self, storage_key: str, stream: BinaryIO) -> str:
        """流式写入（`docs/02` §3.3 的 `put(storage_key, stream)`）。

        Args:
            storage_key: 目标键（`docs/02` §3.5）。
            stream: 二进制流；按 `chunk_size` 分块读取（`docs/02` §3.6）。

        Returns:
            传入的 `storage_key`（`docs/02` §3.3 的流式形状返回键）。
        """
        path = self.path_for(storage_key)
        await asyncio.to_thread(self._write_stream, path, stream)
        return storage_key

    async def get(self, reference: str) -> bytes:
        """读回字节流（`docs/02` §11 / §29 / §33）。

        Args:
            reference: 存储键，或**裸产物 id**（见模块裁决 4）。

        Returns:
            产物字节。

        Raises:
            ArtifactError: `STRUCTAI-6200`，`reason="missing_payload"` —— 文件不存在，
                或裸 id 命中 0 条 / 多条（见模块裁决 4）。
        """
        path = await self._resolved_existing_path(reference)
        return await asyncio.to_thread(path.read_bytes)

    async def get_stream(self, reference: str) -> BinaryIO:
        """以二进制流返回产物（`docs/02` §3.3 的 `get(storage_key) -> BinaryIO`）。

        ⚠️ 调用方负责关闭返回的流。
        """
        path = await self._resolved_existing_path(reference)
        handle = await asyncio.to_thread(path.open, "rb")
        return handle

    async def delete(self, reference: str) -> None:
        """删除产物并剪掉空目录（`docs/02` §30 的重试语义：**幂等**）。

        文件不存在**不**是错误；裸 id 命中多条时**不**删除任何一条（模块裁决 5）。
        """
        if self._looks_like_key(reference):
            await asyncio.to_thread(self._delete_payload, self.path_for(reference))
            return
        matches = self._matches_for_artifact_id(reference)
        if len(matches) > 1:
            raise _missing_payload()
        if not matches:
            return
        await asyncio.to_thread(self._delete_payload, matches[0])

    async def exists(self, reference: str) -> bool:
        """产物是否存在（`docs/02` §3.3 / §49 的 Artifact Test Matrix）。

        裸 id 不存在 → `False`（**不**抛）；非法键 → `STRUCTAI-6200`（模块裁决 4）。
        """
        if self._looks_like_key(reference):
            path = self.path_for(reference)
            return await asyncio.to_thread(path.is_file)
        return len(self._matches_for_artifact_id(reference)) > 0

    async def checksum(self, reference: str) -> str:
        """读回并计算 SHA-256（`docs/02` §3.6 / §84 的完整性验证）。

        Raises:
            ArtifactError: `STRUCTAI-6200`，`reason="missing_payload"`。
        """
        path = await self._resolved_existing_path(reference)
        return await asyncio.to_thread(self._checksum_file, path)

    # ===== 路径守卫（公开，供上层 / 测试断言）=====

    def path_for(self, reference: str) -> Path:
        """把存储键解析为根目录内的真实路径（`docs/02` §3.4 / §56）。

        Args:
            reference: 存储键（`docs/02` §3.5）。

        Returns:
            `<root>/<tenant_id>/<project_id>/<artifact_id>/payload`（不必存在）。

        Raises:
            ArtifactError: `STRUCTAI-6200` —— 词法非法落 `reason="invalid_storage_key"`；
                解析后逃出 `root`（含符号链接）落 `reason="path_traversal"`。
        """
        relative = relative_storage_path(reference)
        candidate = self._root.joinpath(*relative.parts)
        if not candidate.resolve().is_relative_to(self._root):
            raise ArtifactError(
                "artifact path escapes the storage root",
                details={"stage": STORAGE_STAGE, "reason": "path_traversal"},
            )
        return candidate

    def __repr__(self) -> str:
        """诊断表示（只有根路径与分块大小，**绝不**含 payload）。"""
        return (
            f"LocalFilesystemStorage(root={self._root.as_posix()!r}, chunk_size={self._chunk_size})"
        )

    # ===== 内部：键 / 引用解析 =====

    def _key_from_metadata(self, metadata: Mapping[str, Any]) -> str:
        """由元数据得到存储键（`docs/02` §3.5 / §33）。"""
        key = metadata.get("storage_key")
        if isinstance(key, str) and key:
            return key
        tenant_id = metadata.get("tenant_id")
        artifact_id = metadata.get("artifact_id")
        project_id = metadata.get("project_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise _invalid_metadata()
        if not isinstance(artifact_id, str) or not artifact_id:
            raise _invalid_metadata()
        if project_id is not None and not isinstance(project_id, str):
            raise _invalid_metadata()
        return storage_key_for(
            tenant_id=tenant_id,
            project_id=project_id,
            artifact_id=artifact_id,
        )

    def _looks_like_key(self, reference: str) -> bool:
        """是否按**存储键**解析（含分隔符即视为键，见模块裁决 4）。"""
        return "/" in reference or "\\" in reference

    def _matches_for_artifact_id(self, artifact_id: str) -> tuple[Path, ...]:
        """裸产物 id 的候选路径（`<root>/*/*/<id>/payload`，见模块裁决 4）。"""
        if not artifact_id:
            return ()
        pattern = f"*/*/{glob.escape(artifact_id)}/{PAYLOAD_FILENAME}"
        return tuple(sorted(self._root.glob(pattern)))

    async def _resolved_existing_path(self, reference: str) -> Path:
        """解析引用并要求**恰好一条**命中且文件存在（见模块裁决 4）。"""
        if self._looks_like_key(reference):
            path = self.path_for(reference)
            exists = await asyncio.to_thread(path.is_file)
            if not exists:
                raise _missing_payload()
            return path
        matches = self._matches_for_artifact_id(reference)
        if len(matches) != 1:
            raise _missing_payload()
        return matches[0]

    # ===== 内部：阻塞 I/O（一律经 `asyncio.to_thread`，见模块裁决 2）=====

    def _write_bytes(self, path: Path, data: bytes) -> None:
        """原子写入字节（见模块裁决 1）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + TMP_SUFFIX)
        try:
            with temporary.open("wb") as handle:
                handle.write(data)
            os.replace(temporary, path)
        except BaseException:
            _unlink_quietly(temporary)
            raise

    def _write_stream(self, path: Path, stream: BinaryIO) -> None:
        """分块写入流并原子替换（`docs/02` §3.3 / §3.6）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + TMP_SUFFIX)
        try:
            with temporary.open("wb") as handle:
                while True:
                    chunk = stream.read(self._chunk_size)
                    if not chunk:
                        break
                    handle.write(chunk)
            os.replace(temporary, path)
        except BaseException:
            _unlink_quietly(temporary)
            raise

    def _delete_payload(self, path: Path) -> None:
        """删除产物并向上剪掉空目录（不含 `root`；见模块裁决 5）。"""
        if path.exists():
            path.unlink()
        parent = path.parent
        while parent != self._root and parent.is_relative_to(self._root):
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def _checksum_file(self, path: Path) -> str:
        """分块计算文件校验值（`docs/02` §3.6）。"""
        with path.open("rb") as handle:
            return sha256_stream(handle)


def _unlink_quietly(path: Path) -> None:
    """尽力删除临时文件（失败不掩盖原始异常）。"""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def _invalid_metadata() -> ArtifactError:
    """元数据不足以定位存储键（`STRUCTAI-6200`，`docs/07` §11 / §14.3）。"""
    return ArtifactError(
        "artifact storage metadata is invalid",
        details={"stage": STORAGE_STAGE, "reason": "invalid_metadata"},
    )


def _missing_payload() -> ArtifactError:
    """产物 payload 不可定位 / 不存在（`STRUCTAI-6200`，`docs/07` §11 / §14.3）。"""
    return ArtifactError(
        "artifact payload is missing",
        details={"stage": STORAGE_STAGE, "reason": "missing_payload"},
    )
