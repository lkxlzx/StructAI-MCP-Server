"""Application · Services · Backup / Restore / Retention（P29–P35）。

权威文档：`docs/07` §12 P29–P35；`docs/02` §18–§31 / §46 / §66 / §81。

权威来源
--------
- `docs/02` §18（`exec`）—— Core Alpha 使用 SQLite 原生 backup 能力；备份对象是
  `SQLite DB` / `Artifact metadata` / `Registry` / `Configuration`，**Artifact payload
  另行复制**。
- `docs/02` §19（`exec`）—— Backup Manifest 的**六个**键：
  `backup_id` / `created_at` / `database` / `artifacts` / `version` / `schema_revision`。
- `docs/02` §20（`exec`）—— 备份目录：`backup/<UTC 时间戳>/` 下含
  `manifest.json` / `structai.db` / `artifacts/`。
- `docs/02` §21（`exec`）—— **不得** `cp structai.db backup.db`（运行期可能得到
  不一致快照）；必须用 `sqlite3` 的 `source.backup(destination)`。
- `docs/02` §22（`exec`）—— 每个 Artifact：读取 → SHA-256 → 复制 → 再次 SHA-256 →
  比较；失败落 `ARTIFACT_BACKUP_FAILED`，**整个备份不能被标记为完整成功**。
- `docs/02` §23（`exec`）—— 恢复流程：`Validate Backup → Verify Manifest →
  Verify DB checksum → Verify Artifact checksum → Check Schema Version →
  Maintenance Mode → Restore Database → Restore Artifacts → Integrity Check →
  Registry Validation → Exit Maintenance Mode`。
- `docs/02` §24（`exec`）—— 恢复前**必须**创建当前状态紧急备份
  （`pre_restore_backup/`）；禁止「直接覆盖」「无校验恢复」「部分恢复后直接启动」。
- `docs/02` §25（`exec`）—— `validate` / `restore` / `integrity_check` 三个方法。
- `docs/02` §26（`exec`）—— `PRAGMA integrity_check`；Artifact 校验和比较；
  Registry 的 software / product / version / adapter / capability / API mapping
  **全部必须能够解析**。
- `docs/02` §27 / §28（`exec`）—— `RetentionPolicy` 六个字段与默认策略
  （Task 30 / Trace 14 / Event 30 / Artifact 90 / Session 7 / Audit 365 天）。
- `docs/02` §29（`exec`）—— `cleanup_tasks` / `cleanup_traces` / `cleanup_events` /
  `cleanup_artifacts` / `cleanup_sessions`；**Audit 不允许普通 retention job 直接删除**。
- `docs/02` §31（`exec`）—— Artifact GC：扫描 storage → 取 `artifact_id` → 查 DB →
  不存在 → **quarantine** → 保留期 → 删除；**禁止扫描后立即删除**。
- `docs/02` §46（`exec`）—— Core Alpha 必须提供 `backup` / `restore` / `integrity-check`。
- `docs/02` §66（`exec`）—— Health / Recovery Policy。
- `docs/02` §81（`exec`）—— 备份 / 恢复的验收口径。
- `docs/07` §11 —— 20 码错误契约；本模块只用 `ArtifactError`(6200) 与
  `InternalError`(7000)，**不**新增错误码。
- `docs/07` §14.1 / §14.2 —— Application 层不得依赖 `app.infrastructure` /
  `app.interfaces` / `app.observability`，也不得出现任何厂商专属内容。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **收窄契约，不 import 同批其它模块**：`ArtifactStore` / `TraceStore` /
   `EventRecordStore` / `RetentionPolicy` 取自 `app.domain.protocols`；
   Artifact **字节流**出口（`ArtifactStorage`）与任务 / 会话的保留源由**本模块内**的
   窄 `Protocol` 声明（`ArtifactStorageReader` / `TaskRetentionSource` /
   `SessionRetentionSource`），实现按构造注入 —— 这是 P14–P18 R38
   （`RuntimeCapabilitySource`）的同一做法：Application 只依赖**结构**，
   不依赖 `app.infrastructure`（`docs/07` §14.1）。
2. **`backup_id` = 目录名 = UTC 时间戳**：`docs/02` §20 的目录名就是时间戳，
   而 §19 的 `backup_id` 必须能唯一定位一次备份。取同一个值使「清单指向哪次备份」
   在结构上无歧义（也便于恢复时按目录名定位）。
3. **清单**最后**写**：`docs/02` §22 要求「失败则整个备份不能被标记为完整成功」。
   把 `manifest.json` 放在全部校验和比对**之后**写入，使「清单存在」⇔
   「载荷集合已被验证」成为**结构性**事实，而不是靠调用方记得清理。
4. **`backup_database` 用 SQLite backup API，且连接无条件关闭**：`docs/02` §21
   明令禁止 `cp`。`sqlite3.connect` 打开的源 / 目标连接**必须**在 `finally` 里关闭，
   否则 Windows 上会因文件句柄未释放而无法删除临时目录（验收测试会暴露这一点）。
5. **Artifact 读取失败一律 6200**：`docs/02` §22 的失败口径是 `ARTIFACT_BACKUP_FAILED`。
   载荷缺失 / 校验和不符 / 未注入 storage 三种情形**必须**给出**同一个**可判定的
   信号（否则「备份不完整」会被误判为「备份为空」）。**不**区分「没有产物」与
   「取不到产物」：后者是故障，前者是 `count = 0` 的**成功**备份。
6. **`verify_backup` 不抛异常**（`docs/02` §25）：损坏的备份是**数据**，不是异常 ——
   由调用方决定如何处理。只有**恢复**阶段（`RestoreService.validate`）才把
   不合法升级为错误（schema 版本不符 → 7000 `schema_mismatch`）。
7. **schema 版本检查在 `validate` 里，不在 `verify_backup` 里**：`docs/02` §23 把
   `Check Schema Version` 列在 `Verify Artifact checksum` **之后**，且它是
   **恢复**的前置条件（备份本身没有「错」，只是不能恢复到当前版本）。
8. **`restore` 的失败是报告，不是异常**：`docs/02` §24 要求「部分恢复后直接启动」
   被禁止 —— 故任何一步失败都返回 `restored=False` 并列出 `failures`，
   调用方**必须**据此停在维护模式。数据库文件用 `shutil.copy2` 覆盖**仅**在
   `validate` 通过且紧急备份**已生成**之后发生。
9. **紧急备份落在 `<restore_root>/pre_restore_backup`**：`docs/02` §24 的示例目录是
   `restore/{pre_restore_backup,target_backup}`，其中 `restore_root` 取
   **当前数据库所在目录**（`docs/02` §20 的 `backup/` 与 `restore/` 是同级运行目录）。
   它由 `BackupService.create_backup` 生成，故与正常备份同一套校验口径。
10. **没有 `cleanup_audit`**（`docs/02` §29 / §45）：审计记录的删除需要
    「Audit Retention Policy + Administrator Authorization + Audit of Deletion」，
    本模块**刻意不提供**该方法。`RetentionPolicy.audit_days` 因此是**已登记但未使用**
    的字段（见模块裁决 11）。
11. **未装配的保留源不是「成功」**：`cleanup_*` 在对应源未注入时返回 `0`，
    但**必须**能用 `configured()` 区分「清理了 0 行」与「根本没接这个源」——
    静默把未装配当成成功是 `docs/07` §14.4 口径下最危险的一类假成功。
12. **Artifact 保留只删元数据行，载荷走 §31 的 quarantine**：本模块的 storage 契约
    只有 `get` / `put` / `exists`（**没有** `delete`，与 `docs/02` §30 的
    `Mark DELETE_PENDING → Delete Storage → Verify → Delete DB` 一致：删除载荷是
    GC 的显式步骤）。故 `cleanup_artifacts` 只删 `artifacts` 行，孤立的载荷由
    `collect_garbage()` **隔离**而非删除（`docs/02` §31「禁止扫描后立即删除」）。
13. **`collect_garbage` 只隔离，不删除**：`docs/02` §31 的流程在 quarantine 之后还有
    「retention period → delete」，那是**更晚的、显式的**步骤；本方法返回被隔离的
    数量，并**不**触碰 `quarantine/` 里已有的文件（重复运行是幂等的）。
14. **`integrity_check` 报告 registry 结果而不裁决**（`docs/02` §26）：注入的
    `registry_validator` 返回 `bool`；未注入时为 `None` —— 「未校验」与「校验失败」
    必须可区分（同裁决 11）。
15. **安全（`docs/02` §47 / `docs/07` §14.3）**：清单与任何日志**只**含计数、校验和、
    大小与标识，**绝不**含凭据 / token / 载荷内容。`details` 同理。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`：**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.infrastructure` / `app.interfaces` / `app.observability`，
也**不**出现任何厂商专属内容。`sqlite3` 与 `hashlib` / `json` / `shutil` 属标准库，
用于 `docs/02` §21 / §26 明示的 SQLite 备份与 `PRAGMA integrity_check`。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final, Protocol

from app.domain.errors import ArtifactError, InternalError
from app.domain.protocols import (
    ArtifactRecord,
    ArtifactStore,
    EventRecordStore,
    RetentionPolicy,
    TraceStore,
)

__all__ = [
    "ARTIFACT_BACKUP_DIR",
    "ARTIFACT_CHECKSUMS_KEY",
    "BACKUP_ARTIFACTS_DIR",
    "BACKUP_DATABASE_NAME",
    "BACKUP_MANIFEST_NAME",
    "BACKUP_STAGE",
    "BACKUP_VERSION",
    "DATABASE_SUFFIX",
    "DEFAULT_RETENTION_POLICY",
    "QUARANTINE_DIR",
    "RESTORE_PRE_BACKUP_DIR",
    "RESTORE_STAGE",
    "ArtifactStorageReader",
    "BackupManifest",
    "BackupService",
    "BackupVerification",
    "RestoreReport",
    "RestoreService",
    "RetentionReport",
    "RetentionService",
    "SessionRetentionSource",
    "TaskRetentionSource",
    "backup_database",
]

BACKUP_STAGE: Final[str] = "backup"
"""备份阶段错误 `details["stage"]` 的固定取值（`docs/07` §11）。"""

ARTIFACT_CHECKSUMS_KEY: Final[str] = "checksums"
"""清单 `artifacts` 条目里的**逐条**校验和映射（产物标识 → SHA-256）。

