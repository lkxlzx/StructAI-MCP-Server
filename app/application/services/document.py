"""Application · Services · DocumentService（`docs/02` §30 / §57 / §4.3 / §4.4 / §41 / §50）。

权威来源
--------
- `docs/02` §30（`blue` / `source9`）—— `DocumentService` 的职责：文档生命周期与版本；
  它是**唯一**改变文档状态的入口。
- `docs/02` §57（`blue`）—— 文档操作词表：`NEW` → `OPEN` → `SAVE` → `SAVE_AS` → `CLOSE`，
  另有 `INFO`（「INFO 不改变生命周期」，`docs/02` §4.3）。
- `docs/02` §4.3（`blue`）—— `new` / `open` / `save` / `save_as` / `close` / `info`
  的操作级语义；`docs/02` §4.4 给出 `new(ctx, name, document_type)` 等方法签名。
- `docs/02` §4.1 / §4.2 —— `documents` 表的真实列（`project_id` / `model_id` / `name` /
  `path` / `status`）与 `document_versions` 的 `(document_id, version)` 唯一约束。
- `docs/02` §41（`blue`）—— `DocumentInfo` 的字段：`document_id` / `name` /
  `document_type` / `status` / `current_version`。
- `docs/02` §50（`blue`）—— 版本链：每次 `save` 追加一行，最新版本是 `current_version`。
- `docs/02` §48（`exec`）—— 跨租户与「不存在」**不得区分**（同一形状，不泄露存在性）。
- `docs/07` §12 P30 / §4.3 #15 —— `documents` 是 24 张冻结表之一；`docs/07` §14.4 ——
  Service **绝不** `commit` / `rollback`（事务边界归 `UnitOfWork`）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **操作生命周期 vs 持久化状态（本批最重要的裁决）**：`docs/02` §4.3 / §57 描述的是
   **操作**序列 `NEW → OPEN → SAVE → SAVE_AS → CLOSE`，而冻结的 `documents.status` 列与
   冻结的 `DocumentStatus` 枚举（P03）只有 `NEW` / `OPEN` / `CLOSED` 三值，本批**不得改
   表**。裁决：`SAVE` / `SAVE_AS` 是**保持 `OPEN`** 的操作（它们只追加版本 / 改名），
   `CLOSE` 把 `OPEN → CLOSED`，`INFO` 什么都不改。`DOCUMENT_STATUS_EDGES` 因此只描述
   **持久化**列的三值转移。
2. **`CLOSED → OPEN` 允许**：`docs/02` §4.3 的 `open` 只写「打开文档」，没有说「已关闭的
   文档不可再打开」。冻结枚举把 `CLOSED` 定义为**生命周期终态以外的**状态（不是 Task 的
   终态语义），且 `docs/02` §57 的操作序列可从 `NEW` 重新开始。故 `CLOSED → OPEN` 合法
   （重新打开），`CLOSED → CLOSED` 等自转移仍非法。
3. **`new()` 的 `project_id` 是关键字参数**：`docs/02` §4.4 的签名是
   `new(ctx, name, document_type)`，但冻结的 `documents` 表把 `project_id` 声明为
   `NOT NULL`（`docs/07` §4.3 #15）。**表结构胜出** —— 没有 `project_id` 就无法落行，
   故它是必需的关键字参数（不新增列，也不允许 `NULL`）。
4. **租户归属经 `project_id` 派生**：`documents` 表**没有** `tenant_id` 列
   （`docs/02` §11 / §22）。故租户断言经注入的 `tenant_of_project(project_id)` 解析，
   而**不**信任 `ctx` 里的任何身份字段（`docs/07` §8.1：身份只能由 Core 构造）。
   **缺省 `None` = 「不做租户断言」**：这使本服务可在未装配项目查找时独立使用（例如
   装配期自检），但也意味着该模式下**没有**跨租户拦截 —— 调用方必须显式注入查找才获得
   隔离。这一点是刻意的、可断言的：`tenant_of_project is None` 时 `_assert_tenant`
   只回读 `ctx` 的租户，不做比较。
5. **`save()` 的 `checksum` 允许为空串**：`ArtifactRecord.checksum` 是可选的
   （`docs/02` §29 的 `checksum` 由存储后端计算）。`DocumentVersionRecord.checksum` 是
   必填 `str`，故 `None` → `""`（**不**伪造摘要值）。
6. **`save_as()` 复用最新版本的产物**：`docs/02` §4.4 的 `save_as` 没有独立的存储概念，
   而冻结的 `document_versions` 契约要求 `artifact_id`。故 `save_as` 只**改名**
   （`documents.name`），并在**已有**最新版本时追加一行复用其 `artifact_id` /
   `checksum`（版本号 +1）；**没有**任何版本时不追加（没有可复用的产物，不伪造一行）。
7. **`document_type` 是进程内登记**：`documents` 表**没有** `document_type` 列
   （`docs/02` §4.1 的 ORM 有，但不在 `docs/07` §4.3 的 24 张表内）—— 本批不得改表。
   故 `new()` 把 `document_type` 记在进程内映射里，`info()` 从中读取；未登记时返回空串
   （Alpha 限制，与 `InMemoryDocumentVersionStore` 同一口径）。
8. **`INFO` 不改变生命周期**（`docs/02` §4.3）：`info()` 只读行 + 读最新版本，
   返回 `DocumentInfo`；`INFORMATION_ONLY_OPERATION` 是该操作名的可断言常量。
9. **不存在的文档 → `STRUCTAI-7000`**：`docs/02` §48 要求「不存在」与「属于别的租户」
   同一形状；本服务对**未知文档**落 `InternalError`（`STRUCTAI-7000`，
   `reason = "unknown_document"`），对**租户不符**落 `TenantAccessDeniedError`
   （`STRUCTAI-4200`，`reason = "tenant_mismatch"`）—— 两者的 `details` 形状一致
   （只有 `stage` + `reason`，**不**回显任何标识），故不泄露存在性。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与**同层**的 `app.application.services`：
**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，**不**依赖 `app.infrastructure`
（持久化与产物写入经 Domain 契约 / 本地收窄契约注入），也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Protocol

from app.domain.enums import DocumentStatus
from app.domain.errors import EngineeringValidationError, InternalError, TenantAccessDeniedError
from app.domain.protocols import (
    ArtifactRecord,
    DocumentDraft,
    DocumentSnapshot,
    DocumentStore,
    DocumentVersionRecord,
    DocumentVersionStore,
)

__all__ = [
    "DOCUMENT_STATUS_EDGES",
    "DOCUMENT_LIFECYCLE_ORDER",
    "DOCUMENT_STAGE",
    "INFORMATION_ONLY_OPERATION",
    "DocumentArtifactWriter",
    "DocumentInfo",
    "DocumentService",
]

DOCUMENT_STAGE: Final[str] = "document"
"""本模块所有异常 `details["stage"]` 的固定取值（`docs/07` §11 的诊断口径）。"""

DOCUMENT_LIFECYCLE_ORDER: Final[tuple[str, ...]] = (
    "NEW",
    "OPEN",
    "SAVE",
    "SAVE_AS",
    "CLOSE",
)
"""`docs/02` §4.3 / §57 的**操作**生命周期顺序（逐字抄写，供断言；见模块裁决 1）。

