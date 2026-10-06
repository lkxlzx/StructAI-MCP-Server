"""Infrastructure · Storage · Base（`docs/02` §3.3 / §3.4 / §3.5 / §3.6；§29 / §33 / §55 / §56）。

权威来源
--------
- `docs/02` §3.3（Storage Protocol）—— 流式形状：`put(storage_key, stream)` /
  `get(storage_key) -> BinaryIO` / `delete(storage_key)` / `exists(storage_key)`。
- `docs/02` §3.4（LocalFilesystemStorage）—— 目录
  `./data/artifacts/<tenant_id>/<project_id>/<artifact_id>/payload`，并明确
  「**禁止**直接使用用户提供的文件名作为最终路径」。
- `docs/02` §3.5（Storage Key）—— `{tenant_id}/{project_id}/{artifact_id}/payload`。
- `docs/02` §3.6（Checksum）—— 上传时计算 SHA-256，`sha256_stream` 的**分块**实现
  （逐字照抄），完整性验证为 `checksum(original) == checksum(read)`。
- `docs/02` §29（Artifact Storage）—— 数据库只保存 metadata，字节流落存储后端；
  第一阶段实现 `LocalFilesystemStorage`。
- `docs/02` §33（Artifact Service）—— 存储键由服务端生成，不由调用方提供路径。
- `docs/02` §55（Core Alpha Implementation Order）第 24 项 = Artifact Storage。
- `docs/02` §56（Definition of Done）—— `[ ] Artifact Storage`；安全验收含
  `artifact path traversal protection` / `artifact filename sanitization`。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **存储键的形状是冻结契约，本模块是它的唯一权威实现点**：`docs/02` §3.5 的
   `{tenant_id}/{project_id}/{artifact_id}/payload`。`project_id` 缺失时（手工上传 /
   导出，`docs/02` §29）用 `MISSING_PROJECT_SEGMENT = "-"` 占位，**不**留空段 ——
   空段会让「同一租户下的不同项目」在路径上不可区分，且与 §3.4 的目录形状冲突。
   ⚠️ `app/application/**` **不得**依赖 `app.infrastructure`（`docs/07` §14.1），
   故 `ArtifactService` 只能**照抄**同一形状（见该模块裁决 1）；本模块是形状的
   唯一定义点，跨模块一致性由验收测试断言。
2. **`sanitize_filename()` 只是「用户文件名 → 安全标签」的清洗器，不是路径来源**：
   `docs/02` §3.4 的禁止项针对的是「把用户文件名当最终路径」。本函数剥掉目录成分、
   把 `[A-Za-z0-9._-]` 之外的字符替换为 `_`、剥掉前导点、截断到 128 字符、空串回落
   `"artifact"`（`docs/02` §56 的 `artifact filename sanitization`）。产物路径**始终**
   由 `storage_key_for()` 决定，用户文件名最多只作为 `mime_type` / 元数据出现
   （`artifacts` 表**没有** name 列，`docs/07` §4.3 #21）。
3. **`relative_storage_path()` 是唯一的遍历守卫**：绝对键、`..` 段、空段、反斜杠
   一律拒绝（`ArtifactError` `STRUCTAI-6200`，`reason="invalid_storage_key"`）。
   拒绝比「规范化后继续」安全 —— 规范化会把 `/etc/passwd` 悄悄变成 `etc/passwd`，
   让攻击者拿到一个「看起来正常」的键（`docs/02` §56 的 path traversal protection）。
   真实路径是否仍在 `root` 之内由后端在 `path_for()` 里用 `Path.resolve()` 再确认一次
   （符号链接逃逸），失败落 `reason="path_traversal"`。
4. **`ArtifactStorageBackend` 在 Domain 契约上**追加** `exists()`，不改 Domain**：
   `docs/02` §49 的 Artifact Test Matrix 要求 `exists` 可验收，而 P03 冻结的
   `app.domain.protocols.ArtifactStorage`（`docs/02` §11 / §29 / §33）只有
   `put` / `get` / `delete`。本模块因此声明子协议，Domain 契约**一字未动**。
5. **`sha256_bytes()` 与 `sha256_stream()` 共用同一个算法常量**
   （`SHA256_ALGORITHM = "sha256"`、`CHECKSUM_LENGTH = 64`）：内存路径（
   `ArtifactService.create` 已有 `bytes`）与流式路径（`docs/02` §3.6）必须给出**同一**
   校验值，否则「写后读回校验」会自相矛盾。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（`ArtifactStorage` 契约、`ArtifactError`）：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.application` /
`app.interfaces`，也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath
from typing import BinaryIO, Final, Protocol

from app.domain.errors import ArtifactError
from app.domain.protocols import ArtifactStorage

__all__ = [
    "CHECKSUM_LENGTH",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_FILENAME",
    "FILENAME_MAX_LENGTH",
    "MISSING_PROJECT_SEGMENT",
    "PAYLOAD_FILENAME",
    "SHA256_ALGORITHM",
    "STORAGE_STAGE",
    "ArtifactStorageBackend",
    "artifact_of_storage_key",
    "relative_storage_path",
    "sanitize_filename",
    "sha256_bytes",
    "sha256_stream",
    "storage_key_for",
    "storage_key_segments",
    "tenant_of_storage_key",
]

STORAGE_STAGE: Final[str] = "storage"
"""错误信封里的 `stage` 字面量（`docs/07` §11 / §14.3：`details` 只放 `stage` / `reason`）。"""

SHA256_ALGORITHM: Final[str] = "sha256"
"""校验算法（`docs/02` §3.6；`docs/07` §4.3 #21 的 `checksum` 列）。"""

