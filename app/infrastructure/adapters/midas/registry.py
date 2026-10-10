"""Infrastructure · Adapters · MIDAS · Registry —— 端点数据的只读访问层（`docs/04` §7 / §16）。

权威来源
--------
- `docs/04` §7.1（Registry 目标）—— `Operation → Product → Version → Method → Endpoint →
  Request Schema → Response Schema → Transformer → Verification Status`；
  数据库只存**标识**（如 `midas.node.v1`），**不得**存任意 Python 代码。
- `docs/04` §16（Registry Resolver）—— 解析优先级 `exact product → exact version →
  method/path → operation → compatible range → fallback → reject`；**禁止**版本不匹配时
  盲目使用最新 API；找不到匹配 → `UNSUPPORTED`。
- `registry/README.md` §4 / §5 —— `key` / `uri` / `methods` / `wrapper` /
  `product_overrides` / `solver` / `availability` / `enabled` / `path_key_supported` /
  `risk` / `schema_shape` / `table_type` 的**唯一权威**口径。
- `docs/07` §7.2 —— `availability` → `verification_status` 的映射规则
  （`verified→VERIFIED` / `unverified→UNVERIFIED` / `untested→PARTIAL` /
  `enabled=false→DEPRECATED`）。

落地裁决（只补实现手段，不改任何取值）
------------------------------------
1. **数据只读、不改写**：本模块只解析 `registry/manifest.json` 与
   `registry/schema/**/*.json`，**不**做任何字段改名 / 值改写（`docs/04` §107 的
   「原样登记」）；`read_root` 取自数据文件的 `wrapper.read_root`（`registry/README.md`
   §8.1：YAML 为唯一真源，`manifest.json` 由 `sync_manifest.py` 派生）。
2. **产品差异先查 `product_overrides` 再回落主定义**（`registry/README.md` §5 第 2 步）。
   覆盖项的字段名**逐字**取自数据（`uri` / `methods` / `wrapper.{write,shape,body_kind}` /
   `delete_all_via_body`）。
3. **`version` 不在数据里**：`registry/` 无版本字段（`api_registry.py` 的字段来源表已记录），
   故本层不做版本比较 —— 版本由 `AdapterManifest`（`docs/04` §62）与实例声明决定，
   匹配失败一律**拒绝**（`docs/04` §16 的 `reject`），**不**回落「最新 API」。
4. **找不到 key → 明确失败**：`endpoint()` 抛 `MidasCapabilityError`（`3000`），
   `details.reason = "endpoint_not_in_registry"`；**不**返回 `None`、**不**猜测路径。
5. **响应解包链是数据侧声明、Adapter 不得猜**（`docs/07` §16 R83，P134 新增）：
   `ResolvedEndpoint.read_path` 按「`product_overrides.<产品>.wrapper.read_root_path` →
   端点定义 `wrapper.read_root_path` → `read_root`」的顺序给出**唯一**解包链；
   **空元组 = 数据侧未声明**，Adapter 据此**明确报错**（禁止 R83 描述的静默降级：
   取不到 `read_root` 就退回整包 → 转换器字段全 `None` 而不报错）。
   取值只来自数据与实测（`registry/README.md` §4 / §8.1），本模块**不**推断信封。
6. **响应方向 Schema 与请求方向**：`registry/schema/**` 的**一份文件**同时承载两个方向 ——
   `schema` = 请求方向（原样登记，**不改写**），`response` = **response 方向**
   （`{direction, source, schema}`，由 `registry/tools/sync_response_schemas.py`
   按**实测信封**生成，`registry/README.md` §2.2）。本模块只**读**两者：
   `schema_json()` 给请求方向，`response_schema_json()` 给响应方向（未声明 → `None`）。
   `docs/07` §16 R87 的判定点据此从「恒为假」变为「按数据如实判定」。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py` / `manifest.py`；**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces`，也**不**写数据库。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.infrastructure.adapters.midas.errors import MidasCapabilityError, MidasConnectionError
from app.infrastructure.adapters.midas.write_templates import (
    WritePayloadTemplate,
    WriteTemplateSet,
    load_write_templates,
)

__all__ = [
    "DEPRECATED",
    "MANIFEST_FILENAME",
    "PARTIAL",
    "UNVERIFIED",
    "VERIFIED",
    "EndpointDefinition",
    "MidasRegistry",
    "ResolvedEndpoint",
    "verification_status_for",
]

MANIFEST_FILENAME: Final[str] = "manifest.json"
"""`registry/README.md` §2：全量索引文件名。"""

VERIFIED: Final[str] = "VERIFIED"
UNVERIFIED: Final[str] = "UNVERIFIED"
PARTIAL: Final[str] = "PARTIAL"
DEPRECATED: Final[str] = "DEPRECATED"
"""`docs/04` §8 的四个状态取值（逐字照抄）。"""

_AVAILABILITY_TO_STATUS: Final[dict[str, str]] = {
    "verified": VERIFIED,
    "unverified": UNVERIFIED,
    "untested": PARTIAL,
}
"""`docs/07` §7.2 的映射规则（关键）：`availability` → `verification_status`。"""


def verification_status_for(*, availability: str, enabled: bool) -> str:
    """`availability` + `enabled` → `verification_status`（`docs/07` §7.2）。

    Args:
        availability: 数据文件的实测可用性（`registry/README.md` §4）。
        enabled: 数据文件的 `enabled` 标志。

    Returns:
        `VERIFIED` / `UNVERIFIED` / `PARTIAL` / `DEPRECATED`。

    Note:
        `enabled=false` **优先**（`docs/07` §7.2 的 `DB.SWIND` 即 `untested` + 禁用 →
        `DEPRECATED`），与 `docs/04` §8 的 DEPRECATED 语义一致。
    """
    if not enabled:
        return DEPRECATED
    return _AVAILABILITY_TO_STATUS.get(str(availability), PARTIAL)


@dataclass(frozen=True, slots=True)
class EndpointDefinition:
    """一条端点定义（字段逐字取自 `registry/manifest.json`）。"""

    key: str
    namespace: str
    uri: str
    methods: tuple[str, ...]
    products: tuple[str, ...]
    wrapper_write: str
    read_root: str
    schema_path: str
    schema_shape: str
    solver: str
    execution_mode: str
    availability: str
    enabled: bool
    disable_reason: str
    risk_level: str
    destructive: bool
    delete_without_body_is_global: bool
    table_type: str
    title: str
    provenance: tuple[str, ...]
    overrides: Mapping[str, Mapping[str, Any]]
    read_root_path: tuple[str, ...] = ()
    """**响应解包链**（`docs/07` §16 R83；P134 新增）。

    数据侧**可选**声明的解包链（`wrapper.read_root_path`），用于「响应信封与
    `read_root` 不一致」的产品：`CIVIL_DESIGNER` 实测业务载荷在
    `result.return_value`（R83），故其链为 `("result", "return_value")`。
    缺省空元组 = 数据侧未声明，此时由 `read_root` 兜底（见 `resolve()`）。
    """

    @property
    def verification_status(self) -> str:
        """本端点的 `verification_status`（`docs/07` §7.2）。"""
        return verification_status_for(availability=self.availability, enabled=self.enabled)


@dataclass(frozen=True, slots=True)
class ResolvedEndpoint:
    """某个 `(product, key, method)` 的**已解析**端点（`docs/04` §16 的解析结果）。"""

    definition: EndpointDefinition
    product: str
    method: str
    uri: str
    wrapper_write: str
    wrapper_shape: str
    body_kind: str
    read_root: str
    delete_all_via_body: bool
    read_path: tuple[str, ...] = ()
    """**响应解包链**（P134 / R83）：如 `("result", "return_value")` 的逐层键路径。

    由 `resolve()` 按「产品覆盖 → 端点定义 → `read_root`」的顺序给出；
    **空元组 = 数据侧未声明**，此时 Adapter 必须**明确报错**，而不是把整包
    当成载荷（`docs/07` §16 R83：静默降级会把「信封不一致」伪装成「字段全空」）。
    """

    @property
    def key(self) -> str:
        """Registry key（`registry/README.md` §4）。"""
        return self.definition.key

    @property
    def table_type(self) -> str:
        """POST 命名空间的 `Argument.TABLE_TYPE` 取值（可能为空串）。"""
        return self.definition.table_type

    @property
    def solver(self) -> str:
        """求解器约束（空串 = 标准求解器，`registry/README.md` §4）。"""
        return self.definition.solver

    @property
    def verification_status(self) -> str:
        """`verification_status`（`docs/07` §7.2）。"""
        return self.definition.verification_status

    @property
    def is_flat(self) -> bool:
        """请求体是否**扁平**（Designer 形态；`docs/07` §7.6）。"""
        return self.wrapper_shape == "flat"

    @property
    def requires_array_body(self) -> bool:
        """请求体是否必须为数组（`flat_array` / `body_kind = array`）。"""
        return self.body_kind == "array" or self.definition.schema_shape == "flat_array"

    @property
    def requires_object_body(self) -> bool:
        """请求体是否必须为对象（`flat_object` / `body_kind = object`）。"""
        return self.body_kind == "object" or self.definition.schema_shape == "flat_object"

    @property
    def has_declared_read_path(self) -> bool:
        """该端点是否声明了解包链（`docs/07` §16 R83；P134 新增）。"""
        return bool(self.read_path)


class MidasRegistry:
    """`registry/` 的只读视图（`docs/04` §7.1；`registry/README.md` §5）。"""

    def __init__(
        self,
        *,
        root: Path,
        definitions: Mapping[str, EndpointDefinition],
        order: Sequence[str],
    ) -> None:
        """由已解析的定义构造（**不**做 I/O）。"""
        self._root = root
        self._definitions = dict(definitions)
        self._order = tuple(order)
        self._write_templates: WriteTemplateSet | None = None

    # ===== 查询 =====

    @property
    def root(self) -> Path:
        """数据目录（`Settings.registry_root`）。"""
        return self._root

    def keys(self) -> tuple[str, ...]:
        """全部 Registry key（数据文件顺序 = `registry/manifest.json` 顺序）。"""
        return self._order

    def products(self) -> tuple[str, ...]:
        """数据里出现过的产品键（升序）。"""
        return tuple(sorted({p for d in self._definitions.values() for p in d.products}))

    def endpoint(self, key: str) -> EndpointDefinition:
        """按 key 取端点定义（`registry/README.md` §5 第 1 步）。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000`，该 key 不在数据里（见裁决 4）。
        """
        definition = self._definitions.get(str(key))
        if definition is None:
            raise MidasCapabilityError("endpoint_not_in_registry", endpoint=str(key))
        return definition

    def has(self, key: str) -> bool:
        """该 key 是否在数据里。"""
        return str(key) in self._definitions

    def resolve(self, *, key: str, product: str, method: str | None = None) -> ResolvedEndpoint:
        """解析一个端点的**产品视图**（`docs/04` §16；`registry/README.md` §5 第 2 步）。

        Args:
            key: Registry key。
            product: 数据侧的产品键（如 `CIVIL_NX`）。
            method: 目标方法；`None` → 取该产品的第一个可用方法。

        Returns:
            已应用 `product_overrides` 的端点视图。

        Raises:
            MidasCapabilityError: 产品不支持该端点，或方法不在该产品的可用方法集内
                （`registry/README.md` §5 第 3 步：**不**发请求，直接返回结构化错误）。
        """
        definition = self.endpoint(key)
        override = definition.overrides.get(str(product))
        if override is None and str(product) not in definition.products:
            raise MidasCapabilityError(
                "endpoint_not_available_for_product", endpoint=key, product=str(product)
            )
        override = override or {}
        methods = self.methods_for(key=key, product=str(product))
        if not methods:
            # 数据里 `DB.SWIND` 之类**没有**任何方法（`enabled: false`，`registry/README.md`
            # §4 的 `methods_unknown`）：此时按空方法解析，让调用方走到 `guard_enabled()`
            # 的**禁用**拒绝，而不是在解析层报一个含糊的「没有方法」。
            chosen = ""
        elif method is None:
            chosen = methods[0]
        else:
            chosen = str(method).upper()
            if chosen not in methods:
                raise MidasCapabilityError(
                    "method_not_available_for_product",
                    endpoint=key,
                    product=str(product),
                    method=chosen,
                )
        wrapper = dict(override.get("wrapper") or {})
        return ResolvedEndpoint(
            definition=definition,
            product=str(product),
            method=chosen,
            uri=_normalize_uri(str(override.get("uri") or definition.uri)),
            wrapper_write=str(wrapper.get("write") or definition.wrapper_write),
            wrapper_shape=str(wrapper.get("shape") or ""),
            body_kind=str(wrapper.get("body_kind") or ""),
            read_root=definition.read_root,
            delete_all_via_body=bool(override.get("delete_all_via_body")),
            read_path=_read_path(
                wrapper.get("read_root_path"),
                definition=definition,
            ),
        )

    def methods_for(self, *, key: str, product: str) -> tuple[str, ...]:
        """该端点在**该产品**上的可用方法（先 `product_overrides.<产品>.methods`，再回落主定义）。

        ⚠️ `docs/07` §7.6 / `registry/README.md` §4：产品差异**先查** `product_overrides`
        —— 例如 `CIVIL_DESIGNER` 的 `DB.NODE` / `DB.ELEM` 只有 `GET`（数据侧声明），
        基础定义里的 `POST` / `PUT` / `DELETE` **不**适用于该产品。

        Args:
            key: Registry key。
            product: 数据侧产品键（`GEN_NX` / `CIVIL_NX` / `CIVIL_DESIGNER`）。

        Returns:
            该产品的方法集（可能为空 —— 数据侧没有方法时按空集返回，由调用方决定如何处理）。
        """
        definition = self.endpoint(key)
        override = definition.overrides.get(str(product)) or {}
        return _methods(override.get("methods")) or definition.methods

    # ===== Schema（`docs/04` §13 / §107）=====

    def schema_document(self, key: str) -> dict[str, Any] | None:
        """读取端点 Schema 文件的**原文**（原样登记，不改写任何取值）。

        Returns:
            文件内容（`{key, uri, source, schema, shape?}`）；该端点无 Schema 时 `None`
            （数据里 **20** 个端点尚无 Schema，`docs/07` §16 R5）。
        """
        definition = self.endpoint(key)
        if not definition.schema_path:
            return None
        path = self._root / definition.schema_path
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MidasConnectionError(
                "registry_schema_unreadable",
                endpoint=key,
                path=definition.schema_path,
                error=type(error).__name__,
            ) from error

    def schema_json(self, key: str) -> dict[str, Any] | None:
        """端点 Schema 文件里的 `schema` 字段（原样，未剥离包装根键）。"""
        document = self.schema_document(key)
        if document is None:
            return None
        raw = document.get("schema")
        return raw if isinstance(raw, dict) else None

    def response_schema_document(self, key: str) -> dict[str, Any] | None:
        """端点 Schema 文件里的 **response 方向**块（`docs/07` §16 R87；P136 新增）。

        数据侧在同一份 Schema 文件里用 `response` 块声明**实测过的响应信封**
        （由 `registry/tools/sync_response_schemas.py` 生成；`registry/README.md` §2.2）。
        **没有**该块 = 数据侧没有 response 方向 Schema（`availability` 非 `verified`
        的端点一律没有）—— 返回 `None`，调用方据此**如实**判假，**不**猜。

        Returns:
            `{direction, source, schema}`；未声明时 `None`。
        """
        document = self.schema_document(key)
        if document is None:
            return None
        block = document.get("response")
        return dict(block) if isinstance(block, Mapping) else None

    def response_schema_json(self, key: str) -> dict[str, Any] | None:
        """**response 方向**的 JSON Schema 本体（未声明 → `None`，见裁决 6）。"""
        block = self.response_schema_document(key)
        if block is None:
            return None
        raw = block.get("schema")
        return dict(raw) if isinstance(raw, Mapping) else None

    def effective_schema(self, key: str) -> dict[str, Any] | None:
        """剥离**请求体包装根键**后的生效 Schema（P09 同一口径，`docs/07` §16 R18）。

        Returns:
            生效 Schema；无法判定时返回原值（**不**改写任何取值）。
        """
        raw = self.schema_json(key)
        if raw is None:
            return None
        return unwrap_schema(raw)

    def request_schema_fields(self, key: str) -> tuple[str, ...]:
        """生效 Schema 根级的字段名（Transformer 的**唯一**字段白名单来源）。

        Raises:
            MidasCapabilityError: 该端点没有可用 Schema —— 无法判定字段名时
                **不**臆造（`docs/04` §107 / `docs/07` §7.4 的硬约束）。
        """
        effective = self.effective_schema(key)
        if effective is None:
            raise MidasCapabilityError("endpoint_schema_unavailable", endpoint=key)
        properties = effective.get("properties")
        if not isinstance(properties, Mapping):
            raise MidasCapabilityError("endpoint_schema_has_no_properties", endpoint=key)
        return tuple(str(name) for name in properties)

    def item_schema(self, key: str) -> dict[str, Any]:
        """生效 Schema 的**条目**形状：`ITEMS` 数组元素或根对象本身。

        数据里两种形态都存在（`registry/README.md` §2.1 的 377 包装 + 237 直写），
        故此处只做**机械**判定：根级有 `ITEMS`（数组）→ 取 `items`；否则取根对象。
        """
        effective = self.effective_schema(key) or {}
        properties = effective.get("properties")
        if isinstance(properties, Mapping):
            items = properties.get("ITEMS")
            if isinstance(items, Mapping):
                element = items.get("items")
                if isinstance(element, Mapping):
                    return dict(element)
        return dict(effective)

    # ===== 写路径请求体模板（P139；数据侧 `registry/live/write_templates.json`）=====

    def write_templates(self) -> WriteTemplateSet:
        """装载数据侧**写路径请求体模板**（惰性；缺文件 → 空集合）。

        P138c 的真实批量实测暴露：`write_probe.derive_body()` 机械派生的零值请求体
        被实例拒绝（9 / 10 个候选 `400`）。P139 把**真实请求体**落成数据
        （`registry/live/write_templates.json`，由 `registry/tools/check_write_templates.py`
        逐条复算），本方法只是它的**唯一**读取点 —— Core 里**不**硬编码任何模板。

        Returns:
            `WriteTemplateSet`（首次调用后缓存；`registry/` 是只读数据）。
        """
        if self._write_templates is None:
            self._write_templates = load_write_templates(self._root)
        return self._write_templates

    def write_template(self, key: str) -> WritePayloadTemplate | None:
        """按端点 key 取写路径请求体模板（无模板 → `None`，调用方回落 `derive_body`）。"""
        return self.write_templates().get(str(key))

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含** secret）。"""
        statuses: dict[str, int] = {}
        for definition in self._definitions.values():
            status = definition.verification_status
            statuses[status] = statuses.get(status, 0) + 1
        return {
            "endpoints": len(self._definitions),
            "products": list(self.products()),
            "verification_status": dict(sorted(statuses.items())),
        }

    def __len__(self) -> int:
        return len(self._definitions)

    # ===== 装配 =====

    @classmethod
    def load(cls, registry_root: str | Path) -> MidasRegistry:
        """从 `registry/` 装载端点索引（`registry/README.md` §5 第 1 步）。

        Raises:
            MidasConnectionError: `STRUCTAI-2000`，索引缺失 / 不可解析 ——
                数据源不可用属**部署**事实，**不**静默回落空表。
        """
        root = Path(registry_root)
        path = root / MANIFEST_FILENAME
        if not path.is_file():
            raise MidasConnectionError("registry_manifest_missing", path=str(path))
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise MidasConnectionError(
                "registry_manifest_unreadable", path=str(path), error=type(error).__name__
            ) from error
        raw_endpoints = document.get("endpoints")
        if not isinstance(raw_endpoints, list):
            raise MidasConnectionError("registry_manifest_has_no_endpoints", path=str(path))

        definitions: dict[str, EndpointDefinition] = {}
        order: list[str] = []
        for entry in raw_endpoints:
            if not isinstance(entry, Mapping):
                raise MidasConnectionError("registry_manifest_entry_malformed", path=str(path))
            definition = _definition(entry)
            definitions[definition.key] = definition
            order.append(definition.key)
        return cls(root=root, definitions=definitions, order=order)


# ===== 解析辅助（只做机械变换）=====


def unwrap_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    """剥离请求体包装根键（P09 的 `_effective_schema` 同口径，见模块裁决 1）。

    `registry/schema/**` 的两种形态（`registry/README.md` §2.1）：直接是 JSON Schema，
    或 `{<包装根键>: <JSON Schema>}`。判定只依据**结构**（有无 `properties` / `type`），
    **不**猜字段名。
    """
    if "properties" in schema or "type" in schema or "$schema" in schema:
        return dict(schema)
    if len(schema) == 1:
        only = next(iter(schema.values()))
        if isinstance(only, Mapping):
            return dict(only)
    return dict(schema)


def _definition(entry: Mapping[str, Any]) -> EndpointDefinition:
    """把 `manifest.json` 的一条记录机械转成 `EndpointDefinition`。"""
    wrapper = entry.get("wrapper") or {}
    risk = entry.get("risk") or {}
    overrides = entry.get("product_overrides") or {}
    return EndpointDefinition(
        key=str(entry.get("key") or ""),
        namespace=str(entry.get("namespace") or ""),
        uri=_normalize_uri(str(entry.get("uri") or "")),
        methods=_methods(entry.get("methods")),
        products=tuple(str(item) for item in _as_sequence(entry.get("products"))),
        wrapper_write=str(wrapper.get("write") or "none"),
        read_root=str(wrapper.get("read_root") or ""),
        read_root_path=_declared_read_path(wrapper.get("read_root_path")),
        schema_path=str(entry.get("schema") or ""),
        schema_shape=str(entry.get("schema_shape") or ""),
        solver=str(entry.get("solver") or ""),
        execution_mode=str(entry.get("execution_mode") or ""),
        availability=str(entry.get("availability") or ""),
        enabled=bool(entry.get("enabled", True)),
        disable_reason=str(entry.get("disable_reason") or ""),
        risk_level=str(risk.get("level") or ""),
        destructive=bool(risk.get("destructive", False)),
        delete_without_body_is_global=bool(risk.get("delete_without_body_is_global", False)),
        table_type=str(entry.get("table_type") or ""),
        title=str(entry.get("title") or ""),
        provenance=tuple(str(item) for item in _as_sequence(entry.get("provenance"))),
        overrides={
            str(product): dict(value)
            for product, value in overrides.items()
            if isinstance(value, Mapping)
        },
    )


def _declared_read_path(value: object) -> tuple[str, ...]:
    """数据侧的 `wrapper.read_root_path` → 元组（**不改写任何取值**）。

    `registry/README.md` §4 的 `product_overrides` 允许各产品覆盖**响应信封**：
    `CIVIL_DESIGNER` 实测业务载荷在 `result.return_value`（`docs/07` §16 R83），
    而 NX 系的 `read_root` 与顶层键一致，故只有 Designer 需要声明这条链。
    逗号分隔的字符串与列表两种写法都接受（与数据里 `methods` 的既有口径一致）。
    """
    return tuple(str(part).strip() for part in _as_sequence(value) if str(part).strip())


def _read_path(declared: object, *, definition: EndpointDefinition) -> tuple[str, ...]:
    """解包链的**唯一**判定点（`docs/07` §16 R83；P134 新增）。

    顺序：**产品覆盖声明** → **端点定义声明** → `read_root` 兜底 → 空（未声明）。
    空元组不是「整包即载荷」，而是「数据侧没有可用的解包链」——
    Adapter 必须据此**明确报错**（`docs/07` §16 R83 禁止静默降级）。
    """
    override_chain = _declared_read_path(declared)
    if override_chain:
        return override_chain
    if definition.read_root_path:
        return definition.read_root_path
    if definition.read_root:
        return (definition.read_root,)
    return ()


def _as_sequence(value: object) -> tuple[object, ...]:
    """把数据里的列表字段归一成元组（字符串按逗号切分）。"""
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence):
        return tuple(value)
    return ()


def _methods(value: object) -> tuple[str, ...]:
    """方法集：大写归一（`registry/README.md` §4）。"""
    return tuple(str(item).upper() for item in _as_sequence(value))


def _normalize_uri(uri: str) -> str:
    """补前导斜杠（个别产品覆盖值省略，`api_registry.py` 同口径）。"""
    if not uri:
        return ""
    return uri if uri.startswith("/") else f"/{uri}"
