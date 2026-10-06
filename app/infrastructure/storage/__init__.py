"""Infrastructure · Storage 包导出（`docs/07` §3.3；`docs/02` §3.3 / §3.4 / §29 / §33）。

`docs/07` §3.3 冻结的结构：

    app/infrastructure/storage/  base.py · local.py · manager.py

本包是 P29（Artifact Storage）的唯一入口：

| 文件 | 内容 | 规范 |
| --- | --- | --- |
| `base.py` | 存储键形状 / SHA-256 / 文件名清洗 / 遍历守卫 / 后端契约 | `docs/02` §3.3–§3.6 |
| `local.py` | `LocalFilesystemStorage`（Core Alpha 实现） | `docs/02` §3.4 / §29 / §56 |
| `manager.py` | `ArtifactStorageManager` + `build_local_storage` | `docs/02` §29 / §33 |

红线（`docs/07` §14.1 / §14.4）：本包只依赖标准库与 `app.domain`，**不**反向依赖
`app.application` / `app.interfaces`；存储后端**不**持有事务、**不** `commit`；
产物**内容不落数据库**（`docs/02` §29 / §33），用户文件名**绝不**成为路径
（`docs/02` §3.4）。
"""

from __future__ import annotations

from app.infrastructure.storage.base import (
    CHECKSUM_LENGTH,
    DEFAULT_CHUNK_SIZE,
    MISSING_PROJECT_SEGMENT,
    PAYLOAD_FILENAME,
    SHA256_ALGORITHM,
    STORAGE_STAGE,
    ArtifactStorageBackend,
    artifact_of_storage_key,
    relative_storage_path,
    sanitize_filename,
    sha256_bytes,
    sha256_stream,
    storage_key_for,
    storage_key_segments,
    tenant_of_storage_key,
)
from app.infrastructure.storage.local import BACKEND_NAME, LocalFilesystemStorage
from app.infrastructure.storage.manager import (
    DEFAULT_BACKEND_NAME,
    MANAGER_STAGE,
    ArtifactStorageManager,
    build_local_storage,
)

__all__ = [
    "BACKEND_NAME",
    "CHECKSUM_LENGTH",
    "DEFAULT_BACKEND_NAME",
    "DEFAULT_CHUNK_SIZE",
    "MANAGER_STAGE",
    "MISSING_PROJECT_SEGMENT",
    "PAYLOAD_FILENAME",
    "SHA256_ALGORITHM",
    "STORAGE_STAGE",
    "ArtifactStorageBackend",
    "ArtifactStorageManager",
    "LocalFilesystemStorage",
    "artifact_of_storage_key",
    "build_local_storage",
    "relative_storage_path",
    "sanitize_filename",
    "sha256_bytes",
    "sha256_stream",
    "storage_key_for",
    "storage_key_segments",
    "tenant_of_storage_key",
]
