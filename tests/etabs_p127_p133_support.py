"""P127–P133（第二个软件 Adapter：CSI ETABS）的**共享装配辅助**。

⚠️ 本模块**只**提供装配 / 扫描 / 规范原文副本，**不**承载任何断言：
每个测试自己用 `tmp_path` 建独立临时库、独立假 COM 派发
（沿用 `tests/midas_p119_p126_support.py` / `tests/p42_p48_support.py` 的既定风格）。

规范原文副本一律**写在测试侧**、不从被测模块导入 —— 这样「规范说 X」与
「实现给出 X」是两个独立事实。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

import p42_p48_support as core
from app.domain.enums import SoftwareConnectionState
from app.infrastructure.adapters.etabs import (
    CREDENTIAL_REFERENCE_KEY,
    EtabsAdapter,
    EtabsTimeoutError,
    install,
)
from app.infrastructure.database.models.software import (
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.infrastructure.registry.capability_registry import CapabilityRegistry
from app.infrastructure.registry.operation_registry import OperationRegistry

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
ETABS_PACKAGE_DIR = APP_DIR / "infrastructure" / "adapters" / "etabs"

# ===== 规范原文副本（**不**从被测模块导入）=====

MANIFEST_SPEC: tuple[str, str, str] = ("csi.etabs", "CSI", "ETABS")
"""`docs/07` §12 P127 + `docs/01` §20 L911–912 的 Manifest 取值（`name` 见实现裁决 1）。"""

SUPPORTED_VERSIONS_SPEC: tuple[str, ...] = ("22",)
"""`docs/01` §20 L913 / `docs/02` §58 L26178：ETABS 版本（严格精确匹配）。"""

PROTOCOLS_SPEC: tuple[str, ...] = ("COM",)
"""`docs/01` §20 L915 / `docs/03` §106 L3178：协议族。"""

TRACEABLE_FACT_SPEC: tuple[str, str, str, str] = (
    "ANALYSIS.STATIC",
    "engineering_analysis",
    "COM",
    "RunAnalysis",
)
"""`docs/02` §88 L7602–7612 / `docs/03` §106 L3173–3181：**唯一**可追溯的原生事实。"""

PROVENANCE_ANCHORS_SPEC: tuple[str, ...] = (
    "docs/02 §88 L7602-7612",
    "docs/03 §106 L3173-3181",
    "docs/01 §20 L907-918",
    "docs/02 §58 L26168-26183",
)
"""允许引用的出处锚点（逐字照抄 `catalogue.PROVENANCE_ANCHORS` 的规范侧副本）。"""

PARTIAL_OPERATIONS_SPEC: tuple[str, ...] = ("ANALYSIS.STATIC",)
"""本批**只**登记为 `PARTIAL` 的 Operation（其余 68 个**不入** catalogue）。"""

OPERATION_COUNTS_SPEC: tuple[tuple[str, int], ...] = core.TOOL_OPERATION_COUNTS_SPEC
"""9 Tool / **69** Operation（`docs/07` §5.1；与 P42–P48 同一份副本）。"""

HARDENING_ITEMS_SPEC: tuple[str, ...] = (
    "Connection pool",
    "Timeout",
    "Retry",
    "Circuit breaker",
    "Rate limit",
    "Concurrency",
    "Resource lock",
    "Credential rotation",
    "Secret redaction",
    "Structured logging",
    "Metrics",
    "Trace",
    "Audit",
    "Recovery",
    "Reconcile",
    "Contract test",
    "E2E",
    "Backup",
    "Version migration",
)
"""`docs/04` §151 的 **19** 项（逐字照抄）。"""

CONTRACT_LEVELS_CI: tuple[str, ...] = ("L1", "L2", "L3")
CONTRACT_LEVELS_DEDICATED: tuple[str, ...] = ("L4", "L5")
"""`docs/04` §71：CI 跑 L1–L3；L4–L5 需专用环境（本机**不**存在）。"""

SECRET = "probe-credential-not-a-real-secret"
"""测试用凭据（仅进程内注入，**不**落任何文件；`docs/07` §14.3）。"""

VENDOR_NAMES: tuple[str, ...] = core.VENDOR_NAMES
"""`docs/07` §14.2 的厂商名清单（与既有 14 个扫描测试同一份副本）。"""


# ===== 假 COM 派发（L3 Mock Transport；`docs/04` §71）=====


class RecordingDispatch:
    """记录全部原生调用的假 COM 派发（`docs/01` §20 的协议层）。

    ⚠️ 它是**我们自己的端口**（`lifecycle.ComDispatch`）的实现，不是任何厂商 SDK：
    `invoke` 只按 Adapter 给出的方法名与参数原样记录并回一个可配置的载荷。
    """

    def __init__(
        self,
        *,
        payload: Mapping[str, Any] | None = None,
        failures: tuple[str, ...] = (),
    ) -> None:
        """构造并绑定应答 / 失败脚本（`failures` 逐次消费）。"""
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.attached = False
        self.attach_count = 0
        self.detach_count = 0
        self.secrets: list[str | None] = []
        self._payload = dict(payload or {})
        self._failures = list(failures)

    async def attach(self, *, secret: str | None = None) -> None:
        """建立会话（记录凭据**值**只为验证轮换；**不**落盘）。"""
        self.attached = True
        self.attach_count += 1
        self.secrets.append(secret)

    async def detach(self) -> None:
        """释放会话（幂等）。"""
        self.attached = False
        self.detach_count += 1

    async def is_attached(self) -> bool:
        """会话是否可用。"""
        return self.attached

    async def invoke(self, *, method: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """记录一次原生调用并按脚本应答（超时用**传输层**的 `TimeoutError`）。"""
        self.calls.append((str(method), dict(arguments)))
        if self._failures:
            failure = self._failures.pop(0)
            if failure == "timeout":
                raise TimeoutError("native call timed out")
            raise RuntimeError("native call failed")
        return dict(self._payload)

    def methods(self) -> list[str]:
        """已发生的原生方法名（顺序即调用顺序）。"""
        return [method for method, _arguments in self.calls]


class FakeCredentialProvider:
    """测试用凭据提供者（`docs/07` §8.5：凭据只经注入，值**不**落盘）。"""

    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        """绑定引用名 → 值（可在测试中改写以模拟轮换）。"""
        self.values: dict[str, str] = dict(values or {})
        self.references: list[str] = []

    async def get_secret(self, reference: str) -> str:
        """按引用名读取凭据值（**不**回显给任何日志）。"""
        self.references.append(str(reference))
        return self.values[str(reference)]


# ===== 装配 =====


def etabs_adapter(
    dispatch: RecordingDispatch,
    *,
    allow_partial: bool = True,
    credential_provider: FakeCredentialProvider | None = None,
    credential_reference: str = "",
    budget_seconds: float = 3600.0,
) -> EtabsAdapter:
    """构造一个可连接的 ETABS Adapter（凭据只经内存注入）。"""
    return EtabsAdapter(
        dispatch=dispatch,
        credential_provider=credential_provider,
        credential_reference=credential_reference,
        allow_partial=allow_partial,
        budget_seconds=budget_seconds,
    )


def connect_config(**extra: Any) -> dict[str, Any]:
    """连接配置（版本来自实例声明；`docs/01` §20 L913）。"""
    return {"version": SUPPORTED_VERSIONS_SPEC[0], **extra}


async def insert_etabs_instance(
    factory: async_sessionmaker[AsyncSession],
    *,
    status: str = str(SoftwareConnectionState.CONNECTED),
    credential_reference: str = "",
) -> str:
    """插入 ETABS 软件实例（四级软件注册表；`docs/07` §4.3 #10–#13）。

    ⚠️ 软件实例行由**测试侧**用仓储插入（生产路径由部署方写入）—— `docs/04` §154 的
    「只增加 Adapter」因此不需要 Core 侧任何改动。
    """
    async with UnitOfWork.from_session_factory(factory) as uow:
        software = SoftwareORM(
            vendor=MANIFEST_SPEC[1],
            name=MANIFEST_SPEC[2],
            status=str(SoftwareConnectionState.CONNECTED),
        )
        uow.session.add(software)
        await uow.session.flush()
        product = SoftwareProductORM(software_id=str(software.id), product=MANIFEST_SPEC[2])
        uow.session.add(product)
        await uow.session.flush()
        version = SoftwareVersionORM(product_id=str(product.id), version=SUPPORTED_VERSIONS_SPEC[0])
        uow.session.add(version)
        await uow.session.flush()
        instance = SoftwareInstanceORM(
            version_id=str(version.id),
            name="ETABS 22 (P127)",
            endpoint=None,
            status=status,
            credential_reference=credential_reference or None,
        )
        uow.session.add(instance)
        await uow.session.flush()
        return str(instance.id)


async def software_instance_status(
    factory: async_sessionmaker[AsyncSession], instance_id: str
) -> str:
    """读回实例状态（`docs/02` §19 的连接生命周期）。"""
    async with factory() as session:
        row = (
            await session.execute(
                select(SoftwareInstanceORM.status).where(SoftwareInstanceORM.id == instance_id)
            )
        ).scalar()
    return str(row)


async def seeded_etabs_runtime(
    tmp_path: Path,
    monkeypatch: Any,
    *,
    name: str = "p127.db",
    allow_partial: bool = True,
    dispatch: RecordingDispatch | None = None,
    status: str = str(SoftwareConnectionState.CONNECTED),
) -> tuple[Any, async_sessionmaker[AsyncSession], dict[str, str], RecordingDispatch]:
    """装配「已配备库 + 进程级运行时 + 已注册 / 已连接的 ETABS 实例」。

    Returns:
        `(runtime, factory, ids, dispatch)`；`ids` 含 `tenant_id` / `user_id` /
        `project_id` / `instance_id` / `model_id`。
    """
    monkeypatch.setenv(core.ADMIN_PASSWORD_ENV, core.TEST_PASSWORD)
    settings = core.seeded_settings(tmp_path, name=name)
    engine: AsyncEngine = core.engine_for(settings)
    await core.create_tables(engine)
    factory = create_session_factory(engine)
    await core.seed(factory)
    runtime = core.build_execution_runtime(
        settings,
        operation_registry=await OperationRegistry.load(engine, factory),
        capability_registry=await CapabilityRegistry.load(engine, factory),
    )
    runtime.session_factory = factory
    recorder = dispatch or RecordingDispatch(payload={"completed": True})
    install(
        runtime.adapters,
        adapter=etabs_adapter(recorder, allow_partial=allow_partial),
        factory=lambda: etabs_adapter(recorder, allow_partial=allow_partial),
    )
    instance_id = await insert_etabs_instance(factory, status=status)
    async with factory() as session:
        tenant_id, user_id, project_id = await core.seeded_ids(session)
    model_id = await core.link_instance_to_project(
        factory, project_id=project_id, instance_id=instance_id, name="P127 ETABS Model"
    )
    await engine.dispose()
    ids = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "project_id": project_id,
        "instance_id": instance_id,
        "model_id": model_id,
    }
    return runtime, factory, ids, recorder


def app_module_paths() -> list[Path]:
    """`app/` 下的模块文件（**豁免**两个厂商子包；`docs/07` §14.2 / §7.1）。"""
    exempt = {ETABS_PACKAGE_DIR, APP_DIR / "infrastructure" / "adapters" / "midas"}
    return sorted(
        path
        for path in APP_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and not (exempt & set(path.parents))
    )


__all__ = [
    "CONTRACT_LEVELS_CI",
    "CONTRACT_LEVELS_DEDICATED",
    "CREDENTIAL_REFERENCE_KEY",
    "ETABS_PACKAGE_DIR",
    "EtabsTimeoutError",
    "FakeCredentialProvider",
    "HARDENING_ITEMS_SPEC",
    "MANIFEST_SPEC",
    "OPERATION_COUNTS_SPEC",
    "PARTIAL_OPERATIONS_SPEC",
    "PROTOCOLS_SPEC",
    "PROVENANCE_ANCHORS_SPEC",
    "REPO_ROOT",
    "RecordingDispatch",
    "SECRET",
    "SUPPORTED_VERSIONS_SPEC",
    "TRACEABLE_FACT_SPEC",
    "VENDOR_NAMES",
    "app_module_paths",
    "connect_config",
    "etabs_adapter",
    "insert_etabs_instance",
    "seeded_etabs_runtime",
    "software_instance_status",
]
