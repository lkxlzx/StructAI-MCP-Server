"""Infrastructure · Adapters · MIDAS · Live —— L4 / L5 实测契约层（`docs/04` §69–§72）。

权威来源
--------
- `docs/04` §69（Contract Test 目的）—— 证明「Registry 描述 == 真实 MIDAS API」；
  测试对象 = `HTTP Method` / `Path` / `Request` / `Response` / `Status` / `Schema` /
  `Business Effect`。
- `docs/04` §71（分层）—— **L4** Live MIDAS Contract Test · **L5** Business Effect Test；
  CI 默认 L1–L3，L4–L5 需**专用 MIDAS 环境**。
- `docs/04` §72（安全）—— Live Test **必须**使用专用实例 / 专用 API Key / 专用项目 /
  专用测试模型；**不得**触碰生产模型。
- `docs/04` §8（Registry 状态）—— `VERIFIED` 是 **7 项 AND**；本模块按该 7 项
  给出**可执行**判定（`docs/07` §16 R1 / R78）。
- `docs/04` §18（API Contract Snapshot）—— 记录 `method` / `path` / `schema_hash` /
  `tested_at`。

落地裁决（只补实现手段，不改任何取值）
------------------------------------
1. **L4 是「只读探针」**：`MidasLiveProber` 只发 `GET`，逐端点记录
   「实测 `method` / `path` / 状态码 / 顶层键 / 期望解包链 / schema hash」。
   **零副作用** —— 不写、不删、不改（`docs/04` §72）。
2. **信封判定复用数据侧的解包链**（`docs/07` §16 R83）：`ResolvedEndpoint.read_path`
   是唯一口径；本模块**不**另写一套「顶层键应该叫什么」的规则。
3. **状态码如实分类**（`docs/07` §16 R76 / R84）：
   2xx 且信封命中 → `PASSED`；2xx 且 `{"message": ""}`（该数据块在当前模型上为空）
   → `PARTIAL`（**不**算失败）；2xx 但信封不命中 → `FAILED`；2xx 但数据侧**未声明**
   解包链 → `PARTIAL`（`read_root_undeclared_in_registry`）；4xx / 5xx → `FAILED`
   （如 `-M1` 端点与 `DB.SPAN` 在 GEN NX 上 404）；传输失败 / 超时 → `SKIPPED`
   （云端中继首次调用会复现，见 R84）。
4. **L5 只在专用测试项目上执行**（`docs/04` §72）：专用项目由**环境变量显式声明**，
   缺失时 `MidasLiveBusinessEffect` 直接**拒绝**（`dedicated_test_project_not_declared`），
   **绝不**回落到「当前打开的项目」；创建 / 读回 / 删除**只**针对本次自己创建的 ID。
5. **`VERIFIED` 的 7 项 AND 逐项可执行**（`seven_and_verdict` / `registry_evidence`）：
   数据侧只提供 6 项里的一部分；**Response Schema 已确认** 这一项在 P136 之前
   **恒为假**（`registry/` 只有请求方向 Schema，`docs/07` §16 R87）。P136 起数据侧为
   **已实测**的端点补了 `direction: response` 的 `response` 块
   （`registry/tools/sync_response_schemas.py`；`registry/README.md` §2.2），
   故该项**按数据如实判定**：声明了即为真，未声明（`availability` 非 `verified`、
   或该端点没有 Schema 文件）即为假 —— 缺项时如实保持 `PARTIAL` 并报出缺哪一项
   （`docs/07` §16 R78 / R87）。
6. **凭据只经运行环境**：本模块**不**读任何凭据（由 `MidasHttpClient` +
   `MidasEnvironmentCredential` 负责），记录里**只**有状态码 / 键名 / 哈希 ——
   **绝不**落库响应体原文、请求体原文或 MAPI-Key（`docs/07` §14.3）。
7. **本模块不 commit**：事务边界只归 `UnitOfWork`（`docs/07` §14.4 / `docs/02` §16）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块位于 MIDAS 子包内（`grep -ri midas app/` 的唯一豁免区），依赖 SQLAlchemy
与同包的 `client.py` / `registry.py` / `errors.py` / `models.py`；**不**依赖
`app.interfaces`，**不**被 Core 引用。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.adapters.midas.client import MidasHttpClient
from app.infrastructure.adapters.midas.errors import (
    MidasCapabilityError,
    MidasConnectionError,
    MidasTimeoutError,
)
from app.infrastructure.adapters.midas.models import MidasApiVerificationORM
from app.infrastructure.adapters.midas.registry import MidasRegistry, ResolvedEndpoint
from app.infrastructure.adapters.midas.transforms import TRANSFORMER_REGISTRY
from app.infrastructure.database.base import utcnow

__all__ = [
    "CONTRACT_LEVEL_L4",
    "CONTRACT_LEVEL_L5",
    "BODY_METHODS",
    "EMPTY_BLOCK_KEY",
    "LIVE_PROJECT_ENV",
    "MAX_PROBE_ATTEMPTS",
    "MIDAS_LIVE_ENV",
    "PROBE_FAILED",
    "PROBE_PARTIAL",
    "PROBE_PASSED",
    "PROBE_SKIPPED",
    "RESULT_QUERY_NAMESPACE",
    "SEVEN_AND_ITEMS",
    "STATUS_PARTIAL",
    "STATUS_VERIFIED",
    "WRITE_PATH_METHODS",
    "WriteCoverage",
    "BusinessEffectOutcome",
    "DedicatedTestProject",
    "LiveProbeReport",
    "LiveProbeResult",
    "MidasLiveBusinessEffect",
    "MidasLiveProber",
    "SevenAndVerdict",
    "dedicated_test_project_from_env",
    "has_request_body",
    "not_applicable_items",
    "live_opt_in_from_env",
    "model_write_keys",
    "read_verifications",
    "record_verifications",
    "registry_evidence",
    "result_query_keys",
    "seven_and_verdict",
    "write_only_keys",
    "write_path_coverage",
    "write_path_keys",
]

CONTRACT_LEVEL_L4: Final[str] = "L4"
CONTRACT_LEVEL_L5: Final[str] = "L5"
"""`docs/04` §71 的专用环境两层（CI 层 L1–L3 见 `tests/test_midas_contract_p124.py`）。"""

PROBE_PASSED: Final[str] = "PASSED"
PROBE_FAILED: Final[str] = "FAILED"
PROBE_PARTIAL: Final[str] = "PARTIAL"
PROBE_SKIPPED: Final[str] = "SKIPPED"
"""探针结论（写进 `midas_api_verifications.status`；见裁决 3）。"""

STATUS_VERIFIED: Final[str] = "VERIFIED"
STATUS_PARTIAL: Final[str] = "PARTIAL"
"""`docs/04` §8 的状态取值里本模块用到的两个（其余由数据侧机械映射）。"""

EMPTY_BLOCK_KEY: Final[str] = "message"
"""实测空块形态（CIVIL NX 的只读端点返回 `{"message": ""}`；见裁决 3）。"""

MIDAS_LIVE_ENV: Final[str] = "MIDAS_LIVE_L4"
"""L4/L5 的**显式开关**（测试侧 opt-in；缺省不跑真实实例）。"""

LIVE_PROJECT_ENV: Final[str] = "MIDAS_LIVE_PROJECT"
"""专用测试项目声明（`docs/04` §72 第 3 要素；**只**经环境变量，值不落盘）。"""

MAX_PROBE_ATTEMPTS: Final[int] = 3
"""重试上限（云端中继首次调用会超时，`docs/07` §16 R84 的可执行容忍）。"""

SEVEN_AND_ITEMS: Final[tuple[str, ...]] = (
    "official_endpoint_confirmed",
    "http_method_confirmed",
    "request_schema_confirmed",
    "response_schema_confirmed",
    "product_scope_confirmed",
    "version_range_confirmed",
    "live_contract_test_passed",
)
"""`docs/04` §8 的 `VERIFIED` 七项 AND（逐条照抄；见裁决 5）。"""

BODY_METHODS: Final[tuple[str, ...]] = ("POST", "PUT", "PATCH")
"""会产生**请求体**的方法（`docs/07` §6；`DELETE` 的 key 走路径 / 查询，不算请求体）。"""


def has_request_body(registry: MidasRegistry, key: str) -> bool:
    """该端点是否可能有**请求体**（`methods` 里含 `BODY_METHODS` 之一）。

    Args:
        registry: 已装载的 `registry/`。
        key: Registry key。

    Returns:
        含 `POST` / `PUT` / `PATCH` 时为真；纯 `GET` 端点（如 `OPE.PROJECTSTATUS`）为假。
    """
    methods = {str(method).upper() for method in registry.endpoint(key).methods}
    return any(method in methods for method in BODY_METHODS)


def not_applicable_items(registry: MidasRegistry, key: str) -> tuple[str, ...]:
    """7 项 AND 里对**该端点不适用**（因而不构成缺口）的项 —— P138b 裁决。

    裁决（`docs/07` §16 R5，P138b）：`request_schema_confirmed` 对**无请求体**的端点
    （`methods` 不含 `POST` / `PUT` / `PATCH`）**不适用** —— 没有请求体就没有请求 Schema
    可确认，把「没有请求 Schema」判成缺口是**类别错误**，会让这类端点**永远** `PARTIAL`。
    本函数把该裁决变成**可执行判定**：不适用 ⇒ 该项视为满足（`registry_evidence` 里为真），
    同时**如实**报出「是哪一项、为什么」。

    ⚠️ 只对**无请求体**的端点生效：带 `POST` 的端点（如 `OPE.STORYPROP`）仍如实判假。

    Args:
        registry: 已装载的 `registry/`。
        key: Registry key。

    Returns:
        不适用项名（当前至多一项）；不适用时为**空元组**。
    """
    if has_request_body(registry, key):
        return ()
    return ("request_schema_confirmed",)


# ===== L4 探针 =====


@dataclass(frozen=True, slots=True)
class LiveProbeResult:
    """一个端点在某个实例上的 **L4 实测**结论（`docs/04` §18 的 Snapshot 字段）。"""

    instance: str
    product: str
    key: str
    method: str
    uri: str
    read_root: str
    read_path: tuple[str, ...]
    schema_hash: str
    status_code: int
    outcome: str
    detail: str
    top_level_keys: tuple[str, ...] = ()
    body_bytes: int = 0
    attempts: int = 1

    @property
    def is_passed(self) -> bool:
        """是否命中「Registry 描述 == 真实 API」。"""
        return self.outcome == PROBE_PASSED

    def as_record(
        self, *, version_range: str, contract_level: str = CONTRACT_LEVEL_L4
    ) -> dict[str, Any]:
        """写进 `midas_api_verifications` 的一行（**不含**任何响应体 / 凭据）。"""
        return {
            "endpoint_key": self.key,
            "contract_level": str(contract_level),
            "product": self.product,
            "version_range": str(version_range),
            "method": self.method,
            "path": self.uri,
            "status": self.outcome,
            "schema_hash": self.schema_hash,
            "detail": self.detail,
            "verified_at": utcnow(),
        }


@dataclass(frozen=True, slots=True)
class LiveProbeReport:
    """一次 L4 探测的汇总（**只**含计数与端点标识，便于作为验收证据）。"""

    instance: str
    product: str
    results: tuple[LiveProbeResult, ...] = ()
    generated_at: datetime | None = None

    def counts(self) -> dict[str, int]:
        """按结论计数（升序键）。"""
        totals: dict[str, int] = {}
        for result in self.results:
            totals[result.outcome] = totals.get(result.outcome, 0) + 1
        return dict(sorted(totals.items()))

    def failures(self) -> tuple[LiveProbeResult, ...]:
        """`FAILED` 的条目（验收时要逐条解释）。"""
        return tuple(result for result in self.results if result.outcome == PROBE_FAILED)

    def undeclared(self) -> tuple[LiveProbeResult, ...]:
        """数据侧未声明解包链的条目（R14 的收口清单）。"""
        return tuple(
            result for result in self.results if result.detail == "read_root_undeclared_in_registry"
        )


class MidasLiveProber:
    """**只读** L4 探针（`docs/04` §69 / §71；见裁决 1）。"""

    def __init__(
        self,
        client: MidasHttpClient,
        registry: MidasRegistry,
        *,
        instance: str,
        product: str,
    ) -> None:
        """绑定客户端 / Registry / 实例标识（**不**做 I/O）。"""
        self._client = client
        self._registry = registry
        self._instance = str(instance)
        self._product = str(product)

    @property
    def instance(self) -> str:
        """实例标识（诊断用；**不是** Base URL，更不是凭据）。"""
        return self._instance

    @property
    def product(self) -> str:
        """数据侧的产品键（如 `GEN_NX`）。"""
        return self._product

    def read_keys(self) -> tuple[str, ...]:
        """该实例上**只读可用**的端点 key（`GET` + `enabled` + 产品可得）。"""
        keys: list[str] = []
        for key in self._registry.keys():
            definition = self._registry.endpoint(key)
            if "GET" not in definition.methods or not definition.enabled:
                continue
            if self._product in definition.products or self._product in definition.overrides:
                keys.append(key)
        return tuple(keys)

    async def probe(self, key: str) -> LiveProbeResult:
        """探测一个端点（**只**发 `GET`，**不**抛 4xx 业务错误）。"""
        resolved = self._registry.resolve(key=key, product=self._product, method="GET")
        schema_hash = _schema_hash(self._registry, key)
        attempts = 1
        while True:
            try:
                response = await self._client.probe_payload(resolved.uri)
                break
            except (MidasTimeoutError, MidasConnectionError) as error:
                attempts += 1
                if attempts > MAX_PROBE_ATTEMPTS:
                    return _result(
                        self,
                        resolved,
                        schema_hash=schema_hash,
                        status_code=0,
                        outcome=PROBE_SKIPPED,
                        detail=f"transport_error:{type(error).__name__}",
                        attempts=attempts,
                    )
        outcome, detail = _classify(
            resolved, response.status_code, response.payload, response.json_ok
        )
        return _result(
            self,
            resolved,
            schema_hash=schema_hash,
            status_code=response.status_code,
            outcome=outcome,
            detail=detail,
            top_level_keys=tuple(str(name) for name in response.payload),
            body_bytes=response.body_bytes,
            attempts=attempts,
        )

    async def probe_keys(self, keys: Sequence[str]) -> LiveProbeReport:
        """逐个探测给定 key（顺序执行；**不**并发打真实实例）。"""
        results = tuple([await self.probe(key) for key in keys])
        return LiveProbeReport(
            instance=self._instance,
            product=self._product,
            results=results,
            generated_at=utcnow(),
        )

    async def probe_all_read_endpoints(self) -> LiveProbeReport:
        """探测该实例上全部只读端点（L4 的全量口径）。"""
        return await self.probe_keys(self.read_keys())


def _result(
    prober: MidasLiveProber,
    resolved: ResolvedEndpoint,
    *,
    schema_hash: str,
    status_code: int,
    outcome: str,
    detail: str,
    top_level_keys: tuple[str, ...] = (),
    body_bytes: int = 0,
    attempts: int = 1,
) -> LiveProbeResult:
    """构造一条探针结果（唯一的构造点）。"""
    return LiveProbeResult(
        instance=prober.instance,
        product=prober.product,
        key=resolved.definition.key,
        method=resolved.method,
        uri=resolved.uri,
        read_root=resolved.read_root,
        read_path=tuple(resolved.read_path),
        schema_hash=schema_hash,
        status_code=int(status_code),
        outcome=str(outcome),
        detail=str(detail),
        top_level_keys=top_level_keys,
        body_bytes=int(body_bytes),
        attempts=int(attempts),
    )


def _classify(
    resolved: ResolvedEndpoint,
    status_code: int,
    payload: Mapping[str, Any],
    json_ok: bool,
) -> tuple[str, str]:
    """状态码 + 载荷 → `(结论, 说明)`（**唯一**判定点；见裁决 3）。"""
    if status_code >= 400:
        return PROBE_FAILED, f"http_{int(status_code)}"
    if not json_ok:
        return PROBE_FAILED, "response_not_json"
    if not payload:
        # `{}` = 该数据块在当前模型上为空（GEN NX 的 `OPE.SECTPROP` 实测形态）——
        # 与 `{"message": ""}` 同族，**不**算「信封不符」（见裁决 3）。
        return PROBE_PARTIAL, "empty_data_block"
    if _is_empty_block(payload):
        return PROBE_PARTIAL, "empty_data_block"
    chain = tuple(resolved.read_path)
    if not chain:
        return PROBE_PARTIAL, "read_root_undeclared_in_registry"
    node: Any = payload
    for step in chain:
        if not isinstance(node, Mapping) or step not in node:
            return PROBE_FAILED, f"response_envelope_mismatch:{step}"
        node = node[step]
    if node is None:
        return PROBE_PARTIAL, "empty_data_block"
    return PROBE_PASSED, "envelope_confirmed"


def _is_empty_block(payload: Mapping[str, Any]) -> bool:
    """`{"message": ""}`（CIVIL NX 的空数据块形态）判定（见裁决 3）。"""
    return set(payload) == {EMPTY_BLOCK_KEY} and not payload.get(EMPTY_BLOCK_KEY)


def _schema_hash(registry: MidasRegistry, key: str) -> str:
    """端点 Schema 的 sha256（`docs/04` §18 / §107；无 Schema → 空串）。"""
    document = registry.schema_json(key)
    if document is None:
        return ""
    blob = json.dumps(document, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(blob).hexdigest()


# ===== 记录落库（`docs/04` §18；**不** commit，见裁决 7）=====


async def record_verifications(
    session: AsyncSession,
    results: Iterable[LiveProbeResult],
    *,
    version_range: str,
    contract_level: str = CONTRACT_LEVEL_L4,
) -> dict[str, int]:
    """把探针结论 upsert 进 `midas_api_verifications`（幂等；见裁决 7）。

    Returns:
        `{"inserted": n, "updated": n, "unchanged": n}`。
    """
    counters = {"inserted": 0, "updated": 0, "unchanged": 0}
    for result in results:
        record = result.as_record(version_range=version_range, contract_level=contract_level)
        identity = {
            "endpoint_key": record["endpoint_key"],
            "contract_level": record["contract_level"],
            "product": record["product"],
            "version_range": record["version_range"],
        }
        statement = select(MidasApiVerificationORM).filter_by(**identity)
        row = (await session.execute(statement)).scalars().first()
        if row is None:
            session.add(MidasApiVerificationORM(**{**identity, **record}))
            await session.flush()
            counters["inserted"] += 1
            continue
        changed = False
        for name, value in record.items():
            if name in identity:
                continue
            if getattr(row, name) != value:
                setattr(row, name, value)
                changed = True
        counters["updated" if changed else "unchanged"] += 1
    return counters


async def read_verifications(
    session: AsyncSession,
    *,
    key: str,
    contract_level: str = CONTRACT_LEVEL_L4,
) -> tuple[MidasApiVerificationORM, ...]:
    """回查某端点的 L4 记录（「真实写入且可回查」的可执行证据）。"""
    statement = (
        select(MidasApiVerificationORM)
        .where(
            MidasApiVerificationORM.endpoint_key == str(key),
            MidasApiVerificationORM.contract_level == str(contract_level),
        )
        .order_by(MidasApiVerificationORM.product)
    )
    return tuple((await session.execute(statement)).scalars().all())


# ===== 写路径覆盖（`docs/07` §16 R4 / R14；P138c）=====


WRITE_PATH_METHODS: Final[tuple[str, ...]] = ("POST", "PUT", "DELETE", "PATCH")
"""数据侧「**写路径**」方法集 —— R4 / R14 覆盖率的**分母**口径（唯一）。"""

RESULT_QUERY_NAMESPACE: Final[str] = "POST"
"""**结果表 / 文本导出**命名空间（`/POST/TABLE` · `/POST/TEXT` · `/POST/PM` ·
`/POST/STEELCODECHECK`）。

