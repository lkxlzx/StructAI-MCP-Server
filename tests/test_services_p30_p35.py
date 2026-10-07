"""P30 / P35 验收测试：Document / Model / Result 服务 + AdapterResolver。

验收点（与 BRIEF C 的 gate 一一对应）：

① Document 生命周期（`docs/02` §30 / §57 / §4.3 / §4.4）：`new` → `NEW`；`open` →
   `NEW → OPEN`；`save` 追加版本 1、2 且记录 `artifact_id` / `checksum`；未 `OPEN` 的
   `save` → `STRUCTAI-1200` `document_not_open`；`close` → `CLOSED`；二次 `close` →
   `STRUCTAI-1200` `illegal_transition`；`info` 报 `current_version`；`SAVE` / `SAVE_AS`
   **不改变**持久化状态；版本表拒绝重复 `(document_id, version)`；租户不符 → `STRUCTAI-4200`
   且形状与「未知文档」一致；空白名 → `STRUCTAI-1200`。
② Model（`docs/02` §48 / §32 / §33）：六个 `query_*` 用**精确**的 Operation 名与参数映射
   调用注入的来源（替身记录调用）；四个 `assign_*` 只返回 `ModelAssignment`，
   替身来源**一次都没被调用**（证明写操作不在此处执行）。
③ Result（`docs/02` §90 / §31 / §35 / §89 / §49）：`paginate` 与 §90 的规范副本**逐字**
   一致（固定向量 + 独立算出的游标字面量）；`has_more` / `next_cursor` 语义；游标往返；
   非法游标 → `STRUCTAI-1200`；`limit <= 0` → `STRUCTAI-1200`；无界 payload 不可能；
   `normalize` 接受规范映射 / 裸序列 / 裸映射并丢弃畸形分页；`link_artifacts` 去重且保序。
④ AdapterResolver（`docs/02` §87 / §13 / §56 / §48；`docs/07` §16 R35）：正常路径解析出
   厂商 / 产品 / 版本 / Adapter；未知实例 → `STRUCTAI-3000` 且 `details` **不含**实例标识；
   `vendor_product_for` 未绑定时返回 `None` 且不抛；`registered()` 转发来源的键。
⑤ 红线（`docs/07` §14.1 / §14.2 / §14.4 / §11）：`commit` / `rollback` 调用点只在
   `unit_of_work.py`（AST）；`app/` 内厂商名 0 处；`app/` 内的 `STRUCTAI-xxxx` 恰好 20 个码；
   `documents` 的列集合与冻结规范一致；Application 层不依赖 `app.infrastructure`。

⚠️ 本文件里的「规范原文副本」（操作生命周期顺序 / 三值转移表 / 20 码清单 / `documents`
列集合 / 分页信封与游标字面量 / 查询与赋值 Operation 名）**故意不**从被测模块取：
若断言只与被测常量比较，「常量被改错」与「实现被改错」会一起通过（同源循环）。
"""

from __future__ import annotations

import ast
import base64
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.services.adapter_resolver import (
    AdapterResolver,
)
from app.application.services.capability_resolver import CapabilityResolver
from app.application.services.document import (
    DOCUMENT_LIFECYCLE_ORDER,
    DOCUMENT_STATUS_EDGES,
    INFORMATION_ONLY_OPERATION,
    DocumentService,
)
from app.application.services.model import (
    ASSIGN_OPERATIONS,
    QUERY_OPERATIONS,
    ModelAssignment,
    ModelService,
)
from app.application.services.result import (
    DATA_KEY,
    DEFAULT_RESULT_LIMIT,
    HAS_MORE_KEY,
    NEXT_CURSOR_KEY,
    PAGINATION_KEY,
    CanonicalResult,
    ResultService,
    decode_cursor,
    encode_cursor,
    envelope,
    paginate,
)
from app.domain.enums import DocumentStatus, ExecutionMode, RiskLevel, SoftwareConnectionState
from app.domain.errors import (
    CapabilityError,
    EngineeringValidationError,
    InternalError,
    TenantAccessDeniedError,
)
from app.domain.protocols import (
    ArtifactRecord,
    OperationDefinition,
    SoftwareInstanceRecord,
)
from app.domain.value_objects import DEFAULT_PAGE_LIMIT
from app.infrastructure.database.models.document import DocumentORM
from app.infrastructure.database.repositories.document import (
    InMemoryDocumentVersionStore,
    build_document_store,
    build_document_version_store,
)
from app.infrastructure.database.unit_of_work import UnitOfWork

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"

TENANT_ID = "11111111-1111-4111-8111-111111111111"
OTHER_TENANT_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
INSTANCE_ID = "44444444-4444-4444-8444-444444444444"
UNKNOWN_ID = "99999999-9999-4999-8999-999999999999"
MODEL_ID = "55555555-5555-4555-8555-555555555555"

SessionFactory = async_sessionmaker[AsyncSession]

# ===== 规范原文副本（`docs/02` §4.3 / §57 / §90 / §48 / §49；`docs/07` §4.3 / §11）=====

DOCUMENT_LIFECYCLE_ORDER_SPEC = ("NEW", "OPEN", "SAVE", "SAVE_AS", "CLOSE")
"""`docs/02` §4.3 / §57 的**操作**生命周期顺序（逐字抄写）。"""

DOCUMENT_STATUS_VALUES_SPEC = ("NEW", "OPEN", "CLOSED")
"""`docs/02` §8 / §30：`DocumentStatus` 的三值（持久化取值域）。"""

DOCUMENT_TRANSITIONS_SPEC: Mapping[str, frozenset[str]] = {
    "NEW": frozenset({"OPEN", "CLOSED"}),
    "OPEN": frozenset({"CLOSED"}),
    "CLOSED": frozenset({"OPEN"}),
}
"""`documents.status` 列的冻结转移表（`docs/02` §4.3 / §57）。"""