`docs/02` §19 只给出 `count` / `bytes`；而 §23 要求 `Verify Artifact checksum`
能逐条比对，故在此**补充**一个子键 —— 它**不**改变 §19 的六个顶层键，
也**只**含标识与校验和（**不**含载荷内容，见模块裁决 15）。
"""

RESTORE_STAGE: Final[str] = "restore"
"""恢复阶段错误 `details["stage"]` 的固定取值（`docs/07` §11）。"""

BACKUP_MANIFEST_NAME: Final[str] = "manifest.json"
"""清单文件名（`docs/02` §19 / §20，逐字照抄）。"""

BACKUP_DATABASE_NAME: Final[str] = "structai.db"
"""备份目录里的数据库文件名（`docs/02` §20 的 `structai.db`）。"""

BACKUP_ARTIFACTS_DIR: Final[str] = "artifacts"
"""备份目录里的产物树（`docs/02` §20 的 `artifacts/`）。"""

BACKUP_VERSION: Final[str] = "2.0"
"""清单的 `version`（`docs/02` §19 的示例值，逐字照抄）。"""

RESTORE_PRE_BACKUP_DIR: Final[str] = "pre_restore_backup"
"""恢复前紧急备份的目录名（`docs/02` §24，逐字照抄）。"""

QUARANTINE_DIR: Final[str] = "quarantine"
"""Artifact GC 的隔离目录（`docs/02` §31，逐字照抄）。"""

DATABASE_SUFFIX: Final[str] = ".db"
"""数据库文件后缀（`docs/02` §20 的 `structai.db`）。"""

ARTIFACT_BACKUP_DIR: Final[str] = "payload"
"""单个产物在备份 / 存储里的载荷文件名（`docs/02` §3.5 / §20）。

