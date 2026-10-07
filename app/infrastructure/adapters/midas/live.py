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
   数据侧只提供 6 项里的一部分，**Response Schema 已确认** 这一项在本仓库的数据里
   **恒为假**（`registry/` 无 response 方向 Schema）—— 故**任何**端点都**不**得升
   `VERIFIED`，如实保持 `PARTIAL` 并报出缺哪一项（`docs/07` §16 R78）。
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
    "EMPTY_BLOCK_KEY",
    "LIVE_PROJECT_ENV",
    "MAX_PROBE_ATTEMPTS",
    "MIDAS_LIVE_ENV",
    "PROBE_FAILED",
    "PROBE_PARTIAL",
    "PROBE_PASSED",
    "PROBE_SKIPPED",
    "SEVEN_AND_ITEMS",
    "STATUS_PARTIAL",
    "STATUS_VERIFIED",
    "BusinessEffectOutcome",
    "DedicatedTestProject",
    "LiveProbeReport",
    "LiveProbeResult",
    "MidasLiveBusinessEffect",
    "MidasLiveProber",
    "SevenAndVerdict",
    "dedicated_test_project_from_env",
    "live_opt_in_from_env",
    "read_verifications",
    "record_verifications",
    "registry_evidence",
    "seven_and_verdict",
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
        "request_schema_confirmed": registry.effective_schema(key) is not None,
        "response_schema_confirmed": _has_response_schema(registry, key),
        "product_scope_confirmed": product in definition.products
        or product in definition.overrides,
        "version_range_confirmed": bool(supported_versions)
        and str(version) in {str(item) for item in supported_versions},
        "live_contract_test_passed": str(live_outcome) == PROBE_PASSED,
    }


def _has_response_schema(registry: MidasRegistry, key: str) -> bool:
    """数据侧是否存在 **response** 方向的 Schema（见裁决 5）。

    ⚠️ `registry/` 目前**只有**请求 Schema（`midas_api_schemas.direction = "request"`），
    因此本项在数据上**恒为假** —— 这正是 `VERIFIED` 不得升级的唯一原因，
    也是「如实保持 `PARTIAL` 并说明缺哪一项」的可执行判定。
    """
    document = registry.schema_document(key)
    if document is None:
        return False
    return str(document.get("direction") or "request") == "response"


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
