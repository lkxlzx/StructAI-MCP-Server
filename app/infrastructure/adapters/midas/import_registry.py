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

7. **response 方向 Schema 也落库**（P137a，`docs/07` §16 R87 的收口）：数据侧
   `registry/schema/**` 的**同一份**文件里既有请求方向 `schema`（原样登记），也有
   `response` 块（`registry/README.md` §2.2）。本模块**两个方向都导入**：
   `midas_api_schemas` 按 `schema_uri` 各占一行（`direction` = `request` /
   `response`，响应方向的模板 = `midas://<product>/<code>/response/v1`），并**回填**
   `midas_api_endpoints.response_schema_id` 与 `midas_api_mappings.response_schema`
   （与 `request_schema*` 同口径：存的是 **Schema 行的 id**）。
   未声明 `response` 块 / 取不到本体 → 如实留 `None` / 不建行（**不**臆造）。
8. **7 项 AND 只做如实报告**（P137b，`docs/07` §16 R78 / R87）：`ImportReport.seven_and`
   汇总**同一判定点**（`live.py` 的 `registry_evidence` / `seven_and_verdict`）在每个 key
   上的结论（逐项满足 / 缺项 / `VERIFIED` vs `PARTIAL` 计数）。端点行的
   `verification_status` **仍**只由 `availability` 机械映射（`docs/07` §7.2），**绝不**因
   CI 层记录（L1–L3）或本报告升级任何状态；L4 / L5 结论**只**经
   `seven_and_report(..., live_outcomes=...)` 显式传入才参与判定。

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
from app.infrastructure.adapters.midas.live import (
    SEVEN_AND_ITEMS,
    STATUS_PARTIAL,
    STATUS_VERIFIED,
    registry_evidence,
    seven_and_verdict,
)
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
    "REQUEST_DIRECTION",
    "RESPONSE_DIRECTION",
    "RESPONSE_SCHEMA_URI_TEMPLATE",
    "SCHEMA_URI_TEMPLATE",
    "VERSION_RANGE",
    "ImportReport",
    "MidasRegistryImporter",
    "SevenAndReport",
    "schema_uri_for",
    "seven_and_report",
]

VERSION_RANGE: Final[str] = "2025-2026"
"""`docs/04` §61 / §62：本 Adapter 声明的版本区间（`2025` / `2026`）。"""

DECLARED_PRODUCTS: Final[tuple[str, ...]] = ("CIVIL_NX", "GEN_NX")
"""`docs/07` §7.1 + `docs/04` §76 声明的产品（见裁决 6）。"""

SCHEMA_URI_TEMPLATE: Final[str] = "midas://{product}/{code}/request/v1"
"""`docs/07` §7.2 的 `schema_uri` 模板（见裁决 2）。"""

REQUEST_DIRECTION: Final[str] = "request"
RESPONSE_DIRECTION: Final[str] = "response"
"""`midas_api_schemas.direction` 的两个取值（`docs/04` §12；见裁决 7）。"""

RESPONSE_SCHEMA_URI_TEMPLATE: Final[str] = "midas://{product}/{code}/response/v1"
"""**response 方向**的 `schema_uri` 模板（P137a；`docs/07` §7.2 / §16 R87）。"""

_SCHEMA_URI_TEMPLATES: Final[dict[str, str]] = {
    REQUEST_DIRECTION: SCHEMA_URI_TEMPLATE,
    RESPONSE_DIRECTION: RESPONSE_SCHEMA_URI_TEMPLATE,
}
"""方向 → `schema_uri` 模板（`schema_uri_for` 的**唯一**取值点，见裁决 7）。"""

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


def schema_uri_for(key: str, *, product: str, direction: str = REQUEST_DIRECTION) -> str:
    """端点 key → `schema_uri`（`docs/07` §7.2；见裁决 2 / 7）。

    Args:
        key: Registry key（`DB.NODE` → `db/node`）。
        product: Manifest 产品名（`CIVIL NX` → 产品段 `civil`）。
        direction: `request`（缺省，§7.2 原文）或 `response`（P137a）。

    Raises:
        ValueError: 未知方向 —— **不**回落请求方向（`docs/04` §107 的「不臆造」）。
    """
    template = _SCHEMA_URI_TEMPLATES.get(str(direction))
    if template is None:
        raise ValueError(f"unknown schema direction: {direction!r}")
    slug = str(product).strip().lower().split()[0]
    return template.format(product=slug, code=str(key).lower().replace(".", "/"))


