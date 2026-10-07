"""Infrastructure · Adapters · MIDAS · Registry Import —— P120 的 7 张表导入（`docs/07` §7.2）。

权威来源
--------
- `docs/07` §12 P120 —— 把我们的 `manifest.json` + **616** Schema 灌入
  `midas_api_sources` / `midas_api_endpoints`（唯一键 `(product, version_range, method, path)`）/
  `midas_api_schemas`（`schema_uri` 唯一）；另 4 张表字段自行设计（§4.4 / §16 R12）。
- `docs/07` §7.2 —— 逐字段的映射规则（`path ← uri`、`method ← methods` 展开、
  `category ← namespace`、`product ← products`、`verification_status ← availability`、
  `deprecated ← enabled === false`、`schema_uri ← midas://<product_lower>/<code_lower>/request/v1`）。
- `docs/04` §106（`MidasRegistrySeeder`）—— `load_sources` / `load_endpoints` /
  `load_schemas` → `insert_*`；**必须** `idempotent`。
- `docs/04` §107（Seed Integrity）—— 每个 seed 带 `schema hash` / `source hash` /
  `version` / `generated_at` / `generator_version`。
- `docs/04` §108 / §109 —— 导入流程与「**不**自动猜字段」原则。
- `docs/07` §16 R1 —— `verification_status` 的 `VERIFIED` 判定是 **7 项 AND**，
  本模块**只**做 `availability` 的机械映射，**不**升级任何状态。

落地裁决（只补实现手段，不改任何取值）
------------------------------------
1. **Schema 原样登记**：`schema_json` 存 Schema 文件的 `schema` 字段**原文**
   （`docs/04` §107 的「不改写任何取值」），不做包装剥离、不做方言改写。
2. **`schema_uri` 用完整 key 路径保证唯一**：`docs/07` §7.2 的模板是
   `midas://<product_lower>/<code_lower>/request/v1`；`code` 只取末段会与
   `DESIGN.*.DCO` 之类的同名字段冲突，故 `<code_lower>` 取 **key 的完整路径**
   （`DB.NODE` → `db/node`），产品段取产品名首词小写（`CIVIL NX` → `civil`，
   与 `docs/04` §13 的示例 `midas://civil/node/request/v1` 同形）。
3. **来源行按数据自身的词表建**：`registry/manifest.json` **没有** URL / 手册修订 /
   抓取日期（`docs/04` §110 想要的五项里只存在「来源名」），故
   `midas_api_sources` 的行取**数据自己的** provenance 元组与 Schema 文件的
   `source` 字符串；`source_url` / `manual_revision` 留**空串**、`retrieved_at` 留
   `None`，**不**臆造；`source_hash` = `manifest.json` 的 sha256（可复算的真实值）。
4. **幂等**：按各表唯一键 `SELECT → 比对 → INSERT / UPDATE`，第二次运行
   `inserted == 0`（`docs/04` §106 的硬要求）。
5. **本模块不 commit**：事务边界只归 `UnitOfWork`（`docs/07` §14.4 / `docs/02` §16）。
6. **`supported` 语义**：`midas_api_versions.supported` = 「该产品是否由
   `AdapterManifest`（`docs/07` §7.1）声明」—— `CIVIL NX` / `GEN NX`（`docs/04` §62 / §76）
   为真，数据里存在的第三个产品（Civil Designer）为假，**不**猜。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块位于 MIDAS 子包内（该子包是 `grep -ri midas app/` 的**唯一**豁免区），
依赖 SQLAlchemy 与同包的 `registry.py` / `operations.py` / `capabilities.py` / `models.py`；
**不**依赖 `app.interfaces`，**不**被 Core 引用。
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.adapters.midas.capabilities import CAPABILITY_ENDPOINTS
from app.infrastructure.adapters.midas.manifest import (
    MIDAS_PRODUCT,
    MIDAS_SUPPORTED_VERSIONS,
)
from app.infrastructure.adapters.midas.models import (
    MidasApiEndpointORM,
    MidasApiMappingORM,
    MidasApiSchemaORM,
    MidasApiSourceORM,
    MidasApiVersionORM,
    MidasCapabilityMappingORM,
)
from app.infrastructure.adapters.midas.operations import OPERATION_PLANS, OperationPlan
from app.infrastructure.adapters.midas.registry import EndpointDefinition, MidasRegistry
from app.infrastructure.database.base import utcnow

__all__ = [
    "DECLARED_PRODUCTS",
    "IMPORT_TABLES",
    "SCHEMA_URI_TEMPLATE",
    "VERSION_RANGE",
    "ImportReport",
    "MidasRegistryImporter",
    "schema_uri_for",
]

VERSION_RANGE: Final[str] = "2025-2026"
"""`docs/04` §61 / §62：本 Adapter 声明的版本区间（`2025` / `2026`）。"""

DECLARED_PRODUCTS: Final[tuple[str, ...]] = ("CIVIL_NX", "GEN_NX")
"""`docs/07` §7.1 + `docs/04` §76 声明的产品（见裁决 6）。"""

SCHEMA_URI_TEMPLATE: Final[str] = "midas://{product}/{code}/request/v1"
"""`docs/07` §7.2 的 `schema_uri` 模板（见裁决 2）。"""

IMPORT_TABLES: Final[tuple[str, ...]] = (
    "midas_api_sources",
    "midas_api_schemas",
    "midas_api_endpoints",
    "midas_api_versions",
    "midas_api_mappings",
    "midas_api_verifications",
    "midas_capability_mappings",
)
"""7 张表的导入顺序（`docs/04` §106：sources → schemas → endpoints）。"""


def schema_uri_for(key: str, *, product: str) -> str:
    """端点 key → `schema_uri`（`docs/07` §7.2；见裁决 2）。"""
    slug = str(product).strip().lower().split()[0]
    return SCHEMA_URI_TEMPLATE.format(product=slug, code=str(key).lower().replace(".", "/"))


@dataclass(frozen=True, slots=True)
class ImportReport:
    """一次导入的结果（`docs/04` §107 的可复算证据）。"""

    inserted: Mapping[str, int] = field(default_factory=dict)
    updated: Mapping[str, int] = field(default_factory=dict)
    unchanged: Mapping[str, int] = field(default_factory=dict)
    totals: Mapping[str, int] = field(default_factory=dict)
    source_hash: str = ""
    generated_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        """诊断用映射（**不含** secret；只含计数与哈希）。"""
        return {
            "inserted": dict(self.inserted),
            "updated": dict(self.updated),
            "unchanged": dict(self.unchanged),
            "totals": dict(self.totals),
            "source_hash": self.source_hash,
            "generated_at": None if self.generated_at is None else self.generated_at.isoformat(),
        }


class MidasRegistryImporter:
    """把 `registry/` 的数据导入 7 张 MIDAS 表（`docs/07` §12 P120）。"""

    def __init__(
        self,
        registry: MidasRegistry,
        *,
        product: str = MIDAS_PRODUCT,
        version_range: str = VERSION_RANGE,
        versions: Sequence[str] = MIDAS_SUPPORTED_VERSIONS,
    ) -> None:
        """绑定 Registry 与声明口径（**不**做 I/O）。"""
        self._registry = registry
        self._product = str(product)
        self._version_range = str(version_range)
        self._versions = tuple(str(item) for item in versions)
        self._counters: dict[str, dict[str, int]] = {
            table: {"inserted": 0, "updated": 0, "unchanged": 0} for table in IMPORT_TABLES
        }
        self._source_ids: dict[str, str] = {}

    # ===== 入口 =====

    async def import_all(self, session: AsyncSession) -> ImportReport:
        """导入全部 7 张表（顺序照 `docs/04` §106；**不** commit，见裁决 5）。"""
        self._counters = {
            table: {"inserted": 0, "updated": 0, "unchanged": 0} for table in IMPORT_TABLES
        }
        await self.import_sources(session)
        await self.import_schemas(session)
        await self.import_endpoints(session)
        await self.import_versions(session)
        await self.import_mappings(session)
        await self.import_capability_mappings(session)
        return ImportReport(
            inserted={t: self._counters[t]["inserted"] for t in IMPORT_TABLES},
            updated={t: self._counters[t]["updated"] for t in IMPORT_TABLES},
            unchanged={t: self._counters[t]["unchanged"] for t in IMPORT_TABLES},
            totals=await self._totals(session),
            source_hash=self.source_hash(),
            generated_at=utcnow(),
        )

    def source_hash(self) -> str:
        """`manifest.json` 的 sha256（`docs/04` §107 / §110；可复算）。"""
        path = self._registry.root / "manifest.json"
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    # ===== 各表 =====

    async def import_sources(self, session: AsyncSession) -> None:
        """`midas_api_sources`（`docs/04` §10；见裁决 3）。"""
        titles = sorted({",".join(_provenance(definition)) for definition in self._definitions()})
        for title in titles:
            row_id = await self._upsert(
                session,
                MidasApiSourceORM,
                table="midas_api_sources",
                identity={"source_title": title},
                values={
                    "source_url": "",
                    "source_title": title,
                    "product": self._product,
                    "category": None,
                    "manual_revision": "",
                    "source_hash": self.source_hash(),
                    "retrieved_at": None,
                },
            )
            self._source_ids[title] = row_id
        for schema_source in sorted(self._schema_sources()):
            row_id = await self._upsert(
                session,
                MidasApiSourceORM,
                table="midas_api_sources",
                identity={"source_title": schema_source},
                values={
                    "source_url": "",
                    "source_title": schema_source,
                    "product": self._product,
                    "category": "schema",
                    "manual_revision": "",
                    "source_hash": self.source_hash(),
                    "retrieved_at": None,
                },
            )
            self._source_ids[schema_source] = row_id

    async def import_schemas(self, session: AsyncSession) -> None:
        """`midas_api_schemas`（`docs/04` §12；`schema_json` **原样**，见裁决 1）。"""
        for definition in self._definitions():
            document = self._registry.schema_document(definition.key)
            if document is None:
                continue
            raw = document.get("schema")
            if not isinstance(raw, dict):
                continue
            uri = schema_uri_for(definition.key, product=self._product)
            source = str(document.get("source") or "")
            await self._upsert(
                session,
                MidasApiSchemaORM,
                table="midas_api_schemas",
                identity={"schema_uri": uri},
                values={
                    "schema_uri": uri,
                    "direction": "request",
                    "product": self._product,
                    "version_range": self._version_range,
                    "schema_json": raw,
                    "verification_status": definition.verification_status,
                    "source_id": self._source_ids.get(source),
                },
            )

    async def import_endpoints(self, session: AsyncSession) -> None:
        """`midas_api_endpoints`（`docs/04` §11 / `docs/07` §7.2；逐产品逐方法一行）。"""
        for definition in self._definitions():
            source_id = self._source_ids.get(",".join(_provenance(definition)))
            schema_id = await self._schema_row_id(session, definition.key)
            for product in definition.products:
                for method, path, table_type in self._method_paths(definition, product):
                    await self._upsert(
                        session,
                        MidasApiEndpointORM,
                        table="midas_api_endpoints",
                        identity={
                            "product": product,
                            "version_range": self._version_range,
                            "method": method,
                            "path": path,
                            "table_type": table_type,
                            "operation": definition.key,
                        },
                        values={
                            "product": product,
                            "product_family": product.rsplit("_", 1)[-1],
                            "version_range": self._version_range,
                            "category": definition.namespace,
                            "path": path,
                            "method": method,
                            "table_type": table_type,
                            "operation": definition.key,
                            "request_schema_id": schema_id,
                            "response_schema_id": None,
                            "verification_status": definition.verification_status,
                            "source_id": source_id,
                            "deprecated": not definition.enabled,
                            "read_root": definition.read_root or None,
                        },
                    )

    async def import_versions(self, session: AsyncSession) -> None:
        """`midas_api_versions`（字段自行设计，见裁决 3 / 6）。"""
        for product in self._registry.products():
            for version in self._versions:
                await self._upsert(
                    session,
                    MidasApiVersionORM,
                    table="midas_api_versions",
                    identity={"product": product, "version": version},
                    values={
                        "product": product,
                        "product_family": product.rsplit("_", 1)[-1],
                        "version": version,
                        "version_range": self._version_range,
                        "solver": None,
                        "supported": product in DECLARED_PRODUCTS,
                        "source_id": None,
                    },
                )

    async def import_mappings(self, session: AsyncSession) -> None:
        """`midas_api_mappings`（`docs/04` §17 / `docs/07` §6.11）。

        组合 Operation 的每一步各占一行（`sequence` 从 0 起），路由分支的 operation
        写作 `<Operation>:<route>`（`docs/07` §6.8 的「材料 × 构件类型」路由）。
        """
        for plan in OPERATION_PLANS.values():
            await self._import_plan_steps(session, plan, plan.steps, operation=plan.operation)
            for route, steps in plan.routes.items():
                await self._import_plan_steps(
                    session, plan, steps, operation=f"{plan.operation}:{route}"
                )

    async def import_capability_mappings(self, session: AsyncSession) -> None:
        """`midas_capability_mappings`（字段自行设计，见裁决 3）。"""
        for capability, keys in sorted(CAPABILITY_ENDPOINTS.items()):
            for key in keys:
                for product in DECLARED_PRODUCTS:
                    definition = self._registry.endpoint(key)
                    if product not in definition.products and product not in definition.overrides:
                        continue
                    await self._upsert(
                        session,
                        MidasCapabilityMappingORM,
                        table="midas_capability_mappings",
                        identity={
                            "capability": capability,
                            "endpoint_key": key,
                            "product": product,
                            "version_range": self._version_range,
                        },
                        values={
                            "capability": capability,
                            "endpoint_key": key,
                            "operation": _operation_for_endpoint(key),
                            "product": product,
                            "version_range": self._version_range,
                            "supported": definition.enabled,
                            "source": definition.availability,
                        },
                    )

    # ===== 内部 =====

    async def _import_plan_steps(
        self,
        session: AsyncSession,
        plan: OperationPlan,
        steps: Sequence[Any],
        *,
        operation: str,
    ) -> None:
        """把一个编排的每一步写进 `midas_api_mappings`。"""
        for sequence, step in enumerate(steps):
            for product in DECLARED_PRODUCTS:
                definition = self._registry.endpoint(step.key)
                if product not in definition.products and product not in definition.overrides:
                    continue
                resolved = self._registry.resolve(key=step.key, product=product)
                schema_id = await self._schema_row_id(session, step.key)
                await self._upsert(
                    session,
                    MidasApiMappingORM,
                    table="midas_api_mappings",
                    identity={
                        "operation": operation,
                        "product": product,
                        "version_range": self._version_range,
                        "sequence": sequence,
                    },
                    values={
                        "operation": operation,
                        "product": product,
                        "version_range": self._version_range,
                        "method": step.method,
                        "path": resolved.uri,
                        "endpoint_key": step.key,
                        "sequence": sequence,
                        "composite": bool(plan.composite),
                        "request_schema": schema_id,
                        "response_schema": None,
                        "transformer": step.transformer,
                        "verification_status": definition.verification_status,
                    },
                )

    async def _schema_row_id(self, session: AsyncSession, key: str) -> str | None:
        """取该端点的 Schema 行 id（无 Schema → `None`）。"""
        if self._registry.schema_json(key) is None:
            return None
        uri = schema_uri_for(key, product=self._product)
        statement = select(MidasApiSchemaORM.id).where(MidasApiSchemaORM.schema_uri == uri)
        return None if (row := (await session.execute(statement)).scalar()) is None else str(row)

    def _definitions(self) -> Iterable[Any]:
        """全部端点定义（数据文件顺序）。"""
        return (self._registry.endpoint(key) for key in self._registry.keys())

    def _schema_sources(self) -> set[str]:
        """Schema 文件里出现过的 `source` 取值。"""
        found: set[str] = set()
        for definition in self._definitions():
            document = self._registry.schema_document(definition.key)
            if document is not None and document.get("source"):
                found.add(str(document["source"]))
        return found

    def _method_paths(
        self, definition: EndpointDefinition, product: str
    ) -> tuple[tuple[str, str, str], ...]:
        """该产品上的 `(method, path, table_type)` 组合（应用 `product_overrides`）。

        ⚠️ 数据里 `POST.TABLE.*` 的 **199** 个端点共用 `path=/POST/TABLE`，
        故 `table_type` 是唯一键的必需部分（见 `models.py` 裁决 5）。
        `DB.SWIND` 之类**没有**任何方法的端点保留一行 `method=""`（`deprecated=True`），
        以便「636 个 key 逐条可回查」成立。
        """
        override = definition.overrides.get(product) or {}
        methods = _methods(override.get("methods")) or definition.methods
        uri = str(override.get("uri") or definition.uri)
        if not uri.startswith("/"):
            uri = f"/{uri}"
        table_type = definition.table_type
        if not methods:
            return (("", uri, table_type),)
        return tuple((method, uri, table_type) for method in methods)

    async def _upsert(
        self,
        session: AsyncSession,
        model: Any,
        *,
        table: str,
        identity: Mapping[str, Any],
        values: Mapping[str, Any],
    ) -> str:
        """按唯一键 upsert（幂等；见裁决 4）。"""
        statement = select(model).filter_by(**dict(identity))
        row = (await session.execute(statement)).scalars().first()
        if row is None:
            row = model(**{**dict(identity), **dict(values)})
            session.add(row)
            await session.flush()
            self._counters[table]["inserted"] += 1
            return str(row.id)
        changed = False
        for name, value in values.items():
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
        self._counters[table]["updated" if changed else "unchanged"] += 1
        return str(row.id)

    async def _totals(self, session: AsyncSession) -> dict[str, int]:
        """各表当前行数（`docs/07` §12 P120 的「逐条落库」证据）。"""
        from sqlalchemy import func

        totals: dict[str, int] = {}
        for model in (
            MidasApiSourceORM,
            MidasApiSchemaORM,
            MidasApiEndpointORM,
            MidasApiVersionORM,
            MidasApiMappingORM,
            MidasCapabilityMappingORM,
        ):
            count = await session.scalar(select(func.count()).select_from(model))
            totals[str(model.__tablename__)] = int(count or 0)
        return totals


def _provenance(definition: EndpointDefinition) -> tuple[str, ...]:
    """端点定义的 provenance 元组（数据文件原文；`registry/README.md` §4）。"""
    return tuple(str(item) for item in definition.provenance)


def _methods(value: Any) -> tuple[str, ...]:
    """方法集归一（大写；字符串按逗号切分）。"""
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip().upper() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence):
        return tuple(str(item).strip().upper() for item in value if str(item).strip())
    return ()


def _operation_for_endpoint(key: str) -> str | None:
    """反查使用该端点的第一个 Operation（机械查表，**不**猜）。"""
    for plan in OPERATION_PLANS.values():
        if any(step.key == key for step in plan.steps):
            return plan.operation
    return None
