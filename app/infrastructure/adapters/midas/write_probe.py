"""Infrastructure · Adapters · MIDAS · Write-path probe（P135，`docs/07` §16 R4 / R14 收口）。

权威来源
--------
- `docs/04` §71 / §72 —— Contract Test 分层（L1–L3 属 CI，L4 / L5 属**专用环境**），
  以及 Live 安全四要素（专用实例 / 专用 Key / **专用项目** / 专用测试模型）。
- `docs/07` §16 **R4** —— 写路径实测覆盖仅 **11 / 369**（「Adapter 生产就绪度不足」）；
  R4 的建议是「用**独立测试项目**批量『创建 → 读回 → 删除』」。
- `docs/07` §16 **R14** —— 写路径端点**未**被只读探针覆盖（379 个）。
- `docs/07` §6.4 / §7.6 —— NX 系 `DELETE` **必须**带路径 key（不带 = 删全表，历史事故）；
  Designer 的空主体 / `Type=0` 一律拒绝。
- `docs/04` §72 —— 专用测试项目的声明**只**经环境变量（`MIDAS_LIVE_PROJECT`）。

落地裁决（P135 的 R4 / R14 收口）
-----------------------------------
1. **只读探针覆盖不到的写路径，用「三步链」逐个端点实测**：对每个「有写方法 +
   已声明读路径 + 有原生 Transformer」的端点执行
   `list_existing → create → read_back → delete`，每一步都走**数据侧**的
   `registry/` 解析与 `transforms.py` 的 Transformer（**不**另写一套请求组装）。
2. **只在专用测试项目上执行**：`project is None` → 立即
   `STRUCTAI-3000 dedicated_test_project_not_declared`（与 `MidasLiveBusinessEffect`
   同一口径），**绝不**回落到「当前打开的项目」。
3. **只碰自己创建的 ID**：编号一律取「既有编号集合 + 1」（`max + 1`），
   因此**不覆盖**任何既有条目；删除只按该编号的路径 key 发出。
4. **请求体由数据侧 Schema 机械派生，不臆造语义**：`derive_body()` 按
   `registry/` 的请求 Schema 递归取值 —— `default` → `enum[0]` → `const` →
   `examples[0]` → 按 `type` 的零值（`string` 用**字段名**、`number` / `integer` 用 `0`、
   `boolean` 用 `false`、`array` 用 `[]`、`object` 递归）。
   取不到（无 Schema / 无可用分支）→ 该端点如实记 `NO_PAYLOAD_TEMPLATE`，
   **不**猜字段、**不**发请求。
5. **危险端点一律排除**（`docs/07` §6.4 / §7.6）：`destructive` / `delete_without_body_is_global` /
   `delete_all_via_body` / 无 `path_key_supported` 的删除面**不**进入创建链；
   因此本探针**不会**产生任何「删全表」形态的请求。
6. **结论只有四态，且都不美化**：
   `PASSED`（三步全成立）/ `FAILED`（原生拒绝或读回缺失）/
   `NO_PAYLOAD_TEMPLATE`（数据侧取不到请求体模板）/
   `NO_READBACK`（该端点没有可用的读路径，无法读回）。
   计数与逐条明细进 `WriteProbeReport`，供 `midas_api_verifications` 的 L5 行落地。
7. **失败只归类，不上抛**：单个端点的原生失败是**数据**（`docs/02` §25 的同一口径），
   由调用方决定如何处理；只有「未声明专用项目」这一**纪律**问题才抛异常。
8. **请求体模板是数据**（P139，`docs/07` §16 R4 的分子）：`registry/live/write_templates.json`
   声明每个写端点的**真实请求体**（来源 = 上游手册示例 + 逐条 `adjustments`，由
   `registry/tools/check_write_templates.py` **逐条复算**）与**前置链**。本模块**只**读它：
   有模板用模板，无模板仍走 `derive_body()`；两者都取不到 → 如实记 `NO_PAYLOAD_TEMPLATE`
   （**不**猜字段、**不**发请求）。**不**放宽判定：`PASSED` 仍要求
   「创建 → 读回 → 按路径 key 删除」三步全成立（见裁决 6）。
9. **前置链只碰自建编号**（P139）：模板声明的 `prerequisites` 由本模块**按顺序**创建
   （编号即目标请求体引用的编号，**全部**是本次自建），目标删除后**逆序**删除；
   任一步失败 → 目标如实记 `FAILED`（`detail` = `prerequisite_failed:<key>#<id>:<原因>`），
   **不**美化、**不**继续写。
10. **状态码保真**（P139）：`status_code` 来自**响应**（`MidasHttpClient.send_result()`），
   不再是常量 `200`；失败路径仍以异常归类（`details.status_code` 即原生状态码）。
11. **编号一律重新分配（R96）**：模板里声明的编号（前置的 `item_id`、目标 body 里的自身编号）
   **不**照抄 —— 探针取「该端点既有编号的 `max + 1`」（`id_source = "target"` 的前置取**目标**
   编号），并按模板声明的 `references` / `self_references` 写回所有引用路径；`allow_non_empty=True`
   时空项目闸门改为**更强**的判据：清理后逐端点核对「既有编号集合**一字未变**」，变了即如实
   `FAILED`（`detail = existing_id_set_changed`）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包模块；**不**引用 SQLAlchemy / FastAPI / MCP SDK，
**不**依赖 `app.interfaces` / `app.application`。凭据仍**只**经 `MidasHttpClient`
的注入凭据提供者解析（本模块**不**接触任何凭据值）。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from app.infrastructure.adapters.midas.client import MidasHttpClient
from app.infrastructure.adapters.midas.errors import MidasCapabilityError
from app.infrastructure.adapters.midas.live import DedicatedTestProject
from app.infrastructure.adapters.midas.registry import MidasRegistry, ResolvedEndpoint
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.adapters.midas.write_templates import (
    ID_SOURCE_TARGET,
    OWNER_BODY_LABEL,
    WritePayloadTemplate,
    WritePrerequisite,
)

__all__ = [
    "EMPTINESS_GATE_KEYS",
    "PAYLOAD_SOURCE_SCHEMA_DERIVED",
    "WRITE_PROBE_FAILED",
    "WRITE_PROBE_NO_PAYLOAD",
    "WRITE_PROBE_NO_READBACK",
    "WRITE_PROBE_PASSED",
    "WRITE_METHODS",
    "WriteProbeOutcome",
    "WriteProbeReport",
    "MidasLiveWriteProbe",
    "derive_body",
    "transformer_name_for",
]

WRITE_PROBE_PASSED: Final[str] = "PASSED"
WRITE_PROBE_FAILED: Final[str] = "FAILED"
WRITE_PROBE_NO_PAYLOAD: Final[str] = "NO_PAYLOAD_TEMPLATE"
WRITE_PROBE_NO_READBACK: Final[str] = "NO_READBACK"
"""四态结论（见裁决 6）。"""

WRITE_METHODS: Final[tuple[str, ...]] = ("POST", "PUT")
"""本探针实际发出的**写入**方法（`DELETE` 只作清理，见裁决 3）。"""

PAYLOAD_SOURCE_SCHEMA_DERIVED: Final[str] = "schema_derived"
"""请求体来源：数据侧 Schema **机械派生**（`derive_body()`，见裁决 8）。