@dataclass(frozen=True, slots=True)
class ImportReport:
    """一次导入的结果（`docs/04` §107 的可复算证据）。"""

    inserted: Mapping[str, int] = field(default_factory=dict)
    updated: Mapping[str, int] = field(default_factory=dict)
    unchanged: Mapping[str, int] = field(default_factory=dict)
    totals: Mapping[str, int] = field(default_factory=dict)
    source_hash: str = ""
    generated_at: datetime | None = None
    seven_and: SevenAndReport | None = None
    """7 项 AND 的**如实报告**（P137b；见裁决 8）—— **不**参与任何状态写入。"""

    def as_dict(self) -> dict[str, Any]:
        """诊断用映射（**不含** secret；只含计数与哈希）。"""
        return {
            "inserted": dict(self.inserted),
            "updated": dict(self.updated),
            "unchanged": dict(self.unchanged),
            "totals": dict(self.totals),
            "source_hash": self.source_hash,
            "seven_and": None if self.seven_and is None else self.seven_and.as_dict(),
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
            seven_and=self._seven_and_report(),
            generated_at=utcnow(),
        )

    def source_hash(self) -> str:
        """`manifest.json` 的 sha256（`docs/04` §107 / §110；可复算）。"""
        path = self._registry.root / "manifest.json"
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def _seven_and_report(self) -> SevenAndReport:
        """P137b：7 项 AND 的**如实报告**（见裁决 8；**不**写任何状态）。

        版本取声明区间的**最后一个**（`2026`）—— 第 6 项只在版本不在声明区间内时为假，
        故该选择**不**影响结论；L4 / L5 结论在本报告里**不**参与（CI 层无专用环境，
        见 `seven_and_report` 的 `live_outcomes`）。
        """
        return seven_and_report(
            self._registry,
            version=self._versions[-1] if self._versions else "",
            supported_versions=self._versions,
        )

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
        """`midas_api_schemas`：**两个方向**各占一行（`docs/04` §12；见裁决 1 / 7）。

        `schema_json` 一律**原样**登记（不改写任何取值）：请求方向取文件里的
        `schema`，响应方向取 `response.schema`（`registry/README.md` §2.2）。
        未声明 `response` 块 / 取不到本体 → 该方向**不**建行（**不**臆造）。
        """
        for definition in self._definitions():
            document = self._registry.schema_document(definition.key)
            if document is None:
                continue
            await self._upsert_schema_row(
                session,
                definition=definition,
                direction=REQUEST_DIRECTION,
                raw=document.get("schema"),
                source=str(document.get("source") or ""),
            )
            block = self._registry.response_schema_document(definition.key)
            if block is None:
                continue
            await self._upsert_schema_row(
                session,
                definition=definition,
                direction=RESPONSE_DIRECTION,
                raw=block.get("schema"),
                source=str(block.get("source") or ""),
            )

    async def _upsert_schema_row(
        self,
        session: AsyncSession,
        *,
        definition: EndpointDefinition,
        direction: str,
        raw: Any,
        source: str,
    ) -> None:
        """登记一行 `midas_api_schemas`（**唯一**的 Schema 行写入点，见裁决 7）。"""
        if not isinstance(raw, dict):
            return
        uri = schema_uri_for(definition.key, product=self._product, direction=direction)
        await self._upsert(
            session,
            MidasApiSchemaORM,
            table="midas_api_schemas",
            identity={"schema_uri": uri},
            values={
                "schema_uri": uri,
                "direction": str(direction),
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
            response_schema_id = await self._response_schema_row_id(session, definition.key)
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
                            "response_schema_id": response_schema_id,
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
                response_schema_id = await self._response_schema_row_id(session, step.key)
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
                        "response_schema": response_schema_id,
                        "transformer": step.transformer,
                        "verification_status": definition.verification_status,
                    },
                )

    async def _schema_row_id(self, session: AsyncSession, key: str) -> str | None:
        """取该端点**请求方向** Schema 行的 id（无 Schema → `None`）。"""
        if self._registry.schema_json(key) is None:
            return None
        return await self._schema_id_by_uri(session, schema_uri_for(key, product=self._product))

    async def _response_schema_row_id(self, session: AsyncSession, key: str) -> str | None:
        """取该端点**response 方向** Schema 行的 id（未声明 → `None`，见裁决 7）。"""
        if self._registry.response_schema_json(key) is None:
            return None
        return await self._schema_id_by_uri(
            session,
            schema_uri_for(key, product=self._product, direction=RESPONSE_DIRECTION),
        )

    async def _schema_id_by_uri(self, session: AsyncSession, uri: str) -> str | None:
        """按 `schema_uri` 取行 id（**唯一**的按 URI 查 id 点）。"""
        statement = select(MidasApiSchemaORM.id).where(MidasApiSchemaORM.schema_uri == uri)
        return None if (row := (await session.execute(statement)).scalar()) is None else str(row)

    def _definitions(self) -> Iterable[Any]:
        """全部端点定义（数据文件顺序）。"""
        return (self._registry.endpoint(key) for key in self._registry.keys())

    def _schema_sources(self) -> set[str]:
        """Schema 文件里出现过的 `source` 取值（**两个方向**都算，见裁决 7）。"""
        found: set[str] = set()
        for definition in self._definitions():
            document = self._registry.schema_document(definition.key)
            if document is None:
                continue
            if document.get("source"):
                found.add(str(document["source"]))
            block = document.get("response")
            if isinstance(block, Mapping) and block.get("source"):
                found.add(str(block["source"]))
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


