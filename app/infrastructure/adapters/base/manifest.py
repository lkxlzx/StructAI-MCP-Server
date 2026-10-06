"""Infrastructure · Adapters · Base · Manifest —— Adapter 的**软件无关**注册声明。

权威来源
--------
- `docs/02` §6（`adapter`）—— 每个 Adapter 必须声明的字段：`name` / `vendor` /
  `product` / `versions` / `protocols` / `capabilities`（示例为
  `structai.mock` + `IN_PROCESS`）。
- `docs/02` §7（`adapter`）—— `AdapterManifest` 的 Python 形状（`supported_versions` /
  `protocols` / `capabilities` 均为元组）。
- `docs/02` §19（`adapter`）—— Manifest 校验：`name` / `vendor` / `product` /
  `supported_versions` 缺一即拒绝。
- `docs/02` §20（`adapter`）—— 版本匹配：**严格精确**；`requested = 2027` 而只声明
  `2025/2026` → **拒绝**，**不得**偷偷使用 `2026`。
- `docs/07` §14.5 —— 接入新软件只允许「新增 Adapter + Mapping + API Registry 数据」，
  故 Manifest 是**声明**而不是逻辑。
- `docs/07` §14.2 —— Capability 取值中**不得**出现厂商名；本模块只校验**形状**
  （厂商名检查属 Core 红线，落在 `tests/` 的 `VENDOR_NAMES`，`app/` 内不写厂商名）。

落地裁决（只补实现手段，不改字段名 / 取值）
------------------------------------------
1. **`protocols` 是开放词表**：`docs/02` §6 用 `IN_PROCESS`、§22（`impl`）用 `REST`。
   本模块**不**把它固化成枚举 —— 那会与 `docs/07` §14.5 的「新增 Adapter 不改 Core」
   冲突。校验只要求「非空、大写 token」。
2. **`capabilities` 允许为空**：`docs/02` §22（`impl`）的真实厂商 Manifest 示例即
   `"capabilities": []`（能力由运行时探测给出，§21 / §23）。
3. **校验失败 → `InternalError`（`STRUCTAI-7000`）**：`docs/02` §19 原文用
   `ConfigurationError`，该名称**不在** `docs/07` §11 的 20 码契约内。按 P08 的既有
   裁决（Registry 校验失败 → `InternalError`，`docs/07` §14.4「Server MUST NOT
   become READY」）复用 20 码内的兜底码，**不**新增码。
4. **`manifest_key` 不含 `name`**：`docs/02` §12（`adapter`）的注册键是
   `(vendor, product, name)`，但 `docs/07` §12 P19–P20 门槛 ② 明确「同一
   `(vendor, product)` **不**重复注册」—— 即「一个产品一个 Adapter」。本模块以
   `(vendor, product)` 为**唯一键**（`AdapterManager` 据此拒绝重复注册），
   `name` 仅作诊断标识。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与 `app.domain`（**不**依赖 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.interfaces`）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from app.domain.errors import InternalError

__all__ = [
    "CAPABILITY_TOKEN_PATTERN",
    "MANIFEST_TOKEN_PATTERN",
    "AdapterManifest",
    "manifest_key",
]

MANIFEST_TOKEN_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*$"
"""`protocols` 的 token 形状（大写标识符，如 `IN_PROCESS` / `REST`）。"""

CAPABILITY_TOKEN_PATTERN: Final[str] = r"^[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+$"
"""`capabilities` 的 token 形状（点分大写，如 `MODEL.NODE.WRITE`）。"""

_TOKEN_RE: Final[re.Pattern[str]] = re.compile(MANIFEST_TOKEN_PATTERN)
_CAPABILITY_RE: Final[re.Pattern[str]] = re.compile(CAPABILITY_TOKEN_PATTERN)


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    """Adapter 注册声明（`docs/02` §6 / §7；逐字段照抄）。

    Attributes:
        name: Adapter 包标识（如 `structai.mock`）；诊断用，**不**参与注册键（见裁决 4）。
        vendor: 厂商（如 `StructAI`）。厂商名只允许出现在 Adapter 层。
        product: 产品（如 `MockEngineering`）。
        supported_versions: 声明支持的版本集合；匹配是**严格精确**的（`docs/02` §20）。
        protocols: 通信协议（`IN_PROCESS` / `REST` …）；开放词表（见裁决 1）。
        capabilities: **静态**能力清单；运行时清单由 `get_capabilities()` 给出
            （`docs/02` §21 / §23）。允许为空（见裁决 2）。
    """

    name: str
    vendor: str
    product: str
    supported_versions: tuple[str, ...] = field(default_factory=tuple)
    protocols: tuple[str, ...] = field(default_factory=tuple)
    capabilities: tuple[str, ...] = field(default_factory=tuple)

    # ===== 校验（`docs/02` §19）=====

    def validate(self) -> AdapterManifest:
        """校验 Manifest 完整性（`docs/02` §19）。

        Returns:
            自身（便于链式调用 / 装配期断言）。

        Raises:
            InternalError: `STRUCTAI-7000`，任一必填项缺失或形状非法（见裁决 3）。
        """
        self._require_text("name", self.name)
        self._require_text("vendor", self.vendor)
        self._require_text("product", self.product)
        if not self.supported_versions:
            self._reject("supported_versions", "Adapter versions are required")
        for version in self.supported_versions:
            self._require_text("supported_versions", version)
        if not self.protocols:
            self._reject("protocols", "Adapter protocols are required")
        for protocol in self.protocols:
            if _TOKEN_RE.match(protocol) is None:
                self._reject("protocols", "Adapter protocol is not a token")
        for capability in self.capabilities:
            if _CAPABILITY_RE.match(capability) is None:
                self._reject("capabilities", "Adapter capability is not a dotted code")
        return self

    # ===== 匹配（`docs/02` §20）=====

    def supports_version(self, version: str) -> bool:
        """版本是否被**精确**声明（`docs/02` §20）。

        Args:
            version: 待判定的版本（如软件实例落库的版本号）。

        Returns:
            仅在 `supported_versions` 中**精确**命中时为 `True`；
            不命中即 `False` —— 调用方必须**拒绝**，不得回落（`docs/02` §20）。
        """
        return str(version) in self.supported_versions

    def matches(self, *, vendor: str, product: str) -> bool:
        """是否就是该 `(vendor, product)`（大小写敏感的精确比较）。"""
        return self.vendor == vendor and self.product == product

    # ===== 内部 =====

    def _require_text(self, field_name: str, value: str) -> None:
        """要求为非空文本（`docs/02` §19）。"""
        if not isinstance(value, str) or not value.strip():
            self._reject(field_name, "Adapter field is required")

    def _reject(self, field_name: str, message: str) -> None:
        """抛装配期校验失败（`STRUCTAI-7000`，见裁决 3）。

        `details` 只含**字段名**与 Adapter 自身声明的标识 ——
        不含凭据、不含厂商 endpoint（`docs/07` §14.3）。
        """
        raise InternalError(
            message,
            details={
                "stage": "adapter_manifest",
                "field": field_name,
                "adapter": self.name,
            },
        )


def manifest_key(manifest: AdapterManifest) -> tuple[str, str]:
    """注册键 = `(vendor, product)`（`docs/07` §12 P19–P20 门槛 ②；见裁决 4）。"""
    return (manifest.vendor, manifest.product)