这些端点是**查询**：请求体用 `Argument.TABLE_TYPE`（或表名）**取表**，响应就是表本身；
它们**不创建 / 不修改 / 不删除**任何模型对象 → `docs/07` §16 R4 / R14 的 L5 三步链
（创建 → 读回 → 按路径 key 删除）**结构上不适用**（没有「自建 ID」可读回 / 可删）。

⚠️ **裁决（P141）：不挪分母。** `write_path_keys()` 仍是 R4 / R14 的**分母**（**609**）；
本常量只把分母**显式划分**成「**模型写端点**」与「**结果表 / 文本查询端点**」两个子桶，
并**同时**报两个覆盖率（`WriteCoverage.ratio` = 原口径；`WriteCoverage.model_write_ratio` =
子桶口径）—— 既**不**放宽判定，也**不**用子桶掩盖任何未覆盖的模型写端点。

**恢复 / 变更条件**：若将来要改用子桶作为 R4 / R14 的正式分母，必须是一次**显式裁决**
（写明判据与影响面），**不**得由本函数自动改变 `write_path_keys()` 的口径。"""


def write_path_keys(registry: MidasRegistry) -> tuple[str, ...]:
    """数据侧**写路径端点**（`methods` 含 `WRITE_PATH_METHODS` 之一），按 key 升序。

    ⚠️ 这是 R4 / R14 覆盖率的**分母**（**唯一**口径）：凡有写入方法的端点，其写路径都
    需要真实 L5 才算覆盖 —— 只读 L4 探针只覆盖 `GET`（`registry/README.md` §8.1）。
    其中**连 `GET` 都没有**的那部分（`write_only_keys`）是只读探针**完全**覆盖不到的。
    """
    keys: list[str] = []
    for key in registry.keys():
        try:
            definition = registry.endpoint(key)
        except Exception:  # noqa: BLE001 - 数据缺陷不应打断枚举
            continue
        methods = {str(method).upper() for method in definition.methods}
        if any(method in methods for method in WRITE_PATH_METHODS):
            keys.append(key)
    return tuple(sorted(keys))


def write_only_keys(registry: MidasRegistry) -> tuple[str, ...]:
    """数据侧**只写端点**（`methods` **不含** `GET`）—— 只读探针**完全**覆盖不到的那部分。

    这是 R4 / R14 里「只读探针覆盖不到」那句话的**可执行**含义（旧记录写 369 / 379，
    与任何可执行判定都对不上，已按本函数重算）。
    """
    keys: list[str] = []
    for key in registry.keys():
        try:
            definition = registry.endpoint(key)
        except Exception:  # noqa: BLE001 - 数据缺陷不应打断枚举
            continue
        methods = {str(method).upper() for method in definition.methods}
        if "GET" not in methods:
            keys.append(key)
    return tuple(sorted(keys))


def result_query_keys(registry: MidasRegistry) -> tuple[str, ...]:
    """分母里的**结果表 / 文本查询**端点（`namespace == RESULT_QUERY_NAMESPACE`；见该常量）。

    Returns:
        按 key 升序；`write_path_keys()` 的**子集**（判据只看数据侧的 `namespace`）。
    """
    namespace = f"{RESULT_QUERY_NAMESPACE}."
    return tuple(key for key in write_path_keys(registry) if key.startswith(namespace))


def model_write_keys(registry: MidasRegistry) -> tuple[str, ...]:
    """分母里的**模型写**端点 = `write_path_keys()` − `result_query_keys()`（见上方常量）。"""
    excluded = set(result_query_keys(registry))
    return tuple(key for key in write_path_keys(registry) if key not in excluded)


@dataclass(frozen=True, slots=True)
class WriteCoverage:
    """写路径覆盖的**唯一**口径（R4 / R14 共用；P138c 裁决，P141 加**子桶**）。

    `total` / `ratio` 仍是 R4 / R14 的**正式**口径（`write_path_keys()`，**609**）；
    `model_write` / `model_write_ratio` 是**同一分母**下的子桶（见 `RESULT_QUERY_NAMESPACE`），
    只用于说明「结果表 / 文本查询端点」在 L5 三步链下**结构上不适用**的那一部分，
    **不**替代正式口径、**不**放宽任何判定。
    """

    covered: int
    total: int
    write_only: int = 0
    covered_keys: tuple[str, ...] = ()
    total_keys: tuple[str, ...] = ()
    result_query: int = 0
    model_write: int = 0
    model_write_covered: int = 0

    @property
    def ratio(self) -> str:
        """`<分子> / <分母>`（报告与文档**只**引用它，避免两处口径不一致）。"""
        return f"{self.covered} / {self.total}"

    @property
    def model_write_ratio(self) -> str:
        """**子桶**口径：`<模型写分子> / <模型写分母>`（见 `RESULT_QUERY_NAMESPACE` 的裁决）。"""
        return f"{self.model_write_covered} / {self.model_write}"

    def as_dict(self) -> dict[str, Any]:
        """诊断映射（**不含**凭据 / 响应体）。"""
        return {
            "covered": self.covered,
            "total": self.total,
            "write_only": self.write_only,
            "ratio": self.ratio,
            "result_query": self.result_query,
            "model_write": self.model_write,
            "model_write_covered": self.model_write_covered,
            "model_write_ratio": self.model_write_ratio,
            "covered_keys": list(self.covered_keys),
        }


def write_path_coverage(
    registry: MidasRegistry,
    rows: Iterable[object],
    *,
    contract_level: str = CONTRACT_LEVEL_L5,
) -> WriteCoverage:
    """按 `midas_api_verifications` 的 **L5** 行重算写路径覆盖（R4 / R14 的统一判定）。

    分子 = 有 `contract_level == L5` 且 `status == PASSED` 记录的**去重** key ∩ 写路径端点；
    分母 = `write_path_keys(registry)`。**不**沿用任何手工誊抄的旧数（P137 记录 R4 为
    `11 / 369`、R14 为 `379`，两处口径不一致）。

    Args:
        registry: 已装载的 `registry/`。
        rows: 验证记录（`MidasApiVerificationORM`，或任何带 `endpoint_key` /
            `contract_level` / `status` 属性的对象）。
        contract_level: 计入的行级口径；缺省 **L5**。

    Returns:
        `WriteCoverage`（分子 / 分母 / 逐 key 证据）。
    """
    write_keys = write_path_keys(registry)
    allowed = set(write_keys)
    passed: set[str] = set()
    for row in rows:
        if str(getattr(row, "contract_level", "")) != str(contract_level):
            continue
        if str(getattr(row, "status", "")) != PROBE_PASSED:
            continue
        key = str(getattr(row, "endpoint_key", ""))
        if key in allowed:
            passed.add(key)
    covered = tuple(sorted(passed))
    model_keys = model_write_keys(registry)
    model_allowed = set(model_keys)
    model_covered = tuple(key for key in covered if key in model_allowed)
    return WriteCoverage(
        covered=len(covered),
        total=len(write_keys),
        write_only=len(write_only_keys(registry)),
        covered_keys=covered,
        total_keys=write_keys,
        result_query=len(result_query_keys(registry)),
        model_write=len(model_keys),
        model_write_covered=len(model_covered),
    )


# ===== 七项 AND（`docs/04` §8；`docs/07` §16 R1 / R78）=====


@dataclass(frozen=True, slots=True)
class SevenAndVerdict:
    """`docs/04` §8 的 `VERIFIED` 判定结果（逐项给出满足 / 缺失）。"""

    status: str
    satisfied: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        """是否满足全部 7 项（**只**在 `missing` 为空时为真）。"""
        return self.status == STATUS_VERIFIED

    def as_dict(self) -> dict[str, Any]:
        """诊断用映射（**不含** secret）。"""
        return {
            "status": self.status,
            "satisfied": list(self.satisfied),
            "missing": list(self.missing),
        }


def seven_and_verdict(evidence: Mapping[str, bool]) -> SevenAndVerdict:
    """按 7 项 AND 给出 `VERIFIED` / `PARTIAL`（见裁决 5）。

    缺失的键按 **False** 处理（**不**假定满足），因此调用方漏传任何一项都**不会**
    得到 `VERIFIED`。`PARTIAL` 是唯一的下调目标 —— `UNVERIFIED` 的语义是
    「仅存在于草稿 / 未来版本」（`docs/04` §8），与本层不符。
    """
    missing = tuple(item for item in SEVEN_AND_ITEMS if not bool(evidence.get(item, False)))
    if missing:
        return SevenAndVerdict(
            status=STATUS_PARTIAL,
            satisfied=tuple(item for item in SEVEN_AND_ITEMS if item not in missing),
            missing=missing,
        )
    return SevenAndVerdict(status=STATUS_VERIFIED, satisfied=tuple(SEVEN_AND_ITEMS))


def registry_evidence(
    registry: MidasRegistry,
    *,
    key: str,
    product: str,
    version: str,
    supported_versions: Sequence[str],
    live_outcome: str = "",
) -> dict[str, bool]:
    """从**数据 + L4 实测**导出 7 项 AND 的证据（见裁决 5）。

    Args:
        registry: 已装载的 `registry/`。
        key: Registry key。
        product: 数据侧产品键。
        version: 实例声明的版本。
        supported_versions: `AdapterManifest.supported_versions`。
        live_outcome: L4 探针结论（空串 = 未实测 → 第 7 项为假）。

    Returns:
        7 个键的布尔证据（**恰好**等于 `SEVEN_AND_ITEMS`）。
    """
    definition = registry.endpoint(key)
    method_ok = False
    if definition.methods:
        resolved = registry.resolve(key=key, product=product)
        method_ok = bool(resolved.method)
    return {
        "official_endpoint_confirmed": bool(definition.uri.startswith("/")),
        "http_method_confirmed": method_ok,
        "request_schema_confirmed": (
            registry.effective_schema(key) is not None
            or "request_schema_confirmed" in not_applicable_items(registry, key)
        ),
        "response_schema_confirmed": _has_response_schema(registry, key),
        "product_scope_confirmed": product in definition.products
        or product in definition.overrides,
        "version_range_confirmed": bool(supported_versions)
        and str(version) in {str(item) for item in supported_versions},
        "live_contract_test_passed": str(live_outcome) == PROBE_PASSED,
    }


def _has_response_schema(registry: MidasRegistry, key: str) -> bool:
    """数据侧是否声明了 **response** 方向的 Schema（见裁决 5）。

    P136 起数据侧为**已实测**的端点补了 `response` 块
    （`registry/tools/sync_response_schemas.py`；`registry/README.md` §2.2），
    故本项**不再恒为假**：只有真声明了 `direction: response` 才为真。
    未声明的端点（`availability` 非 `verified`、或没有 Schema 文件）仍如实判假 ——
    这正是「如实保持 `PARTIAL` 并说明缺哪一项」的可执行判定（`docs/07` §16 R87）。
    """
    block = registry.response_schema_document(key)
    if block is None:
        return False
    return str(block.get("direction") or "") == "response"


# ===== L5 业务效果（`docs/04` §71 / §72；见裁决 4）=====


@dataclass(frozen=True, slots=True)
class DedicatedTestProject:
    """`docs/04` §72 的专用测试项目声明（**值只经环境变量**）。"""

    name: str

    def __repr__(self) -> str:
        """诊断表示：只报「已声明」，**不**回显项目名（可能是真实工程名）。"""
        return "DedicatedTestProject(declared=True)"


@dataclass(frozen=True, slots=True)
class BusinessEffectOutcome:
    """L5 的结论（创建 → 读回 → 删除，**只**针对自己创建的 ID）。"""

    key: str
    product: str
    steps: tuple[str, ...] = ()
    created_id: str = ""
    read_back: bool = False
    deleted: bool = False
    outcome: str = PROBE_SKIPPED
    detail: str = ""

    @property
    def is_passed(self) -> bool:
        """三步全部成立才算通过。"""
        return self.outcome == PROBE_PASSED

    def as_record(self, *, version_range: str, path: str) -> dict[str, Any]:
        """写进 `midas_api_verifications` 的 L5 行（**不含**响应体 / 凭据）。"""
        return {
            "endpoint_key": self.key,
            "contract_level": CONTRACT_LEVEL_L5,
            "product": self.product,
            "version_range": str(version_range),
            "method": "POST",
            "path": str(path),
            "status": self.outcome,
            "schema_hash": "",
            "detail": self.detail,
            "verified_at": utcnow(),
        }


def dedicated_test_project_from_env(environ: Mapping[str, str]) -> DedicatedTestProject | None:
    """读专用测试项目声明（缺失 → `None`；**不**回落「当前打开的项目」）。"""
    raw = str(environ.get(LIVE_PROJECT_ENV) or "").strip()
    return DedicatedTestProject(name=raw) if raw else None


def live_opt_in_from_env(environ: Mapping[str, str]) -> bool:
    """L4/L5 的显式开关（`MIDAS_LIVE_ENV`；缺省关闭）。"""
    raw = str(environ.get(MIDAS_LIVE_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


class MidasLiveBusinessEffect:
    """L5 业务效果验证（`docs/04` §71 / §72；见裁决 4）。

    🔴 **纪律**：只在**专用测试项目**（`docs/04` §72 第 3 要素）上执行，且
    **只**对自己创建的 ID 做 创建 → 读回 → 删除；`DELETE` **必须**带路径 key
    （`docs/07` §6.4 / §7.6：NX 系不带路径 key = 删全表）。
    """

    def __init__(
        self,
        client: MidasHttpClient,
        registry: MidasRegistry,
        *,
        product: str,
        project: DedicatedTestProject | None,
        node_key: str = "DB.NODE",
        transformer_name: str = "midas.node.v1",
        marker: float = 1.0,
    ) -> None:
        """绑定客户端 / Registry / 专用项目声明（**不**做 I/O）。

        Args:
            client: MIDAS 客户端（凭据由运行环境注入）。
            registry: 已装载的 `registry/`。
            product: 数据侧产品键（NX 系才有 `POST` / `DELETE`；Designer 的
                `DB.NODE` 在数据里**只有** `GET`，故 L5 默认跑 NX 系）。
            project: 专用测试项目声明；`None` → `run()` **明确拒绝**。
            node_key: 用于三步链的端点 key。
            transformer_name: 该端点的**原生转换器**名（数据侧 Transformer 注册表），
                canonical → native 的**唯一**转换点（`docs/04` §20–§23）。
            marker: 新建节点的坐标标记（便于人工核对，**不**覆盖既有节点）。
        """
        self._client = client
        self._registry = registry
        self._product = str(product)
        self._project = project
        self._node_key = str(node_key)
        self._transformer_name = str(transformer_name)
        self._marker = float(marker)

    @property
    def project(self) -> DedicatedTestProject | None:
        """专用测试项目声明（`None` = 未声明 → `run()` 直接拒绝）。"""
        return self._project

    async def run(self) -> BusinessEffectOutcome:
        """执行 L5 三步链（无专用项目声明 → 明确拒绝，**不**回落）。

        Raises:
            MidasCapabilityError: `STRUCTAI-3000`，未声明专用测试项目
                （`details.reason = "dedicated_test_project_not_declared"`）。
        """
        if self._project is None:
            raise MidasCapabilityError("dedicated_test_project_not_declared")
        create = self._registry.resolve(key=self._node_key, product=self._product, method="POST")
        read = self._registry.resolve(key=self._node_key, product=self._product, method="GET")
        delete = self._registry.resolve(key=self._node_key, product=self._product, method="DELETE")
        steps = ("list_existing", "create", "read_back", "delete")
        created_id = ""
        cleaned = False
        transformer = TRANSFORMER_REGISTRY[self._transformer_name](self._registry)
        try:
            existing = _existing_ids(
                await self._client.send(self._client.build_request(read, operation="LIVE.L5.LIST")),
                read,
            )
            # 🔴 只挑**未被占用**的编号：绝不覆盖既有节点（`docs/04` §72 的「专用测试模型」）
            created_id = str(
                max((int(item) for item in existing if str(item).isdigit()), default=0) + 1
            )
            native_body = transformer.to_native({"x": self._marker, "y": self._marker, "z": 0.0})
            create_request = self._client.build_request(
                create,
                operation="LIVE.L5.CREATE",
                body=native_body,
                wrapper=transformer.wrapper_key(),
                item_id=created_id,
            )
            await self._client.send(create_request)
            read_back = created_id in _existing_ids(
                await self._client.send(self._client.build_request(read, operation="LIVE.L5.READ")),
                read,
            )
            delete_request = self._client.build_request(
                delete, operation="LIVE.L5.DELETE", item_ids=(created_id,)
            )
            await self._client.send(delete_request)
            cleaned = True
            return BusinessEffectOutcome(
                key=self._node_key,
                product=self._product,
                steps=steps,
                created_id=created_id,
                read_back=read_back,
                deleted=True,
                outcome=PROBE_PASSED if read_back else PROBE_FAILED,
                detail="create_read_delete_confirmed" if read_back else "read_back_missing",
            )
        finally:
            # 兜底：**只**删除本次自己创建的 ID（已删则忽略；绝不动别人的 ID）
            if created_id and not cleaned:
                await self._best_effort_delete(delete, created_id)

    async def _best_effort_delete(self, resolved: ResolvedEndpoint, item_id: str) -> None:
        """兜底删除**自己创建的** ID（失败只忽略，不影响原始结论）。"""
        try:
            request = self._client.build_request(
                resolved, operation="LIVE.L5.CLEANUP", item_ids=(item_id,)
            )
            await self._client.send(request)
        except Exception:  # noqa: BLE001 - 清理路径不得掩盖原始结论
            return None


def _existing_ids(payload: Mapping[str, Any], resolved: ResolvedEndpoint) -> tuple[str, ...]:
    """读回结果里的原生编号集合（按数据侧解包链逐层取，**不**猜结构）。

    NX 系的 `DB.*` 读响应是**编号键映射**（`{<read_root>: {"1": {...}}}`，
    `registry/README.md` §4）；Designer 的 `result.return_value` 是数组，
    编号取条目里的 `ID`。两种形态都**只**做机械提取。
    """
    node: Any = payload
    for step in resolved.read_path:
        if not isinstance(node, Mapping) or step not in node:
            return ()
        node = node[step]
    if isinstance(node, Mapping):
        return tuple(str(key) for key in node)
    if isinstance(node, Sequence) and not isinstance(node, str):
        return tuple(
            str(item.get("id") or item.get("ID") or "")
            for item in node
            if isinstance(item, Mapping)
        )
    return ()