# ===== 7 项 AND 的如实报告（P137b；`docs/04` §8 / `docs/07` §16 R78 / R87）=====


@dataclass(frozen=True, slots=True)
class SevenAndReport:
    """`VERIFIED` 的 7 项 AND 在**当前数据 + 可选 L4 结论**下的汇总（见裁决 8）。

    ⚠️ 本报告**只**汇总判定点（`live.registry_evidence` / `seven_and_verdict`）的结论，
    **不**写任何 `verification_status` —— 端点行的状态仍只由 `availability` 机械映射
    （`docs/07` §7.2），故本报告**绝不**因 CI 层记录（L1–L3）升级任何端点（R78 / R87）。
    """

    endpoints: int = 0
    live_outcomes: int = 0
    satisfied: Mapping[str, int] = field(default_factory=dict)
    missing: Mapping[str, int] = field(default_factory=dict)
    verdicts: Mapping[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """诊断用映射（**不含** secret；只含计数与逐项名称）。"""
        return {
            "endpoints": int(self.endpoints),
            "live_outcomes": int(self.live_outcomes),
            "satisfied": dict(self.satisfied),
            "missing": dict(self.missing),
            "verdicts": dict(self.verdicts),
        }


def seven_and_report(
    registry: MidasRegistry,
    *,
    version: str,
    supported_versions: Sequence[str],
    live_outcomes: Mapping[str, str] | None = None,
) -> SevenAndReport:
    """按 **7 项 AND** 汇总每个 key 的判定（见裁决 8；判定点**不**复制）。

    Args:
        registry: 已装载的 `registry/`。
        version: 第 6 项用的实例版本（调用方给**声明区间内**的版本）。
        supported_versions: `AdapterManifest.supported_versions`。
        live_outcomes: `key → L4 结论`（只有 `PASSED` 才使第 7 项为真）；缺省 =
            **CI 层**（无 L4 / L5 结论 → 第 7 项**如实**为假，**不**伪造实测）。

    Returns:
        `SevenAndReport`：逐项满足 / 缺项计数与 `VERIFIED` / `PARTIAL` 计数。

    Note:
        每个 key 的判定口径 = **第一个声明产品** + 调用方给的版本 —— 证据仍由
        `live.registry_evidence`（**唯一**判定点）给出，本函数**不**新增第二套判定；
        也**不**把结论写回 `verification_status`（见裁决 8）。
    """
    outcomes = dict(live_outcomes or {})
    satisfied: dict[str, int] = {item: 0 for item in SEVEN_AND_ITEMS}
    verdicts: dict[str, int] = {STATUS_VERIFIED: 0, STATUS_PARTIAL: 0}
    for key in registry.keys():
        definition = registry.endpoint(key)
        product = (
            definition.products[0] if definition.products else next(iter(definition.overrides), "")
        )
        evidence = registry_evidence(
            registry,
            key=key,
            product=product,
            version=str(version),
            supported_versions=supported_versions,
            live_outcome=str(outcomes.get(key, "")),
        )
        verdict = seven_and_verdict(evidence)
        verdicts[verdict.status] = verdicts.get(verdict.status, 0) + 1
        for item in verdict.satisfied:
            satisfied[item] = satisfied.get(item, 0) + 1
    endpoints = len(registry)
    return SevenAndReport(
        endpoints=endpoints,
        live_outcomes=len(outcomes),
        satisfied=satisfied,
        missing={item: endpoints - satisfied.get(item, 0) for item in SEVEN_AND_ITEMS},
        verdicts=verdicts,
    )