⚠️ 这是**操作**词表，不是 `documents.status` 的取值域：`SAVE` / `SAVE_AS` 保持 `OPEN`，
`CLOSE` 才把状态移到 `CLOSED`。持久化取值域只有 `NEW` / `OPEN` / `CLOSED`
（冻结枚举 `app.domain.enums.DocumentStatus`）。
"""

INFORMATION_ONLY_OPERATION: Final[str] = "INFO"
"""`docs/02` §4.3 的信息类操作：**不改变生命周期**（见模块裁决 8）。"""

DOCUMENT_STATUS_EDGES: Mapping[str, frozenset[str]] = MappingProxyType(
    {
        DocumentStatus.NEW.value: frozenset(
            {DocumentStatus.OPEN.value, DocumentStatus.CLOSED.value}
        ),
        DocumentStatus.OPEN.value: frozenset({DocumentStatus.CLOSED.value}),
        DocumentStatus.CLOSED.value: frozenset({DocumentStatus.OPEN.value}),
    }
)
"""`documents.status` 列的冻结转移表（`docs/02` §4.3 / §57；见模块裁决 1 / 2）。

- `NEW → {OPEN, CLOSED}`：`new` 之后可以打开，也可以直接关闭（从未打开的文档允许废弃）。
- `OPEN → {CLOSED}`：只有 `close` 会离开 `OPEN`；`save` / `save_as` **保持** `OPEN`。
- `CLOSED → {OPEN}`：允许重新打开（见模块裁决 2）。
"""


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    """一份文档的信息视图（`docs/02` §41，逐字段照抄）。

    Attributes:
        document_id: 文档标识。
        name: 文档名（`documents.name`）。
        document_type: 文档类型；来自进程内登记（见模块裁决 7），未登记为空串。
        status: `documents.status`（`NEW` / `OPEN` / `CLOSED`）。
        current_version: 最新版本号；从未 `save` 过时为 `0`（`docs/02` §50）。
    """

    document_id: str
    name: str
    document_type: str
    status: str
    current_version: int


class DocumentArtifactWriter(Protocol):
    """产物写入的**本地收窄契约**（收窄契约 pattern，同 R38 的 `RuntimeCapabilitySource`）。

    `ArtifactService`（`app/application/services/artifact.py`，由本批另一 Agent 拥有）
    **结构上**即满足它：它提供同一签名的 `async create(...)` 并返回
    `app.domain.protocols.ArtifactRecord`。本模块因此**不**导入那个模块
    （它可能尚未落地），也不导入 `app.infrastructure`（`docs/07` §14.1）。

    ⚠️ 实现必须与业务写**同一** `UnitOfWork`，并**绝不**记录 secret
    （`docs/07` §14.3：产物内容不落数据库）。
    """

    async def create(
        self,
        *,
        tenant_id: str,
        data: bytes,
        mime_type: str,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> ArtifactRecord:
        """写入一段产物字节流并返回其元数据（`docs/02` §29 / §33）。"""
        ...


class DocumentService:
    """文档生命周期服务（`docs/02` §30 / §57 / §4.3 / §4.4 / §41 / §50）。

    ⚠️ 本服务只经 Domain 契约读写：**不** `commit` / `rollback`（`docs/07` §14.4），
    **不**依赖 `app.infrastructure`（`docs/07` §14.1），也**不**信任 `ctx` 的租户
    （`docs/07` §8.1；见模块裁决 4）。
    """

    def __init__(
        self,
        store: DocumentStore,
        versions: DocumentVersionStore,
        *,
        artifacts: DocumentArtifactWriter | None = None,
        tenant_of_project: Callable[[str], Awaitable[str | None]] | None = None,
    ) -> None:
        """绑定文档仓储、版本注册表与可选的产物写入 / 租户查找。

        Args:
            store: 满足 `app.domain.protocols.DocumentStore` 的持久化来源。
            versions: 满足 `app.domain.protocols.DocumentVersionStore` 的版本注册表
                （Core Alpha 为 `InMemoryDocumentVersionStore`，见该模块的 Alpha 限制）。
            artifacts: 产物写入器（`DocumentArtifactWriter`）；`None` 时 `save()` 拒绝
                （`STRUCTAI-7000`，`reason = "artifact_writer_not_configured"`）。
            tenant_of_project: 项目 → 租户的解析函数；`None` = **不做租户断言**
                （见模块裁决 4）。注入后即获得跨租户拦截（`docs/02` §11 / §48）。
        """
        self._documents = store
        self._versions = versions
        self._artifacts = artifacts
        self._tenant_of_project = tenant_of_project
        self._document_types: dict[str, str] = {}

    @property
    def store(self) -> DocumentStore:
        """文档持久化来源（只读用途）。"""
        return self._documents

    @property
    def versions(self) -> DocumentVersionStore:
        """版本注册表（只读用途）。"""
        return self._versions

    @property
    def artifacts(self) -> DocumentArtifactWriter | None:
        """产物写入器；未配置时为 `None`（`save()` 据此拒绝）。"""
        return self._artifacts

    # ===== 生命周期（`docs/02` §4.3 / §4.4 / §57）=====

    async def new(
        self,
        ctx: object,
        name: str,
        document_type: str,
        *,
        project_id: str,
        model_id: str | None = None,
    ) -> DocumentSnapshot:
        """创建一个新文档，状态 `NEW`（`docs/02` §4.4；见模块裁决 3）。

        Args:
            ctx: 执行上下文；本方法只从中读取租户用于**断言**（见模块裁决 4）。
            name: 文档名；空白即拒绝（`STRUCTAI-1200`）。
            document_type: 文档类型；登记在进程内映射里（见模块裁决 7）。
            project_id: 归属项目（`documents.project_id` 为 `NOT NULL`）。
            model_id: 可选关联的工程模型。

        Returns:
            新文档的快照（`status = NEW`）。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`，`name` 为空白
                （`details = {stage: "document", reason: "invalid_name"}`）。
            TenantAccessDeniedError: `STRUCTAI-4200`，`ctx` 的租户与项目租户不符
                （见模块裁决 4 / 9）。
        """
        if not str(name).strip():
            raise EngineeringValidationError(
                "document name must not be blank",
                details={"stage": DOCUMENT_STAGE, "reason": "invalid_name"},
            )
        await self._assert_tenant(ctx, project_id)
        snapshot = await self._documents.create(
            DocumentDraft(
                project_id=str(project_id),
                name=str(name),
                status=DocumentStatus.NEW.value,
                model_id=None if model_id is None else str(model_id),
            )
        )
        self._document_types[snapshot.id] = str(document_type)
        return snapshot

    async def open(self, ctx: object, document_id: str) -> DocumentSnapshot:
        """打开文档（`NEW → OPEN` 或 `CLOSED → OPEN`；`docs/02` §4.3）。

        Raises:
            InternalError: `STRUCTAI-7000`，文档不存在（`reason = "unknown_document"`）。
            EngineeringValidationError: `STRUCTAI-1200`，非法转移
                （`details` 带 `from` / `to`）。
            TenantAccessDeniedError: `STRUCTAI-4200`，租户不符（见模块裁决 4 / 9）。
        """
        snapshot = await self._load(ctx, document_id)
        return await self._move(snapshot, DocumentStatus.OPEN.value)

    async def save(
        self,
        ctx: object,
        document_id: str,
        content: bytes,
        *,
        mime_type: str = "application/octet-stream",
    ) -> DocumentVersionRecord:
        """保存内容为一个新版本（`docs/02` §4.4 / §50）。

        文档必须处于 `OPEN`（`SAVE` 保持 `OPEN`，见模块裁决 1）；版本号 = 最新版本 + 1
        （从未保存过时为 `1`）。

        Args:
            ctx: 执行上下文（租户断言）。
            document_id: 目标文档。
            content: 内容字节流；经注入的产物写入器落盘（`docs/02` §29）。
            mime_type: 内容类型；缺省 `application/octet-stream`。

        Returns:
            新追加的版本记录（`docs/02` §4.2）。

        Raises:
            InternalError: `STRUCTAI-7000`，未配置产物写入器
                （`reason = "artifact_writer_not_configured"`），或文档不存在。
            EngineeringValidationError: `STRUCTAI-1200`，文档不在 `OPEN`
                （`reason = "document_not_open"`）。
            TenantAccessDeniedError: `STRUCTAI-4200`，租户不符。
        """
        if self._artifacts is None:
            raise InternalError(
                "artifact writer is not configured",
                details={"stage": DOCUMENT_STAGE, "reason": "artifact_writer_not_configured"},
            )
        snapshot = await self._load(ctx, document_id)
        if str(snapshot.status) != DocumentStatus.OPEN.value:
            raise EngineeringValidationError(
                "document is not open",
                details={"stage": DOCUMENT_STAGE, "reason": "document_not_open"},
            )

        latest = await self._versions.latest(snapshot.id)
        version = (latest.version if latest is not None else 0) + 1
        artifact = await self._artifacts.create(
            tenant_id=await self._tenant_for(snapshot.project_id),
            data=content,
            mime_type=str(mime_type),
            project_id=snapshot.project_id,
        )
        return await self._versions.append(
            document_id=snapshot.id,
            version=version,
            artifact_id=artifact.id,
            checksum=artifact.checksum or "",
        )

    async def save_as(
        self,
        ctx: object,
        document_id: str,
        new_name: str,
    ) -> DocumentSnapshot:
        """另存为：改名并（在已有版本时）追加一行复用产物的版本（`docs/02` §4.4）。

        见模块裁决 6：冻结 schema 里 `save_as` **没有**独立存储概念，故它只改
        `documents.name` 并保持状态不变；已有最新版本时追加一行（版本号 +1、
        `artifact_id` / `checksum` 与最新版本相同），没有版本时不追加。

        Raises:
            EngineeringValidationError: `STRUCTAI-1200`，`new_name` 为空白
                （`reason = "invalid_name"`，与 `new()` 同一不变量）。
            InternalError: `STRUCTAI-7000`，文档不存在。
            TenantAccessDeniedError: `STRUCTAI-4200`，租户不符。
        """
        if not str(new_name).strip():
            raise EngineeringValidationError(
                "document name must not be blank",
                details={"stage": DOCUMENT_STAGE, "reason": "invalid_name"},
            )
        snapshot = await self._load(ctx, document_id)
        updated = await self._documents.update(snapshot.id, fields={"name": str(new_name)})
        if updated is None:
            raise self._unknown_document()

        latest = await self._versions.latest(snapshot.id)
        if latest is not None:
            await self._versions.append(
                document_id=snapshot.id,
                version=latest.version + 1,
                artifact_id=latest.artifact_id,
                checksum=latest.checksum,
            )
        return updated

    async def close(self, ctx: object, document_id: str) -> None:
        """关闭文档（`OPEN → CLOSED`；`docs/02` §4.3）。

        Raises:
            InternalError: `STRUCTAI-7000`，文档不存在。
            EngineeringValidationError: `STRUCTAI-1200`，非法转移（已 `CLOSED` 再 `close`
                即非法 —— 见模块裁决 1 / 2）。
            TenantAccessDeniedError: `STRUCTAI-4200`，租户不符。
        """
        snapshot = await self._load(ctx, document_id)
        await self._move(snapshot, DocumentStatus.CLOSED.value)

    async def info(self, ctx: object, document_id: str) -> DocumentInfo:
        """读取文档信息（`docs/02` §41 / §4.3 的 `INFO`；不改变生命周期）。

        `current_version` 取自版本注册表的最新版本（`docs/02` §50）；从未保存过时为 `0`。

        Raises:
            InternalError: `STRUCTAI-7000`，文档不存在。
            TenantAccessDeniedError: `STRUCTAI-4200`，租户不符。
        """
        snapshot = await self._load(ctx, document_id)
        latest = await self._versions.latest(snapshot.id)
        return DocumentInfo(
            document_id=snapshot.id,
            name=snapshot.name,
            document_type=self._document_types.get(snapshot.id, ""),
            status=str(snapshot.status),
            current_version=latest.version if latest is not None else 0,
        )

    def lifecycle_order(self) -> tuple[str, ...]:
        """`docs/02` §57 的操作生命周期顺序（返回常量，见模块裁决 1）。"""
        return DOCUMENT_LIFECYCLE_ORDER

    # ===== 内部 =====

    async def _load(self, ctx: object, document_id: str) -> DocumentSnapshot:
        """读取文档并做租户断言（`docs/02` §48；见模块裁决 9）。"""
        snapshot = await self._documents.get(str(document_id))
        if snapshot is None:
            raise self._unknown_document()
        await self._assert_tenant(ctx, snapshot.project_id)
        return snapshot

    async def _move(self, snapshot: DocumentSnapshot, target: str) -> DocumentSnapshot:
        """按冻结转移表改状态（`docs/02` §4.3；见模块裁决 1 / 2）。"""
        current = str(snapshot.status)
        if target not in DOCUMENT_STATUS_EDGES.get(current, frozenset()):
            raise EngineeringValidationError(
                "illegal document transition",
                details={
                    "stage": DOCUMENT_STAGE,
                    "reason": "illegal_transition",
                    "from": current,
                    "to": target,
                },
            )
        updated = await self._documents.update(snapshot.id, fields={"status": target})
        if updated is None:
            raise self._unknown_document()
        return updated

    async def _assert_tenant(self, ctx: object, project_id: str) -> None:
        """断言 `ctx` 的租户与项目租户一致（`docs/02` §11 / §48；见模块裁决 4）。

        - 未注入 `tenant_of_project` → **不做断言**（缺省语义，见模块裁决 4）。
        - `ctx` 没有租户 → 无法比对，放行（身份缺失不是本服务的判定对象）。
        - 项目租户取不到（`None`）或与 `ctx` 不符 → 同一个 `STRUCTAI-4200`。
        """
        if self._tenant_of_project is None:
            return
        context_tenant = _context_tenant(ctx)
        if context_tenant is None:
            return
        project_tenant = await self._tenant_of_project(str(project_id))
        if project_tenant is None or str(project_tenant) != context_tenant:
            raise TenantAccessDeniedError(
                "tenant access denied",
                details={"stage": DOCUMENT_STAGE, "reason": "tenant_mismatch"},
            )

    async def _tenant_for(self, project_id: str) -> str:
        """解析项目租户供产物写入使用；未注入查找时为空串（见模块裁决 4）。"""
        if self._tenant_of_project is None:
            return ""
        project_tenant = await self._tenant_of_project(str(project_id))
        return "" if project_tenant is None else str(project_tenant)

    @staticmethod
    def _unknown_document() -> InternalError:
        """构造未知文档错误（`STRUCTAI-7000`；见模块裁决 9）。"""
        return InternalError(
            "document not found",
            details={"stage": DOCUMENT_STAGE, "reason": "unknown_document"},
        )


def _context_tenant(ctx: object) -> str | None:
    """取 `ctx.identity.tenant_id`（`docs/02` §3 / §26）。

    只经 `getattr` 读取（与 `app/application/resource/resolver.py` 同一手法），
    使本模块不依赖 `app.application.execution.context`（避免环状依赖）。
    """
    identity = getattr(ctx, "identity", None)
    tenant = getattr(identity, "tenant_id", None)
    return None if tenant is None else str(tenant)