INFORMATION_ONLY_OPERATION_SPEC = "INFO"
"""`docs/02` §4.3：`INFO` 不改变生命周期。"""

QUERY_OPERATIONS_SPEC = (
    "MODEL.NODE.QUERY",
    "MODEL.ELEMENT.QUERY",
    "MODEL.MATERIAL.QUERY",
    "MODEL.SECTION.QUERY",
    "MODEL.BOUNDARY.QUERY",
    "MODEL.LOAD.QUERY",
)
"""`docs/02` §48 的六个读方法归一化后的 Operation 名。"""

ASSIGN_OPERATIONS_SPEC = (
    "MODEL.MATERIAL.ASSIGN",
    "MODEL.SECTION.ASSIGN",
    "MODEL.BOUNDARY.ASSIGN",
    "MODEL.LOAD.ASSIGN",
)
"""`docs/02` §48 的四个写方法归一化后的 Operation 名。"""

PAGINATION_ENVELOPE_KEYS_SPEC = ("data", "pagination")
"""`docs/02` §90 / §31 的信封键（顺序无关，集合相等）。"""

PAGINATION_KEYS_SPEC = ("has_more", "next_cursor")
"""`docs/02` §90 的分页对象键。"""

CURSOR_FOR_2_SPEC = "Mg=="
"""偏移 2 的 base64 字面量（独立算出，证明游标口径）。"""

CURSOR_FOR_4_SPEC = "NA=="
"""偏移 4 的 base64 字面量（独立算出）。"""

DOCUMENTS_TABLE_COLUMNS_SPEC = (
    "id",
    "project_id",
    "model_id",
    "name",
    "path",
    "status",
    "created_at",
    "updated_at",
)
"""`docs/07` §4.3 #15 的 `documents` 列集合（含通用 UUID 主键 / 时间戳规则）。"""

ERROR_CODES_SPEC = (
    "STRUCTAI-1000",
    "STRUCTAI-1100",
    "STRUCTAI-1200",
    "STRUCTAI-1300",
    "STRUCTAI-2000",
    "STRUCTAI-2100",
    "STRUCTAI-2200",
    "STRUCTAI-2300",
    "STRUCTAI-3000",
    "STRUCTAI-4000",
    "STRUCTAI-4100",
    "STRUCTAI-4200",
    "STRUCTAI-5000",
    "STRUCTAI-5100",
    "STRUCTAI-5200",
    "STRUCTAI-5300",
    "STRUCTAI-6000",
    "STRUCTAI-6100",
    "STRUCTAI-6200",
    "STRUCTAI-7000",
)
"""`docs/07` §11：**20 码**错误契约（逐字抄写；本批不得扩）。"""

VENDOR_NAMES = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")
"""`docs/07` §14.2：`app/` 内禁止出现的厂商名。"""

SECRET_MARKERS = ("password", "api_key", "api-key", "token", "private_key", "secret")
"""`docs/07` §14.3：不得出现在 `details` / 记录 / 库中的 secret 形态词。"""

FORBIDDEN_FRAMEWORK_ROOTS = ("sqlalchemy", "fastapi", "mcp", "httpx")
"""`docs/07` §14.1：Application 层不得依赖的框架 / SDK。"""

OWNED_MODULES = (
    "app/infrastructure/database/repositories/document.py",
    "app/application/services/document.py",
    "app/application/services/model.py",
    "app/application/services/result.py",
    "app/application/services/adapter_resolver.py",
)
"""本批新增的源码模块（用于红线断言）。"""


# ===== 辅助（AST / SQL 钩子）=====


def _relative_path(relative: str) -> Path:
    """仓库内相对路径 → 绝对路径。"""
    return REPO_ROOT / relative


def _imported_modules(path: Path) -> set[str]:
    """文件里 `import` / `from … import` 的模块名（AST 级）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _commit_or_rollback_calls(path: Path) -> list[str]:
    """文件内 `.commit()` / `.rollback()` 调用的属性名（AST 级，忽略文档字符串）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"commit", "rollback"}
    ]


