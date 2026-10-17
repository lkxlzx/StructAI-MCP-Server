"""Infrastructure · Adapters · MIDAS · Adapter —— 适配器实现（`docs/07` §7.1）。

权威来源
--------
- `docs/07` §7.1（唯一入口）—— MIDAS 代码**只能**出现在本子包；Adapter 实现
  `EngineeringSoftwareAdapter` 的八个方法（`docs/02` §32），Core 侧只经该契约调用。
- `docs/07` §7.2 / §7.3 / §7.4 / §7.5 / §7.6 —— Registry 接入、由数据驱动的请求构造、
  Transformer、错误归一化、实测行为约束。
- `docs/07` §6（全章）—— Operation → endpoint 编排（`operations.py`）。
- `docs/04` §3.1 / §3.2（职责边界）—— Adapter 负责协议 / 认证 / 转换 / 重试语义；
  **不**负责权限、租户、任务编排（那是 Core）。
- `docs/04` §62（Version Adapter Manifest）—— `midas.civil` / `CIVIL NX` / `2025,2026` / `REST`。
- `docs/04` §76（GEN NX Adapter）—— 共享 HTTP / 凭据 / Registry / Transformer 框架，
  仅 product / mapping / capability / result 不同。

落地裁决（只补实现手段，不改契约）
--------------------------------
1. **一个类承载两个产品视图**：`docs/04` §76 的 GEN NX 与 CIVIL NX 共享**同一个**
   实现（差异全在 `registry/` 数据与 `product_overrides` 里）。P119 的注册键固定为
   `(MIDAS, CIVIL NX)`（`docs/07` §7.1），实例级产品经连接配置 `product` 选择
   （`CIVIL NX` / `GEN NX`），**不**为每个产品复制一个类。
2. **版本来自实例声明**：`registry/` 无版本字段（`registry/README.md` §4），
   故 `get_version()` 只回连接配置 / Manifest 声明里的版本，探测不到即空串，**不**猜。
3. **`cancel()` 明确失败**：`registry/manifest.json` 里**没有**取消类端点，
   故本批**不**伪造取消（`docs/07` §14.4 / `docs/02` §30）——
   抛 `STRUCTAI-3000`（`details.reason = "cancel_not_supported"`），
   由 Core 的取消路径按 R48 保留 `CANCEL_REQUESTED`。
4. **`allow_unverified` 只服务 Contract Test**：生产路径下 `verification_status != VERIFIED`
   一律拒绝（`docs/04` §130；见 `client.py` 裁决 5）。
5. **组合 Operation 按步骤顺序执行**：`BUILD.*` / `MODEL.COPY/MOVE/MIRROR/PATTERN/
   GENERATE_GRID` 逐步调用底层端点（`docs/07` §6.5 / §16 R2）；某一步缺少对应载荷 →
   该步**跳过**（记入 `skipped`），**不**臆造空载荷。
6. **`MODEL.LOAD.ASSIGN` 按荷载类型只走一步**：`docs/07` §6.3 列了六个荷载端点，
   本次调用只执行 `load_type` 对应的那一个（`transforms.LOAD_TRANSFORMERS` 的键）。
7. **结果过滤在 canonical 侧**（`transforms.py` 裁决 8）：`node_ids` / `element_ids` /
   `load_cases` 只作用于**已解析**的行。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain`、`app.config`、Adapter 基座与同包的
`registry.py` / `client.py` / `transforms.py` / `operations.py` / `capabilities.py` /
`health.py` / `manifest.py` / `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK，
**不**依赖 `app.interfaces` / `app.application`，**不**写数据库。
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Final

from app.config.settings import Settings
from app.infrastructure.adapters.base.adapter import BaseAdapter
from app.infrastructure.adapters.midas.capabilities import (
    DesignCodeProbe,
    capability_codes,
)
from app.infrastructure.adapters.midas.client import (
    MIDAS_BASE_URL_ENV,
    MIDAS_MAPI_KEY_ENV,
    BuiltRequest,
    MidasEnvironmentCredential,
    MidasHttpClient,
)
from app.infrastructure.adapters.midas.errors import (
    MidasAPIError,
    MidasCapabilityError,
    MidasConnectionError,
    MidasValidationError,
)
from app.infrastructure.adapters.midas.health import HEALTH_CHECK_ENDPOINT, MidasHealthChecker
from app.infrastructure.adapters.midas.manifest import (
    MIDAS_ADAPTER_NAME,
    MIDAS_CAPABILITIES,
    MIDAS_PRODUCT,
    MIDAS_PROTOCOLS,
    MIDAS_SUPPORTED_VERSIONS,
    MIDAS_VENDOR,
    registry_product_key,
)
from app.infrastructure.adapters.midas.operations import (
    LOAD_STEP_BY_TYPE,  # noqa: F401
    EndpointStep,
    OperationPlan,
    plan_for,
    select_steps,
)
from app.infrastructure.adapters.midas.registry import MidasRegistry, ResolvedEndpoint
from app.infrastructure.adapters.midas.spec_guard import guard_spec_values
from app.infrastructure.adapters.midas.transforms import (
    TRANSFORMER_REGISTRY,
    DesignResultTransformer,
    DisplacementTransformer,
    ElementForceTransformer,
    ReactionTransformer,
    ResultRequestTransformer,
    parse_table,
)

__all__ = [
    "LOAD_STEP_BY_TYPE",
    "MIDAS_INSTANCE_PRODUCTS",
    "MidasAdapter",
    "WRITE_INTENT_TRANSFORMERS",
]

MIDAS_INSTANCE_PRODUCTS: Final[tuple[str, ...]] = ("CIVIL NX", "GEN NX")
"""`docs/04` §61 / §62：本 Adapter 服务的两个产品（共享实现，见裁决 1）。"""


WRITE_INTENT_TRANSFORMERS: Final[dict[str, str]] = {
    "write_node": "midas.node.v1",
    "write_element": "midas.elem.v1",
    "write_material": "midas.matl.v1",
    "write_section": "midas.sect.v1",
    "write_boundary": "midas.cons.v1",
    "write_load_case": "midas.stld.v1",
}
"""写步骤的 `intent` → Transformer 名（`write_load` 走 `LoadTransformer` 分派）。"""

_RESULT_ROW_TRANSFORMERS: Final[dict[str, Any]] = {
    "DISPLACEMENTG": DisplacementTransformer,
    "DISPLACEMENTL": DisplacementTransformer,
    "REACTIONG": ReactionTransformer,
    "REACTIONL": ReactionTransformer,
    "REACTIONLSURFACESPRING": ReactionTransformer,
    "BEAMFORCE": ElementForceTransformer,
    "TRUSSFORCE": ElementForceTransformer,
    "CODE-TABLE": DesignResultTransformer,
}
"""结果 `TABLE_TYPE` → 行解析器（`docs/07` §6.7 / §6.8）。"""


class MidasAdapter(BaseAdapter):
    """MIDAS CIVIL NX / GEN NX 适配器（`docs/07` §7.1；`docs/04` §4 / §76）。"""

    name: ClassVar[str] = MIDAS_ADAPTER_NAME
    vendor: ClassVar[str] = MIDAS_VENDOR
    product: ClassVar[str] = MIDAS_PRODUCT
    supported_versions: ClassVar[tuple[str, ...]] = MIDAS_SUPPORTED_VERSIONS
    protocols: ClassVar[tuple[str, ...]] = MIDAS_PROTOCOLS
    capabilities: ClassVar[tuple[str, ...]] = MIDAS_CAPABILITIES

    def __init__(
        self,
        *,
        registry: MidasRegistry | None = None,
        registry_root: str | None = None,
        credential_provider: Any = None,
        transport: Any = None,
        environ: Mapping[str, str] | None = None,
        allow_unverified: bool = False,
        allow_native_crash_risk: bool = False,
        product: str | None = None,
    ) -> None:
        """构造（**不**做 I/O；见裁决 4 的 `allow_unverified`）。"""
        super().__init__()
        self._registry = registry
        self._registry_root = registry_root
        self._credentials = credential_provider
        self._transport = transport
        self._environ: Mapping[str, str] = os.environ if environ is None else environ
        self._allow_unverified = bool(allow_unverified)
        # ⚠️ **P164-c（事故驱动）**：`NATIVE_CRASH_ENDPOINTS`（`client.py`）里的设计执行
        # 端点**实测会把 MIDAS Gen NX 打崩**（`wg_db.dll` 访问违例）。默认**拦死**；
        # 只有「已取得用户明确同意、且知道会打崩他的软件」时才显式打开。
        self._allow_native_crash_risk = bool(allow_native_crash_risk)
        self._client: MidasHttpClient | None = None
        self._configured_product = str(product) if product else ""
        self._product = self._configured_product or MIDAS_PRODUCT
        # ⚠️ **P160c / R143**：核心**自己确知**的「项目文件路径」——
        # `DOC.NEW` 清空、`DOC.OPEN` / `DOC.SAVEAS` **成功后**置上。
        # 用途：`DOC.SAVE` 在没有路径的项目上会弹「另存为」**模态窗口**并**挂起 API**
        # （实测事故）⇒ 只有**确知**有路径才允许发 `SAVE`。
        self._project_path: str | None = None
        self._product_key = registry_product_key(self._product)
        self._solver = ""
        self._declared_version = ""

    # ===== 诊断（只读）=====

    @property
    def product_key(self) -> str:
        """当前实例的**数据侧**产品键（`CIVIL_NX` / `GEN_NX`；见裁决 1）。"""
        return self._product_key

    @property
    def registry(self) -> MidasRegistry | None:
        """已装载的 Registry（未连接时为 `None`）。"""
        return self._registry

    @property
    def allow_unverified(self) -> bool:
        """是否处于 Contract Test 模式（见裁决 4）。"""
        return self._allow_unverified

    @property
    def allow_native_crash_risk(self) -> bool:
        """是否已显式放开「已知会打崩宿主程序」的端点（**默认 `False`**；P164-c）。"""
        return self._allow_native_crash_risk

    # ===== 生命周期（`docs/02` §10 / §54）=====

    async def _connect(self, config: dict[str, Any]) -> None:
        """建立连接：装载 Registry → 构造客户端 → 健康探测（`docs/02` §54）。

        Raises:
            MidasConnectionError: `STRUCTAI-2000`，Base URL / Registry 不可用。
        """
        self._product = str(config.get("product") or self._configured_product or MIDAS_PRODUCT)
        self._product_key = registry_product_key(self._product)
        self._solver = str(config.get("solver") or "")
        self._declared_version = str(config.get("version") or "")
        base_url = str(config.get("base_url") or self._environ.get(MIDAS_BASE_URL_ENV) or "")
        if not base_url:
            raise MidasConnectionError("base_url_not_configured")
        if self._registry is None:
            root = config.get("registry_root") or self._registry_root or Settings().registry_root
            self._registry = MidasRegistry.load(str(root))
        self._client = MidasHttpClient(
            base_url,
            self._credentials or MidasEnvironmentCredential(self._environ),
            str(config.get("secret_ref") or MIDAS_MAPI_KEY_ENV),
            transport=self._transport,
        )

    async def _disconnect(self) -> None:
        """关闭底层连接池（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            await client.close()

    async def get_version(self) -> str:
        """软件版本（见裁决 2：只回实例声明，探测不到即空串）。"""
        return self._declared_version

    async def get_capabilities(self) -> list[str]:
        """运行时能力清单（`docs/07` §7.4；能力码取自落库的 41 条词表）。"""
        if self._registry is None:
            return []
        return capability_codes(self._registry, product=self._product_key)

    async def health_check(self) -> dict[str, Any]:
        """健康检查（`docs/02` §25 的四键形状；见 `health.py`）。"""
        if self._client is None or self._registry is None:
            return {
                "healthy": False,
                "state": "ERROR",
                "version": self._declared_version,
                "latency_ms": 0,
                "error": {"type": "NotConnectedError"},
            }
        resolved = self._registry.resolve(key=HEALTH_CHECK_ENDPOINT, product=self._product_key)
        self._last_health = await MidasHealthChecker(self._client).check(
            version=self._declared_version, path=resolved.uri
        )
        return dict(self._last_health)

    async def cancel(self, task_id: str) -> None:
        """**明确失败**：数据里没有取消类端点（见裁决 3）。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000`，`details.reason = "cancel_not_supported"`。
        """
        raise MidasCapabilityError("cancel_not_supported", task_id=str(task_id))

    # ===== 设计规范探测（`docs/07` §6.12）=====

    async def design_code_supported(self, *, material: str, code: str) -> bool:
        """请求的规范是否可用（零副作用探测；结果只留连接会话）。

        Raises:
            MidasCapabilityError: 未连接（无法探测）。
        """
        if self._client is None:
            raise MidasCapabilityError("adapter_not_connected")
        return await DesignCodeProbe(self._client).supported(material=material, code=code)

    # ===== 执行（`docs/02` §32 / §48；`docs/07` §7.3）=====

    async def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        context: Any,
    ) -> dict[str, Any]:
        """执行一个规范化 Operation（`docs/02` §32）。

        Args:
            operation: 规范化 Operation 名（如 `BUILD.COLUMN`）——**不是**任何端点。
            parameters: 规范化参数（`docs/02` §24 的 `input_schema` 口径）。
            context: 执行上下文（Adapter 只经 `adapter_context_from()` 取用）。

        Returns:
            规范化结果：`{operation, product, adapter, executed[], skipped[], data{}}`。

        Raises:
            MidasCapabilityError: 未连接 / Operation 未映射 / 路由不到。
            MidasValidationError: 参数不足或语义非法（**不**臆造载荷）。
            StructAIError: 由 `execute_normalized()` 归一化后的 20 码异常。
        """
        if self._client is None or self._registry is None:
            raise MidasCapabilityError("adapter_not_connected")
        plan = plan_for(str(operation))
        steps = self._steps_for(plan, parameters)
        payloads = _build_payloads(parameters)
        executed: list[dict[str, Any]] = []
        skipped: list[str] = []
        data: dict[str, Any] = {}
        for step in steps:
            if not _has_payload(step, parameters, payloads):
                skipped.append(step.key)
                continue
            outcome = await self._run_step(
                operation=str(operation), step=step, parameters=parameters, payloads=payloads
            )
            executed.append(outcome)
            data[step.intent] = outcome.get("data")
        return {
            "operation": str(operation),
            "product": self._product,
            "adapter": self.name,
            "executed": executed,
            "skipped": skipped,
            "data": data,
        }

    # ===== 步骤选择（`docs/07` §6.3 / §6.5）=====

    def _steps_for(
        self, plan: OperationPlan, parameters: Mapping[str, Any]
    ) -> tuple[EndpointStep, ...]:
        """选定本次调用的步骤（`operations.select_steps`；见裁决 5 / 6）。

        分派（荷载按类型 / 校核按材料 × 构件）**只**在 `operations.py` 里实现一次，
        本方法只是转发，避免出现第二份判定（`docs/02` §61）。
        """
        return select_steps(plan.operation, parameters)

    # ===== 单步执行 =====

    async def _run_step(
        self,
        *,
        operation: str,
        step: EndpointStep,
        parameters: Mapping[str, Any],
        payloads: Mapping[str, Any],
    ) -> dict[str, Any]:
        """执行一步（`docs/07` §7.3 的构造 + 发送）。"""
        resolved = self._require_registry().resolve(
            key=step.key, product=self._product_key, method=step.method
        )
        if step.intent == "read":
            return await self._read(operation, step, resolved)
        if step.intent == "result":
            return await self._result(operation, step, resolved, parameters)
        if step.intent == "analyze":
            return await self._arguments_step(
                operation,
                step,
                resolved,
                parameters,
                transformer_name="midas.anal.v1",
                arguments=_analysis_arguments(parameters),
            )
        if step.intent == "design":
            # ⚠️ **P164-c / R154（事故驱动，**结构性防护**）**：`_design_arguments()` 产出的是
            # **小写 canonical 键**（`perform_type` / `elements` / …），而原生 `*-ANAL` 要的是
            # `PERFORM_TYPE` / `ELEMS.KEYS`。**没有转换器时 `_arguments_step` 会把 canonical 体
            # 原样发出去** ⇒ 原生收到形状不符的设计体 ⇒ **MIDAS Gen NX 直接崩溃**
            # （实测：`DESIGN.RC.KDS-41-20-2022.BD-ANAL`，恢复文件 `p164c-concrete_restore.mgbx`）。
            # ⇒ 宁可在**发请求前**明确失败，也不让一个畸形体把宿主程序打崩。
            if not step.transformer:
                raise MidasValidationError(
                    "design_transformer_missing",
                    endpoint=str(step.key),
                    operation=str(operation),
                    note=(
                        "`intent=design` 的步骤**必须**有转换器：`_design_arguments()` 产出的是"
                        "小写 canonical 键，没有转换器就会把畸形体发给原生设计引擎"
                        "（实测会**打崩** MIDAS Gen NX）。"
                    ),
                )
            return await self._arguments_step(
                operation,
                step,
                resolved,
                parameters,
                transformer_name=step.transformer,
                arguments=_design_arguments(parameters),
            )
        if step.intent == "design_result":
            return await self._design_result(operation, step, resolved, parameters)
        if step.intent in VIEW_ARGUMENT_CHANNELS:
            # ⚠️ **P160d / R148**：`VIEW.*` 的三步**形状不同** ⇒ 各走**自己的**参数通道
            # （`display` / `result_graphic` / `capture`）—— 共用一份 `arguments` 时，
            # 传并集会被 `VIEW.CAPTURE` 的白名单转换器**拒**，传子集则 `VIEW.DISPLAY` **400**。
            return await self._arguments_step(
                operation,
                step,
                resolved,
                parameters,
                transformer_name=step.transformer,
                arguments=dict(parameters.get(VIEW_ARGUMENT_CHANNELS[step.intent]) or {}),
            )
        if step.intent == "view":
            return await self._arguments_step(
                operation,
                step,
                resolved,
                parameters,
                transformer_name=step.transformer,
                arguments=dict(parameters.get("arguments") or {}),
            )
        if step.intent == "write_doc":
            # ⚠️ **P160 / R143**：DOC 的**文件操作**必须先过「项目路径」守卫（见 `_doc_arguments`）。
            arguments = _doc_arguments(step, parameters)
            if step.key == "DOC.SAVE" and self._project_path is None:
                # ⚠️ **P160c 实测（R146）**：`SAVE` **带**路径 ⇒ **不**弹窗，但原生**忽略**它
                # ⇒ 若项目**自身无路径**，这次 `SAVE` 会**静默什么都不做**（假成功）。
                # ⇒ 故这里按**核心自己确知**的状态拦（`NEW` 清、`SAVEAS`/`OPEN` 成功后置）。
                raise MidasValidationError(
                    "project_path_not_established",
                    endpoint=step.key,
                    hint=(
                        "本项目**尚无**文件路径 ⇒ 先 `SAVE_AS`（带项目路径）或 `OPEN`。"
                        "⚠️ 直接发 `SAVE` 即使**带**路径，原生也会**忽略**它 ⇒ 会**静默不保存**。"
                    ),
                )
            result = await self._arguments_step(
                operation,
                step,
                resolved,
                parameters,
                transformer_name=step.transformer,
                arguments=arguments,
            )
            self._remember_project_path(step, parameters)
            return result
        if step.intent.startswith("delete_"):
            return await self._delete(operation, step, resolved, parameters)
        return await self._write(operation, step, resolved, payloads, parameters=parameters)

    def _require_registry(self) -> MidasRegistry:
        """取已装载 Registry（未连接 → `STRUCTAI-3000`）。"""
        if self._registry is None:
            raise MidasCapabilityError("adapter_not_connected")
        return self._registry

    def _remember_project_path(self, step: EndpointStep, parameters: Mapping[str, Any]) -> None:
        """按**成功**的 DOC 文件操作记住 / 清除项目路径（`docs/07` §16.1 **R143**）。

        ⚠️ 只在**已经发出且未抛错**之后调用 ⇒ 走到这里即视为成功。
        """
        # ⚠️ **P160c 实测（R145）**：`DOC.NEW` 的体**只能**是 `{}` —— 带路径时原生**接受但忽略**
        # （`200` 假成功），项目**仍无路径** ⇒ 核心**必须**在这里**清空**，否则后续 `SAVE`
        # 会被放行并弹「另存为」窗口挂起 API。**唯一**给项目路径的办法是 `SAVE_AS` / `OPEN`。
        if step.key == "DOC.NEW":
            self._project_path = None
        elif step.key in {"DOC.OPEN", "DOC.SAVEAS"}:
            raw_path = parameters.get("project_path")
            if raw_path is None and isinstance(parameters.get("arguments"), str):
                raw_path = parameters.get("arguments")
            self._project_path = str(raw_path).strip() if raw_path is not None else None

    async def _read(
        self, operation: str, step: EndpointStep, resolved: ResolvedEndpoint
    ) -> dict[str, Any]:
        """读步骤：GET → 按 `read_root` 解包 → 可选 Transformer。

        ⚠️ DB 类端点的读响应是**编号键映射**（`{<read_root>: {"1": {...}}}`，
        `registry/README.md` §4 的 `wrapper.read_root`）；编号进 canonical 的 `id`
        （`docs/04` §23 的 `native_id → canonical_id` 映射）。
        """
        request = self._build(operation, resolved, body=None, wrapper="none")
        response = await self._send(request)
        payload = _unwrap(response, resolved)
        transformer = (
            TRANSFORMER_REGISTRY[step.transformer](self._require_registry())
            if step.transformer and step.transformer in TRANSFORMER_REGISTRY
            else None
        )
        canonical: list[Any] = []
        for item_id, native_item in _items_of(payload):
            mapped = transformer.from_native(native_item) if transformer else dict(native_item)
            if item_id is not None:
                mapped.setdefault("id", item_id)
            canonical.append(mapped)
        return {
            "endpoint": resolved.definition.key,
            "method": request.method,
            "uri": request.uri,
            "intent": step.intent,
            "items": canonical,
            "data": canonical,
        }

    async def _write(
        self,
        operation: str,
        step: EndpointStep,
        resolved: ResolvedEndpoint,
        payloads: Mapping[str, Any],
        *,
        parameters: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """写步骤：按 intent 取载荷 → Transformer → 构造 → 发送（见裁决 5）。"""
        items = list(payloads.get(step.intent) or [])
        if not items:
            raise MidasValidationError(
                "step_payload_missing", endpoint=resolved.definition.key, intent=step.intent
            )
        transformer_name = WRITE_INTENT_TRANSFORMERS.get(step.intent) or step.transformer
        transformer = (
            self._build_transformer(transformer_name, resolved, parameters)
            if transformer_name
            else None
        )
        prepared = [
            self._prepare_item(item, transformer=transformer, resolved=resolved) for item in items
        ]
        wrapper = prepared[0][1]
        items_style = prepared[0][2]
        bodies = [body for body, _wrapper, _style in prepared]
        results: list[dict[str, Any]] = []
        if items_style:
            # ⚠️ **R128（P155 修复）**：`ITEMS` 形态的 `Assign` **每条一个请求**，外层键 = 该条目的
            # **编号**（`{"Assign": {"<编号>": {"ITEMS": […]}}}`）—— 与**数据侧实测可用**的形状一致
            # （`write_probe` 把整份模板体当条目 + `_wrap` 的非 `ITEMS` 分支按键包装）。
            # 外层键**必须**是存在的对象编号：无效键时原生**静默 `200` 而不落库**（假成功陷阱）
            # ⇒ 取不到键就**明确失败**（`_item_key`），**不**臆造 `1`。
            for body, item in zip(bodies, items, strict=True):
                request = self._build(
                    operation,
                    resolved,
                    body=[body],
                    wrapper=wrapper,
                    items_style=True,
                    item_id=_item_key(item, transformer, endpoint=resolved.definition.key),
                )
                results.append(await self._send(request))
        else:
            for body, item in zip(bodies, items, strict=True):
                request = self._build(
                    operation, resolved, body=body, wrapper=wrapper, item_id=item.get("id")
                )
                results.append(await self._send(request))
        return {
            "endpoint": resolved.definition.key,
            "method": resolved.method,
            "uri": resolved.uri,
            "intent": step.intent,
            "responses": results,
            "data": results,
        }

    def _build_transformer(
        self,
        name: str,
        resolved: ResolvedEndpoint,
        parameters: Mapping[str, Any] | None,
    ) -> Any:
        """构造 Transformer，并在**配置类端点**上按生效规范注入字段集（P176 / R168）。

        ⚠️ **为什么需要它**：配置类端点（`DCO` 等）的**可接受字段集随生效设计规范变化**
        （实测：`KDS 41 20 : 2022` 接受 12 / 13 个字段；`GB/T50010-10` 接受 **0** 个）
        ⇒ 类级 `fields` 常量**必然**在某一种规范下失败（`400 Wrong Field`）。
        字段集因此是**运行时数据**：本方法按 `(material, code)` 从 Registry 查出后注入。

        **生效规范从哪来**（按优先级）：
        1. 调用方**显式**给的 `design_code`（裸字符串或 `[{"dgn_code": ...}]`）；
        2. 否则：**不注入** ⇒ 用类级 `fields`（**既有行为逐字不变**）。

        ⚠️ **缺记录时不猜**：`registry/live/design_code_field_sets.json` 里
        没有该 `(material, code)` 记录时 ——
        * 调用方**没**给该配置项 ⇒ 该步会在 `_has_payload` 处**跳过**（安全 —— 实测
          `DCO` 为空时设计链照常跑通）；
        * 调用方**给了**该配置项 ⇒ 抛 `design_option_not_characterized_for_code`
          （**不**按类级字段硬发 —— 那正是会 `400` 的路径）。

        Raises:
            MidasValidationError: `design_option_not_characterized_for_code` ——
                该 `(material, code)` 未实测，而调用方仍给了配置项。
        """
        factory = TRANSFORMER_REGISTRY[name]
        code = _design_code_of(parameters)
        if not code:
            return factory(self._require_registry())
        material = _design_material_of(resolved.definition.key)
        endpoint = _design_config_endpoint_of(resolved.definition.key)
        if material is None or endpoint is None:
            return factory(self._require_registry())
        # ⚠️ **类级字段表对它「自己那个规范」是对的** —— 每个设计 Transformer 的类级
        # `endpoint` 就标明了归属（如 `midas.design.dco.v1` 的
        # `DESIGN.STEEL.KDS-41-30-2022.DCO` ⇒ 它的 `fields` 是 **KDS 钢**规范的）。
        # ⇒ 调用方给的码**与该归属一致**时，类级默认即正确，**不**需要覆盖
        #   （否则会把本来正确的配置误判为「未实测」）。
        if code == _code_of_class_endpoint(factory):
            return factory(self._require_registry())
        field_set = self._require_registry().design_code_field_set(material, code, endpoint)
        if field_set is None:
            if parameters is not None and _has_payload_for_config(parameters, endpoint):
                raise MidasValidationError(
                    "design_option_not_characterized_for_code",
                    endpoint=resolved.definition.key,
                    design_code=code,
                    hint=(
                        f"`{material}` 的规范 `{code}` 在本仓**未实测**配置端点的可接受字段集"
                        " ⇒ 不猜字段。请先实测并登记到 "
                        "`registry/live/design_code_field_sets.json`，或不要传该配置项"
                        "（配置项为空时设计链照常跑通）。"
                    ),
                )
            return factory(self._require_registry())
        allowed = {field_map.native for field_map in factory.fields}
        kept = tuple(
            field_map
            for field_map in factory.fields
            if field_map.native in field_set.fields and field_map.native in allowed
        )
        return factory(self._require_registry(), fields=kept)

    def _prepare_item(
        self,
        item: Mapping[str, Any],
        *,
        transformer: Any,
        resolved: ResolvedEndpoint,
    ) -> tuple[dict[str, Any], str, bool]:
        """把一条 canonical 条目转成 `(原生体, 包装键, 是否 ITEMS 数组)`。

        `docs/04` §32 的荷载按 `load_type` 分派到**不同端点**（`DB.CNLD` / `DB.BMLD` /
        `DB.PRES` / `DB.BODF`），因此包装键与形态必须按**该条目的**分派结果取，
        不能按分派器本身取（见 `transforms.LoadTransformer`）。
        """
        source = dict(item)
        active = transformer
        if transformer is not None and hasattr(transformer, "delegate") and "load_type" in source:
            active = transformer.delegate(str(source["load_type"]))
            # `load_type` 是**分派键**，不是该端点 Schema 里的字段（`docs/04` §32）。
            source.pop("load_type", None)
        if active is None:
            return source, _wrapper_of(resolved), resolved.requires_array_body
        if active.field_for("id") is None:
            # canonical 的 `id` 在 `Assign` 包装里作**键**（`docs/04` §23），
            # 不是原生字段；只有把 `id` 映射到原生列（如 `ID`）的端点才保留它。
            source.pop("id", None)
        return active.to_native(source), active.wrapper_key(), active.is_items_style()

    async def _delete(
        self,
        operation: str,
        step: EndpointStep,
        resolved: ResolvedEndpoint,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """删除步骤：**必须**带路径 key（`docs/07` §6.4 / §7.6）。"""
        item_ids = _item_ids(parameters)
        if not item_ids:
            raise MidasValidationError(
                "delete_requires_item_ids", endpoint=resolved.definition.key, operation=operation
            )
        request = self._build(operation, resolved, body=None, wrapper="none", item_ids=item_ids)
        response = await self._send(request)
        return {
            "endpoint": resolved.definition.key,
            "method": request.method,
            "uri": request.uri,
            "intent": step.intent,
            "responses": [response],
            "data": response,
        }

    async def _design_result(
        self,
        operation: str,
        step: EndpointStep,
        resolved: ResolvedEndpoint,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """设计结果步骤（`docs/04` §53–§54）：`*-TABLE` 端点 + 结果表解析。

        ⚠️ 该端点的 `Argument` 形状与 `POST.TABLE` **不同**（`docs/04` §54 的
        `ELEMS` / `SECTIONS` / `TABLE_TYPE`），故参数由调用方给出（`parameters["arguments"]`），
        本方法**不**臆造字段；响应按 `wrapper.read_root`（如 `CODE-TABLE`）选行解析器。
        """
        arguments = dict(parameters.get("arguments") or {})
        request = self._build(operation, resolved, body=arguments, wrapper=_wrapper_of(resolved))
        response = await self._send(request)
        return {
            "endpoint": resolved.definition.key,
            "method": request.method,
            "uri": request.uri,
            "intent": step.intent,
            "data": _parse_design_table(response, resolved),
        }

    async def _result(
        self,
        operation: str,
        step: EndpointStep,
        resolved: ResolvedEndpoint,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """结果步骤：`POST /POST/TABLE` + `Argument.TABLE_TYPE`（`docs/07` §6.7）。"""
        registry = self._require_registry()
        table_type = str(parameters.get("table_type") or resolved.table_type)
        arguments: dict[str, Any] = {"table_type": table_type}
        for canonical, key in (
            ("components", "components"),
            ("load_cases", "load_cases"),
            ("unit", "unit"),
            ("table_name", "table_name"),
        ):
            if parameters.get(key) is not None:
                arguments[canonical] = parameters[key]
        body = ResultRequestTransformer(registry).to_native(arguments)
        request = self._build(operation, resolved, body=body, wrapper="Argument")
        response = await self._send(request)
        parsed = _parse_result(response, table_type=table_type, parameters=parameters)
        return {
            "endpoint": resolved.definition.key,
            "method": request.method,
            "uri": request.uri,
            "intent": step.intent,
            "table_type": table_type,
            "data": parsed,
        }

    async def _arguments_step(
        self,
        operation: str,
        step: EndpointStep,
        resolved: ResolvedEndpoint,
        parameters: Mapping[str, Any],
        *,
        transformer_name: str | None,
        arguments: Any,
    ) -> dict[str, Any]:
        """通用步骤：由调用方给出该端点的 `arguments`（**不**臆造字段）。

        `transformer_name` 非空时先用它做 Schema 白名单校验（`docs/04` §107）；
        为空时按数据的包装键原样包装（`view` / `design_result` / `write_doc`）。
        """
        registry = self._require_registry()
        # ⚠️ **P160 / R143**：体**不**再强制成对象 —— `DOC.OPEN` / `DOC.SAVEAS` 的体是
        # **字符串路径**（手册示例 `{"Argument": "C:\\MIDAS\\FSM.mcb"}`）。
        body: Any = arguments
        wrapper = _wrapper_of(resolved)
        if transformer_name and transformer_name in TRANSFORMER_REGISTRY:
            transformer = TRANSFORMER_REGISTRY[transformer_name](registry)
            body = transformer.to_native(arguments)
            wrapper = transformer.wrapper_key()
        request = self._build(operation, resolved, body=body, wrapper=wrapper)
        response = await self._send(request)
        return {
            "endpoint": resolved.definition.key,
            "method": request.method,
            "uri": request.uri,
            "intent": step.intent,
            "data": response,
        }

    # ===== 构造 / 发送（护栏在此把关，见 `client.py`）=====

    def _build(
        self,
        operation: str,
        resolved: ResolvedEndpoint,
        *,
        body: Any = None,
        wrapper: str = "none",
        items_style: bool = False,
        item_id: Any = None,
        item_ids: Sequence[str] = (),
    ) -> BuiltRequest:
        """构造请求（护栏在 `build_request` 内求值）。

        ⚠️ **R140**：**先**做说明书枚举预检（`spec_guard`）—— 非法枚举原生**不**校验，
        会一路走到 UI 层并**弹窗 / 崩溃**（实测事故），故必须拦在**我们这一侧**。

        ⚠️ **P168 / R161（普查驱动，**用户已授权**）**：这里传的是 `effective_schema()`，
        **不**是 `schema_json()`。`registry/schema/**` 的文件有两种根形态：
        `{"properties": {<包装键>: …}}`（**228** 个）与 `{<包装键>: {"properties": …}}`
        （**393** 个，其中 **104** 个带枚举约束）。`spec_guard` 的下钻约定是
        `schema["properties"][包装键]` ⇒ 对**后一种**形态 `root` 为空、**一个字段都不检查**
        （**盲区**：`VIEW.RESULTGRAPHIC`、**全部 194 个 `POST.TABLE.*` 变体**、`DB.PRES` /
        `DB.MVHL` / `OPE.USLC` …）⇒ R140 的保护在这些端点上**只是名义上的**。
        `effective_schema()` = P09 就有的 `unwrap_schema()`（剥掉包装根键，
        `request_schema_fields()` 一直用它）⇒ 两种形态**都**可下钻
        （实测 **225 / 225**，其中 **104** 个由盲变可见，已可见的 **121** 个**零回归**）。
        """
        client = self._require_client()
        registry = self._require_registry()
        guard_spec_values(
            registry.effective_schema(resolved.definition.key),
            body,
            endpoint=resolved.definition.key,
            wrapper=wrapper,
        )
        return client.build_request(
            resolved,
            operation=operation,
            body=body,
            wrapper=wrapper,
            items_style=items_style,
            item_id=item_id,
            item_ids=item_ids,
            solver=self._solver,
            allow_unverified=self._allow_unverified,
            allow_native_crash_risk=self._allow_native_crash_risk,
        )

    async def _send(self, request: BuiltRequest) -> dict[str, Any]:
        """发出请求（错误由 `client.py` 归一化）。"""
        return await self._require_client().send(request)

    def _require_client(self) -> MidasHttpClient:
        """取客户端（未连接 → `STRUCTAI-3000`）。"""
        if self._client is None:
            raise MidasCapabilityError("adapter_not_connected")
        return self._client


# ===== 参数辅助（只做机械展开，**不**臆造字段）=====


def _item_key(item: Mapping[str, Any], transformer: Any, *, endpoint: str) -> Any:
    """条目在 `Assign` 里的**外层键**（`docs/07` §16.1 **R128**）。

    规则（**由代码导出，不臆造**）：取该 Transformer 字段表里**映射到原生 `ID`** 的 canonical 字段
    —— `DB.CONS` 是 `node_id`（支承的编号**就是**它所在节点的编号），节点 / 梁 / 面荷载是 `id`。

    ⚠️ 外层键**必须**是**存在的**对象编号：无效键时原生会**静默 `200` 而不落库**
    （假成功陷阱）⇒ 取不到就**明确失败**，**不**回落到 `"1"`。

    Raises:
        MidasValidationError: `STRUCTAI-1200`，条目里没有可用的编号（**不**臆造键）。
    """
    if transformer is not None:
        for field in getattr(transformer, "fields", ()):
            if str(getattr(field, "native", "")) == "ID":
                value = item.get(field.canonical)
                if value is not None:
                    return value
                break
    value = item.get("id")
    if value is None:
        raise MidasValidationError(
            "assign_item_key_missing", endpoint=endpoint, item=sorted(str(key) for key in item)
        )
    return value


def _build_payloads(parameters: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """把参数展开成各写步骤的载荷（见裁决 5；`docs/07` §13.5 的 `BUILD.COLUMN` 形态）。"""
    payloads: dict[str, list[dict[str, Any]]] = {
        "write_node": _mapping_list(parameters.get("nodes")),
        "write_element": _mapping_list(parameters.get("elements")),
        "write_material": _mapping_list(parameters.get("materials")),
        "write_section": _mapping_list(parameters.get("sections")),
        "write_boundary": _mapping_list(parameters.get("boundaries")),
        "write_load_case": _mapping_list(parameters.get("load_case_definition")),
        "write_load": _load_items(parameters),
        "write_load_combination": _mapping_list(parameters.get("load_combinations")),
        # ⚠️ **P157 / R141**：`DESIGN.STEEL` 的**配置**四步（手册方法 = `GET, PUT, DELETE`）。
        # ⚠️ **P159 / R133**：单位系统（模型级设置）—— 载荷入口 = `parameters["unit"]`。
        "write_unit": _mapping_list(parameters.get("unit")),
        # ⚠️ **P176 / R168**：裸字符串也要认（`_mapping_list` 对字符串返回空列表 ⇒ 静默跳过）。
        "write_design_code": _design_code_items(parameters),
        "write_design_option": _mapping_list(parameters.get("design_option")),
        "write_design_frame": _mapping_list(parameters.get("design_frame")),
        "write_design_member": _mapping_list(parameters.get("design_members")),
    }
    if payloads["write_node"] and payloads["write_element"]:
        return payloads
    column = _column_payloads(parameters)
    for intent, items in column.items():
        payloads[intent] = items or payloads[intent]
    return payloads


def _column_payloads(parameters: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """`BUILD.COLUMN` 的 `docs/07` §13.5 形态 → 四类载荷（**不**猜缺失字段）。"""
    base = parameters.get("base_node")
    height = parameters.get("height")
    if not isinstance(base, Mapping) or height is None:
        return {}
    material_name = parameters.get("material")
    section_name = parameters.get("section")
    section_type = parameters.get("section_type")
    if material_name is None or section_name is None or section_type is None:
        raise MidasValidationError(
            "build_column_requires_material_section_and_section_type",
            missing=[
                name
                for name, value in (
                    ("material", material_name),
                    ("section", section_name),
                    ("section_type", section_type),
                )
                if value is None
            ],
        )
    x, y, z = (float(base.get(axis, 0.0)) for axis in ("x", "y", "z"))
    top = float(height)
    nodes = [
        {"id": 1, "x": x, "y": y, "z": z},
        {"id": 2, "x": x, "y": y, "z": z + top},
    ]
    elements = [
        {
            "id": 1,
            "type": str(parameters.get("element_type") or "BEAM"),
            "node_ids": [1, 2],
            "material_id": 1,
            "section_id": 1,
            "angle": parameters.get("angle"),
        }
    ]
    materials = [
        {
            "id": 1,
            "name": str(material_name),
            "type": str(parameters.get("material_type") or "STEEL"),
            "elastic_modulus": parameters.get("elastic_modulus"),
            "poisson_ratio": parameters.get("poisson_ratio"),
            "density": parameters.get("density"),
        }
    ]
    sections = [
        {
            "id": 1,
            "name": str(section_name),
            "section_type": str(section_type),
            "shape": parameters.get("shape"),
        }
    ]
    return {
        "write_node": nodes,
        "write_element": elements,
        "write_material": materials,
        "write_section": sections,
    }


def _analysis_arguments(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """`DOC.ANAL` 的参数（Schema 只声明 `Argument.TYPE`）。"""
    return {"analysis_type": parameters.get("analysis_type")}


def _design_arguments(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """设计执行参数（`*-ANAL` 的 `PERFORM_TYPE` / `ELEMS` / `SECTIONS` / `SELECTIONS`）。

    ⚠️ **P164-c / R154（实测驱动）**：
    * `DESIGN.RC.KDS-41-20-2022.WD-ANAL`（**墙**设计）的 `Argument` **只有** `SELECTIONS`
      （`{WALL_IDS, STORY}` 数组），与同族其它 `*-ANAL` **不同形** ⇒ 单独透传（**不**臆造）。
    * ⚠️ **只返回调用方真正给了的字段**（丢掉 `None`）：`SchemaBoundTransformer.to_native()`
      在**检查 `None` 之前**就校验字段名 ⇒ 多带一个 `None` 会让**所有**不含该字段的转换器
      抛 `transformer_field_not_in_schema`（本批实测踩到）。
      ⚠️ 反过来也**不能**把 `None` 收进白名单 —— 那会**放宽**「不臆造字段」的判定。
    """
    candidates = {
        "perform_type": parameters.get("perform_type"),
        "elements": parameters.get("elements"),
        "sections": parameters.get("sections"),
        "selections": parameters.get("selections"),
    }
    arguments = {key: value for key, value in candidates.items() if value is not None}

    # ⚠️ **P164-c / R154（事故驱动，**自洽性守卫**）**：`PERFORM_TYPE` 与目标选择**必须一致** ——
    # 手册把三者定义得很清楚：`ALL` = 全部构件 · `ELEMS` = 按**单元编号** ·
    # `SECTIONS` = 按**截面编号**。
    # 发 `PERFORM_TYPE="ALL"` **同时**带 `ELEMS.KEYS` 是**自相矛盾**的请求。
    # 实测：这种矛盾请求会让 MIDAS Gen NX 在 `wg_db.dll` 里**访问违例崩溃**
    # （`GenNX.exe` 26.9.1.1001 · `0xc0000005` · offset `0x2d97e5c`，两次实测同一偏移）。
    # ⇒ 在**发请求前**明确失败 —— **绝不**把一个自相矛盾的设计请求交给原生设计引擎。
    perform = arguments.get("perform_type")
    if perform == "ALL" and ("elements" in arguments or "sections" in arguments):
        raise MidasValidationError(
            "design_target_conflict",
            perform_type=perform,
            given=sorted(k for k in ("elements", "sections") if k in arguments),
            note=(
                '`PERFORM_TYPE="ALL"`（全部构件）不能与 `elements` / `sections` 同时给出 —— '
                "那是自相矛盾的请求（实测会**打崩** MIDAS Gen NX）。"
                '要按编号设计请用 `perform_type="ELEMS"` 或 `"SECTIONS"`。'
            ),
        )
    if perform == "ELEMS" and "elements" not in arguments:
        raise MidasValidationError(
            "design_target_missing", perform_type=perform, note="`ELEMS` 需要 `elements`。"
        )
    if perform == "SECTIONS" and "sections" not in arguments:
        raise MidasValidationError(
            "design_target_missing", perform_type=perform, note="`SECTIONS` 需要 `sections`。"
        )
    return arguments


def _parse_result(
    response: Mapping[str, Any], *, table_type: str, parameters: Mapping[str, Any]
) -> dict[str, Any]:
    """解析结果表并按 canonical 侧过滤（`docs/04` §47；见裁决 7）。"""
    transformer_class = _RESULT_ROW_TRANSFORMERS.get(str(table_type).upper())
    if transformer_class is None:
        table = parse_table(response, table_name=str(table_type))
        return {
            "table_type": table.table_name,
            "units": dict(table.units),
            "columns": list(table.head),
            "rows": [dict(row) for row in table.rows],
        }
    parsed = transformer_class().parse(response, table_name=str(table_type))
    parsed["rows"] = _filter_rows(parsed["rows"], parameters)
    return parsed


def _parse_design_table(response: Mapping[str, Any], resolved: ResolvedEndpoint) -> dict[str, Any]:
    """解析设计结果表（`docs/04` §53–§54）：按 `wrapper.read_root` 选行解析器。

    `DESIGN.*.*-TABLE` 端点的数据里 `table_type` 为空、`read_root` 为表名
    （如 `CODE-TABLE`），故这里以 `read_root` 为口径；未登记的表名走**通用**解析
    （只回 `columns` / `rows` 原文，**不**臆造 canonical 字段）。
    """
    table_name = resolved.read_root or resolved.definition.table_type
    transformer_class = _RESULT_ROW_TRANSFORMERS.get(str(table_name).upper())
    if transformer_class is None:
        table = parse_table(response, table_name=str(table_name))
        return {
            "table_type": table.table_name,
            "units": dict(table.units),
            "columns": list(table.head),
            "rows": [dict(row) for row in table.rows],
        }
    return transformer_class().parse(response, table_name=str(table_name))


def _filter_rows(
    rows: Sequence[Mapping[str, Any]], parameters: Mapping[str, Any]
) -> list[Mapping[str, Any]]:
    """按 `node_ids` / `element_ids` / `load_cases` 过滤（只比较，**不**造值）。"""
    node_ids = {str(item) for item in parameters.get("node_ids") or ()}
    element_ids = {str(item) for item in parameters.get("element_ids") or ()}
    load_cases = {str(item) for item in parameters.get("load_cases") or ()}
    kept: list[Mapping[str, Any]] = []
    for row in rows:
        if node_ids and str(row.get("node_id")) not in node_ids:
            continue
        if element_ids and str(row.get("element_id")) not in element_ids:
            continue
        if load_cases and str(row.get("load_case")) not in load_cases:
            continue
        kept.append(row)
    return kept


def _has_payload(
    step: EndpointStep, parameters: Mapping[str, Any], payloads: Mapping[str, Any]
) -> bool:
    """该步骤本次是否有载荷（见裁决 5）。"""
    if step.intent.startswith("write_") and step.intent != "write_doc":
        return bool(payloads.get(step.intent))
    if step.intent.startswith("write_") and step.intent != "write_doc":
        return bool(payloads.get(step.intent))
    return True


def _items_of(payload: Any) -> list[tuple[str | None, Mapping[str, Any]]]:
    """把读响应解包成 `(编号, 条目)` 列表（`docs/04` §23 的编号映射）。

    - `{"ITEMS": [ ... ]}` → 每条一个元素（编号为 `None`）；
    - `{"1": {...}, "2": {...}}`（DB 类端点）→ 编号取自**键**；
    - 单对象 → 一条（编号 `None`）。

    ⚠️ **P158 / R130**：`ITEMS` 形态的端点（`DB.CONS` / `DB.CNLD` / `DB.BMLD` / `DB.PRES`）
    读回来是 `{<编号>: {"ITEMS": [<条目>, …]}}` —— 原先把**外层 `ITEMS` 包装体**当成条目
    ⇒ Transformer 在包装体这一层找不到 `ID` / `CONSTRAINT` / `LCNAME` … ⇒ canonical 取值
    **全 `None`**（只剩由**编号键**补的 `id`）。这里改为**逐元素**展开（编号仍作兜底 `id`）。
    """
    if isinstance(payload, Mapping):
        for name in ("ITEMS", "items"):
            nested = payload.get(name)
            if isinstance(nested, Sequence) and not isinstance(nested, str):
                return [(None, item) for item in nested if isinstance(item, Mapping)]
        if payload and all(isinstance(value, Mapping) for value in payload.values()):
            items: list[tuple[str | None, Mapping[str, Any]]] = []
            for key, value in payload.items():
                items.extend(_explode_items(str(key), value))
            return items
        return [(None, payload)]
    if isinstance(payload, Sequence) and not isinstance(payload, str):
        return [(None, item) for item in payload if isinstance(item, Mapping)]
    return []


def _explode_items(
    key: str, value: Mapping[str, Any]
) -> list[tuple[str | None, Mapping[str, Any]]]:
    """一个编号键下的条目：`ITEMS` 包装体 ⇒ **逐元素**展开；否则整体一条（**P158 / R130**）。

    ⚠️ 外层编号**不丢**：仍作为该条的**兜底 `id`**（元素自带 `ID` 时以元素为准）。
    """
    for name in ("ITEMS", "items"):
        nested = value.get(name)
        if isinstance(nested, Sequence) and not isinstance(nested, str):
            inner = [item for item in nested if isinstance(item, Mapping)]
            if inner:
                return [(key, item) for item in inner]
    return [(key, value)]


def _unwrap(response: Mapping[str, Any], resolved: ResolvedEndpoint) -> Any:
    """按数据侧声明的**解包链**取业务载荷（`docs/07` §16 R83；P134 新增）。

    链取自 `ResolvedEndpoint.read_path`：NX 系 = `(read_root,)`；
    `CIVIL_DESIGNER` 实测 = `("result", "return_value")`（R83）。
    **取不到就明确报错** —— R83 的静默降级（退回整包 → 转换器字段全 `None`）
    必须被禁止（`docs/07` §14.4 的「不允许带病继续」）。

    Raises:
        MidasCapabilityError: `STRUCTAI-3000`，数据侧**未声明**解包链
            （`details.reason = "endpoint_read_path_undeclared"`）。
        MidasAPIError: `STRUCTAI-2200`，响应信封与数据侧声明不符
            （`details.reason = "response_envelope_mismatch"`）。
    """
    chain = resolved.read_path
    if not chain:
        raise MidasCapabilityError(
            "endpoint_read_path_undeclared",
            endpoint=resolved.definition.key,
            product=resolved.product,
        )
    node: Any = response
    for step in chain:
        if not isinstance(node, Mapping) or step not in node:
            raise MidasAPIError(
                "response_envelope_mismatch",
                endpoint=resolved.definition.key,
                product=resolved.product,
                missing_step=str(step),
            )
        node = node[step]
    return node


def _items_style(transformer: Any) -> bool:
    """该端点是否用 `ITEMS` 数组承载条目（由 Schema 决定）。"""
    if transformer is None:
        return False
    return transformer.is_items_style()


VIEW_ARGUMENT_CHANNELS: Final[dict[str, str]] = {
    "view_display": "display",
    "view_result": "result_graphic",
    "view_capture": "capture",
}
"""`VIEW.*` 各步的参数通道（`docs/07` §16.1 **R148**）。

⚠️ 三步**形状不同**：`VIEW.DISPLAY` / `VIEW.RESULTGRAPHIC` 要**原生键**（无转换器），
`VIEW.CAPTURE` 要**canonical 键**（有白名单转换器）⇒ **不**能共用一份 `arguments`。
"""

DOC_PATH_OPERATIONS: Final[frozenset[str]] = frozenset(
    {"DOC.OPEN", "DOC.SAVE", "DOC.SAVEAS", "DOC.EXPORT", "DOC.IMPORT"}
)
"""**必须带项目路径**的 DOC 文件操作（`docs/07` §16.1 **R143**；P175/R168 扩入两个导出导入端点）。

⚠️ **P175 为何把 `DOC.EXPORT` / `DOC.IMPORT` 也纳入**：二者的 `Argument` **就是文件路径**
（手册示例 `{"Argument": "C:/MIDAS/FSM.json"}`），与 `OPEN` / `SAVEAS` **同形**
⇒ 缺路径同样会弹「另存为」模态窗口挂起 API（R143 的那类事故）。实测确认二者体取
**路径字符串**（见 `registry/live/model_doc_probe.json`）。

⚠️ **用户给出的产品规则**：**保存 / 另存必须带项目路径**，否则 MIDAS 会弹出「另存为」
**模态窗口** ⇒ **挂起 API、阻塞链路**（P160b 实测：一次无路径的 `DOC.SAVE` 弹了窗，
**由用户手动操作**才解除）。文件操作一律在**项目文件夹**内。
⇒ 核心**先拦**：缺路径 ⇒ `STRUCTAI-1200` `project_path_required`，**一条请求都不发**。
"""


def _doc_arguments(step: EndpointStep, parameters: Mapping[str, Any]) -> Any:
    """DOC 文件操作的请求体（**项目路径守卫**；`docs/07` §16.1 **R143**）。

    - `DOC.OPEN` / `DOC.SAVEAS`：体**就是**路径字符串（手册示例 `{"Argument": "<路径>"}`）；
    - `DOC.SAVE`：手册体是 `{"Argument": {}}` —— 路径由**项目自身**持有，故这里**只**做
      **前置断言**（调用方必须给出项目路径，表示「该项目已有路径」），**不**把它塞进体里。

    Raises:
        MidasValidationError: `STRUCTAI-1200`，缺项目路径（`reason = "project_path_required"`）。
            ⚠️ **必须**在**发请求之前**拦住 —— 否则 MIDAS 会弹「另存为」模态窗口并挂起 API。
    """
    if step.key not in DOC_PATH_OPERATIONS:
        # ⚠️ **不**做文件操作的 DOC 步骤（如 `DOC.NEW`）⇒ 原样发对象体，**不**要求路径。
        return dict(parameters.get("arguments") or {})
    raw_path = parameters.get("project_path")
    if raw_path is None and isinstance(parameters.get("arguments"), str):
        raw_path = parameters.get("arguments")
    project_path = str(raw_path).strip() if raw_path is not None else ""
    if not project_path:
        raise MidasValidationError(
            "project_path_required",
            endpoint=step.key,
            hint=(
                "保存 / 另存必须带项目路径（文件操作在**项目文件夹**内）；"
                "缺路径时 MIDAS 会弹「另存为」模态窗口并**挂起 API**。"
            ),
        )
    # ⚠️ **P160c（用户口径的更正）**：**保存**（`DOC.SAVE`）**也**带项目路径 ——
    # 用户原话：「**保存及另存必须代项目路径**，不然会弹出另存窗口，这会挂起 API 造成
    # API 链路阻塞」。⚠️ 上游手册的 `DOC.SAVE` 体写的是 `{}`（**与厂商行为不符**，
    # 同 `DOC.ANAL` 的 `TYPE` 取值那一类）⇒ **以用户口径 + 实测为准**。
    return project_path


def _wrapper_of(resolved: ResolvedEndpoint) -> str:
    """按数据 / Schema 决定包装键（`transforms.py` 裁决 3 的同一口径）。"""
    return resolved.wrapper_write if resolved.wrapper_write else "none"


def _item_ids(parameters: Mapping[str, Any]) -> tuple[str, ...]:
    """删除目标的路径 key（`docs/07` §6.4）。"""
    raw = parameters.get("item_ids") or parameters.get("ids")
    if raw is None:
        return ()
    if isinstance(raw, Sequence) and not isinstance(raw, str):
        return tuple(str(item) for item in raw)
    return (str(raw),)


def _mapping_list(value: Any) -> list[dict[str, Any]]:
    """把参数里的条目归一成映射列表（`None` → 空列表；**不**臆造条目）。"""
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Sequence) and not isinstance(value, str):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


DESIGN_CODE_SENSITIVE_ENDPOINTS: Final[frozenset[str]] = frozenset({"DCO"})
"""**字段集随生效设计规范变化**的设计端点末段（`P176 / R168`）。

⚠️ **只有 `DCO`**（设计选项）—— P176 实测：KDS 下接受 12 / 13 个字段，`GB/T50010-10` 下
接受 **0** 个（`DESIGN_CD` 也被拒）。

⚠️ **同族的 `DCTL`（框架控制）/ `MEMB`（构件指派）与规范无关**（同批实测：
中国规范下两者 `PUT` 均 `200`）⇒ **不**纳入本集合 —— 纳入会把本来正确的配置
误判为「未实测」而**误报错**（P176 实测踩到：`MEMB` 被拦，整个设计任务 `FAILED`）。

⚠️ 其余设计端点（`DRC` / `*-ANAL` / `*-TABLE`）的字段集同样与规范无关。
"""

DESIGN_MATERIAL_SEGMENTS: Final[frozenset[str]] = frozenset({"RC", "STEEL", "SRC"})
"""设计端点的**材料段**（`DESIGN.<material>.<...>`）。"""


def _design_code_of(parameters: Mapping[str, Any] | None) -> str:
    """取调用方**显式**给的设计规范码（没给 → 空串 ⇒ 不注入字段集）。"""
    if not parameters:
        return ""
    items = _design_code_items(parameters)
    if not items:
        return ""
    return str(items[0].get("dgn_code") or "").strip()


def _design_material_of(endpoint_key: str) -> str | None:
    """从端点 key 取材料段（`DESIGN.RC.KDS-41-20-2022.DCO` → `RC`）；取不到 → `None`。"""
    parts = str(endpoint_key).split(".")
    if len(parts) >= 3 and parts[0] == "DESIGN" and parts[1] in DESIGN_MATERIAL_SEGMENTS:
        return parts[1]
    return None


def _design_config_endpoint_of(endpoint_key: str) -> str | None:
    """从端点 key 取**随规范变化**的配置端点末段（`...DCO` → `DCO`）；其余 → `None`。"""
    tail = str(endpoint_key).rsplit(".", 1)[-1]
    return tail if tail in DESIGN_CODE_SENSITIVE_ENDPOINTS else None


def _has_payload_for_config(parameters: Mapping[str, Any], endpoint: str) -> bool:
    """调用方是否为该配置端点**给了**载荷（给了 ⇒ 未实测时必须显式失败，**不**硬发）。"""
    field = {
        "DCO": "design_option",
        "DCTL": "design_frame",
        "MEMB": "design_members",
    }.get(str(endpoint))
    if field is None:
        return False
    return bool(_mapping_list(parameters.get(field)))


CLASS_ENDPOINT_CODES: Final[dict[str, str]] = {
    "DESIGN.RC.KDS-41-20-2022": "KDS 41 20 : 2022",
    "DESIGN.STEEL.KDS-41-30-2022": "KDS 41 30 : 2022",
    "DESIGN.SRC.AIK-SRC2K": "AIK-SRC2K",
}
"""类级 `endpoint` 的规范段 → **该 Transformer 的 `fields` 所属规范码**。

⚠️ 这张表是**机械的**：`registry/design_codes.yaml` 的 `designer_design.selectors`
已把 `endpoint_prefix` ↔ `code` 记成数据（本表是它在**应用侧**的等价物 ——
`pyyaml` 不在依赖清单，故此处以内联映射表达，**不**新增依赖）。

⚠️ 它**不**声称「实例支持哪些规范」——那由**实测**决定
（`registry/live/design_code_field_sets.json`）。
"""


def _code_of_class_endpoint(factory: Any) -> str:
    """该 Transformer 的类级 `fields` **所属**的规范码（取不到 → 空串）。"""
    endpoint = str(getattr(factory, "endpoint", "") or "")
    for prefix, code in CLASS_ENDPOINT_CODES.items():
        if endpoint.startswith(prefix):
            return code
    return ""


def _design_code_items(parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
    """设计规范条目：**裸字符串**与**映射列表**两种形态都接受（P176 / R168）。

    ⚠️ **为什么需要它**：`_mapping_list` 对**字符串**返回**空列表**（它只认映射 / 映射序列）
    ⇒ 调用方按最自然的方式传 `design_code: "GB/T50010-10"` 时，`DESIGN.RC.DRC` 那一步
    会拿到**空载荷**而被**静默跳过** ⇒ 规范**根本没切换**，而调用方看不出任何异常
    （实测：`BD-ANAL` 仍按**旧规范**跑）。

    ⇒ 这里把裸字符串归一成 `[{"dgn_code": <code>}]`（与 Transformer 的 canonical 字段名一致），
    与既有的 `design_code: [{"dgn_code": ...}]` 形态**并存**（向后兼容）。

    ⚠️ **不**臆造字段：只做 `str → {"dgn_code": str}` 这一种机械转换；
    其余类型（数字 / 布尔 / 嵌套）**不**猜测，原样交给 `_mapping_list` 处理（⇒ 空列表）。
    """
    value = parameters.get("design_code")
    if isinstance(value, str) and value.strip():
        return [{"dgn_code": value.strip()}]
    return _mapping_list(value)


def _load_items(parameters: Mapping[str, Any]) -> list[dict[str, Any]]:
    """荷载条目：把 `load_type` 并入条目（`transforms.LoadTransformer` 据此分派）。"""
    items = _mapping_list(parameters.get("load"))
    load_type = parameters.get("load_type")
    if load_type is None:
        return items
    return [{**item, "load_type": str(load_type).upper()} for item in items]