CHECKSUM_LENGTH: Final[int] = 64
"""SHA-256 十六进制摘要长度（`docs/02` §3.6 的 `hexdigest()`）。"""

DEFAULT_CHUNK_SIZE: Final[int] = 1024 * 1024
"""分块读写大小（`docs/02` §3.6 的 `stream.read(1024 * 1024)`，逐字照抄）。"""

PAYLOAD_FILENAME: Final[str] = "payload"
"""产物字节流的文件名（`docs/02` §3.4 / §3.5；**不是**用户文件名）。"""

MISSING_PROJECT_SEGMENT: Final[str] = "-"
"""`project_id` 缺失时的路径段占位（见模块裁决 1）。"""

FILENAME_MAX_LENGTH: Final[int] = 128
"""清洗后的文件名上限（`docs/02` §56 的 filename sanitization）。"""

DEFAULT_FILENAME: Final[str] = "artifact"
"""清洗后为空时的回落标签（`docs/02` §56）。"""

_UNSAFE_FILENAME_CHARS: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9._-]")


def sha256_stream(stream: BinaryIO) -> str:
    """分块读取并返回 SHA-256 十六进制摘要（`docs/02` §3.6，逐字照抄）。

    Args:
        stream: 二进制流（`docs/02` §3.3 的 `get()` 产物）。

    Returns:
        64 位十六进制字符串（`CHECKSUM_LENGTH`）。

    ⚠️ 分块读取是**必须**的（`docs/07` §14.4：禁止无限 payload）：一次性
    `stream.read()` 会把整个产物读进内存。
    """
    digest = hashlib.sha256()
    while True:
        chunk = stream.read(DEFAULT_CHUNK_SIZE)
        if not chunk:
            break
        digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    """返回内存中字节的 SHA-256 十六进制摘要（`docs/02` §3.6）。

    与 `sha256_stream()` 使用**同一**算法与**同一**长度口径（见模块裁决 5）。
    """
    return hashlib.sha256(data).hexdigest()


def storage_key_for(*, tenant_id: str, project_id: str | None, artifact_id: str) -> str:
    """构造存储键（`docs/02` §3.5，逐字照抄形状）。

    Args:
        tenant_id: 租户标识（`artifacts` 表**没有** `tenant_id` 列，`docs/07` §4.3 #21）。
        project_id: 项目标识；`None` → `MISSING_PROJECT_SEGMENT`（见模块裁决 1）。
        artifact_id: 产物标识（服务端生成的 UUID 字符串）。

    Returns:
        `"{tenant_id}/{project_id}/{artifact_id}/payload"`。
    """
    return f"{tenant_id}/{project_id or MISSING_PROJECT_SEGMENT}/{artifact_id}/{PAYLOAD_FILENAME}"