def _recorded_statements(engine: AsyncEngine) -> list[str]:
    """录制引擎上执行过的 SQL 语句（验收用 SQL 级钩子）。"""
    statements: list[str] = []

    def _capture(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", _capture)
    return statements


def _table_verbs(statements: Sequence[str], table: str) -> list[str]:
    """只保留作用于指定表的语句的写动词（按表名过滤）。"""
    verbs: list[str] = []
    for statement in statements:
        lowered = statement.lower()
        if f" {table} " not in lowered and f" {table}(" not in lowered:
            continue
        verbs.append(statement.lstrip().split(None, 1)[0].upper())
    return verbs


# ===== 替身（收窄契约的结构实现）=====


@dataclass(frozen=True, slots=True)
class _Identity:
    """最小身份上下文（本服务只读 `identity.tenant_id`）。"""

    tenant_id: str


@dataclass(frozen=True, slots=True)
class _Context:
    """最小执行上下文（`docs/02` §3 的收窄形态）。"""

    identity: _Identity


def _context(tenant_id: str = TENANT_ID) -> _Context:
    """构造一个携带指定租户的上下文。"""
    return _Context(identity=_Identity(tenant_id=tenant_id))


def _tenant_lookup(tenant_id: str) -> Callable[[str], Awaitable[str | None]]:
    """构造项目 → 租户的查找（固定返回同一租户）。"""

    async def lookup(project_id: str) -> str | None:
        return tenant_id

    return lookup


class _ArtifactWriter:
    """`DocumentArtifactWriter` 的替身（记录调用并返回确定性的产物元数据）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create(
        self,
        *,
        tenant_id: str,
        data: bytes,
        mime_type: str,
        project_id: str | None = None,
        task_id: str | None = None,
    ) -> ArtifactRecord:
        """记录一次产物写入并返回固定元数据。"""
        index = len(self.calls)
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "data": data,
                "mime_type": mime_type,
                "project_id": project_id,
                "task_id": task_id,
            }
        )
        return ArtifactRecord(
            id=f"artifact-{index}",
            storage_backend="local",
            storage_key=f"{tenant_id}/{project_id}/artifact-{index}/payload",
            mime_type=mime_type,
            size=len(data),
            checksum=f"checksum-{index}",
        )


class _ModelSource:
    """`ModelQuerySource` 的替身（记录每次调用）。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def query(
        self,
        *,
        software_instance_id: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: object,
    ) -> Mapping[str, Any]:
        """记录调用并回一个固定规范映射。"""
        self.calls.append(
            {
                "software_instance_id": software_instance_id,
                "operation": operation,
                "parameters": dict(parameters),
                "context": context,
            }
        )
        return {"data": []}


class _InstanceSource:
    """`InstanceLookup` 的替身（返回固定实例或 `None`）。"""

    def __init__(self, record: SoftwareInstanceRecord | None = None) -> None:
        self._record = record
        self.calls: list[str] = []

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """记录查询并返回固定记录。"""
        self.calls.append(instance_id)
        return self._record


@dataclass(frozen=True, slots=True)
class _Manifest:
    """Adapter Manifest 的最小形态（`docs/02` §87 第三段）。"""

    vendor: str
    product: str


@dataclass(frozen=True, slots=True)
class _Adapter:
    """Adapter 的最小形态（只需 `manifest` 供注册键读取）。"""

    manifest: _Manifest


class _AdapterSource:
    """`AdapterResolverSource` 的替身（同步返回绑定或 `None`）。"""

    def __init__(
        self,
        *,
        adapters: Mapping[str, object] | None = None,
        keys: Sequence[tuple[str, str]] = (),
        raise_on_lookup: bool = False,
    ) -> None:
        self._adapters = dict(adapters or {})
        self._keys = tuple(keys)
        self._raise_on_lookup = raise_on_lookup
        self.resolved: list[str] = []

    def adapter_for_instance(self, instance_id: str) -> object | None:
        """返回已绑定的 Adapter；未绑定时返回 `None`（或按开关抛出）。"""
        if self._raise_on_lookup:
            raise LookupError(f"Adapter not found: {instance_id}")
        return self._adapters.get(instance_id)

    async def resolve_for_instance(self, software_instance_id: str) -> object:
        """异步解析路径：本替身一律失败（证明回落路径也被处理）。"""
        self.resolved.append(software_instance_id)
        raise LookupError(f"Adapter not found: {software_instance_id}")

    def registered_keys(self) -> Sequence[tuple[str, str]]:
        """返回固定的注册键。"""
        return self._keys


class _CapabilityRegistry:
    """`CapabilityLookup` 的替身（词表只含显式给出的码）。"""

    def __init__(self, codes: Sequence[str]) -> None:
        self._codes = tuple(codes)

    def codes(self) -> Sequence[str]:
        """全部能力码。"""
        return self._codes

    def capabilities_for(self, operation: str) -> Sequence[str]:
        """某 Operation 依赖的能力码（本替身不声明关系）。"""
        return ()


def _instance_record() -> SoftwareInstanceRecord:
    """一个已连接的软件实例（`docs/02` §19 / §12）。"""
    return SoftwareInstanceRecord(
        id=INSTANCE_ID,
        name="instance-under-test",
        status=SoftwareConnectionState.CONNECTED.value,
        vendor="StructAI",
        product="MockEngineering",
        version="2026",
    )


def _operation(name: str, *, capabilities: Sequence[str] = ()) -> OperationDefinition:
    """构造一条 Operation 定义（`docs/02` §11 的 12 字段）。"""
    return OperationDefinition(
        name=name,
        tool="engineering_model_query",
        risk_level=RiskLevel.LOW,
        execution_mode=ExecutionMode.SYNC,
        input_schema="structai://schema/model/query/v1",
        output_schema="structai://schema/model/query/v1",
        required_capabilities=tuple(capabilities),
    )


def _document_service(
    session: AsyncSession,
    *,
    artifacts: _ArtifactWriter | None = None,
    versions: InMemoryDocumentVersionStore | None = None,
    tenant_of_project: Callable[[str], Awaitable[str | None]] | None = None,
) -> DocumentService:
    """装配一个绑定给定会话的 `DocumentService`（`docs/02` §30）。"""
    return DocumentService(
        build_document_store(session),
        build_document_version_store() if versions is None else versions,
        artifacts=artifacts,
        tenant_of_project=tenant_of_project,
    )


async def _document_row(session: AsyncSession, document_id: str) -> DocumentORM | None:
    """直接读 `documents` 行（用于证明**持久化**状态，而非快照）。"""
    result = await session.execute(select(DocumentORM).where(DocumentORM.id == document_id))
    return result.scalar_one_or_none()


# ===== ① Document（`docs/02` §30 / §57 / §4.3 / §4.4）=====


def test_document_lifecycle_constants_match_the_frozen_spec() -> None:
    """门槛 ①（`docs/02` §4.3 / §57）：操作顺序与持久化转移表逐字一致。"""
    assert tuple(DOCUMENT_LIFECYCLE_ORDER) == DOCUMENT_LIFECYCLE_ORDER_SPEC
    assert INFORMATION_ONLY_OPERATION == INFORMATION_ONLY_OPERATION_SPEC
    assert dict(DOCUMENT_STATUS_EDGES) == DOCUMENT_TRANSITIONS_SPEC
    assert set(DOCUMENT_STATUS_EDGES) == set(DOCUMENT_STATUS_VALUES_SPEC)
    assert {value.value for value in DocumentStatus} == set(DOCUMENT_STATUS_VALUES_SPEC)


async def test_new_creates_a_document_in_the_new_state(session_factory: SessionFactory) -> None:
    """门槛 ①（`docs/02` §4.4）：`new` 落 `status = NEW` 并记住 project / model。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session)
        snapshot = await service.new(
            _context(), "bridge-model", "DRAWING", project_id=PROJECT_ID, model_id=MODEL_ID
        )
        assert snapshot.status == DocumentStatus.NEW.value
        assert snapshot.name == "bridge-model"
        assert snapshot.project_id == PROJECT_ID
        assert snapshot.model_id == MODEL_ID
        assert service.lifecycle_order() == DOCUMENT_LIFECYCLE_ORDER_SPEC
        assert await service.store.get(snapshot.id) == snapshot


async def test_open_moves_new_to_open_and_persists_the_status(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §4.3）：`open` 把 `NEW → OPEN` 落到 `documents.status`。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session)
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        opened = await service.open(ctx, snapshot.id)
        assert opened.status == DocumentStatus.OPEN.value
        row = await _document_row(uow.session, snapshot.id)
        assert row is not None
        assert row.status == DocumentStatus.OPEN.value


async def test_save_appends_versions_with_the_artifact_and_checksum(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §4.4 / §50）：`save` 追加版本 1、2 并记录产物与摘要。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        writer = _ArtifactWriter()
        versions = build_document_version_store()
        service = _document_service(
            uow.session,
            artifacts=writer,
            versions=versions,
            tenant_of_project=_tenant_lookup(TENANT_ID),
        )
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)

        first = await service.save(ctx, snapshot.id, b"first", mime_type="text/plain")
        second = await service.save(ctx, snapshot.id, b"second")

        assert (first.version, second.version) == (1, 2)
        assert (first.artifact_id, first.checksum) == ("artifact-0", "checksum-0")
        assert (second.artifact_id, second.checksum) == ("artifact-1", "checksum-1")
        latest = await versions.latest(snapshot.id)
        assert latest is not None
        assert latest.version == 2
        ordered = await versions.list_for_document(snapshot.id)
        assert [record.version for record in ordered] == [1, 2]
        assert writer.calls[0]["tenant_id"] == TENANT_ID
        assert writer.calls[0]["project_id"] == PROJECT_ID
        assert writer.calls[0]["mime_type"] == "text/plain"
        assert writer.calls[1]["mime_type"] == "application/octet-stream"
        assert writer.calls[0]["data"] == b"first"


async def test_save_on_a_new_document_is_rejected_with_1200(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §4.3）：未 `OPEN` 的文档不能 `save`。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session, artifacts=_ArtifactWriter())
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        with pytest.raises(EngineeringValidationError) as error:
            await service.save(ctx, snapshot.id, b"payload")
        assert error.value.code == "STRUCTAI-1200"
        assert error.value.details == {"stage": "document", "reason": "document_not_open"}


async def test_save_without_an_artifact_writer_is_7000(session_factory: SessionFactory) -> None:
    """门槛 ①（`docs/02` §29）：未注入产物写入器时 `save` 明确失败（不静默丢内容）。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session)
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)
        assert service.artifacts is None
        with pytest.raises(InternalError) as error:
            await service.save(ctx, snapshot.id, b"payload")
        assert error.value.code == "STRUCTAI-7000"
        assert error.value.details == {
            "stage": "document",
            "reason": "artifact_writer_not_configured",
        }


