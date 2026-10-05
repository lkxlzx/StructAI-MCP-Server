"""Registry · API Registry —— 软件 API 映射数据（`docs/07` §12 P08；`docs/02` §23）。

权威来源
--------
- `docs/02` §23（API Registry）—— **只保存九个字段**：`software` / `product` / `version` /
  `operation` / `protocol` / `method` / `path` / `request_schema` / `response_schema`；
  「复杂转换逻辑放 Adapter，不放数据库中执行任意 Python」。
- `registry/README.md` —— **本 Registry 的唯一数据源**：`registry/manifest.json` 是 636 端点
  的全量索引（`registry/README.md` §5 第 1 步：「启动时加载 `registry/manifest.json`
  建立 key → 定义文件索引」）；`availability` / `enabled` / `wrapper` 等口径见 §4。
- `docs/07` §6 —— Operation → 端点映射（P122 的 Adapter 编排依据）。
- `docs/07` §14.2 —— Core 中**不得**出现任何厂商专属的 endpoint / 参数 / 响应 / SDK；
  因此本模块**不硬编码任何路径**，一切取值来自数据文件（红线检查：`app/` 内厂商名 0 处）。

字段来源（逐字段可回溯到数据文件，**不臆造**）
--------------------------------------------
| 字段 | 来源 |
| --- | --- |
| `software` | `registry/` 数据中**无**厂商字段 → 取 `product` 的**末段**做机械归族（`CIVIL_NX` / `GEN_NX` → `NX`，`CIVIL_DESIGNER` → `DESIGNER`）；**不**引入厂商名（`docs/07` §14.2） |
| `product` | `manifest.json` 端点的 `products[]` |
| `version` | `registry/` 数据中无版本字段 → 留空（软件版本由 Adapter Manifest 声明，`docs/07` §7.1；P119 才落地） |
| `operation` | `manifest.json` 端点的 `key`（如 `DB.NODE` / `POST.TABLE.DISPLACEMENTG`） |
| `protocol` | 数据中无协议字段 → 固定 `REST`（`docs/02` §23 示例值 ＋ `docs/07` §7.1 `protocols=[REST]`；协议族，非厂商专属值） |
| `method` | `manifest.json` 端点的 `methods`（`product_overrides.<产品>.methods` 优先）—— **逐方法一条记录** |
| `path` | `manifest.json` 端点的 `uri`（`product_overrides.<产品>.uri` 优先）；个别覆盖值省略前导斜杠，做**机械补全**（不改任何段名） |
| `request_schema` | `manifest.json` 端点的 `schema`（本地 JSON Schema 文件）：**616** 个端点有值；另 **20** 个端点源手册尚无 Schema（`docs/07` §16 R5）→ 留空并计数，不臆造路径 |
| `response_schema` | `registry/` **无**响应 Schema 文件（`schema_ref.introspect` 只存在于端点 YAML，且是软件侧自省路径、非本地 Schema）→ 留空，不臆造路径 |

只读：本模块不写数据库、不提交事务（`docs/02` §45 Registry 最终边界；`docs/07` §14.4）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from app.domain.errors import InternalError, NotFoundError

__all__ = [
    "API_REGISTRY_FIELDS",
    "MANIFEST_NAME",
    "PROTOCOL_REST",
    "ApiRegistry",
    "ApiRegistryEntry",
]

logger = logging.getLogger("structai.registry")

MANIFEST_NAME: Final[str] = "manifest.json"
"""`registry/README.md` §2 / §5：全量索引文件名。"""

PROTOCOL_REST: Final[str] = "REST"
"""协议族取值（`docs/02` §23 示例 ＋ `docs/07` §7.1 `protocols=[REST]`）。"""

API_REGISTRY_FIELDS: Final[tuple[str, ...]] = (
    "software",
    "product",
    "version",
    "operation",
    "protocol",
    "method",
    "path",
    "request_schema",
    "response_schema",
)
"""`docs/02` §23：API Registry **只**保存这九个字段（不多不少）。"""


@dataclass(frozen=True, slots=True)
class ApiRegistryEntry:
    """一条 API 映射记录（`docs/02` §23 的九字段，顺序与规范一致）。

    ⚠️ `version` / `response_schema` 在本批的数据源里**无值**（见模块 docstring 的字段来源表），
    故为空字符串；它们仍是规范要求的字段，P119/P120 接入真实软件时由 Adapter 侧补齐。
    """

    software: str
    product: str
    version: str
    operation: str
    protocol: str
    method: str
    path: str
    request_schema: str
    response_schema: str


class ApiRegistry:
    """软件 API 映射注册表（`docs/02` §23；`docs/07` §12 P08 门槛 ⑥）。

    **只读**：只做装配与查询，不执行任何 API（`docs/02` §45）。
    """

    def __init__(
        self,
        entries: Iterable[ApiRegistryEntry] = (),
        *,
        endpoint_keys: Iterable[str] = (),
        disabled: Mapping[str, str] | None = None,
        schemas: Iterable[str] | None = None,
    ) -> None:
        """由映射记录构造。

        Args:
            entries: 映射记录。
            endpoint_keys: 数据文件里的**全部**端点 key（含被禁用的）。
            disabled: 被禁用的端点 key → 原因（数据文件原文）。
            schemas: 数据文件里的**全部**请求 Schema 路径（含被禁用端点的）；
                缺省时从 `entries` 推导。
        """
        self._entries: tuple[ApiRegistryEntry, ...] = tuple(entries)
        self._index: dict[tuple[str, str, str], ApiRegistryEntry] = {
            (entry.product, entry.operation, entry.method): entry for entry in self._entries
        }
        self._endpoint_keys: tuple[str, ...] = tuple(endpoint_keys)
        self._disabled: Mapping[str, str] = dict(disabled or {})
        self._schemas: tuple[str, ...] = tuple(
            sorted(
                schemas
                if schemas is not None
                else {entry.request_schema for entry in self._entries if entry.request_schema}
            )
        )

    # ===== 查询 =====

    def resolve(
        self,
        *,
        product: str,
        operation: str,
        method: str,
    ) -> ApiRegistryEntry | None:
        """按 `(product, operation, method)` 定位一条映射（`registry/README.md` §5 第 2 步）。"""
        return self._index.get((product, operation, method.upper()))

    def for_operation(
        self,
        operation: str,
        *,
        product: str | None = None,
        method: str | None = None,
    ) -> tuple[ApiRegistryEntry, ...]:
        """某 Operation 的全部映射（可按产品 / 方法收窄）。"""
        wanted = method.upper() if method else None
        return tuple(
            entry
            for entry in self._entries
            if entry.operation == operation
            and (product is None or entry.product == product)
            and (wanted is None or entry.method == wanted)
        )

    def for_product(self, product: str) -> tuple[ApiRegistryEntry, ...]:
        """某产品的全部映射。"""
        return tuple(entry for entry in self._entries if entry.product == product)

    def list(self) -> tuple[ApiRegistryEntry, ...]:
        """全部映射（构造顺序 = 数据文件顺序，输出确定）。"""
        return self._entries

    def endpoint_keys(self) -> tuple[str, ...]:
        """数据文件里的全部端点 key（`registry/README.md` §3：**636** 个）。"""
        return self._endpoint_keys

    def request_schemas(self) -> tuple[str, ...]:
        """数据文件里被引用的请求 Schema（去重升序；`registry/README.md` §3：**616** 个）。

        ⚠️ 含**被禁用端点**（`enabled: false`）的 Schema —— 它们仍属「可装载」的 Schema 资产。
        """
        return self._schemas

    def is_disabled(self, key: str) -> bool:
        """该端点是否被数据文件显式禁用（`registry/README.md` §4 的 `enabled: false`）。"""
        return key in self._disabled

    def disable_reason(self, key: str) -> str:
        """被禁用端点的原因（数据文件原文；未禁用返回空串）。"""
        return self._disabled.get(key, "")

    def products(self) -> tuple[str, ...]:
        """出现过的产品（升序）。"""
        return tuple(sorted({entry.product for entry in self._entries}))

    def summary(self) -> dict[str, Any]:
        """装配摘要（供启动日志与验收证据；**不含** secret）。"""
        return {
            "endpoints": len(self._endpoint_keys),
            "entries": len(self._entries),
            "schemas": len(self._schemas),
            "products": list(self.products()),
            "disabled": sorted(self._disabled),
            "entries_without_schema": sum(
                1 for entry in self._entries if not entry.request_schema
            ),
        }

    def __len__(self) -> int:
        return len(self._entries)

    # ===== 装配 =====

    @classmethod
    def load(cls, registry_root: str | Path) -> ApiRegistry:
        """从 `registry/` 装载映射（`docs/02` §23；`registry/README.md` §5）。

        Args:
            registry_root: 数据目录（默认由 `Settings.registry_root` 给出）。

        Returns:
            已装载的 `ApiRegistry`。

        Raises:
            NotFoundError: 数据目录里没有 `manifest.json`（数据源缺失）。
            InternalError: 索引不可解析，或记录不合法（空字段 / 重复的
                `(product, operation, method)`）。
        """
        root = Path(registry_root)
        manifest_path = root / MANIFEST_NAME
        if not manifest_path.is_file():
            raise NotFoundError(f"API registry manifest not found: {manifest_path}")

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise InternalError(
                "API registry manifest is unreadable",
                details={"path": str(manifest_path), "error": type(error).__name__},
            ) from error

        endpoints = manifest.get("endpoints")
        if not isinstance(endpoints, list):
            raise InternalError(
                "API registry manifest has no `endpoints` list",
                details={"path": str(manifest_path)},
            )

        entries: list[ApiRegistryEntry] = []
        keys: list[str] = []
        disabled: dict[str, str] = {}
        schemas: set[str] = set()
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                raise InternalError(
                    "API registry manifest has a malformed endpoint entry",
                    details={"path": str(manifest_path)},
                )
            key = str(endpoint.get("key") or "")
            if not key:
                raise InternalError(
                    "API registry manifest has an endpoint without `key`",
                    details={"path": str(manifest_path)},
                )
            keys.append(key)

            schema = str(endpoint.get("schema") or "")
            if schema:
                schemas.add(schema)

            methods = _methods(endpoint.get("methods"))
            if not endpoint.get("enabled", True) or not methods:
                disabled[key] = str(
                    endpoint.get("disable_reason") or "no method advertised by the source manual"
                )
                continue

            overrides = endpoint.get("product_overrides") or {}
            for product in _strings(endpoint.get("products")):
                override = overrides.get(product) or {}
                product_methods = _methods(override.get("methods")) or methods
                path = _normalize_path(str(override.get("uri") or endpoint.get("uri") or ""))
                for method in product_methods:
                    entries.append(
                        ApiRegistryEntry(
                            software=_software_family(product),
                            product=product,
                            version="",
                            operation=key,
                            protocol=PROTOCOL_REST,
                            method=method,
                            path=path,
                            request_schema=schema,
                            response_schema="",
                        )
                    )

        _validate(entries, manifest_path)
        registry = cls(entries, endpoint_keys=keys, disabled=disabled, schemas=schemas)
        logger.info("api registry loaded: %s", registry.summary())
        return registry


# ===== 数据文件的解析辅助（只做机械变换，不改任何取值）=====


def _strings(value: object) -> tuple[str, ...]:
    """把数据文件里的列表字段归一成字符串元组（`methods` 在索引里是逗号串）。"""
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, Sequence):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _methods(value: object) -> tuple[str, ...]:
    """方法集：大写归一（`registry/README.md` §4：`methods` 为实测可用方法集）。"""
    return tuple(method.upper() for method in _strings(value))


def _software_family(product: str) -> str:
    """由产品键机械归族：取**末段**（`CIVIL_NX` / `GEN_NX` → `NX`；`CIVIL_DESIGNER` → `DESIGNER`）。

    `registry/` 数据里没有厂商字段，Core 也**不得**出现厂商名（`docs/07` §14.2），
    故 `software` 只做产品键的机械切分，不引入任何硬编码映射表。
    """
    return product.rsplit("_", 1)[-1]


def _normalize_path(uri: str) -> str:
    """路径归一：数据里的 `uri` 含前导斜杠（`registry/README.md` §4）；个别产品覆盖值省略，补全之。"""
    if not uri:
        return ""
    return uri if uri.startswith("/") else f"/{uri}"


def _validate(entries: Sequence[ApiRegistryEntry], manifest_path: Path) -> None:
    """校验映射记录（`docs/02` §23；`docs/07` §14.4：失败 → 不得 READY）。

    ⚠️ `request_schema` **允许为空**：数据源里 636 个端点中有 **20** 个尚无 JSON Schema
    （`docs/07` §16 R5），这是数据现状、不是装配错误；空值以 `summary()` 的
    `entries_without_schema` 计数上报，不臆造路径。

    Raises:
        InternalError: `operation` / `product` / `method` / `path` 为空，
            或 `(product, operation, method)` 重复。
    """
    failures: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        blank = [
            name
            for name in ("operation", "product", "method", "path")
            if not getattr(entry, name)
        ]
        if blank:
            failures.append(f"{entry.operation or '?'}: empty field(s): {blank}")
        identity = (entry.product, entry.operation, entry.method)
        if identity in seen:
            failures.append(f"duplicate mapping: {identity}")
        seen.add(identity)
    if not entries:
        failures.append("no mapping entry was produced")
    if failures:
        raise InternalError(
            "API registry validation failed",
            details={"path": str(manifest_path), "failures": failures[:20]},
        )