def sanitize_filename(name: str) -> str:
    """把用户提供的文件名清洗为**安全标签**（`docs/02` §3.4 / §56）。

    规则（逐条照抄任务卡）：

    1. 剥掉目录成分（`/` 与 `\\` 都算分隔符）；
    2. `[A-Za-z0-9._-]` 之外的字符替换为 `_`；
    3. 剥掉前导点（`..` / `.bashrc` → 空 / `bashrc`）；
    4. 截断到 `FILENAME_MAX_LENGTH`；
    5. 空串回落 `DEFAULT_FILENAME`。

    ⚠️ 返回值**不得**被当作产物路径：路径只由 `storage_key_for()` 决定（模块裁决 2）。
    """
    candidate = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    candidate = _UNSAFE_FILENAME_CHARS.sub("_", candidate)
    candidate = candidate.lstrip(".")
    candidate = candidate[:FILENAME_MAX_LENGTH]
    return candidate or DEFAULT_FILENAME


def storage_key_segments(key: str) -> tuple[str, ...]:
    """把存储键切成非空段（`docs/02` §3.5）。

    空段被丢弃（`PurePosixPath` 口径），便于按段解析租户 / 产物。
    """
    return tuple(part for part in str(key).split("/") if part)


def tenant_of_storage_key(key: str) -> str | None:
    """取存储键的**第一段**作为租户标识（`docs/02` §3.5）。

    `artifacts` 表没有 `tenant_id` 列（`docs/07` §4.3 #21），租户归属**只**由
    `storage_key` 的路径口径承载；键不可解析（无段）→ `None`。
    """
    segments = storage_key_segments(key)
    return segments[0] if segments else None


def artifact_of_storage_key(key: str) -> str | None:
    """取 `payload` 之前的那一段作为产物标识（`docs/02` §3.5）。

    形状不符（不足两段，或末段不是 `PAYLOAD_FILENAME`）→ `None`。
    """
    segments = storage_key_segments(key)
    if len(segments) < 2 or segments[-1] != PAYLOAD_FILENAME:
        return None
    return segments[-2]


def relative_storage_path(key: str) -> PurePosixPath:
    """把存储键转成**相对**的 POSIX 路径，并做遍历守卫（`docs/02` §3.4 / §56）。

    Args:
        key: 存储键（`docs/02` §3.5 的形状）。

    Returns:
        不含空段的相对路径。

    Raises:
        ArtifactError: `STRUCTAI-6200`，`details={"stage": "storage",
            "reason": "invalid_storage_key"}` —— 空键 / 绝对键 / `..` 段 /
            空段 / 反斜杠（见模块裁决 3）。
    """
    text = key if isinstance(key, str) else str(key)
    if not text or "\\" in text or text.startswith("/"):
        raise _invalid_storage_key(text)
    segments = text.split("/")
    if any(segment in {"", ".."} for segment in segments):
        raise _invalid_storage_key(text)
    return PurePosixPath(*segments)


class ArtifactStorageBackend(ArtifactStorage, Protocol):
    """`ArtifactStorage` 的后端扩展契约（`docs/02` §3.3 / §29 / §33）。

    在 P03 冻结的 Domain 契约（`put` / `get` / `delete`）之上**追加**
    `exists()`（`docs/02` §3.3 与 §49 的 Artifact Test Matrix 都要求它），
    Domain 契约**一字未改**（见模块裁决 4）。
    """

    async def exists(self, reference: str) -> bool: ...


def _invalid_storage_key(key: str) -> ArtifactError:
    """构造非法的存储键错误（`STRUCTAI-6200`，`docs/07` §11 / §14.3）。"""
    return ArtifactError(
        "artifact storage key is invalid",
        details={"stage": STORAGE_STAGE, "reason": "invalid_storage_key"},
    )
