"""P119–P126（MIDAS 接入）的**共享装配辅助**（`docs/07` §12.2；`docs/04` §69–§77）。

⚠️ 本模块**只**提供装配 / 扫描 / 规范原文副本，**不**承载任何断言：
每个测试自己用 `tmp_path` 建独立临时库、独立 Registry 视图、独立假传输
（沿用 `tests/p42_p48_support.py` 的既定风格）。

假传输（L3 Mock Transport，`docs/04` §71）只回答**注册表里确实存在**的端点，
响应形态照 `docs/04` §46 / 官方手册的 Response Examples（`HEAD` + `DATA`）；
请求全部被记录下来，供「请求是否与 §6 映射逐条一致」的断言使用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.infrastructure.adapters.midas.adapter import MidasAdapter
from app.infrastructure.adapters.midas.models import MIDAS_METADATA
from app.infrastructure.adapters.midas.registry import MidasRegistry
from app.infrastructure.database.session import create_engine, create_session_factory

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "app"
REGISTRY_ROOT = REPO_ROOT / "registry"
MIDAS_PACKAGE_DIR = APP_DIR / "infrastructure" / "adapters" / "midas"

# ===== 规范原文副本（**不**从被测模块导入）=====

OPERATION_COUNTS_SPEC: tuple[tuple[str, int], ...] = (
    ("engineering_doc", 6),
    ("engineering_model_query", 8),
    ("engineering_model_assign", 8),
    ("engineering_model_delete", 7),
    ("engineering_model_build", 14),
    ("engineering_view", 7),
    ("engineering_result", 6),
    ("engineering_design", 6),
    ("engineering_analysis", 7),
)
"""`docs/07` §5.1 / §6.10 的每 Tool Operation 数（6+8+8+7+14+7+6+6+7 = **69**）。"""

MANIFEST_SPEC: tuple[str, ...] = ("midas.civil", "MIDAS", "CIVIL NX")
SUPPORTED_VERSIONS_SPEC: tuple[str, ...] = ("2025", "2026")
PROTOCOLS_SPEC: tuple[str, ...] = ("REST",)
"""`docs/07` §7.1 / `docs/04` §62 的 Manifest 取值（逐字照抄）。"""

VERIFICATION_STATUS_SPEC: tuple[str, ...] = ("VERIFIED", "PARTIAL", "UNVERIFIED", "DEPRECATED")
"""`docs/04` §8 的四个状态取值。"""

AVAILABILITY_TO_STATUS_SPEC: tuple[tuple[str, str], ...] = (
    ("verified", "VERIFIED"),
    ("unverified", "UNVERIFIED"),
    ("untested", "PARTIAL"),
)
"""`docs/07` §7.2 的映射规则（逐条照抄）。"""

CONTRACT_LEVELS_SPEC: tuple[str, ...] = ("L1", "L2", "L3", "L4", "L5")
"""`docs/04` §71 的 Contract Test 五层（CI = L1–L3；专用环境 = L4–L5）。"""

END_TO_END_OPERATIONS_SPEC: tuple[str, ...] = (
    "BUILD.COLUMN",
    "MODEL.LOAD.ASSIGN",
    "ANALYSIS.STATIC",
    "RESULT.NODE.DISPLACEMENT",
    "DESIGN.STEEL",
)
"""`docs/07` §13.5 / `docs/04` §74 的 E2E 五步链（逐条照抄）。"""

CIVIL_NX_FIRST_E2E_SPEC: tuple[str, ...] = (
    "connect",
    "health",
    "version",
    "node_query",
    "node_create",
    "node_query_again",
    "node_delete",
    "document_save",
)
"""`docs/04` §73 的第一条 CIVIL NX E2E（八步）。"""

CIVIL_NX_COLUMN_PARAMETERS: dict[str, Any] = {
    "base_node": {"x": 0.0, "y": 0.0, "z": 0.0},
    "height": 6.0,
    "material": "Q355B",
    "section": "H400x400x13x21",
    "section_type": "DBUSER",
    "elastic_modulus": 2.06e11,
    "poisson_ratio": 0.3,
    "density": 7850.0,
}
"""`docs/07` §13.5 的钢柱参数（`section_type` 为 canonical 自由字符串，原样透传）。"""

DISPLACEMENT_UZ_M: float = -5.8252e-4
DESIGN_RATIO: float = 0.72
"""假传输返回的位移 / 设计利用率（与 `docs/02` §42 的 Mock 口径同量级）。"""

VENDOR_NAMES: tuple[str, ...] = ("MIDAS", "CSI", "ANSYS", "SAP2000", "ETABS", "OpenSees")


def displacement_table() -> dict[str, Any]:
    """位移结果表（`docs/04` §46 的 `HEAD` / `DATA` 形态；官方手册 Response Example）。"""
    return {
        "Displacements(Global)": {
            "FORCE": "N",
            "DIST": "m",
            "HEAD": ["Node", "Load", "DX", "DY", "DZ", "RX", "RY", "RZ"],
            "DATA": [["2", "AXIAL", "0.0", "0.0", str(DISPLACEMENT_UZ_M), "0.0", "0.0", "0.0"]],
        }
    }


def design_table() -> dict[str, Any]:
    """设计结果表（`docs/04` §54：`code` 是占位，`ratio` / `status` 取自原生）。"""
    return {
        "CODE-TABLE": {
            "HEAD": ["Elem", "Code", "Ratio", "Status"],
            "DATA": [["1", "CODE-X", str(DESIGN_RATIO), "PASS"]],
        }
    }


ROUTES: dict[tuple[str, str], Any] = {
    ("GET", "/OPE/PROJECTSTATUS"): {"PROJECT": {"NAME": "P119", "STATUS": "READY"}},
    ("GET", "/DB/NODE"): {"NODE": {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}},
    ("POST", "/DB/NODE"): {"Assign": {"1": {"X": 0.0, "Y": 0.0, "Z": 0.0}}},
    ("PUT", "/DB/NODE"): {"Assign": {"1": {"X": 1.0, "Y": 0.0, "Z": 0.0}}},
    ("DELETE", "/DB/NODE/1,2"): {"message": ""},
    ("DELETE", "/DB/NODE/9"): {"message": ""},
    ("GET", "/DB/ELEM"): {"ELEM": {"1": {"TYPE": "BEAM", "NODE": [1, 2]}}},
    ("POST", "/DB/ELEM"): {"Assign": {"1": {"TYPE": "BEAM"}}},
    ("GET", "/DB/MATL"): {"MATL": {"1": {"NAME": "Q355B", "TYPE": "STEEL"}}},
    ("POST", "/DB/MATL"): {"Assign": {"1": {"NAME": "Q355B"}}},
    ("GET", "/DB/SECT"): {"SECT": {"1": {"SECT_NAME": "H400x400x13x21"}}},
    ("POST", "/DB/SECT"): {"Assign": {"1": {"SECT_NAME": "H400x400x13x21"}}},
    ("GET", "/DB/CONS"): {"CONS": {"ITEMS": [{"ID": 1, "CONSTRAINT": "111111"}]}},
    ("POST", "/DB/CONS"): {"Assign": {"ITEMS": [{"ID": 1}]}},
    ("GET", "/DB/STLD"): {"STLD": {"1": {"NO": 1, "NAME": "AXIAL", "TYPE": "USER"}}},
    ("GET", "/DB/BMLD"): {"BMLD": {"ITEMS": []}},
    ("GET", "/DB/GRUP"): {"GRUP": {"1": {"NAME": "G1"}}},
    ("POST", "/DB/CNLD"): {"Assign": {"ITEMS": [{"ID": 1}]}},
    ("POST", "/POST/TABLE"): displacement_table(),
    ("POST", "/DOC/ANAL"): {"Argument": {"TYPE": "STATIC"}},
    ("POST", "/DOC/NEW"): {"Argument": {}},
    ("POST", "/DOC/SAVE"): {"Argument": {}},
    ("POST", "/DESIGN/STEEL/KDS-41-30-2022/CODE-ANAL"): {"Assign": {"Argument": {}}},
    ("POST", "/DESIGN/STEEL/KDS-41-30-2022/CODE-TABLE"): design_table(),
    ("GET", "/DESIGN/STEEL/DSTL"): {"DSTL": {"1": {"DGNCODE": "KDS-41-30-2022"}}},
    ("GET", "/DESIGN/STEEL/KDS-41-30-2022/DCO"): {"DCO": {"1": {}}},
    ("GET", "/DESIGN/STEEL/KDS-41-30-2022/DCTL"): {"DCTL": {"1": {}}},
    ("GET", "/DESIGN/STEEL/KDS-41-30-2022/MEMB"): {"MEMB": {"1": {}}},
}
"""假传输的路由表（key = `(method, path)`；未命中的路径一律 `404`）。"""

BASE_URL = "https://example.invalid/civil"
"""实例 Base URL（**不是** secret；`docs/04` §5.1 的「普通配置」）。"""

SECRET = "probe-key-not-a-real-credential"
"""测试用 MAPI-Key（仅进程内环境注入，**不**落任何文件；`docs/07` §14.3）。"""


class RecordingTransport(httpx.MockTransport):
    """记录全部请求的假传输（L3；`docs/04` §71）。"""

    def __init__(self, prefix: str = "/civil") -> None:
        """构造并绑定处理器（记录 → 查表 → 应答）。"""
        self.calls: list[tuple[str, str, Any]] = []
        self._prefix = prefix
        super().__init__(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        """处理一次请求（未命中的路径 → `404`，与真实软件同形）。"""
        path = request.url.path
        if self._prefix and path.startswith(self._prefix):
            path = path[len(self._prefix) :]
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, path, body))
        payload = ROUTES.get((request.method, path))
        if payload is None:
            return httpx.Response(404, json={"message": "not found"})
        return httpx.Response(200, json=payload)

    def paths(self) -> list[str]:
        """已发生的请求路径（顺序即调用顺序）。"""
        return [path for _method, path, _body in self.calls]

    def methods(self) -> list[str]:
        """已发生的请求方法。"""
        return [method for method, _path, _body in self.calls]

    def clear(self) -> None:
        """清空记录。"""
        self.calls.clear()


def registry() -> MidasRegistry:
    """装载仓库里的 `registry/`（`docs/04` §7.1）。"""
    return MidasRegistry.load(REGISTRY_ROOT)


def adapter(
    *,
    transport: RecordingTransport | None = None,
    product: str = "CIVIL NX",
    allow_unverified: bool = True,
    registry_view: MidasRegistry | None = None,
) -> MidasAdapter:
    """构造一个可连接的 Adapter（凭据只经内存环境注入）。"""
    return MidasAdapter(
        registry=registry_view or registry(),
        transport=transport or RecordingTransport(),
        environ={"MIDAS_BASE_URL": BASE_URL, "MIDAS_MAPI_KEY": SECRET},
        allow_unverified=allow_unverified,
        product=product,
    )


def connect_config(**extra: Any) -> dict[str, Any]:
    """连接配置（版本来自实例声明，`docs/04` §61）。"""
    return {"version": "2026", **extra}


def engine_for(tmp_path: Path, *, name: str = "midas.db") -> AsyncEngine:
    """建临时库引擎（**不**建表）。"""
    return create_engine(f"sqlite+aiosqlite:///{(tmp_path / name).as_posix()}")


async def midas_tables(engine: AsyncEngine) -> None:
    """只建 MIDAS 的 **7** 张表（`docs/07` §4.4；Core 的 24 张表由 Core 侧路径负责）。"""
    async with engine.begin() as connection:
        await connection.run_sync(MIDAS_METADATA.create_all)


def session_factory_for(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """会话工厂（`docs/02` §16：事务边界归 `UnitOfWork`）。"""
    return create_session_factory(engine)


def app_module_paths() -> list[Path]:
    """`app/` 下的模块文件（**豁免** `adapters/midas/`，见 `docs/07` §7.1）。"""
    return sorted(
        path
        for path in APP_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and MIDAS_PACKAGE_DIR not in path.parents
    )
