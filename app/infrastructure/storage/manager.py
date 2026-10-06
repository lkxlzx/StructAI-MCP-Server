"""Infrastructure · Storage · Manager（`docs/02` §29 / §33 / §56）。

权威来源
--------
- `docs/02` §29（Artifact Storage）—— 第一阶段实现 `LocalFilesystemStorage`；
  数据库只保存 metadata（`storage_backend` / `storage_key` / `mime_type` / `size` /
  `checksum`），字节流落存储后端。
- `docs/02` §33（Artifact Service）—— 服务端选择后端；`storage_backend` 是
  `artifacts` 表的列（`docs/07` §4.3 #21），因此「用哪个后端」必须**可记录、可回放**。
- `docs/02` §56（Definition of Done）—— `[ ] Artifact Storage`；后端可替换而不改
  Application 接口（与 `docs/02` §38 的事件总线同一口径）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **注册表在进程内、按名字寻址**：`docs/02` §29 只给出「第一阶段 = 本地文件系统」，
   未规定装配方式。本模块用「名字 → 后端」的注册表承载
   `artifacts.storage_backend`（`docs/07` §4.3 #21）的取值，使「读一个历史产物」可以
   按**当时记录的后端名**回放，而不是假定当前默认后端。注册表是**进程内**的：
   `docs/02` §29 的第一阶段不引入对象存储 SDK，故没有需要跨进程共享的注册信息。
2. **注册 / 取用失败落 `STRUCTAI-7000`（`InternalError`）**：空白名 / 重复注册 /
   未知后端都是**装配错误**，不是业务错误 —— 20 码契约里没有「后端未注册」的码
   （`docs/07` §11），而 7000 是兜底内部错误（`docs/07` §11 的 `INTERNAL_ERROR`）。
   失败**绝不**静默回落到默认后端：那会让「读错后端」表现为「产物不存在」。
3. **`checksum()` 需要后端能力声明**：`docs/02` §3.3 的 `ArtifactStorage` 契约没有
   `checksum`，只有本地后端（`docs/02` §3.6 / §84）提供它。故本模块在调用处收窄为
   私有协议 `_ChecksumCapableBackend`：不支持的后端**明确拒绝**（7000），而不是
   由 Manager 自己去读一遍字节（那会绕过后端封装）。
4. **`build_local_storage()` 注册的是「默认后端名」下的本地后端**：Core Alpha 的
   默认名 `DEFAULT_BACKEND_NAME = "local"` 与 `artifacts.storage_backend` 的落库值
   一致（`docs/02` §29）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain` / 同包的 `storage.base` / `storage.local`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.application` /
`app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, Protocol, cast

from app.domain.errors import InternalError
from app.infrastructure.storage.base import ArtifactStorageBackend
from app.infrastructure.storage.local import LocalFilesystemStorage

__all__ = [
    "DEFAULT_BACKEND_NAME",
    "MANAGER_STAGE",
    "ArtifactStorageManager",
    "build_local_storage",
]

DEFAULT_BACKEND_NAME: Final[str] = "local"
"""Core Alpha 的默认后端名（`docs/02` §29；落 `artifacts.storage_backend`）。"""

MANAGER_STAGE: Final[str] = "storage_manager"
"""错误信封里的 `stage` 字面量（`docs/07` §11 / §14.3）。"""


class _ChecksumCapableBackend(ArtifactStorageBackend, Protocol):
    """能读回并计算校验值的后端（`docs/02` §3.6 / §84；见模块裁决 3）。"""

    async def checksum(self, reference: str) -> str: ...


class ArtifactStorageManager:
    """按名字路由到存储后端（`docs/02` §29 / §33）。

    ⚠️ 进程内注册表（模块裁决 1）：`register()` 在装配期调用，运行期只读。
    本类**不**持有事务、**不** `commit`（`docs/07` §14.4）。
    """

    def __init__(self, *, default_backend: str = DEFAULT_BACKEND_NAME) -> None:
        """建立空注册表并记录默认后端名。

        Args:
            default_backend: 未显式指定 `backend=` 时使用的后端名
                （`docs/02` §29 的 `local`）。
        """
        self._backends: dict[str, ArtifactStorageBackend] = {}
        self._default_backend = default_backend

    @property
    def default_backend(self) -> str:
        """默认后端名（`docs/02` §29 / §33）。"""
        return self._default_backend

    def register(self, name: str, storage: ArtifactStorageBackend) -> None:
        """注册一个后端（装配期调用；`docs/02` §29）。

        Args:
            name: 后端名（落 `artifacts.storage_backend`，`docs/07` §4.3 #21）。
            storage: 后端实现（`docs/02` §3.3 的 `ArtifactStorage` + `exists`）。

        Raises:
            InternalError: `STRUCTAI-7000` —— 名字为空（`reason="invalid_backend"`）
                或重复注册（`reason="duplicate_backend"`）；见模块裁决 2。
        """
        if not name or not name.strip():
            raise InternalError(
                "artifact storage backend name must not be blank",
                details={"stage": MANAGER_STAGE, "reason": "invalid_backend"},
            )
        if name in self._backends:
            raise InternalError(
                "artifact storage backend is already registered",
                details={"stage": MANAGER_STAGE, "reason": "duplicate_backend"},
            )
        self._backends[name] = storage

    def backend(self, name: str | None = None) -> ArtifactStorageBackend:
        """取出后端（`docs/02` §29 / §33）。

        Args:
            name: 后端名；`None` → `default_backend`。

        Returns:
            已注册的后端实现。

        Raises:
            InternalError: `STRUCTAI-7000`，`reason="unknown_backend"`（见模块裁决 2）。
        """
        resolved = self._default_backend if name is None else name
        storage = self._backends.get(resolved)
        if storage is None:
            raise InternalError(
                "artifact storage backend is not registered",
                details={"stage": MANAGER_STAGE, "reason": "unknown_backend"},
            )
        return storage

    def backend_names(self) -> tuple[str, ...]:
        """已注册的后端名（排序；只读诊断，`docs/02` §33）。"""
        return tuple(sorted(self._backends))

    # ===== 直通（`docs/02` §3.3 / §29 / §33）=====

    async def put(
        self,
        data: bytes,
        metadata: Mapping[str, Any],
        *,
        backend: str | None = None,
    ) -> str:
        """写入产物并返回存储键（`docs/02` §3.5 / §29）。"""
        return await self.backend(backend).put(data, metadata)

    async def get(self, reference: str, *, backend: str | None = None) -> bytes:
        """读回产物（`docs/02` §11 / §29 / §33）。"""
        return await self.backend(backend).get(reference)

    async def delete(self, reference: str, *, backend: str | None = None) -> None:
        """删除产物（幂等；`docs/02` §30 / §33）。"""
        await self.backend(backend).delete(reference)

    async def exists(self, reference: str, *, backend: str | None = None) -> bool:
        """产物是否存在（`docs/02` §3.3 / §49）。"""
        return await self.backend(backend).exists(reference)

    async def checksum(self, reference: str, *, backend: str | None = None) -> str:
        """读回并计算校验值（`docs/02` §3.6 / §84；见模块裁决 3）。"""
        storage = cast("_ChecksumCapableBackend", self.backend(backend))
        return await storage.checksum(reference)


def build_local_storage(
    root: str | Path,
    *,
    default_backend: str = DEFAULT_BACKEND_NAME,
) -> ArtifactStorageManager:
    """装配一个只含本地后端的 Manager（`docs/02` §29 / §38）。

    Args:
        root: 存储根目录（`Settings.artifact_root`，`docs/02` §38）。
        default_backend: 后端名 / 默认名（Core Alpha = `local`）。

    Returns:
        已注册本地后端的 `ArtifactStorageManager`。

    ⚠️ 本函数**不**建目录、**不**做 I/O（目录在首次写入时创建，见
    `LocalFilesystemStorage` 的裁决 3）。
    """
    manager = ArtifactStorageManager(default_backend=default_backend)
    manager.register(default_backend, LocalFilesystemStorage(root))
    return manager