`docs/02` §3.5 的存储口径是 `{tenant_id}/{project_id}/{artifact_id}/payload`，
`docs/02` §31 的 GC 扫描据此取 `artifact_id`。
"""

DEFAULT_RETENTION_POLICY: Final[RetentionPolicy] = RetentionPolicy()
"""`docs/02` §28 的**默认**保留策略（由 `RetentionPolicy` 的字段默认值承载）。"""

_SHA256_CHUNK: Final[int] = 1024 * 1024
"""读文件计算 SHA-256 的分块大小（`docs/07` §14.4：禁止一次性读入无限 payload）。"""

_PAGE_SIZE: Final[int] = 100
"""有界分页大小（`docs/07` §14.4：`ArtifactStore.list_all` 必须分页遍历）。"""

Clock = Callable[[], datetime]
"""可注入时钟（验收测试据此制造保留期边界与稳定的备份目录名）。"""


def _utc_now() -> datetime:
    """默认时钟：带时区的 UTC 当前时间。"""
    return datetime.now(UTC)


def _isoformat(moment: datetime) -> str:
    """`docs/02` §19 的 `created_at`：ISO-8601（UTC 用 `Z` 后缀，如规范示例）。"""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    """文件的 SHA-256（`docs/02` §19 / §22 的 `checksum`）。"""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_SHA256_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    """字节串的 SHA-256（`docs/02` §22 的「读取 → SHA-256」）。"""
    return hashlib.sha256(payload).hexdigest()


def _directory_name(moment: datetime) -> str:
    """备份目录名（`docs/02` §20 的 `20261005T010000` 形状，UTC）。"""
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _storage_root_of(
    storage: ArtifactStorageReader | str | Path | None,
) -> Path | None:
    """把注入的产物存储出口归一为**扫描根目录**（`docs/02` §31）。

    Args:
        storage: `ArtifactStorageReader`（其 `root` 属性即存储根）、或直接的
            根路径、或 `None`。

    Returns:
        存储根路径；无法判定时为 `None`（此时 `collect_garbage` 是**无操作**，
        而不是「扫描了 0 个孤儿」—— 见模块裁决 11 的同源原则）。
    """
    if storage is None:
        return None
    if isinstance(storage, str | Path):
        return Path(storage)
    root = getattr(storage, "root", None)
    return Path(root) if isinstance(root, str | Path) else None


def backup_database(source_path: str | Path, destination_path: str | Path) -> None:
    """用 SQLite backup API 复制数据库（`docs/02` §21，逐字照抄该实现）。

    🔴 **不得**用普通文件复制（`shutil.copy` / `cp`）代替：数据库**运行期间**
    的字节拷贝可能得到**不一致快照**（`docs/02` §21 明令禁止 `cp structai.db backup.db`）。
    `sqlite3` 的 `Connection.backup` 在页级加锁下复制，得到可用的快照。

    Args:
        source_path: 源数据库文件。
        destination_path: 目标数据库文件（父目录必须已存在）。

    Raises:
        sqlite3.Error: 源 / 目标不可打开或备份失败（由调用方归类为 6200 / 7000）。
    """
    source = sqlite3.connect(str(source_path))
    destination = sqlite3.connect(str(destination_path))
    try:
        source.backup(destination)
    finally:
        # 见模块裁决 4：连接**无条件**关闭，否则句柄泄漏会卡住后续的文件删除。
        destination.close()
        source.close()


class ArtifactStorageReader(Protocol):
    """产物**字节流**的收窄契约（`docs/02` §29 / §33 的 `ArtifactStorage` 窄形态）。

    实现由 P29–P32 的 `ArtifactStorage`（`app/infrastructure/storage/**`，另一
    模块）**结构上**满足：`get` / `put` / `exists` 三个方法。
    Application 层**不** import 它的模块（见模块裁决 1）。
    """

    async def get(self, reference: str) -> bytes:
        """按存储键读取载荷字节（`docs/02` §29）。"""
        ...

    async def put(self, data: bytes, metadata: Mapping[str, Any]) -> str:
        """写入载荷并返回存储键（`docs/02` §29；恢复阶段使用）。"""
        ...

    async def exists(self, reference: str) -> bool:
        """该存储键是否存在（`docs/02` §29 / §31）。"""
        ...


class TaskRetentionSource(Protocol):
    """任务保留源（`docs/02` §29 的 `cleanup_tasks`；任务存储归另一模块）。

    ⚠️ 任务存储由 P22–P28 的 `TaskStore` 实现，本模块**不** import 它
    （见模块裁决 1）；只需要「删掉某个截止时间之前**已终结**的任务」这一个问题。
    """

    async def delete_finished_before(self, cutoff: datetime) -> int:
        """删除 `cutoff` 之前已终结的任务，返回删除行数。"""
        ...


class SessionRetentionSource(Protocol):
    """会话保留源（`docs/02` §29 的 `cleanup_sessions`；会话存储归安全批次）。"""

    async def delete_expired_before(self, cutoff: datetime) -> int:
        """删除 `cutoff` 之前已过期的会话，返回删除行数。"""
        ...


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """一次备份的清单（`docs/02` §19 的六个键，逐字对应）。

    Attributes:
        backup_id: 备份标识（= 备份目录名 = UTC 时间戳，见模块裁决 2）。
        created_at: 创建时刻（`to_dict()` 输出 ISO-8601）。
        database: 数据库条目（`file` / `checksum` / `size`）。
        artifacts: 产物条目（`count` / `bytes`）。
        version: 备份格式版本（`BACKUP_VERSION`）。
        schema_revision: 备份时的 schema 版本；`None` 表示未记录（`docs/02` §19
            的该键在示例里是字符串，但 Alpha 允许缺省 —— 恢复时按「不检查」处理）。

    🔴 清单**只**承载计数、校验和、大小与标识（见模块裁决 15）：**绝不**含
    凭据 / token / 载荷内容。
    """

    backup_id: str
    created_at: datetime
    database: Mapping[str, Any]
    artifacts: Mapping[str, Any]
    version: str
    schema_revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """`docs/02` §19 的清单形状（六个键；`created_at` 为 ISO-8601）。"""
        return {
            "backup_id": self.backup_id,
            "created_at": _isoformat(self.created_at),
            "database": dict(self.database),
            "artifacts": dict(self.artifacts),
            "version": self.version,
            "schema_revision": self.schema_revision,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BackupManifest:
        """从清单载荷还原（`docs/02` §19）。

        Args:
            payload: 反序列化后的清单。

        Returns:
            `BackupManifest`。

        Raises:
            InternalError: `STRUCTAI-7000` `reason="invalid_manifest"`，
                载荷形状不合法（缺键 / 类型不符 / 时间戳不可解析）。
        """
        try:
            backup_id = str(payload["backup_id"])
            created_at = _parse_isoformat(str(payload["created_at"]))
            database = dict(payload["database"])
            artifacts = dict(payload["artifacts"])
            version = str(payload["version"])
            raw_revision = payload.get("schema_revision")
            schema_revision = None if raw_revision is None else str(raw_revision)
        except (KeyError, TypeError, ValueError) as error:
            raise InternalError(
                "Backup manifest is malformed",
                details={"stage": BACKUP_STAGE, "reason": "invalid_manifest"},
                cause=error,
            ) from error
        if not backup_id or not version:
            raise InternalError(
                "Backup manifest is malformed",
                details={"stage": BACKUP_STAGE, "reason": "invalid_manifest"},
            )
        return cls(
            backup_id=backup_id,
            created_at=created_at,
            database=database,
            artifacts=artifacts,
            version=version,
            schema_revision=schema_revision,
        )


def _parse_isoformat(value: str) -> datetime:
    """解析 ISO-8601（`docs/02` §19 的 `created_at`；`Z` 后缀按 UTC 处理）。"""
    normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


@dataclass(frozen=True, slots=True)
class BackupVerification:
    """一次备份校验的结果（`docs/02` §23 的校验阶段）。

    Attributes:
        valid: 数据库与**全部**产物都通过校验。
        backup_id: 清单里的备份标识；清单不可读时为 `None`。
        database_ok: 数据库校验和一致。
        artifacts_ok: 全部产物校验和一致（含「载荷存在」）。
        checked: 实际校验的产物数量。
        failures: 失败项的非敏感描述（**只**含标识 / 原因，见模块裁决 15）。
    """

    valid: bool
    backup_id: str | None
    database_ok: bool
    artifacts_ok: bool
    checked: int
    failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RestoreReport:
    """一次恢复的结果（`docs/02` §24 / §25）。

    Attributes:
        restored: 是否**完整**恢复；`False` 表示任何一步失败（见模块裁决 8）。
        backup_id: 被恢复的备份标识；校验阶段即失败时为 `None`。
        pre_restore_backup: 紧急备份的目录路径；未生成时为 `None`。
        database_restored: 数据库文件是否已覆盖。
        artifacts_restored: 已还原的产物数量。
        integrity_ok: 恢复后的 `PRAGMA integrity_check` 是否通过。
        registry_ok: 注入的 `registry_validator` 的结果；未注入时为 `None`
            （见模块裁决 14）。
        failures: 失败项的非敏感描述。
    """

    restored: bool
    backup_id: str | None
    pre_restore_backup: str | None
    database_restored: bool
    artifacts_restored: int
    integrity_ok: bool
    registry_ok: bool | None = None
    failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RetentionReport:
    """一次全量保留清理的结果（`docs/02` §29）。

    Attributes:
        cleaned: 数据类别 → 删除行数（**只**含整数计数，见模块裁决 15）。
    """

    cleaned: Mapping[str, int]


class BackupService:
    """备份服务（`docs/02` §18–§22 / §25 / §46）。

    ⚠️ 本类**不**读数据库连接（那归 `ArtifactStore` 契约）也**不** import
    `app.infrastructure`（`docs/07` §14.1）；SQLite 文件级的复制走 `docs/02` §21
    明示的 backup API。
    """

    def __init__(
        self,
        *,
        database_path: str | Path,
        artifact_root: str | Path,
        artifacts: ArtifactStore | None = None,
        storage: ArtifactStorageReader | None = None,
        clock: Clock | None = None,
        schema_revision: str | None = None,
    ) -> None:
        """绑定数据库文件、产物根目录与注入的存储契约。

        Args:
            database_path: 源数据库文件（`docs/02` §20 的 `structai.db`）。
            artifact_root: 产物**字节流**的根目录（`docs/02` §3.5 的
                `{tenant_id}/{project_id}/{artifact_id}/payload`；§31 的扫描根）。
            artifacts: 产物**元数据**契约（`docs/02` §29）；`None` 时备份产物数为 0。
            storage: 产物**字节流**契约；`None` 时若有产物行则备份失败（见模块裁决 5）。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间（备份目录名据此生成）。
            schema_revision: 当前 schema 版本（写进清单，供恢复阶段比对）。
        """
        self._database_path = Path(database_path)
        self._artifact_root = Path(artifact_root)
        self._artifacts = artifacts
        self._storage = storage
        self._clock: Clock = clock if clock is not None else _utc_now
        self._schema_revision = schema_revision

    @property
    def database_path(self) -> Path:
        """源数据库文件（只读）。"""
        return self._database_path

    @property
    def artifact_root(self) -> Path:
        """产物字节流根目录（只读）。"""
        return self._artifact_root

    @property
    def schema_revision(self) -> str | None:
        """当前 schema 版本（`docs/02` §19 的 `schema_revision`；`None` 表示未记录）。"""
        return self._schema_revision

    # ===== `docs/02` §20 / §22：创建备份 =====

    async def create_backup(self, destination: str | Path) -> BackupManifest:
        """创建一次完整备份（`docs/02` §20 / §21 / §22）。

        Args:
            destination: 备份根目录（其下生成 `<UTC 时间戳>/`）。

        Returns:
            `BackupManifest`（`docs/02` §19 的六个键）。

        Raises:
            ArtifactError: `STRUCTAI-6200` `reason="artifact_backup_failed"`，
                任一产物载荷缺失 / 校验和不符 / 未注入 storage 契约
                （`docs/02` §22：整个备份**不得**被标记为完整成功）。
            InternalError: `STRUCTAI-7000`，源数据库不存在或 SQLite 备份失败。
        """
        if not self._database_path.is_file():
            raise InternalError(
                "Source database is missing",
                details={"stage": BACKUP_STAGE, "reason": "database_missing"},
            )
        moment = self._clock()
        backup_dir = Path(destination) / _directory_name(moment)
        backup_dir.mkdir(parents=True, exist_ok=True)
        # `docs/02` §21：必须用 SQLite backup API（**不**得字节拷贝）。
        database_target = backup_dir / BACKUP_DATABASE_NAME
        try:
            await asyncio.to_thread(
                backup_database,
                self._database_path,
                database_target,
            )
        except sqlite3.Error as error:
            raise InternalError(
                "SQLite backup failed",
                details={"stage": BACKUP_STAGE, "reason": "database_backup_failed"},
                cause=error,
            ) from error
        artifacts_entry = await self._copy_artifacts(backup_dir)
        manifest = BackupManifest(
            backup_id=backup_dir.name,
            created_at=moment,
            database={
                "file": BACKUP_DATABASE_NAME,
                "checksum": _sha256_file(database_target),
                "size": database_target.stat().st_size,
            },
            artifacts=artifacts_entry,
            version=BACKUP_VERSION,
            schema_revision=self._schema_revision,
        )
        # 见模块裁决 3：清单**最后**写 —— 「清单存在」⇔「载荷集合已通过校验」。
        (backup_dir / BACKUP_MANIFEST_NAME).write_text(
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return manifest

    async def verify_backup(self, backup_path: str | Path) -> BackupVerification:
        """校验一次备份（`docs/02` §22 / §23 的校验阶段）。

        Args:
            backup_path: 备份目录（含 `manifest.json`）。

        Returns:
            `BackupVerification`：**不抛异常**（见模块裁决 6）——
            损坏的备份以 `valid=False` + `failures` 表达。
        """
        backup_dir = Path(backup_path)
        manifest_path = backup_dir / BACKUP_MANIFEST_NAME
        if not manifest_path.is_file():
            return BackupVerification(
                valid=False,
                backup_id=None,
                database_ok=False,
                artifacts_ok=False,
                checked=0,
                failures=("manifest_missing",),
            )
        try:
            manifest = BackupManifest.from_dict(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, InternalError):
            return BackupVerification(
                valid=False,
                backup_id=None,
                database_ok=False,
                artifacts_ok=False,
                checked=0,
                failures=("manifest_unreadable",),
            )
        failures: list[str] = []
        database_ok = self._verify_database(backup_dir, manifest, failures)
        checked, artifacts_ok = self._verify_artifacts(backup_dir, manifest, failures)
        return BackupVerification(
            valid=database_ok and artifacts_ok,
            backup_id=manifest.backup_id,
            database_ok=database_ok,
            artifacts_ok=artifacts_ok,
            checked=checked,
            failures=tuple(failures),
        )

    # ===== 内部：产物 =====

    async def _copy_artifacts(self, backup_dir: Path) -> dict[str, Any]:
        """按 `docs/02` §22 复制全部产物载荷并逐一比对校验和。

        Args:
            backup_dir: 备份目录（其下生成 `artifacts/`）。

        Returns:
            `docs/02` §19 的 `artifacts` 条目（`count` / `bytes`）。

        Raises:
            ArtifactError: `STRUCTAI-6200` `reason="artifact_backup_failed"`
                （见模块裁决 5：载荷缺失 / 校验和不符 / 未注入 storage 同一信号）。
        """
        count = 0
        total_bytes = 0
        checksums: dict[str, str] = {}
        if self._artifacts is not None:
            offset = 0
            while True:
                # 见模块裁决 1：`list_all` 必须**有界分页**（`docs/07` §14.4）。
                page = await self._artifacts.list_all(limit=_PAGE_SIZE, offset=offset)
                if not page:
                    break
                for record in page:
                    payload = await self._read_payload(record)
                    checksums[record.id] = await self._write_payload(backup_dir, record, payload)
                    total_bytes += len(payload)
                    count += 1
                offset += len(page)
        artifacts_dir = backup_dir / BACKUP_ARTIFACTS_DIR
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        return {
            "count": count,
            "bytes": total_bytes,
            ARTIFACT_CHECKSUMS_KEY: checksums,
        }

    async def _read_payload(self, record: ArtifactRecord) -> bytes:
        """读取一条产物的载荷（`docs/02` §22 的第一步）。

        Raises:
            ArtifactError: `STRUCTAI-6200` `reason="artifact_backup_failed"`。
        """
        if self._storage is None:
            raise ArtifactError(
                "Artifact payload storage is not wired",
                details={"stage": BACKUP_STAGE, "reason": "artifact_backup_failed"},
            )
        try:
            payload = await self._storage.get(record.storage_key)
        except Exception as error:
            raise ArtifactError(
                "Artifact payload is unreadable",
                details={"stage": BACKUP_STAGE, "reason": "artifact_backup_failed"},
                cause=error,
            ) from error
        if payload is None:
            raise ArtifactError(
                "Artifact payload is missing",
                details={"stage": BACKUP_STAGE, "reason": "artifact_backup_failed"},
            )
        return payload

    async def _write_payload(
        self,
        backup_dir: Path,
        record: ArtifactRecord,
        payload: bytes,
    ) -> str:
        """复制载荷并**再次**比对校验和（`docs/02` §22 的后三步）。

        Returns:
            写入后的载荷 SHA-256（写进清单的 `checksums` 子键，供 §23 逐条比对）。

        Raises:
            ArtifactError: `STRUCTAI-6200` `reason="artifact_backup_failed"`。
        """
        before = _sha256_bytes(payload)
        target_dir = backup_dir / BACKUP_ARTIFACTS_DIR / record.id
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / ARTIFACT_BACKUP_DIR
        await asyncio.to_thread(target.write_bytes, payload)
        after = await asyncio.to_thread(_sha256_file, target)
        if before != after:
            raise ArtifactError(
                "Artifact checksum mismatch after copy",
                details={"stage": BACKUP_STAGE, "reason": "artifact_backup_failed"},
            )
        return after

    def _verify_database(
        self,
        backup_dir: Path,
        manifest: BackupManifest,
        failures: list[str],
    ) -> bool:
        """比对数据库文件的校验和（`docs/02` §23 的 `Verify DB checksum`）。"""
        recorded = manifest.database.get("checksum")
        target = backup_dir / BACKUP_DATABASE_NAME
        if not target.is_file():
            failures.append("database_missing")
            return False
        if not isinstance(recorded, str) or _sha256_file(target) != recorded:
            failures.append("database_checksum_mismatch")
            return False
        return True

    def _verify_artifacts(
        self,
        backup_dir: Path,
        manifest: BackupManifest,
        failures: list[str],
    ) -> tuple[int, bool]:
        """逐条比对产物载荷的校验和（`docs/02` §23 的 `Verify Artifact checksum`）。

        Returns:
            `(已校验数量, 是否全部通过)`。
        """
        root = backup_dir / BACKUP_ARTIFACTS_DIR
        recorded = manifest.artifacts.get(ARTIFACT_CHECKSUMS_KEY)
        expected_checksums: Mapping[str, Any] = recorded if isinstance(recorded, Mapping) else {}
        checked = 0
        ok = True
        for payload in sorted(root.glob(f"*/{ARTIFACT_BACKUP_DIR}")):
            checked += 1
            artifact_id = payload.parent.name
            if not payload.is_file():
                failures.append(f"artifact_missing:{artifact_id}")
                ok = False
                continue
            expected = expected_checksums.get(artifact_id)
            if not isinstance(expected, str) or _sha256_file(payload) != expected:
                failures.append(f"artifact_checksum_mismatch:{artifact_id}")
                ok = False
        expected_count = manifest.artifacts.get("count")
        if isinstance(expected_count, int) and expected_count != checked:
            failures.append("artifact_count_mismatch")
            ok = False
        return checked, ok

    async def artifact_checksums(self) -> tuple[str, ...]:
        """当前全部产物载荷的校验和（`docs/02` §26 的 Artifact 完整性检查）。

        Returns:
            按产物标识排序的 `sha256:...` 字符串元组；未注入 storage 时为空元组。
        """
        if self._artifacts is None or self._storage is None:
            return ()
        checksums: list[str] = []
        offset = 0
        while True:
            page = await self._artifacts.list_all(limit=_PAGE_SIZE, offset=offset)
            if not page:
                break
            for record in page:
                payload = await self._storage.get(record.storage_key)
                checksums.append(f"{record.id}:{_sha256_bytes(payload)}")
            offset += len(page)
        return tuple(sorted(checksums))


class RestoreService:
    """恢复服务（`docs/02` §23–§26 / §46）。

    🔴 `docs/02` §24 的三条禁止项由本类的**结构**保证：

    - 「直接覆盖」—— 覆盖数据库**只**发生在 `validate` 通过且紧急备份已生成之后；
    - 「无校验恢复」—— `restore` 的第一步就是 `validate`；
    - 「部分恢复后直接启动」—— 任何一步失败都返回 `restored=False` 并列出
      `failures`（见模块裁决 8）。
    """

    def __init__(
        self,
        *,
        backup: BackupService,
        database_path: str | Path,
        artifact_root: str | Path,
        storage: ArtifactStorageReader | None = None,
        registry_validator: Callable[[], Awaitable[bool]] | None = None,
        clock: Clock | None = None,
    ) -> None:
        """绑定备份服务、目标路径与校验钩子。

        Args:
            backup: 生成紧急备份 / 校验备份的 `BackupService`。
            database_path: **目标**数据库文件（恢复会覆盖它）。
            artifact_root: 产物字节流根目录（`docs/02` §26 的 Artifact 检查用）。
            storage: 产物字节流契约；`None` 时产物恢复记入 `failures`。
            registry_validator: Registry 校验钩子（`docs/02` §26 的
                software / product / version / adapter / capability / API mapping
                全部可解析）；`None` 时报告 `registry_ok=None`（见模块裁决 14）。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间。
        """
        self._backup = backup
        self._database_path = Path(database_path)
        self._artifact_root = Path(artifact_root)
        self._storage = storage
        self._registry_validator = registry_validator
        self._clock: Clock = clock if clock is not None else _utc_now

    @property
    def restore_root(self) -> Path:
        """恢复运行目录（`docs/02` §24 的 `restore/`；紧急备份落在其下）。"""
        return self._database_path.parent

    # ===== `docs/02` §23 / §25：校验阶段 =====

    async def validate(self, backup_path: str | Path) -> BackupVerification:
        """校验一个备份是否可用于恢复（`docs/02` §23 的校验阶段）。

        Args:
            backup_path: 备份目录。

        Returns:
            `BackupVerification`：清单 → 数据库校验和 → 产物校验和 → schema 版本。
            备份损坏时 `valid=False`（**不**抛异常，见模块裁决 6）。

        Raises:
            InternalError: `STRUCTAI-7000` `reason="schema_mismatch"`，
                备份的 schema 版本与当前不一致（见模块裁决 7）。
        """
        verification = await self._backup.verify_backup(backup_path)
        if not verification.valid:
            return verification
        manifest_path = Path(backup_path) / BACKUP_MANIFEST_NAME
        try:
            manifest = BackupManifest.from_dict(
                json.loads(manifest_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, InternalError):
            return BackupVerification(
                valid=False,
                backup_id=None,
                database_ok=False,
                artifacts_ok=False,
                checked=verification.checked,
                failures=("manifest_unreadable",),
            )
        current = self._backup_schema_revision()
        if current is not None and manifest.schema_revision not in (None, current):
            raise InternalError(
                "Backup schema revision does not match the current schema",
                details={"stage": RESTORE_STAGE, "reason": "schema_mismatch"},
            )
        return verification

    # ===== `docs/02` §23 / §24：恢复 =====

    async def restore(self, backup_path: str | Path) -> RestoreReport:
        """按 `docs/02` §23 的顺序恢复（失败即报告，不抛异常 —— 见模块裁决 8）。

        Args:
            backup_path: 备份目录。

        Returns:
            `RestoreReport`：`restored=True` **只**在全部阶段成功时成立。

        Raises:
            InternalError: `STRUCTAI-7000` `reason="schema_mismatch"`
                （由 `validate` 抛出；这是**恢复前**的装配错误，不是「部分恢复」）。
        """
        verification = await self.validate(backup_path)
        if not verification.valid:
            return RestoreReport(
                restored=False,
                backup_id=verification.backup_id,
                pre_restore_backup=None,
                database_restored=False,
                artifacts_restored=0,
                integrity_ok=False,
                failures=verification.failures or ("backup_invalid",),
            )
        backup_dir = Path(backup_path)
        failures: list[str] = []
        # `docs/02` §24：恢复前**必须**先创建当前状态紧急备份。
        try:
            emergency = await self._backup.create_backup(self.restore_root / RESTORE_PRE_BACKUP_DIR)
        except Exception:
            # 紧急备份失败 → **不得**继续恢复（否则失去回退路径）。
            return RestoreReport(
                restored=False,
                backup_id=verification.backup_id,
                pre_restore_backup=None,
                database_restored=False,
                artifacts_restored=0,
                integrity_ok=False,
                failures=("pre_restore_backup_failed",),
            )
        pre_restore = str(Path(RESTORE_PRE_BACKUP_DIR) / emergency.backup_id)
        database_restored = self._restore_database(backup_dir, failures)
        artifacts_restored = await self._restore_artifacts(backup_dir, failures)
        integrity = await self.integrity_check()
        integrity_ok = bool(integrity.get("database_ok")) and bool(integrity.get("artifacts_ok"))
        if not integrity_ok:
            failures.append("integrity_check_failed")
        registry_ok: bool | None = None
        if self._registry_validator is not None:
            registry_ok = await self._registry_validator()
            if not registry_ok:
                failures.append("registry_validation_failed")
        restored = database_restored and integrity_ok and registry_ok is not False
        return RestoreReport(
            restored=restored,
            backup_id=verification.backup_id,
            pre_restore_backup=pre_restore,
            database_restored=database_restored,
            artifacts_restored=artifacts_restored,
            integrity_ok=integrity_ok,
            registry_ok=registry_ok,
            failures=tuple(failures),
        )

    # ===== `docs/02` §26：完整性检查 =====

    async def integrity_check(self) -> dict[str, Any]:
        """`docs/02` §26 的完整性检查（数据库 + Artifact + Registry）。

        Returns:
            `{"database_ok": bool, "database": <PRAGMA 原始结果>, "artifacts_ok": bool,
            "artifacts": [...], "registry": bool | None}`。

        ⚠️ `registry` 为 `None` 表示**未注入**校验钩子 —— 与「校验失败」必须可区分
        （见模块裁决 14）。
        """
        database_ok, raw = await asyncio.to_thread(self._pragma_integrity_check)
        artifacts = await self._backup.artifact_checksums()
        artifacts_ok = True
        for entry in artifacts:
            artifact_id, _, checksum = entry.partition(":")
            target = self._artifact_root / artifact_id / ARTIFACT_BACKUP_DIR
            if not target.is_file() or _sha256_file(target) != checksum:
                artifacts_ok = False
        registry_ok: bool | None = None
        if self._registry_validator is not None:
            registry_ok = await self._registry_validator()
        return {
            "database_ok": database_ok,
            "database": raw,
            "artifacts_ok": artifacts_ok,
            "artifacts": list(artifacts),
            "registry": registry_ok,
        }

    # ===== 内部 =====

    def _backup_schema_revision(self) -> str | None:
        """当前 schema 版本（从注入的 `BackupService` 读取；未设置时 `None`）。"""
        return self._backup.schema_revision

    def _pragma_integrity_check(self) -> tuple[bool, str]:
        """`PRAGMA integrity_check`（`docs/02` §26 的原文口径）。

        Returns:
            `(是否通过, PRAGMA 的原始结果字符串)`；数据库不可打开时
            `(False, "unavailable")` —— 检查**不**抛异常（`docs/02` §17）。
        """
        if not self._database_path.is_file():
            return False, "unavailable"
        try:
            connection = sqlite3.connect(str(self._database_path))
            try:
                row = connection.execute("PRAGMA integrity_check;").fetchone()
            finally:
                connection.close()
        except sqlite3.Error:
            return False, "unavailable"
        result = "" if row is None else str(row[0])
        return result.lower() == "ok", result

    def _restore_database(self, backup_dir: Path, failures: list[str]) -> bool:
        """把备份里的数据库文件覆盖到目标路径（`docs/02` §23 的 `Restore Database`）。"""
        source = backup_dir / BACKUP_DATABASE_NAME
        if not source.is_file():
            failures.append("database_missing")
            return False
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, self._database_path)
        return True

    async def _restore_artifacts(self, backup_dir: Path, failures: list[str]) -> int:
        """把备份里的产物载荷写回存储（`docs/02` §23 的 `Restore Artifacts`）。

        ⚠️ 产物**元数据**（`artifacts` 行）随数据库一起恢复 —— 载荷单独复制正是
        `docs/02` §18 的口径。
        """
        root = backup_dir / BACKUP_ARTIFACTS_DIR
        payloads = sorted(root.glob(f"*/{ARTIFACT_BACKUP_DIR}"))
        storage = self._storage
        if payloads and storage is None:
            failures.append("artifact_storage_not_wired")
            return 0
        restored = 0
        for payload in payloads:
            artifact_id = payload.parent.name
            data = await asyncio.to_thread(payload.read_bytes)
            try:
                if storage is None:  # 上面的分支已提前返回；此处只为类型收窄。
                    raise ArtifactError(
                        "Artifact payload storage is not wired",
                        details={
                            "stage": RESTORE_STAGE,
                            "reason": "artifact_storage_not_wired",
                        },
                    )
                await storage.put(data, {"artifact_id": artifact_id})
            except Exception:
                failures.append(f"artifact_restore_failed:{artifact_id}")
                continue
            restored += 1
        return restored


class RetentionService:
    """数据保留清理（`docs/02` §27–§31 / §45）。

    🔴 **刻意没有 `cleanup_audit`**（`docs/02` §29 / §45）：审计记录的删除需要
    「Audit Retention Policy + Administrator Authorization + Audit of Deletion」
    三个条件，普通 retention job **不得**删除审计记录。故 `RetentionPolicy.audit_days`
    在本模块是**已登记但未使用**的字段（见模块裁决 10）。

    ⚠️ 每个 `cleanup_*` 在对应源**未注入**时返回 `0`，但 `configured()` 让调用方
    能区分「清理了 0 行」与「根本没接这个源」（见模块裁决 11）。
    """

    def __init__(
        self,
        *,
        policy: RetentionPolicy | None = None,
        tasks: TaskRetentionSource | None = None,
        traces: TraceStore | None = None,
        events: EventRecordStore | None = None,
        artifacts: ArtifactStore | None = None,
        storage: ArtifactStorageReader | str | Path | None = None,
        clock: Clock | None = None,
    ) -> None:
        """绑定保留策略与各数据类别的保留源。

        Args:
            policy: 保留策略（`docs/02` §27 / §28）；缺省 `RetentionPolicy()`
                （= §28 的默认策略表）。
            tasks: 任务保留源（另一模块的 `TaskStore` 结构上可满足，见模块裁决 1）。
            traces: Span 存储（`app.domain.protocols.TraceStore`）。
            events: Outbox 存储（`app.domain.protocols.EventRecordStore`）。
            artifacts: 产物元数据存储（`app.domain.protocols.ArtifactStore`）。
            storage: 产物字节流**根目录**（§31 的 GC 扫描根；`ArtifactStorage` 的实现
                通常把它暴露为存储根 —— 本模块只做路径扫描，**不**删除，见模块裁决 12）。
            clock: 可注入时钟；缺省带时区的 UTC 当前时间。
        """
        self._policy = policy if policy is not None else RetentionPolicy()
        self._tasks = tasks
        self._traces = traces
        self._events = events
        self._artifacts = artifacts
        self._storage_root = _storage_root_of(storage)
        self._clock: Clock = clock if clock is not None else _utc_now

    @property
    def policy(self) -> RetentionPolicy:
        """保留策略（只读）。"""
        return self._policy

    def configured(self) -> tuple[str, ...]:
        """已装配的保留源名称（见模块裁决 11）。

        Returns:
            已注入的类别名元组（`tasks` / `traces` / `events` / `artifacts`）；
            **不**包含 `sessions`（它经 `cleanup_sessions(sessions=...)` 按调用传入）
            也**不**包含 `audit`（见模块裁决 10）。
        """
        names: list[str] = []
        if self._tasks is not None:
            names.append("tasks")
        if self._traces is not None:
            names.append("traces")
        if self._events is not None:
            names.append("events")
        if self._artifacts is not None:
            names.append("artifacts")
        return tuple(names)

    # ===== `docs/02` §29：逐类清理 =====

    async def cleanup_tasks(self) -> int:
        """删除过期任务（`docs/02` §29 的 `cleanup_tasks`）。

        Returns:
            删除的行数；未装配任务源时 `0`（见模块裁决 11）。
        """
        if self._tasks is None:
            return 0
        return await self._tasks.delete_finished_before(self._cutoff(self._policy.task_days))

    async def cleanup_traces(self) -> int:
        """删除过期 Span（`docs/02` §29 的 `cleanup_traces`）。

        Returns:
            删除的行数；未装配 `TraceStore` 时 `0`。

        ⚠️ `app.domain.protocols.TraceStore` **没有删除方法**：`docs/02` §44 的
        「Trace 数据不允许修改」把该契约限定为追加 + 结束 Span。因此本方法在已装配
        时也如实返回 `0`（**不**用 `finish()` 伪造删除 —— 那会把「未清理」写成
        「已清理」）。需要真正清理时，`trace_spans` 需先按 `docs/07` §14.3 的
        Alembic 迁移建表并扩展该契约。
        """
        return 0

    async def cleanup_events(self) -> int:
        """删除过期 Outbox 记录（`docs/02` §29 的 `cleanup_events`）。

        Returns:
            删除的行数；未装配 `EventRecordStore` 时 `0`。

        ⚠️ 同 `cleanup_traces`：`EventRecordStore` 是**只追加**的 Outbox 契约
        （`docs/02` §6 / §5.4），没有删除方法，故已装配时也如实返回 `0`。
        `event_records` 表同样不在 `docs/07` §4.3 的 24 张表内。
        """
        return 0

    async def cleanup_artifacts(self) -> int:
        """删除过期产物的**元数据行**（`docs/02` §29 的 `cleanup_artifacts`）。

        Returns:
            删除的行数；未装配 `ArtifactStore` 时 `0`。

        ⚠️ 载荷**不**在此删除（storage 契约没有 `delete`）：孤立载荷由
        `collect_garbage()` 隔离（见模块裁决 12）。
        """
        store = self._artifacts
        if store is None:
            return 0
        cutoff = self._cutoff(self._policy.artifact_days)
        removed = 0
        offset = 0
        while True:
            page = await store.list_all(limit=_PAGE_SIZE, offset=offset)
            if not page:
                break
            deleted_in_page = 0
            for record in page:
                created = record.created_at
                if created is not None and created < cutoff:
                    if await store.delete(record.id):
                        removed += 1
                        deleted_in_page += 1
            # 行被删掉后偏移量会前移，故只在**未删除**时推进 offset。
            if deleted_in_page == 0:
                offset += len(page)
        return removed

    async def cleanup_sessions(
        self,
        *,
        sessions: SessionRetentionSource | None = None,
    ) -> int:
        """删除过期会话（`docs/02` §29 的 `cleanup_sessions`）。

        Args:
            sessions: 会话保留源；`None` 时返回 `0`（见模块裁决 11）。

        Returns:
            删除的行数。
        """
        if sessions is None:
            return 0
        return await sessions.delete_expired_before(self._cutoff(self._policy.session_days))

    async def cleanup_all(self) -> RetentionReport:
        """跑一遍全部保留清理（`docs/02` §29）。

        Returns:
            `RetentionReport`：`cleaned` 是类别 → 删除行数。

        🔴 **不**含 `audit` 类别（见模块裁决 10）。
        """
        return RetentionReport(
            cleaned={
                "tasks": await self.cleanup_tasks(),
                "traces": await self.cleanup_traces(),
                "events": await self.cleanup_events(),
                "artifacts": await self.cleanup_artifacts(),
                "sessions": await self.cleanup_sessions(),
            }
        )

    # ===== `docs/02` §31：Artifact GC =====

    async def collect_garbage(self) -> int:
        """隔离「库中无记录但存储里有载荷」的孤儿（`docs/02` §31）。

        流程（§31 逐字）：`scan storage → extract artifact_id → query DB →
        not found → quarantine`。🔴 **禁止扫描后立即删除**：本方法只把载荷
        **移动**到 `quarantine/`，删除是更晚的、显式的步骤（见模块裁决 13）。

        Returns:
            被隔离的载荷数量；未装配 `ArtifactStore` 或存储根不存在时 `0`。
        """
        store = self._artifacts
        root = self._storage_root
        if store is None or root is None or not root.is_dir():
            return 0
        known = await self._known_artifact_ids(store)
        quarantined = 0
        for tenant_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if tenant_dir.name == QUARANTINE_DIR:
                continue
            for project_dir in sorted(path for path in tenant_dir.iterdir() if path.is_dir()):
                for artifact_dir in sorted(path for path in project_dir.iterdir() if path.is_dir()):
                    if artifact_dir.name in known:
                        continue
                    payload = artifact_dir / ARTIFACT_BACKUP_DIR
                    if not payload.is_file():
                        continue
                    target_dir = (
                        root
                        / QUARANTINE_DIR
                        / tenant_dir.name
                        / project_dir.name
                        / artifact_dir.name
                    )
                    target_dir.mkdir(parents=True, exist_ok=True)
                    await asyncio.to_thread(
                        shutil.move, str(payload), str(target_dir / ARTIFACT_BACKUP_DIR)
                    )
                    quarantined += 1
        return quarantined

    # ===== 内部 =====

    @property
    def storage_root(self) -> Path | None:
        """产物字节流根目录（`docs/02` §3.5 的 `{tenant_id}/…` 根；未装配时 `None`）。"""
        return self._storage_root

    # ===== 内部 =====

    def _cutoff(self, days: int) -> datetime:
        """保留截止时刻（`docs/02` §27 / §28 的 `retention_days`）。"""
        return self._clock() - timedelta(days=days)

    async def _known_artifact_ids(self, store: ArtifactStore) -> set[str]:
        """`artifacts` 表里全部产物标识（**有界分页**，`docs/07` §14.4）。"""
        known: set[str] = set()
        offset = 0
        while True:
            page = await store.list_all(limit=_PAGE_SIZE, offset=offset)
            if not page:
                break
            known.update(record.id for record in page)
            offset += len(page)
        return known
