"""Infrastructure · Adapters · MIDAS · Client —— HTTP 客户端与破坏性护栏（`docs/07` §7.3 / §7.6）。

权威来源
--------
- `docs/04` §6（MIDAS HTTP Client）—— `MidasHttpClient(base_url, credential_provider,
  secret_ref, timeout)` + `get/post/put/delete/close`；请求头 `MAPI-Key` /
  `Content-Type` / `Accept`；**不得**把 MAPI-Key 放进 URL Query。
- `docs/04` §5.1 —— `Base URL → 普通配置`；`MAPI-Key → Secret Reference → CredentialProvider`；
  不得落库 / 打日志 / 打 Trace / 打 Audit / 进响应 / 进异常 message。
- `docs/07` §7.3（由 Registry 驱动的请求构造）—— 四步：产品差异（`Assign` / 扁平）→
  求解器门控 → 破坏性护栏（NX 系 `DELETE` 必须带路径 key）→ 请求体形态。
- `docs/07` §7.6（实测行为约束）—— NX 系不带路径 key 的 `DELETE` 会**删全表**；
  Designer 空主体 / `Type=0` = 删全部；云端中继会间歇掉线（`client does not exist`）。
- `docs/07` §11 补充 —— `CLIENT_NOT_CONNECTED` → `STRUCTAI-2000`；
  `PROJECT_NOT_OPENED` → `STRUCTAI-2200`。

落地裁决（只补实现手段，不改语义）
--------------------------------
1. **凭据只经 `CredentialProvider` 取，只进请求头**：`secret_ref` 是**引用名**
   （`docs/07` §4.3 #13 的 `credential_reference`），值只在发请求那一刻取；
   类里**不缓存**、`repr` **不**含值、异常 **不**回显（`docs/07` §14.3）。
2. **超时预算按 `execution_mode`**：`FAST` 30s / `ASYNC` 120s / `LONG` 3600s
   （`docs/07` §6.9：`DOC.ANAL` 是 `LONG`，超时 3600000 ms）。参数名**不**叫
   `timeout`（`ruff` 的 `ASYNC109`：异步函数用预算语义，与既有 `tests/` 同口径）。
3. **护栏全部在发请求**之前**求值**（`docs/07` §12 P123）：`guard_*()` 是纯函数，
   只读端点数据与入参，任何一条不通过 → 立即抛，**零** I/O。
4. **`DELETE` 的路径 key 是硬约束**：NX 系（`path_key_supported` +
   `delete_without_body_is_global`）必须给出 `item_ids`，拼成 `{uri}/{id1,id2}`；
   Designer（`delete_all_via_body`）在空主体 / `Type == 0` 时拒绝。
5. **`allow_unverified` 只服务 Contract Test（L3 Mock Transport）**：`docs/04` §71 的
   CI 分层是 L1–L3；生产路径**永远**用缺省值 `False`，即 `verification_status != VERIFIED`
   → `RegistryMappingNotVerified`（`docs/04` §130）。该开关**不**改任何
   `verification_status` 取值（`docs/07` §16 R1）。
6. **原生错误文案不外泄**：`details` 只放**非敏感**结构字段（状态码 / 端点 key /
   归一化后的软件侧短原因），响应体原文**不**进 `details`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块依赖 `httpx`（`docs/07` §3.1 冻结的技术栈）、标准库、`app.domain` 与同包的
`errors.py` / `registry.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK，
**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

import httpx

from app.domain.errors import InternalError
from app.infrastructure.adapters.midas.errors import (
    MidasAPIError,
    MidasAuthenticationError,
    MidasConnectionError,
    MidasEndpointDisabled,
    MidasGlobalDeleteRejected,
    MidasSchemaShapeMismatch,
    MidasSolverUnsupported,
    MidasTimeoutError,
    RegistryMappingNotVerified,
)
from app.infrastructure.adapters.midas.registry import VERIFIED, ResolvedEndpoint

__all__ = [
    "DEFAULT_BUDGET_SECONDS",
    "EXECUTION_MODE_BUDGETS",
    "MAPI_KEY_HEADER",
    "BuiltRequest",
    "CredentialProviderLike",
    "MidasHttpClient",
    "ProbeResponse",
    "SendResult",
    "guard_destructive",
    "guard_enabled",
    "guard_shape",
    "guard_solver",
    "guard_verified",
]

MAPI_KEY_HEADER: Final[str] = "MAPI-Key"
"""`docs/04` §6：鉴权请求头（**只**出现在请求头，绝不进 URL / 日志）。"""

DEFAULT_BUDGET_SECONDS: Final[float] = 30.0
"""`docs/04` §6 的缺省超时（30.0）。"""

EXECUTION_MODE_BUDGETS: Final[dict[str, float]] = {
    "FAST": 30.0,
    "ASYNC": 120.0,
    "LONG": 3600.0,
}
"""`registry/README.md` §4 的 `execution.mode` → 超时预算（见裁决 2）。"""

_CLIENT_NOT_CONNECTED_MARKERS: Final[tuple[str, ...]] = ("client does not exist",)
_PROJECT_NOT_OPENED_MARKERS: Final[tuple[str, ...]] = ("project is not opened",)
"""`docs/07` §11 补充：实测得到的两种状态类错误文案（只做**包含**匹配）。"""


class CredentialProviderLike(Protocol):
    """`docs/07` §8.5 的凭据提供者（只取 `get_secret`）。"""

    async def get_secret(self, reference: str) -> str:
        """按引用名读取凭据值。"""
        ...


@dataclass(frozen=True, slots=True)
class BuiltRequest:
    """一条**已构造**的请求（`docs/07` §7.3 的产物；尚未发出）。"""

    operation: str
    endpoint: str
    product: str
    method: str
    uri: str
    body: dict[str, Any] | list[Any] | None
    wrapper: str
    table_type: str
    budget_seconds: float

    def __repr__(self) -> str:
        """诊断表示：**不含**请求体（可能含业务数据），只含定位字段。"""
        return (
            f"BuiltRequest(operation={self.operation!r}, endpoint={self.endpoint!r}, "
            f"method={self.method!r}, uri={self.uri!r}, wrapper={self.wrapper!r})"
        )


@dataclass(frozen=True, slots=True)
class ProbeResponse:
    """一次**零副作用探测**的结果（`docs/04` §69–§72 的 L4 探针；P134 新增）。

    与 `send()` 的区别：**不**因 4xx / 5xx 抛业务错误（探测的目的正是记录状态码），
    也**不**把不可解析的响应体当异常 —— 只如实回报「状态码 / 载荷 / 字节数 / 是否 JSON」。
    载荷**只**用于统计顶层键与信封形态，**不**落库、**不**进日志（`docs/07` §14.3）。
    """

    status_code: int
    payload: dict[str, Any]
    body_bytes: int
    json_ok: bool


@dataclass(frozen=True, slots=True)
class SendResult:
    """一次已构造请求的**保真**结果（P139：状态码来自响应，不是常量）。

    `send()` 只回载荷，调用方拿不到原生状态码 —— P135 的写路径探针因此把
    `status_code` 写成了常量 `200`（`400` 只在 `detail` 里体现）。本类型把
    「原生状态码 + 解析后的载荷」一起回传，让 L5 证据里的状态码**逐条可断言**。

    ⚠️ 仍然**不**把响应体原文落库 / 进日志（`docs/07` §14.3）：载荷只用于统计
    顶层键与信封形态；`4xx` / `5xx` 依旧由 `_raise_for_status()` 归一化后抛出
    （错误路径的 `status_code` 落在异常 `details` 里）。
    """

    status_code: int
    payload: dict[str, Any]


# ===== 护栏（纯函数；`docs/07` §7.3 / §7.6；见裁决 3）=====


def guard_enabled(resolved: ResolvedEndpoint) -> None:
    """`enabled: false` → 拒绝（`registry/README.md` §4）。

    Raises:
        MidasEndpointDisabled: `STRUCTAI-3000`。
    """
    definition = resolved.definition
    if not definition.enabled:
        raise MidasEndpointDisabled(
            definition.key,
            definition.disable_reason,
            product=resolved.product,
        )


def guard_verified(resolved: ResolvedEndpoint, *, operation: str, allow_unverified: bool) -> None:
    """`verification_status != VERIFIED` → 拒绝（`docs/04` §130；`docs/07` §7.2）。

    Raises:
        RegistryMappingNotVerified: `STRUCTAI-3000`，未通过验证的端点。
    """
    if allow_unverified:
        return
    status = resolved.verification_status
    if status != VERIFIED:
        raise RegistryMappingNotVerified(
            operation, resolved.definition.key, status, product=resolved.product
        )


def guard_solver(resolved: ResolvedEndpoint, solver: str) -> None:
    """求解器门控（`docs/07` §7.3 第 2 步 / §7.6）。

    Args:
        resolved: 已解析端点。
        solver: 实例声明的求解器（空串 = 标准求解器）。

    Raises:
        MidasSolverUnsupported: `STRUCTAI-3000`，端点要求别的求解器
            （如 `-M1` 变体仅 `HYPER_S` 可用）。
    """
    required = resolved.solver
    if required and required != str(solver):
        raise MidasSolverUnsupported(required, str(solver), endpoint=resolved.definition.key)


def guard_destructive(
    resolved: ResolvedEndpoint,
    *,
    method: str,
    item_ids: Sequence[str],
    payload: Mapping[str, Any] | None,
) -> None:
    """破坏性护栏（`docs/07` §7.6 的两条实测结论；见裁决 4）。

    Raises:
        MidasGlobalDeleteRejected: `STRUCTAI-1200`，形态会被 MIDAS 解释为「删全表」。
    """
    if str(method).upper() != "DELETE":
        return
    definition = resolved.definition
    if definition.delete_without_body_is_global and not item_ids:
        raise MidasGlobalDeleteRejected(
            "nx_delete_requires_path_key", endpoint=definition.key, product=resolved.product
        )
    if resolved.delete_all_via_body:
        type_field = None if payload is None else payload.get("Type")
        if not payload or type_field in {0, "0"}:
            raise MidasGlobalDeleteRejected(
                "designer_delete_all_via_body", endpoint=definition.key, product=resolved.product
            )


def guard_shape(resolved: ResolvedEndpoint, body: object) -> None:
    """请求体形态护栏（`docs/07` §7.3 第 4 步；`docs/07` §7.6）。

    ⚠️ **无请求体时不判定**（P134 修正）：读步骤（`GET`）与不带体的 `DELETE` 传
    `body=None`，而 Designer 的 `DB.*` 端点声明 `body_kind: object` ——
    旧实现会把「没有体」判成「形态不符」（`STRUCTAI-1200`），使 Designer 的
    **读路径**整体不可用（P134 实测发现，见 `docs/07` §16 R83）。
    形态护栏只约束**实际给出的**体。

    Raises:
        MidasSchemaShapeMismatch: `STRUCTAI-1200`，与数据文件的形态不符。
    """
    if body is None:
        return
    if resolved.requires_array_body and not isinstance(body, list):
        raise MidasSchemaShapeMismatch(resolved.definition.key, "flat_array")
    if resolved.requires_object_body and not isinstance(body, Mapping):
        raise MidasSchemaShapeMismatch(resolved.definition.key, "flat_object")


class MidasHttpClient:
    """MIDAS REST 客户端（`docs/04` §6；`docs/07` §7.3）。

    ⚠️ 本类**不**做任何业务判断（那是 `operations.py` / `adapter.py` 的职责），
    只负责：护栏 → 构造 → 发请求 → 归一化错误。
    """

    def __init__(
        self,
        base_url: str,
        credential_provider: CredentialProviderLike,
        secret_ref: str,
        *,
        budget_seconds: float = DEFAULT_BUDGET_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """绑定 Base URL / 凭据引用 / 传输（**不**做任何 I/O，**不**取凭据）。

        Args:
            base_url: 实例 Base URL（普通配置，**不**是 secret）。
            credential_provider: 凭据提供者（`docs/04` §5.1）。
            secret_ref: 凭据**引用名**（值只在发请求时取，见裁决 1）。
            budget_seconds: 缺省超时预算（可按端点 `execution_mode` 覆盖）。
            transport: 可注入的传输（Contract Test 的 L3 Mock Transport，`docs/04` §71）。
        """
        self._base_url = str(base_url).rstrip("/")
        self._credentials = credential_provider
        self._secret_ref = str(secret_ref)
        self._budget_seconds = float(budget_seconds)
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    # ===== 诊断（绝不暴露凭据）=====

    def __repr__(self) -> str:
        """诊断表示：只含 Base URL 与预算，**不含**凭据（见裁决 1）。"""
        return f"MidasHttpClient(base_url={self._base_url!r}, budget={self._budget_seconds})"

    @property
    def base_url(self) -> str:
        """实例 Base URL（非 secret）。"""
        return self._base_url

    @property
    def secret_ref(self) -> str:
        """凭据**引用名**（非 secret；值不暴露）。"""
        return self._secret_ref

    # ===== 请求构造（`docs/07` §7.3）=====

    def build_request(
        self,
        resolved: ResolvedEndpoint,
        *,
        operation: str,
        body: Mapping[str, Any] | Sequence[Any] | None = None,
        wrapper: str = "none",
        items_style: bool = False,
        item_id: str | int | None = None,
        item_ids: Sequence[str] = (),
        solver: str = "",
        allow_unverified: bool = False,
    ) -> BuiltRequest:
        """护栏 + 构造（**不**发请求；见裁决 3）。

        Args:
            resolved: 已解析端点（`registry.py`）。
            operation: 规范化的 StructAI Operation 名（只作诊断）。
            body: Transformer 产出的**条目**（单条或列表）。
            wrapper: 请求体包装键（`Argument` / `Assign` / `none`）。
            items_style: 该端点是否用 `ITEMS` 数组承载条目。
            item_id: 单条写入的原生编号（`Assign` 包装的键）。
            item_ids: 删除目标的路径 key（`docs/07` §6.4）。
            solver: 实例求解器（用于门控）。
            allow_unverified: 仅 Contract Test 使用（见裁决 5）。

        Returns:
            已构造的请求。

        Raises:
            MidasEndpointDisabled: 端点被数据文件禁用。
            RegistryMappingNotVerified: `verification_status != VERIFIED`。
            MidasSolverUnsupported: 求解器不匹配。
            MidasGlobalDeleteRejected: 破坏性形态会被解释为删全表。
            MidasSchemaShapeMismatch: 请求体形态不符。
        """
        guard_enabled(resolved)
        guard_verified(resolved, operation=operation, allow_unverified=allow_unverified)
        guard_solver(resolved, solver)

        method = resolved.method
        payload = self._wrap(
            resolved, body=body, wrapper=wrapper, items_style=items_style, item_id=item_id
        )
        if method == "DELETE":
            guard_destructive(
                resolved,
                method=method,
                item_ids=item_ids,
                payload=payload if isinstance(payload, Mapping) else None,
            )
        guard_shape(resolved, payload)

        uri = resolved.uri
        if method == "DELETE" and item_ids:
            uri = f"{uri}/{','.join(str(item) for item in item_ids)}"
        return BuiltRequest(
            operation=str(operation),
            endpoint=resolved.definition.key,
            product=resolved.product,
            method=method,
            uri=uri,
            body=payload,
            wrapper=wrapper,
            table_type=resolved.table_type,
            budget_seconds=self.budget_for(resolved),
        )

    def budget_for(self, resolved: ResolvedEndpoint) -> float:
        """按 `execution_mode` 取超时预算（见裁决 2；未登记 → 缺省预算）。"""
        mode = resolved.definition.execution_mode
        return EXECUTION_MODE_BUDGETS.get(mode, self._budget_seconds)

    # ===== 发请求（`docs/04` §6）=====

    async def send(self, request: BuiltRequest) -> dict[str, Any]:
        """发出已构造的请求并解析 JSON（错误一律归一化）。"""
        return (await self.send_result(request)).payload

    async def send_result(self, request: BuiltRequest) -> SendResult:
        """发出已构造的请求，**如实**回报原生状态码 + 解析后的载荷（P139）。

        Returns:
            `SendResult`；`2xx` 的原生状态码**原样**回传（不再假定 `200`）。

        Raises:
            MidasAPIError 及其子类：`4xx` / `5xx`（`details.status_code` 即原生状态码）。
        """
        response = await self._request(
            request.method,
            request.uri,
            body=request.body,
            budget_seconds=request.budget_seconds,
            endpoint=request.endpoint,
        )
        return SendResult(
            status_code=int(response.status_code),
            payload=_json_body(response, endpoint=request.endpoint),
        )

    async def get(self, path: str, *, budget_seconds: float | None = None) -> dict[str, Any]:
        """`GET {path}`（`docs/04` §6）。"""
        response = await self._request(
            "GET", path, body=None, budget_seconds=budget_seconds, endpoint=path
        )
        return _json_body(response, endpoint=path)

    async def post(
        self,
        path: str,
        *,
        json_body: Mapping[str, Any] | Sequence[Any] | None = None,
        budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        """`POST {path}`（`docs/04` §6）。"""
        response = await self._request(
            "POST", path, body=json_body, budget_seconds=budget_seconds, endpoint=path
        )
        return _json_body(response, endpoint=path)

    async def put(
        self,
        path: str,
        *,
        json_body: Mapping[str, Any] | Sequence[Any] | None = None,
        budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        """`PUT {path}`（`docs/04` §6）。"""
        response = await self._request(
            "PUT", path, body=json_body, budget_seconds=budget_seconds, endpoint=path
        )
        return _json_body(response, endpoint=path)

    async def delete(
        self,
        path: str,
        *,
        budget_seconds: float | None = None,
    ) -> dict[str, Any]:
        """`DELETE {path}`（`docs/04` §6；路径 key 由调用方保证，见裁决 4）。"""
        response = await self._request(
            "DELETE", path, body=None, budget_seconds=budget_seconds, endpoint=path
        )
        return _json_body(response, endpoint=path)

    async def probe(self, path: str, *, budget_seconds: float | None = None) -> int:
        """零副作用探测（`registry/README.md` §7.1 第 2 步）：只回状态码。

        `404` = 不支持；`200` = 支持。**不**落盘、**不**抛业务错误。
        """
        try:
            response = await self._raw("GET", path, body=None, budget_seconds=budget_seconds)
        except (MidasConnectionError, MidasTimeoutError):
            raise
        return int(response.status_code)

    async def probe_payload(
        self, path: str, *, budget_seconds: float | None = None
    ) -> ProbeResponse:
        """零副作用探测并**如实回报**状态码与载荷形态（L4 探针用；P134 新增）。

        与 `probe()` 的差别：后者只回状态码，本方法额外回报顶层键与字节数，
        供 `live.py` 判定「实测信封 == 数据侧声明的解包链」。**不**抛 4xx 业务错误
        （404 正是 L4 要记录的事实之一，`docs/07` §16 R76）。

        Raises:
            MidasConnectionError: `STRUCTAI-2000`，传输失败。
            MidasTimeoutError: `STRUCTAI-2300`，超时（云端中继首次调用会复现，
                见 `docs/07` §16 R84）。
        """
        response = await self._raw("GET", path, body=None, budget_seconds=budget_seconds)
        text = _text_of(response)
        payload: dict[str, Any] = {}
        json_ok = False
        if text.strip():
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, Mapping):
                payload = {str(key): value for key, value in parsed.items()}
                json_ok = True
        return ProbeResponse(
            status_code=int(response.status_code),
            payload=payload,
            body_bytes=len(text.encode("utf-8")),
            json_ok=json_ok,
        )

    async def close(self) -> None:
        """关闭底层连接池（幂等）。"""
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()

    # ===== 内部 =====

    def _wrap(
        self,
        resolved: ResolvedEndpoint,
        *,
        body: Mapping[str, Any] | Sequence[Any] | None,
        wrapper: str,
        items_style: bool,
        item_id: str | int | None,
    ) -> dict[str, Any] | list[Any] | None:
        """按包装键构造请求体（`docs/07` §7.3 第 1 / 4 步）。"""
        if body is None:
            return None
        if resolved.is_flat or wrapper in {"", "none"}:
            return dict(body) if isinstance(body, Mapping) else list(body)
        if wrapper == "Assign":
            if items_style:
                items = (
                    list(body)
                    if isinstance(body, Sequence) and not isinstance(body, str)
                    else [body]
                )
                return {"Assign": {"ITEMS": items}}
            key = "1" if item_id is None else str(item_id)
            item = dict(body) if isinstance(body, Mapping) else {}
            return {"Assign": {key: item}}
        if wrapper == "Argument":
            if isinstance(body, Mapping):
                return {"Argument": dict(body)}
            return {"Argument": {"ITEMS": list(body)}}
        return dict(body) if isinstance(body, Mapping) else list(body)

    def _http_client(self) -> httpx.AsyncClient:
        """惰性创建底层客户端（**不**在构造期做 I/O，**不**缓存凭据）。"""
        if self._client is None:
            self._client = httpx.AsyncClient(transport=self._transport)
        return self._client

    async def _request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | Sequence[Any] | None,
        budget_seconds: float | None,
        endpoint: str,
    ) -> httpx.Response:
        """发请求并按 20 码归一化（唯一实现点，见裁决 6）。"""
        response = await self._raw(method, path, body=body, budget_seconds=budget_seconds)
        _raise_for_status(response, endpoint=endpoint)
        return response

    async def _raw(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | Sequence[Any] | None,
        budget_seconds: float | None,
    ) -> httpx.Response:
        """真正发请求（凭据在此刻取，且只进请求头）。"""
        secret = await self._credentials.get_secret(self._secret_ref)
        headers = {
            MAPI_KEY_HEADER: secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        budget = float(budget_seconds if budget_seconds is not None else self._budget_seconds)
        url = f"{self._base_url}{path}"
        try:
            return await self._http_client().request(
                method.upper(),
                url,
                headers=headers,
                json=None if body is None else body,
                timeout=budget,
            )
        except httpx.TimeoutException as error:
            raise MidasTimeoutError("request_timed_out", endpoint=str(path)) from error
        except httpx.TransportError as error:
            raise MidasConnectionError("transport_error", endpoint=str(path)) from error


# ===== 内部辅助 =====


def _raise_for_status(response: httpx.Response, *, endpoint: str) -> None:
    """状态码 + 状态类文案 → 归一化错误（`docs/07` §11 补充）。"""
    text = _text_of(response).lower()
    if any(marker in text for marker in _CLIENT_NOT_CONNECTED_MARKERS):
        raise MidasConnectionError(
            "client_not_connected", endpoint=endpoint, status_code=int(response.status_code)
        )
    if any(marker in text for marker in _PROJECT_NOT_OPENED_MARKERS):
        raise MidasAPIError(
            "project_not_opened", endpoint=endpoint, status_code=int(response.status_code)
        )
    status = int(response.status_code)
    if status < 400:
        return
    if status in {401, 403}:
        raise MidasAuthenticationError(
            "authentication_failed", endpoint=endpoint, status_code=status
        )
    if status == 404:
        raise MidasAPIError("endpoint_not_found", endpoint=endpoint, status_code=status)
    raise MidasAPIError("software_api_error", endpoint=endpoint, status_code=status)


def _text_of(response: httpx.Response) -> str:
    """响应文本（**只**用于状态类文案匹配，不进 `details`）。"""
    try:
        return str(response.text)
    except Exception:  # pragma: no cover - 极端编码异常
        return ""


def _json_body(response: httpx.Response, *, endpoint: str) -> dict[str, Any]:
    """解析响应 JSON（空体 → `{}`；非 JSON → 明确错误）。"""
    text = _text_of(response)
    if not text.strip():
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as error:
        raise MidasAPIError(
            "response_not_json", endpoint=endpoint, status_code=int(response.status_code)
        ) from error
    if isinstance(parsed, Mapping):
        return {str(key): value for key, value in parsed.items()}
    return {"value": parsed}


# ===== 凭据（`docs/04` §5.1；`.env.example` 的 P01 登记口径）=====

MIDAS_BASE_URL_ENV: Final[str] = "MIDAS_BASE_URL"
MIDAS_MAPI_KEY_ENV: Final[str] = "MIDAS_MAPI_KEY"
"""`.env.example`（P01）已登记的**唯一**变量名（见 `health.py` 的模块裁决 1）。"""


class MidasEnvironmentCredential:
    """从运行环境读取 MAPI-Key（`docs/07` §8.5 / §14.3）。

    ⚠️ 与既有 `EnvironmentCredentialProvider` 的差别**只有前缀**：后者把引用名
    规范化成 `STRUCTAI_SECRET_<REF>`，而 `.env.example` 早已把 MIDAS 的变量名
    登记为 `MIDAS_MAPI_KEY`（值一律留空）。本类因此把**引用名当作变量名**，
    以免出现「运维按 `.env.example` 配置、进程却读另一个名字」的部署陷阱。
    需要前缀口径时，注入既有的 `EnvironmentCredentialProvider` 即可。
    """

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        """绑定环境映射（`None` → 进程 `os.environ`；**不**复制，便于测试注入）。"""
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    async def get_secret(self, reference: str) -> str:
        """按变量名读取凭据值（缺失 / 空白 → `STRUCTAI-7000`，**不**回落空串）。

        Raises:
            InternalError: `STRUCTAI-7000`，`details = {"stage": "credentials",
                "reason": "secret_not_configured"}`（**不**回显变量名以外的任何值）。
        """
        value = self._environ.get(str(reference))
        if value is None or not value.strip():
            raise InternalError(
                "credential is not configured in the runtime environment",
                details={"stage": "credentials", "reason": "secret_not_configured"},
            )
        return value

    async def set_secret(self, reference: str, value: str) -> None:
        """**显式拒绝**：凭据只由运行环境注入（`docs/07` §8.5）。

        Raises:
            RuntimeError: 恒定 —— 本进程不得把凭据写回任何存储。
        """
        raise RuntimeError(
            "credentials are injected by the runtime environment only; "
            "the process must never write them back (docs/07 §8.5 / §14.3)"
        )

    async def delete_secret(self, reference: str) -> None:
        """**显式拒绝**：凭据只由运行环境注入（`docs/07` §8.5）。

        Raises:
            RuntimeError: 恒定 —— 本进程不得删除环境中的凭据。
        """
        raise RuntimeError(
            "credentials are injected by the runtime environment only; "
            "the process must never delete them (docs/07 §8.5 / §14.3)"
        )

    def __repr__(self) -> str:
        """诊断表示：**不含**任何值，只报是否已配置。"""
        return f"MidasEnvironmentCredential(configured={MIDAS_MAPI_KEY_ENV in self._environ})"