async def test_close_moves_open_to_closed_and_a_second_close_is_illegal(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §4.3）：`close` 落 `CLOSED`；二次 `close` 是非法转移。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session)
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)
        await service.close(ctx, snapshot.id)
        row = await _document_row(uow.session, snapshot.id)
        assert row is not None
        assert row.status == DocumentStatus.CLOSED.value

        with pytest.raises(EngineeringValidationError) as error:
            await service.close(ctx, snapshot.id)
        assert error.value.code == "STRUCTAI-1200"
        assert error.value.details["reason"] == "illegal_transition"
        assert error.value.details["from"] == DocumentStatus.CLOSED.value
        assert error.value.details["to"] == DocumentStatus.CLOSED.value


async def test_save_and_save_as_never_change_the_persisted_status(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §4.3 / §57）：`SAVE` / `SAVE_AS` 是保持 `OPEN` 的操作。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        versions = build_document_version_store()
        service = _document_service(uow.session, artifacts=_ArtifactWriter(), versions=versions)
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)
        await service.save(ctx, snapshot.id, b"payload")

        renamed = await service.save_as(ctx, snapshot.id, "drawing-v2")
        assert renamed.name == "drawing-v2"
        assert renamed.status == DocumentStatus.OPEN.value
        row = await _document_row(uow.session, snapshot.id)
        assert row is not None
        assert row.status == DocumentStatus.OPEN.value
        assert row.name == "drawing-v2"

        # `SAVE_AS` 复用最新版本的产物（`docs/02` §4.4 没有独立存储概念）。
        latest = await versions.latest(snapshot.id)
        assert latest is not None
        assert latest.version == 2
        assert latest.artifact_id == "artifact-0"
        assert latest.checksum == "checksum-0"


async def test_info_reports_the_current_version_and_the_registered_type(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §41 / §50）：`info` 报最新版本且不改变生命周期。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session, artifacts=_ArtifactWriter())
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)
        await service.save(ctx, snapshot.id, b"one")
        await service.save(ctx, snapshot.id, b"two")

        info = await service.info(ctx, snapshot.id)
        assert info.document_id == snapshot.id
        assert info.name == "drawing"
        assert info.document_type == "DRAWING"
        assert info.status == DocumentStatus.OPEN.value
        assert info.current_version == 2
        row = await _document_row(uow.session, snapshot.id)
        assert row is not None
        assert row.status == DocumentStatus.OPEN.value