⚠️ 模板来源的取值**只**来自数据侧声明（`manual_example` / `manual_example_adjusted` /
`explicit_injection`）—— 本模块**不**自造来源标签，取不到模板即回落本值。
"""

EMPTINESS_GATE_KEYS: Final[tuple[str, ...]] = ("DB.NODE", "DB.ELEM", "DB.MATL", "DB.SECT")
"""「目标项目必须为空」闸门的只读哨兵端点（见裁决 8 / P138c）。

`MidasLiveWriteProbe` 在发**任何**写请求之前，先对这 4 个端点各做一次**只读** `GET`：
只要有一个端点已有既有编号，就**拒绝**（`STRUCTAI-3000 dedicated_test_project_not_empty`）
且**零**写请求 —— 这样「专用空项目」不再依赖**手工**核对（`docs/reports/P137…` §4 的边界）。
传 `emptiness_keys=()` 可**显式**关闭闸门（只用于离线单测的编号选择分支）。
"""

_TRANSFORMER_SUFFIX: Final[str] = ".v1"
"""Transformer 名的后缀（`transforms.py` 的注册键形如 `midas.node.v1`）。"""

_MAX_DEPTH: Final[int] = 4
"""`derive_body` 的递归深度上限（`docs/07` §14.4：禁止无限展开）。"""


@dataclass(frozen=True, slots=True)
class WriteProbeOutcome:
    """一个写路径端点的三步链结论（见裁决 6）。

    Attributes:
        key: `registry/` 的端点 key。
        method: 实际发出的写入方法（`POST` / `PUT`）。
        path: 实际请求路径（脱敏后仍只是 URI，不含查询 / 凭据）。
        outcome: 四态之一（`WRITE_PROBE_*`）。
        created_id: 自己创建的编号（`""` 表示未创建）。
        read_back: 读回是否命中。
        deleted: 是否已按路径 key 清理。
        detail: 非敏感诊断词（**只**含原因与状态码，**不含**响应体原文）。
        status_code: 原生状态码（来自响应，见裁决 10）；未发请求时为 `0`。
        payload_source: 请求体来源 —— 数据侧模板的 `source.kind`
            （`manual_example` / `manual_example_adjusted` / `explicit_injection`）
            或 `PAYLOAD_SOURCE_SCHEMA_DERIVED`（机械派生，见裁决 8）。
        prerequisites: 本次创建并已清理的**前置对象**标签（`<key>#<item_id>`，见裁决 9）。
    """

    key: str
    method: str
    path: str
    outcome: str
    created_id: str = ""
    read_back: bool = False
    deleted: bool = False
    detail: str = ""
    status_code: int = 0
    payload_source: str = ""
    prerequisites: tuple[str, ...] = ()

    @property
    def is_passed(self) -> bool:
        """三步全成立才算通过（`docs/07` §16 R4 的口径）。"""
        return self.outcome == WRITE_PROBE_PASSED


@dataclass(frozen=True, slots=True)
class WriteProbeReport:
    """一次写路径探测的全量结论（见裁决 6）。"""

    product: str
    outcomes: tuple[WriteProbeOutcome, ...] = ()

    def counts(self) -> dict[str, int]:
        """四态计数（**只**含整数）。"""
        counted: dict[str, int] = {
            WRITE_PROBE_PASSED: 0,
            WRITE_PROBE_FAILED: 0,
            WRITE_PROBE_NO_PAYLOAD: 0,
            WRITE_PROBE_NO_READBACK: 0,
        }
        for outcome in self.outcomes:
            counted[outcome.outcome] = counted.get(outcome.outcome, 0) + 1
        return counted

    def passed(self) -> tuple[WriteProbeOutcome, ...]:
        """三步链成立的端点（R4 的**实测覆盖**分子）。"""
        return tuple(item for item in self.outcomes if item.is_passed)

    def failures(self) -> tuple[WriteProbeOutcome, ...]:
        """原生拒绝或读回缺失的端点。"""
        return tuple(item for item in self.outcomes if item.outcome == WRITE_PROBE_FAILED)

    def blocked(self) -> tuple[WriteProbeOutcome, ...]:
        """数据侧取不到请求体模板 / 读路径的端点（**未**发请求）。"""
        return tuple(
            item
            for item in self.outcomes
            if item.outcome in {WRITE_PROBE_NO_PAYLOAD, WRITE_PROBE_NO_READBACK}
        )

    def keys(self) -> tuple[str, ...]:
        """参与探测的端点 key（顺序 = 探测顺序）。"""
        return tuple(item.key for item in self.outcomes)


def transformer_name_for(key: str) -> str:
    """端点 key → 数据侧 Transformer 名（`midas.<code 小写>.v1`；见裁决 1）。

    Args:
        key: `registry/` 的端点 key（如 `DB.NODE`）。

    Returns:
        `midas.node.v1` 形态的名字；`DB.` 前缀之外的 key 一律返回空串
        （**不**猜 Transformer，见裁决 4）。
    """
    namespace, _, code = str(key).partition(".")
    if namespace != "DB" or not code:
        return ""
    return f"midas.{code.lower()}{_TRANSFORMER_SUFFIX}"


def derive_body(schema: Mapping[str, Any] | None, *, depth: int = 0) -> Any:
    """按请求 Schema 机械派生一个**最小**请求体（见裁决 4）。

    ⚠️ 本函数**只**做取值（`default` / `enum[0]` / `const` / `examples[0]` / 按类型的零值），
    **不**解释任何工程语义，也**不**为取不到的字段编造取值。

    Args:
        schema: JSON Schema（`registry/` 的请求方向 Schema，已剥离包装根键）。
        depth: 递归深度（上限 `_MAX_DEPTH`）。

    Returns:
        派生出的取值；`None` 表示**取不到**（调用方据此记 `NO_PAYLOAD_TEMPLATE`）。
    """
    if not isinstance(schema, Mapping) or depth > _MAX_DEPTH:
        return None
    if "default" in schema:
        return schema["default"]
    if "const" in schema:
        return schema["const"]
    enum = schema.get("enum")
    if isinstance(enum, Sequence) and not isinstance(enum, str) and enum:
        return enum[0]
    examples = schema.get("examples")
    if isinstance(examples, Sequence) and not isinstance(examples, str) and examples:
        return examples[0]

    kind = schema.get("type")
    if isinstance(kind, Sequence) and not isinstance(kind, str):
        kind = next((item for item in kind if item != "null"), None)
    properties = schema.get("properties")
    if kind == "object" or isinstance(properties, Mapping):
        required = schema.get("required")
        names = (
            [str(name) for name in required]
            if isinstance(required, Sequence) and not isinstance(required, str)
            else list(properties or {})
        )
        if not names:
            return {}
        derived: dict[str, Any] = {}
        for name in names:
            child = (properties or {}).get(name)
            value = derive_body(child if isinstance(child, Mapping) else {}, depth=depth + 1)
            if value is None:
                return None
            derived[name] = value
        return derived
    if kind == "array":
        items = schema.get("items")
        if isinstance(items, Mapping):
            value = derive_body(items, depth=depth + 1)
            return None if value is None else [value]
        return []
    if kind == "string":
        # 用**字段名**不可得（这里没有字段名上下文）→ 用一个稳定的占位串。
        return "structai-probe"
    if kind in {"number", "integer"}:
        return 0
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    return None


@dataclass(frozen=True, slots=True)
class _PlannedPrerequisite:
    """一个**已定编号**的前置对象（见裁决 11）。

    Attributes:
        prerequisite: 数据侧声明的前置条目（`item_id` 是**模板里**的字面编号，仅作来源定位）。
        item_id: 本次**实分配**的编号（该端点既有编号的 `max + 1`，或目标编号）。
        body: 已写回引用编号的请求体。
    """

    prerequisite: WritePrerequisite
    item_id: str
    body: Any

    def label(self) -> str:
        """`<key>#<实分配编号>` —— 写进 L5 证据的标签（**不**用模板里的字面编号）。"""
        return f"{self.prerequisite.key}#{self.item_id}"


class MidasLiveWriteProbe:
    """写路径端点的三步链实测（`docs/07` §16 R4 / R14；见裁决 1–7）。

    🔴 **纪律**：只在**专用测试项目**上执行（见裁决 2），只碰自己创建的 ID（裁决 3），
    危险端点一律排除（裁决 5）。
    """

    def __init__(
        self,
        client: MidasHttpClient,
        registry: MidasRegistry,
        *,
        product: str,
        project: DedicatedTestProject | None,
        methods: Sequence[str] = WRITE_METHODS,
        limit: int = 0,
        only: Sequence[str] = (),
        emptiness_keys: Sequence[str] | None = None,
        templates: Mapping[str, WritePayloadTemplate] | None = None,
        allow_non_empty: bool = False,
    ) -> None:
        """绑定客户端 / Registry / 专用项目声明（**不**做 I/O）。

        Args:
            client: MIDAS 客户端（凭据由运行环境注入；本模块不接触凭据值）。
            registry: 已装载的 `registry/`。
            product: 数据侧产品键（`GEN_NX` / `CIVIL_NX`）。
            project: 专用测试项目声明；`None` → `probe()` **明确拒绝**（见裁决 2）。
            methods: 参与探测的写入方法；缺省 `POST` / `PUT`（见裁决 5）。
            limit: 最多探测的端点数；`0` 表示不设限（验收用 `limit=3` 等小值）。
            only: 只探测这些 key（给出时**忽略** `limit`）；缺省空 = 全部候选。
            emptiness_keys: 空项目闸门的只读哨兵端点（见裁决 8）；`None` → 用
                `EMPTINESS_GATE_KEYS`（**生产路径的默认**）；传 `()` → **显式**关闭闸门
                （只用于离线单测的编号选择分支，**不**用于真实实例）。
            templates: **显式注入**的请求体模板（`key → WritePayloadTemplate`）；
                `None`（缺省）→ 用数据侧 `registry/live/write_templates.json`
                （经 `MidasRegistry.write_template()` 读取，见裁决 8）。
            allow_non_empty: **显式**允许在非空项目上跑（P141 / R96）；缺省 `False` = 仍要求
                专用项目为空。为真时闸门改为「写前记下被触碰端点的既有编号集合、清理后
                逐端点核对**一字未变**」（见裁决 11）—— 这是**更强**的「只碰自建 ID」判据。
        """
        self._client = client
        self._registry = registry
        self._product = str(product)
        self._project = project
        self._methods = tuple(str(item).upper() for item in methods)
        self._limit = max(int(limit), 0)
        self._only = tuple(str(item) for item in only)
        self._emptiness_keys = tuple(
            EMPTINESS_GATE_KEYS if emptiness_keys is None else emptiness_keys
        )
        self._emptiness_confirmed = False
        self._allow_non_empty = bool(allow_non_empty)
        self._templates: Mapping[str, WritePayloadTemplate] | None = (
            None if templates is None else dict(templates)
        )

    @property
    def project(self) -> DedicatedTestProject | None:
        """专用测试项目声明（`None` = 未声明 → `probe()` 直接拒绝）。"""
        return self._project

    @property
    def product(self) -> str:
        """数据侧产品键。"""
        return self._product

    def template_for(self, key: str) -> WritePayloadTemplate | None:
        """该端点的写路径请求体模板（数据侧声明；显式注入优先，见裁决 8）。

        Args:
            key: Registry key。

        Returns:
            模板；**没有**模板时 `None` —— 调用方回落 `derive_body()`（**不**猜字段）。
        """
        if self._templates is not None:
            return self._templates.get(str(key))
        return self._registry.write_template(str(key))

    def _can_build_request(self, key: str) -> bool:
        """能否为该端点构造**真实**请求体（裁决 12 / `docs/07` §16.1 **R100**）。

        Returns:
            `True` = 已注册的 Transformer（canonical↔native 映射可用）**或** 数据侧
            声明了请求体模板（`registry/live/write_templates.json`）。
            两者都没有 ⇒ 该端点进不了三步链（**不**猜字段、**不**发请求）。
        """
        if TRANSFORMER_REGISTRY.get(transformer_name_for(key)) is not None:
            return True
        return self.template_for(key) is not None

    def _wrapper_for(self, key: str) -> str:
        """该端点在**当前产品**上的请求体包装键（裁决 12）。

        Returns:
            Transformer 已注册 → 用它的 `wrapper_key()`（Schema 绑定）；
            否则用**数据侧**解析结果（`ResolvedEndpoint.wrapper_write`，如 `Assign` / `none`）
            —— 包装键本来就来自 `registry/`，故无 Transformer 也**不**臆造。
        """
        factory = TRANSFORMER_REGISTRY.get(transformer_name_for(key))
        if factory is not None:
            return str(factory(self._registry).wrapper_key())
        resolved = self._registry.resolve(
            key=key, product=self._product, method=self._write_method(key)
        )
        return resolved.wrapper_write

    def candidate_keys(self) -> tuple[str, ...]:
        """可进入三步链的端点 key（见裁决 1 / 5）。

        Returns:
            满足「有写方法 + 有读路径 + 有**已注册**的 Transformer + 非危险形态」的 key，
            顺序取自 `registry.keys()`（确定性）；`limit` 生效时**截断**；
            给了 `only` 时**原样**返回（验收可据此只跑一个端点）。
            ⚠️ Transformer **名可派生但未注册**的端点**不**入候选（P138c 批量实测：否则
            只会白占 `limit` 并记成 `NO_PAYLOAD_TEMPLATE`）。
        """
        if self._only:
            return self._only
        selected: list[str] = []
        for key in self._registry.keys():
            try:
                definition = self._registry.endpoint(key)
            except Exception:  # noqa: BLE001 - 数据缺陷不应打断枚举
                continue
            if self._product not in definition.products:
                continue
            if not definition.enabled or definition.destructive:
                continue
            # ⚠️ **产品级方法覆盖优先**（`docs/07` §7.6 / `registry/README.md` §4；P143 修复）：
            # `CIVIL_DESIGNER` 的 `DB.NODE` / `DB.ELEM` 在数据侧**只有 `GET`**，只看基础
            # `methods` 会把它们误判成候选（实测 `resolve(POST)` 会被拒）。
            methods = self._registry.methods_for(key=key, product=self._product)
            resolved = self._registry.resolve(key=key, product=self._product)
            # ⚠️ `delete_without_body_is_global = True` **不**排除该端点：我们删除时
            # **总是**带路径 key（`docs/07` §6.4），故那一条护栏不会被触发。
            # 真正要排除的是「按主体删全表」的 Designer 形态（见裁决 5）。
            if resolved.delete_all_via_body:
                continue
            if not any(method in methods for method in self._methods):
                continue
            if "GET" not in methods or not definition.read_root:
                continue
            # 裁决 12（P144 / R100）：候选 = 能构造**真实**请求体（Transformer 已注册
            # **或** 有数据侧模板）—— P138c 的「未注册即排除」由此**取代**。
            if not self._can_build_request(key):
                continue
            # 🔴 「能建必须能删」（R100）：没有 `DELETE` 的端点**不**入候选 ——
            # 否则三步链会「建了删不掉」，在真实项目里留下残留。
            if "DELETE" not in methods:
                continue
            selected.append(key)
            if self._limit and len(selected) >= self._limit:
                break
        return tuple(selected)

    async def probe(self) -> WriteProbeReport:
        """逐个端点执行三步链（见裁决 1–6 / 11）。

        Returns:
            `WriteProbeReport`：四态明细 + 计数。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000` —— 未声明专用测试项目（见裁决 2）。
        """
        if self._project is None:
            raise MidasCapabilityError("dedicated_test_project_not_declared")
        # 裁决 8（P138c）：发**任何**写请求之前，先做只读的「项目必须为空」闸门
        await self.assert_project_empty()
        outcomes = [await self.probe_key(key) for key in self.candidate_keys()]
        return WriteProbeReport(product=self._product, outcomes=tuple(outcomes))

    async def probe_key(self, key: str) -> WriteProbeOutcome:
        """对**单个**端点执行三步链（见裁决 1–6 / 8 / 9 / 11）。

        Args:
            key: `registry/` 的端点 key。

        Returns:
            `WriteProbeOutcome`；任何原生失败都被归类而**不**上抛（见裁决 7）。
        """
        # 裁决 8（P138c）：单端点入口也**先**过闸门（`probe()` 已确认则跳过）
        await self.assert_project_empty()
        transformer_name = transformer_name_for(key)
        read = self._registry.resolve(key=key, product=self._product, method="GET")
        write_method = self._write_method(key)
        # ⚠️ 「名字可派生」≠「Transformer 已注册」（P138c）：批量路径**不得**因此抛 `KeyError`，
        # 而应如实归入 `NO_PAYLOAD_TEMPLATE`（**零**写请求）。
        factory = TRANSFORMER_REGISTRY.get(transformer_name)
        template = self.template_for(key)
        # 裁决 12（P144 / `docs/07` §16.1 **R100**）：请求体来源 = Transformer 的
        # canonical↔native 映射 **或** 数据侧声明的请求体模板；**两者都没有**才如实拒绝。
        if factory is None and template is None:
            return WriteProbeOutcome(
                key=key,
                method=write_method or "",
                path=read.uri,
                outcome=WRITE_PROBE_NO_PAYLOAD,
                detail="no_transformer_for_endpoint",
            )
        if not write_method:
            # ⚠️ P143：该**产品**上没有可用的写方法（`product_overrides.<产品>.methods` 覆盖掉了
            # 基础定义）—— 如实记原因，**不**发请求（如 `CIVIL_DESIGNER` 的 `DB.NODE` 只有 `GET`）。
            return WriteProbeOutcome(
                key=key,
                method="",
                path=read.uri,
                outcome=WRITE_PROBE_NO_PAYLOAD,
                detail="no_write_method_for_product",
            )
        write = self._registry.resolve(key=key, product=self._product, method=write_method)
        # 裁决 8（P139）：**优先**用数据侧模板；无模板仍走 `derive_body()`（**不**猜字段）。
        if template is None:
            body = derive_body(self._registry.effective_schema(key))
            payload_source = PAYLOAD_SOURCE_SCHEMA_DERIVED
        else:
            body = template.body
            payload_source = template.source or PAYLOAD_SOURCE_SCHEMA_DERIVED
        if body is None:
            return WriteProbeOutcome(
                key=key,
                method=write_method,
                path=write.uri,
                outcome=WRITE_PROBE_NO_PAYLOAD,
                detail="no_request_body_template",
            )
        wrapper = self._wrapper_for(key)
        created_id = ""
        cleaned = False
        target_sent = False
        prereq_cleaned = False
        created: list[_PlannedPrerequisite] = []
        scope: dict[str, tuple[str, ...]] = {}
        try:
            existing = await self._existing_ids(read)
            scope[key] = existing
            own_id = str(
                max((int(item) for item in existing if str(item).isdigit()), default=0) + 1
            )
            # 裁决 11（P141 / R96）：编号**一律重新分配**（前置 = 该端点 `max + 1`；模板可用
            # `target_id_source` 让**目标自身**取某个前置的编号），并按模板声明的引用写回 body。
            body, planned, created_id = await self._plan(template, body, own_id, scope)
            # 裁决 9（P139）：**先**建模板声明的前置对象（编号即写回后的**实分配**编号）
            for item in planned:
                try:
                    await self._create_prerequisite(item)
                except Exception as error:  # noqa: BLE001 - 前置失败 → 目标如实 FAILED
                    return WriteProbeOutcome(
                        key=key,
                        method=write_method,
                        path=write.uri,
                        outcome=WRITE_PROBE_FAILED,
                        detail=(f"prerequisite_failed:{item.label()}:{_reason_of(error)}"),
                        status_code=_status_of(error),
                        payload_source=payload_source,
                        prerequisites=tuple(entry.label() for entry in created),
                    )
                created.append(item)
            create_request = self._client.build_request(
                write,
                operation=f"LIVE.WRITE.{key}",
                body=body,
                wrapper=wrapper,
                item_id=created_id,
                allow_unverified=True,
            )
            status = await self._send(create_request)
            target_sent = True
            read_back = created_id in await self._existing_ids(read)
            # ⚠️ 删除必须用 **DELETE** 方法的解析结果（`docs/07` §6.4 的路径 key）
            delete_request = self._client.build_request(
                self._registry.resolve(key=key, product=self._product, method="DELETE"),
                operation=f"LIVE.WRITE.{key}.DELETE",
                item_ids=(created_id,),
            )
            await self._send(delete_request)
            cleaned = True
            await self._cleanup_prerequisites(created)
            prereq_cleaned = True
            # 裁决 11（P141 / R96）：**显式**允许非空项目时，清理后核对「既有编号集合一字未变」
            # —— 这是非空场景下的**主**判据；空项目闸门已保证没有既有编号，无需再读一遍。
            drift = await self._scope_drift(scope) if self._allow_non_empty else ()
            passed = read_back and not drift
            return WriteProbeOutcome(
                key=key,
                method=write_method,
                path=write.uri,
                outcome=WRITE_PROBE_PASSED if passed else WRITE_PROBE_FAILED,
                created_id=created_id,
                read_back=read_back,
                deleted=True,
                detail=(
                    "create_read_delete_confirmed"
                    if passed
                    else ("existing_id_set_changed" if drift else "read_back_missing")
                ),
                status_code=status,
                payload_source=payload_source,
                prerequisites=tuple(entry.label() for entry in created),
            )
        except Exception as error:  # noqa: BLE001 - 见裁决 7：归类而不上抛
            return WriteProbeOutcome(
                key=key,
                method=write_method,
                path=write.uri,
                outcome=WRITE_PROBE_FAILED,
                created_id=created_id,
                read_back=False,
                deleted=False,
                detail=_reason_of(error),
                status_code=_status_of(error),
                payload_source=payload_source,
                prerequisites=tuple(entry.label() for entry in created),
            )
        finally:
            # 兜底（见裁决 3 / 9 / 11）：先删**自己创建的**目标编号，再**逆序**删前置对象
            if created_id and target_sent and not cleaned:
                await self._best_effort_delete(key, created_id)
            if not prereq_cleaned:
                await self._cleanup_prerequisites(created)

    async def _create_prerequisite(self, item: _PlannedPrerequisite) -> None:
        """创建一个**前置对象**（见裁决 9 / 11；失败即上抛，由 `probe_key` 归类）。

        Args:
            item: 已定编号的前置对象（`item_id` = **实分配**编号，`body` = 已写回引用的请求体）。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000` —— 前置端点解析失败 / 没有可用写方法
                （数据缺陷**不**静默跳过）。
        """
        prerequisite = item.prerequisite
        # 裁决 12（P144 / R100）：前置的包装键同样「Transformer 优先、否则取数据侧」
        # （`_wrapper_for`）—— **不**再要求前置必须有已注册的 Transformer。
        write = self._registry.resolve(
            key=prerequisite.key,
            product=self._product,
            method=self._write_method(prerequisite.key),
        )
        request = self._client.build_request(
            write,
            operation=f"LIVE.WRITE.PREREQ.{prerequisite.key}",
            body=item.body,
            wrapper=self._wrapper_for(prerequisite.key),
            item_id=item.item_id,
            allow_unverified=True,
        )
        await self._send(request)

    async def _cleanup_prerequisites(self, created: Sequence[_PlannedPrerequisite]) -> None:
        """**逆序**删除本次创建的前置对象（见裁决 9；只碰**实分配**编号，失败忽略）。"""
        for item in reversed(list(created)):
            await self._best_effort_delete(item.prerequisite.key, item.item_id)

    async def assert_project_empty(self) -> None:
        """发**写请求前**的只读闸门：专用测试项目必须为空（见裁决 8 / P138c）。

        对每个哨兵端点（`EMPTINESS_GATE_KEYS`）做**只读** `GET`，用数据侧解包链读既有编号：
        只要有一个端点非空 → **拒绝**，且**零**写请求已发出。一个哨兵都读不到时同样**拒绝**
        （**不**在无法核对的情况下盲写）。`probe()` / `probe_key()` 都会先调用本方法。

        `allow_non_empty=True` 时（P141 / R96）**不**要求为空：写前记下被触碰端点的既有编号
        集合，清理后由 `probe_key()` 的 `_scope_drift()` 逐端点核对**一字未变**（见裁决 11）。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000`：
                `dedicated_test_project_not_empty`（带 `endpoint` / `existing` 诊断字段，
                **不含**响应体原文与凭据），或 `dedicated_test_project_emptiness_unverified`
                （所有哨兵都读不到）。
        """
        if self._emptiness_confirmed or not self._emptiness_keys:
            return
        if self._allow_non_empty:
            # 裁决 11（P141 / R96）：**显式**允许非空项目 → 不要求为空，改由 `_scope_drift()`
            # 在清理后逐端点核对「既有编号集合一字未变」—— 比空项目闸门**更强**的判据。
            self._emptiness_confirmed = True
            return
        checked = 0
        for key in self._emptiness_keys:
            try:
                definition = self._registry.endpoint(key)
            except Exception:  # noqa: BLE001 - 数据侧缺该哨兵不应打断闸门
                continue
            if self._product not in definition.products or not definition.enabled:
                continue
            if "GET" not in definition.methods:
                continue
            try:
                resolved = self._registry.resolve(key=key, product=self._product, method="GET")
                existing = await self._existing_ids(resolved)
            except Exception:  # noqa: BLE001 - 该哨兵不可读 → 不计入核对
                continue
            checked += 1
            if existing:
                raise MidasCapabilityError(
                    "dedicated_test_project_not_empty",
                    endpoint=key,
                    existing=len(existing),
                )
        if not checked:
            raise MidasCapabilityError("dedicated_test_project_emptiness_unverified")
        self._emptiness_confirmed = True

    # ===== 内部 =====

    async def _plan(
        self,
        template: WritePayloadTemplate | None,
        owner_body: Any,
        own_id: str,
        scope: dict[str, tuple[str, ...]],
    ) -> tuple[Any, tuple[_PlannedPrerequisite, ...], str]:
        """把模板里声明的编号**重新分配**到自建编号，并写回所有声明的引用路径（见裁决 11）。

        - 前置编号 = 该端点既有编号的 `max + 1`（同一端点的多个前置依次 +1）；
        - `target_id_source = <key>#<item_id>` → **目标自身**的编号取该前置分配到的编号
          （如 `DB.CONS` 的 `Assign` 键就是它那个节点号）；缺省 = `own_id`；
        - `id_source = "target"` 的前置反过来取**目标**编号；
        - `references[].in` = `OWNER_BODY_LABEL`（目标自身 body）或同一模板里另一个前置的
          `<key>#<item_id>`；模板的 `self_references` 把**目标自身**编号写回目标 body。

        Args:
            template: 该端点的数据侧模板（`None` / 无前置链 → 原样返回）。
            owner_body: 模板声明的目标请求体。
            own_id: 该端点既有编号的 `max + 1`（`target_id_source` 缺省时的目标编号）。
            scope: 写前快照（就地补充被触碰的前置端点的既有编号集合）。

        Returns:
            `(改写后的目标请求体, 已定编号的前置对象, 目标的**实分配**编号)`。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000` —— 模板声明的引用路径 / 承载 body /
                目标编号来源不存在（数据缺陷**不**静默跳过）。
        """
        if template is None or not template.prerequisites:
            return owner_body, (), own_id
        bodies: dict[str, Any] = {OWNER_BODY_LABEL: json.loads(json.dumps(owner_body))}
        for prerequisite in template.prerequisites:
            bodies[prerequisite.label()] = json.loads(json.dumps(prerequisite.body))
        next_ids: dict[str, int] = {}
        allocated: dict[str, str] = {}
        # ① 先定「取自己端点 max + 1」的前置编号
        for prerequisite in template.prerequisites:
            if prerequisite.id_source == ID_SOURCE_TARGET:
                continue
            allocated[prerequisite.label()] = str(
                await self._next_id(prerequisite.key, next_ids, scope)
            )
        # ② 目标的编号：声明的那个前置的编号，否则自己端点的 max + 1
        target_id = own_id
        if template.target_id_source:
            if template.target_id_source not in allocated:
                raise MidasCapabilityError(
                    "write_template_target_id_source_unknown", endpoint=template.key
                )
            target_id = allocated[template.target_id_source]
        # ③ 反向依赖：`id_source = "target"` 的前置取**目标**编号
        for prerequisite in template.prerequisites:
            if prerequisite.id_source == ID_SOURCE_TARGET:
                allocated[prerequisite.label()] = target_id
        # ④ 写回：目标自身编号 + 各前置编号在其声明的路径上
        for path in template.self_references:
            _set_at(bodies[OWNER_BODY_LABEL], path, int(target_id))
        planned: list[_PlannedPrerequisite] = []
        for prerequisite in template.prerequisites:
            item_id = allocated[prerequisite.label()]
            for reference in prerequisite.references:
                container = bodies.get(reference.in_label)
                if container is None:
                    raise MidasCapabilityError(
                        "write_template_reference_unknown_body", endpoint=prerequisite.key
                    )
                _set_at(container, reference.path, int(item_id))
            planned.append(
                _PlannedPrerequisite(
                    prerequisite=prerequisite,
                    item_id=item_id,
                    body=bodies[prerequisite.label()],
                )
            )
        return bodies[OWNER_BODY_LABEL], tuple(planned), target_id

    async def _next_id(
        self, key: str, next_ids: dict[str, int], scope: dict[str, tuple[str, ...]]
    ) -> int:
        """该端点**下一个自建编号**（见裁决 11）。

        首次用到该端点时读一次既有编号（同时计入写前快照），此后同一端点的多个前置依次 `+1`。
        """
        if key not in next_ids:
            resolved = self._registry.resolve(key=key, product=self._product, method="GET")
            existing = await self._existing_ids(resolved)
            scope[key] = existing
            next_ids[key] = (
                max((int(item) for item in existing if str(item).isdigit()), default=0) + 1
            )
        value = next_ids[key]
        next_ids[key] = value + 1
        return value

    async def _scope_drift(self, scope: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
        """清理后逐端点核对「既有编号集合**一字未变**」（见裁决 11）。

        Returns:
            编号集合发生变化的端点 key（升序）；空 = 本次探测**没有**碰任何既有编号。
            读不到（`GET` 失败）**如实**记为漂移 —— **不**假定干净。
        """
        drifted: list[str] = []
        for key, before in sorted(scope.items()):
            try:
                resolved = self._registry.resolve(key=key, product=self._product, method="GET")
                after = await self._existing_ids(resolved)
            except Exception:  # noqa: BLE001 - 读不到即如实记为漂移
                drifted.append(key)
                continue
            if sorted(after) != sorted(before):
                drifted.append(key)
        return tuple(drifted)

    def _write_method(self, key: str) -> str:
        """该端点上第一个可用的写入方法（见裁决 5）。"""
        methods = self._registry.methods_for(key=key, product=self._product)
        for method in self._methods:
            if method in methods:
                return method
        return ""

    async def _existing_ids(self, resolved: ResolvedEndpoint) -> tuple[str, ...]:
        """读回端点当前的编号集合（按数据侧解包链逐层取；**不**猜结构）。"""
        payload = await self._client.send(
            self._client.build_request(resolved, operation="LIVE.WRITE.LIST")
        )
        node: Any = payload
        for step in resolved.read_path:
            if not isinstance(node, Mapping) or step not in node:
                return ()
            node = node[step]
        if isinstance(node, Mapping):
            return tuple(str(item) for item in node)
        if isinstance(node, Sequence) and not isinstance(node, str):
            return tuple(
                str(item.get("id") or item.get("ID") or "")
                for item in node
                if isinstance(item, Mapping)
            )
        return ()

    async def _send(self, request: Any) -> int:
        """发出一条已构造的请求，返回**原生**状态码（响应体**不**落任何字段）。

        P139（见裁决 10）：状态码来自**响应**（`MidasHttpClient.send_result()`），
        不再是常量 `200` —— `2xx` 的原生状态码原样回传；`4xx` / `5xx` 由客户端归一化后
        抛出，`_status_of()` 从异常 `details.status_code` 取**同一**事实。
        """
        result = await self._client.send_result(request)
        return int(result.status_code)

    async def _best_effort_delete(self, key: str, item_id: str) -> None:
        """兜底删除**自己创建的**编号（失败只忽略，不影响原始结论）。"""
        try:
            delete = self._registry.resolve(key=key, product=self._product, method="DELETE")
            request = self._client.build_request(
                delete, operation="LIVE.WRITE.CLEANUP", item_ids=(item_id,)
            )
            await self._client.send(request)
        except Exception:  # noqa: BLE001 - 清理路径不得掩盖原始结论
            return None


def _set_at(body: Any, path: Sequence[Any], value: int) -> None:
    """把 `path` 指向的位置设成 `value`（见裁决 11）。

    Raises:
        MidasCapabilityError: `STRUCTAI-3000` —— 路径在 body 里不存在
            （数据缺陷**不**静默跳过）。
    """
    node: Any = body
    for step in path[:-1]:
        try:
            node = node[step]
        except (KeyError, IndexError, TypeError) as error:
            raise MidasCapabilityError("write_template_reference_path_missing") from error
    last = path[-1]
    if isinstance(node, list) and isinstance(last, int) and -len(node) <= last < len(node):
        node[last] = value
        return
    if isinstance(node, dict) and last in node:
        node[last] = value
        return
    raise MidasCapabilityError("write_template_reference_path_missing")


def _reason_of(error: Exception) -> str:
    """非敏感原因词（**只**取 `details.reason` / 异常类名，**不**回显 message）。"""
    details = getattr(error, "details", None)
    if isinstance(details, Mapping):
        reason = details.get("reason")
        if reason:
            return str(reason)
    return type(error).__name__


def _status_of(error: Exception) -> int:
    """原生状态码（从 `details.status_code` 取；取不到为 `0`）。"""
    details = getattr(error, "details", None)
    if isinstance(details, Mapping):
        value = details.get("status_code")
        if isinstance(value, int):
            return value
    return 0