async def test_version_store_rejects_a_duplicate_document_version() -> None:
    """门槛 ①（`docs/02` §4.2）：`(document_id, version)` 唯一，重复即 `STRUCTAI-7000`。"""
    store = build_document_version_store()
    document_id = str(uuid4())
    first = await store.append(
        document_id=document_id, version=1, artifact_id="artifact-0", checksum="checksum-0"
    )
    assert first.version == 1
    with pytest.raises(InternalError) as error:
        await store.append(
            document_id=document_id, version=1, artifact_id="artifact-1", checksum="checksum-1"
        )
    assert error.value.code == "STRUCTAI-7000"
    assert error.value.details == {"stage": "document", "reason": "duplicate_version"}
    assert await store.latest(str(uuid4())) is None


async def test_unknown_document_and_tenant_mismatch_share_the_same_details_shape(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §48）：未知文档与跨租户**形状一致**且不泄露标识。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        versions = build_document_version_store()
        ctx = _context()
        owner = _document_service(
            uow.session, versions=versions, tenant_of_project=_tenant_lookup(TENANT_ID)
        )
        snapshot = await owner.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)

        foreign = _document_service(
            uow.session, versions=versions, tenant_of_project=_tenant_lookup(OTHER_TENANT_ID)
        )
        with pytest.raises(TenantAccessDeniedError) as mismatch:
            await foreign.open(ctx, snapshot.id)
        with pytest.raises(InternalError) as unknown:
            await owner.open(ctx, UNKNOWN_ID)

        assert mismatch.value.code == "STRUCTAI-4200"
        assert unknown.value.code == "STRUCTAI-7000"
        assert set(mismatch.value.details) == {"stage", "reason"}
        assert set(unknown.value.details) == set(mismatch.value.details)
        assert mismatch.value.details["reason"] == "tenant_mismatch"
        assert unknown.value.details["reason"] == "unknown_document"
        assert snapshot.id not in str(mismatch.value.details)
        assert UNKNOWN_ID not in str(unknown.value.details)


async def test_blank_document_name_is_rejected_with_1200(session_factory: SessionFactory) -> None:
    """门槛 ①（`docs/02` §4.4）：空白文档名即拒绝，且不落任何行。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        store = build_document_store(uow.session)
        service = _document_service(uow.session)
        ctx = _context()
        with pytest.raises(EngineeringValidationError) as error:
            await service.new(ctx, "   ", "DRAWING", project_id=PROJECT_ID)
        assert error.value.code == "STRUCTAI-1200"
        assert error.value.details == {"stage": "document", "reason": "invalid_name"}
        assert await store.list_for_project(PROJECT_ID) == ()


async def test_document_store_update_delete_and_list_for_project(
    session_factory: SessionFactory,
) -> None:
    """门槛 ①（`docs/02` §22 / §26）：仓储只写真实列；未知列返回 `None`；列表有界。"""
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        store = build_document_store(uow.session)
        service = _document_service(uow.session)
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)

        renamed = await store.update(snapshot.id, fields={"name": "renamed"})
        assert renamed is not None
        assert renamed.name == "renamed"
        assert await store.update(snapshot.id, fields={"unknown_column": 1}) is None
        assert await store.update(UNKNOWN_ID, fields={"name": "ghost"}) is None

        listed = await store.list_for_project(PROJECT_ID)
        assert [item.id for item in listed] == [snapshot.id]
        assert await store.list_for_project(UNKNOWN_ID) == ()

        assert await store.delete(snapshot.id) is True
        assert await store.delete(snapshot.id) is False
        assert await store.get(snapshot.id) is None


async def test_document_service_writes_go_through_the_documents_table(
    session_factory: SessionFactory,
    engine: AsyncEngine,
) -> None:
    """门槛 ①（`docs/07` §14.4）：服务只经 `documents` 表读写，且自己**不**提交事务。"""
    statements = _recorded_statements(engine)
    async with UnitOfWork.from_session_factory(session_factory) as uow:
        service = _document_service(uow.session, artifacts=_ArtifactWriter())
        ctx = _context()
        snapshot = await service.new(ctx, "drawing", "DRAWING", project_id=PROJECT_ID)
        await service.open(ctx, snapshot.id)
        await service.save(ctx, snapshot.id, b"payload")

    verbs = _table_verbs(statements, "documents")
    assert "INSERT" in verbs
    assert "UPDATE" in verbs
    assert [
        statement for statement in statements if statement.strip().upper().startswith("COMMIT")
    ] == []
    assert [
        statement for statement in statements if statement.strip().upper().startswith("ROLLBACK")
    ] == []


# ===== ② Model（`docs/02` §48 / §32 / §33）=====


def test_model_operations_match_the_frozen_names() -> None:
    """门槛 ②（`docs/02` §48）：读 / 写 Operation 名与规范副本逐字一致。"""
    assert tuple(QUERY_OPERATIONS) == QUERY_OPERATIONS_SPEC
    assert tuple(ASSIGN_OPERATIONS) == ASSIGN_OPERATIONS_SPEC
    service = ModelService(_ModelSource())
    assert service.operations() == QUERY_OPERATIONS_SPEC + ASSIGN_OPERATIONS_SPEC
    assert isinstance(service.source, _ModelSource)


async def test_query_methods_forward_the_exact_operation_and_parameters() -> None:
    """门槛 ②（`docs/02` §48 / §33）：六个 `query_*` 用精确 Operation 名与参数调用来源。"""
    source = _ModelSource()
    service = ModelService(source)
    context = _context()
    await service.query_node(software_instance_id=INSTANCE_ID, context=context, node_ids=[1, 2])
    await service.query_element(software_instance_id=INSTANCE_ID, context=context, element_ids=[3])
    await service.query_material(
        software_instance_id=INSTANCE_ID, context=context, material_ids=[4]
    )
    await service.query_section(software_instance_id=INSTANCE_ID, context=context, section_ids=[5])
    await service.query_boundary(
        software_instance_id=INSTANCE_ID, context=context, boundary_ids=[6]
    )
    await service.query_load(software_instance_id=INSTANCE_ID, context=context, load_ids=[7])

    assert [call["operation"] for call in source.calls] == list(QUERY_OPERATIONS_SPEC)
    assert [call["parameters"] for call in source.calls] == [
        {"node_ids": [1, 2]},
        {"element_ids": [3]},
        {"material_ids": [4]},
        {"section_ids": [5]},
        {"boundary_ids": [6]},
        {"load_ids": [7]},
    ]
    assert {call["software_instance_id"] for call in source.calls} == {INSTANCE_ID}
    assert all(call["context"] is context for call in source.calls)


async def test_query_without_ids_omits_the_key_and_keeps_filters() -> None:
    """门槛 ②（`docs/02` §48）：不限定标识时载荷里没有标识键；过滤条件原样透传。"""
    source = _ModelSource()
    service = ModelService(source)
    await service.query_node(software_instance_id=INSTANCE_ID, context=_context(), level=3)
    assert source.calls[0]["parameters"] == {"level": 3}


def test_assign_methods_build_payloads_and_never_call_the_source() -> None:
    """门槛 ②（`docs/02` §48；`docs/07` §9）：写方法只构造载荷，绝不执行。"""
    source = _ModelSource()
    service = ModelService(source)
    assignments = [
        service.assign_material(element_ids=[1, 2], material="C30"),
        service.assign_section(element_ids=[3], section="SEC-1"),
        service.assign_boundary(element_ids=[4], boundary="FIXED"),
        service.assign_load(element_ids=[5], load="LC-1", case="dead"),
    ]
    assert all(isinstance(item, ModelAssignment) for item in assignments)
    assert [item.operation for item in assignments] == list(ASSIGN_OPERATIONS_SPEC)
    assert [dict(item.parameters) for item in assignments] == [
        {"element_ids": [1, 2], "material": "C30"},
        {"element_ids": [3], "section": "SEC-1"},
        {"element_ids": [4], "boundary": "FIXED"},
        {"element_ids": [5], "load": "LC-1", "case": "dead"},
    ]
    assert source.calls == []


# ===== ③ Result（`docs/02` §90 / §31 / §35 / §89 / §49）=====


def test_default_result_limit_is_the_frozen_page_limit() -> None:
    """门槛 ③（`docs/02` §31 / §35）：默认页大小取自冻结值对象。"""
    assert DEFAULT_RESULT_LIMIT == DEFAULT_PAGE_LIMIT


def test_paginate_matches_the_frozen_docs_02_90_envelope() -> None:
    """门槛 ③（`docs/02` §90）：固定向量的信封逐字一致（游标字面量独立算出）。"""
    rows = [{"id": index} for index in range(5)]
    first = paginate(rows, limit=2)
    assert set(first) == set(PAGINATION_ENVELOPE_KEYS_SPEC)
    assert first[DATA_KEY] == [{"id": 0}, {"id": 1}]
    assert set(first[PAGINATION_KEY]) == set(PAGINATION_KEYS_SPEC)
    assert first[PAGINATION_KEY] == {HAS_MORE_KEY: True, NEXT_CURSOR_KEY: CURSOR_FOR_2_SPEC}

    second = paginate(rows, limit=2, cursor=CURSOR_FOR_2_SPEC)
    assert second[DATA_KEY] == [{"id": 2}, {"id": 3}]
    assert second[PAGINATION_KEY] == {HAS_MORE_KEY: True, NEXT_CURSOR_KEY: CURSOR_FOR_4_SPEC}

    third = paginate(rows, limit=2, cursor=CURSOR_FOR_4_SPEC)
    assert third[DATA_KEY] == [{"id": 4}]
    assert third[PAGINATION_KEY] == {HAS_MORE_KEY: False, NEXT_CURSOR_KEY: None}


def test_cursor_round_trip_and_decoding_none() -> None:
    """门槛 ③（`docs/02` §35）：游标是不透明 base64 偏移量，往返一致。"""
    assert encode_cursor(0) == base64.urlsafe_b64encode(b"0").decode("ascii")
    assert decode_cursor(None) == 0
    for offset in (0, 1, 7, 50, 4096):
        assert decode_cursor(encode_cursor(offset)) == offset


def test_invalid_cursor_is_rejected_with_1200() -> None:
    """门槛 ③（`docs/07` §14.4）：非法 / 外来游标必须拒绝，绝不静默回退到 0。"""
    foreign = [
        "not-a-cursor!",
        base64.urlsafe_b64encode(b"abc").decode("ascii"),
        base64.urlsafe_b64encode(b"-1").decode("ascii"),
        "",
    ]
    for cursor in foreign:
        with pytest.raises(EngineeringValidationError) as error:
            decode_cursor(cursor)
        assert error.value.code == "STRUCTAI-1200"
        assert error.value.details == {"stage": "result", "reason": "invalid_cursor"}
    with pytest.raises(EngineeringValidationError):
        paginate([1, 2], limit=1, cursor="!!")


def test_paginate_rejects_a_non_positive_limit() -> None:
    """门槛 ③（`docs/02` §31）：`limit <= 0` 即拒绝（装配 / 调用错误）。"""
    for limit in (0, -1):
        with pytest.raises(EngineeringValidationError) as error:
            paginate([1], limit=limit)
        assert error.value.code == "STRUCTAI-1200"
        assert error.value.details == {"stage": "result", "reason": "invalid_limit"}
    with pytest.raises(EngineeringValidationError):
        ResultService(default_limit=0)


def test_paginate_is_never_unbounded() -> None:
    """门槛 ③（`docs/07` §14.4）：不传 `limit` 也**永远**有界。"""
    rows = list(range(500))
    page = paginate(rows)
    assert len(page[DATA_KEY]) == DEFAULT_RESULT_LIMIT
    assert page[PAGINATION_KEY][HAS_MORE_KEY] is True
    assert page[PAGINATION_KEY][NEXT_CURSOR_KEY] == encode_cursor(DEFAULT_RESULT_LIMIT)


def test_normalize_accepts_canonical_sequence_and_bare_mapping() -> None:
    """门槛 ③（`docs/02` §33 / §89）：三种输入形态都归一到规范信封。"""
    service = ResultService()
    canonical = service.normalize(
        "OP", {"data": [1, 2], "pagination": {"has_more": True, "next_cursor": "Mg=="}}
    )
    assert canonical.operation == "OP"
    assert canonical.data == [1, 2]
    assert canonical.pagination == {"has_more": True, "next_cursor": "Mg=="}

    sequence = service.normalize("OP", [1, 2])
    assert sequence.data == [1, 2]
    assert sequence.pagination is None

    single = service.normalize("OP", {"id": 1})
    assert single.data == {"id": 1}
    assert single.pagination is None


def test_normalize_drops_a_malformed_pagination() -> None:
    """门槛 ③（`docs/02` §90）：形状不完整的分页对象一律丢弃，不补齐。"""
    service = ResultService()
    assert (
        service.normalize("OP", {"data": [1], "pagination": {"has_more": True}}).pagination is None
    )
    assert service.normalize("OP", {"data": [1], "pagination": "nope"}).pagination is None
    assert (
        service.normalize("OP", {"data": [1], "pagination": {"next_cursor": "Mg=="}}).pagination
        is None
    )


def test_link_artifacts_deduplicates_and_preserves_order() -> None:
    """门槛 ③（`docs/02` §49）：产物关联去重且保序，且返回新对象。"""
    service = ResultService()
    original = CanonicalResult(operation="OP", data=[], artifacts=("a", "b"))
    linked = service.link_artifacts(original, ["b", "c", "a", "d", "c"])
    assert linked.artifacts == ("a", "b", "c", "d")
    assert original.artifacts == ("a", "b")


def test_paginated_reattaches_artifacts_under_the_artifacts_key() -> None:
    """门槛 ③（`docs/02` §49 / §90）：分页信封 + 产物载体，且映射按单行处理。"""
    service = ResultService()
    result = CanonicalResult(operation="OP", data=[1, 2, 3], artifacts=("a", "b"))
    page = service.paginated(result, limit=2)
    assert page[DATA_KEY] == [1, 2]
    assert page[PAGINATION_KEY] == {HAS_MORE_KEY: True, NEXT_CURSOR_KEY: CURSOR_FOR_2_SPEC}
    assert page["artifacts"] == ["a", "b"]

    single = service.paginated(CanonicalResult(operation="OP", data={"id": 1}), limit=5)
    assert single[DATA_KEY] == [{"id": 1}]
    assert single[PAGINATION_KEY] == {HAS_MORE_KEY: False, NEXT_CURSOR_KEY: None}


def test_envelope_adds_pagination_only_when_given() -> None:
    """门槛 ③（`docs/02` §90）：`envelope` 不给分页时**不**伪造 `pagination` 键。"""
    assert envelope([1]) == {DATA_KEY: [1]}
    assert envelope([1], pagination={HAS_MORE_KEY: False, NEXT_CURSOR_KEY: None}) == {
        DATA_KEY: [1],
        PAGINATION_KEY: {HAS_MORE_KEY: False, NEXT_CURSOR_KEY: None},
    }


# ===== ④ AdapterResolver（`docs/02` §87 / §13 / §56 / §48；`docs/07` §16 R35）=====


async def test_resolve_happy_path_returns_vendor_product_version_and_adapter() -> None:
    """门槛 ④（`docs/02` §87）：实例 → 厂商 / 产品 / 版本 → Adapter。"""
    adapter = _Adapter(manifest=_Manifest(vendor="StructAI", product="MockEngineering"))
    source = _AdapterSource(
        adapters={INSTANCE_ID: adapter}, keys=(("StructAI", "MockEngineering"),)
    )
    resolver = AdapterResolver(source, instances=_InstanceSource(_instance_record()))

    resolution = await resolver.resolve(software_instance_id=INSTANCE_ID)

    assert resolution.software_instance_id == INSTANCE_ID
    assert resolution.vendor == "StructAI"
    assert resolution.product == "MockEngineering"
    assert resolution.version == "2026"
    assert resolution.adapter is adapter
    assert resolver.source is source
    assert isinstance(resolver.instances, _InstanceSource)
    assert resolver.capabilities is None


async def test_unknown_instance_is_3000_without_leaking_the_identifier() -> None:
    """门槛 ④（`docs/02` §48；R35）：未知实例落 `STRUCTAI-3000` 且不泄露存在性。"""
    resolver = AdapterResolver(_AdapterSource(), instances=_InstanceSource(None))
    with pytest.raises(CapabilityError) as error:
        await resolver.resolve(software_instance_id=INSTANCE_ID)
    assert error.value.code == "STRUCTAI-3000"
    assert error.value.details == {"stage": "adapter_resolver", "reason": "adapter_unavailable"}
    assert INSTANCE_ID not in str(error.value.details)


async def test_unbound_adapter_and_missing_instance_source_share_one_error() -> None:
    """门槛 ④（`docs/02` §56）：未绑定 Adapter / 无实例来源都落同一个错误。"""
    unbound = AdapterResolver(_AdapterSource(), instances=_InstanceSource(_instance_record()))
    with pytest.raises(CapabilityError) as error:
        await unbound.resolve(software_instance_id=INSTANCE_ID)
    assert error.value.code == "STRUCTAI-3000"
    assert error.value.details == {"stage": "adapter_resolver", "reason": "adapter_unavailable"}
    assert INSTANCE_ID not in str(error.value.details)

    without_source = AdapterResolver(_AdapterSource())
    with pytest.raises(CapabilityError) as missing:
        await without_source.resolve(software_instance_id=INSTANCE_ID)
    assert missing.value.details == error.value.details
    assert INSTANCE_ID not in str(missing.value.details)


async def test_vendor_product_for_reads_the_bound_manifest_and_never_raises() -> None:
    """门槛 ④（`docs/02` §87 第三段）：已绑定读 Manifest 键；未绑定返回 `None` 且不抛。"""
    adapter = _Adapter(manifest=_Manifest(vendor="StructAI", product="MockEngineering"))
    bound = AdapterResolver(_AdapterSource(adapters={INSTANCE_ID: adapter}))
    assert bound.vendor_product_for(INSTANCE_ID) == ("StructAI", "MockEngineering")
    assert bound.vendor_product_for(UNKNOWN_ID) is None

    raising = AdapterResolver(_AdapterSource(raise_on_lookup=True))
    assert raising.vendor_product_for(INSTANCE_ID) is None


def test_registered_forwards_the_source_keys() -> None:
    """门槛 ④（`docs/02` §14 / §56）：`registered()` 原样转发来源的注册键。"""
    keys = (("StructAI", "MockEngineering"), ("StructAI", "MockAnalysis"))
    resolver = AdapterResolver(_AdapterSource(keys=keys))
    assert resolver.registered() == keys


async def test_resolve_requires_every_capability_when_an_operation_is_given() -> None:
    """门槛 ④（`docs/02` §46 / §87 第四段）：给出 `operation` 时逐个 `require()`。"""
    adapter = _Adapter(manifest=_Manifest(vendor="StructAI", product="MockEngineering"))
    resolver = AdapterResolver(
        _AdapterSource(adapters={INSTANCE_ID: adapter}),
        instances=_InstanceSource(_instance_record()),
        capabilities=CapabilityResolver(
            _CapabilityRegistry(["MODEL.NODE.READ"]), _InstanceSource(_instance_record())
        ),
    )
    known = await resolver.resolve(
        software_instance_id=INSTANCE_ID,
        operation=_operation("MODEL.NODE.QUERY", capabilities=["MODEL.NODE.READ"]),
    )
    assert known.adapter is adapter

    with pytest.raises(CapabilityError) as error:
        await resolver.resolve(
            software_instance_id=INSTANCE_ID,
            operation=_operation("MODEL.NODE.WRITE", capabilities=["MODEL.NODE.WRITE"]),
        )
    assert error.value.code == "STRUCTAI-3000"


# ===== ⑤ 红线（`docs/07` §14.1 / §14.2 / §14.3 / §14.4 / §11）=====


def test_owned_modules_exist_and_match_the_frozen_file_list() -> None:
    """门槛 ⑤：本批只新增约定的 5 个源码模块（+ 本测试文件）。"""
    for relative in OWNED_MODULES:
        assert _relative_path(relative).is_file(), relative
    assert Path(__file__).resolve() == _relative_path("tests/test_services_p30_p35.py")


def test_commit_and_rollback_only_in_unit_of_work() -> None:
    """门槛 ⑤（`docs/07` §14.4）：`commit()` / `rollback()` 调用点只在 `unit_of_work.py`。"""
    committers = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in APP_DIR.rglob("*.py")
        if _commit_or_rollback_calls(path)
    )
    assert committers == ["app/infrastructure/database/unit_of_work.py"]
    for relative in OWNED_MODULES:
        assert _commit_or_rollback_calls(_relative_path(relative)) == [], relative


def test_no_vendor_names_in_app() -> None:
    """门槛 ⑤（`docs/07` §14.2）：`app/` 内厂商名 0 处（大小写不敏感）。"""
    hits = [
        f"{path.relative_to(REPO_ROOT).as_posix()}:{vendor}"
        for path in sorted(APP_DIR.rglob("*.py"))
        if "midas" not in path.parts  # docs/07 §7.1：厂商专属代码的唯一豁免区
        for vendor in VENDOR_NAMES
        if vendor.lower() in path.read_text(encoding="utf-8").lower()
    ]
    assert hits == []


def test_twenty_error_codes_are_not_extended() -> None:
    """门槛 ⑤（`docs/07` §11）：`app/` 内的 `STRUCTAI-xxxx` 字面量恰好是那 20 个码。"""
    declared: set[str] = set()
    for path in sorted(APP_DIR.rglob("*.py")):
        declared.update(re.findall(r"STRUCTAI-\d{4}", path.read_text(encoding="utf-8")))
    assert declared == set(ERROR_CODES_SPEC)
    assert len(ERROR_CODES_SPEC) == 20
    for error in (
        CapabilityError,
        EngineeringValidationError,
        InternalError,
        TenantAccessDeniedError,
    ):
        assert error.code in ERROR_CODES_SPEC


def test_application_layer_does_not_depend_on_infrastructure() -> None:
    """门槛 ⑤（`docs/07` §14.1）：Application 层不得依赖 `app.infrastructure`。"""
    offenders = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (APP_DIR / "application").rglob("*.py")
        if [name for name in _imported_modules(path) if name.startswith("app.infrastructure")]
    )
    assert offenders == []
    for relative in OWNED_MODULES:
        if "/application/" not in relative:
            continue
        modules = _imported_modules(_relative_path(relative))
        assert [name for name in modules if name.split(".")[0] in FORBIDDEN_FRAMEWORK_ROOTS] == []


def test_owned_modules_never_record_secrets() -> None:
    """门槛 ⑤（`docs/07` §14.3）：新模块**绝不**记录 secret；敏感词只出现在否定式说明里。"""
    for relative in OWNED_MODULES:
        text = _relative_path(relative).read_text(encoding="utf-8").lower()
        for marker in SECRET_MARKERS:
            if marker not in text:
                continue
            assert "不得" in text or "绝不" in text or "没有" in text, (relative, marker)


def test_documents_table_matches_the_frozen_column_set() -> None:
    """门槛 ⑤（`docs/07` §4.3 #15）：`documents` 的列集合未被改动。"""
    assert DocumentORM.__tablename__ == "documents"
    columns = tuple(DocumentORM.__table__.columns.keys())
    assert len(columns) == len(DOCUMENTS_TABLE_COLUMNS_SPEC)
    assert set(columns) == set(DOCUMENTS_TABLE_COLUMNS_SPEC)
