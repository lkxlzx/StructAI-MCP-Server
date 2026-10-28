"""Infrastructure · Adapters · Plugins —— 适配器子包的**通用**发现（P185）。

为什么需要它
------------
客户端页要能「连接 / 断开」一个软件实例，而 `AdapterManager` 只认识**已注册**的
`(vendor, product)`。Core 启动时只注册 Mock Adapter；真实厂商 Adapter 是**按需**注册的
（用户点「连接」时才知道要用哪一个）。

⚠️ `docs/07` §14.2：`app/` 内（厂商子包之外）**不得**出现任何厂商名。故本模块
**不**维护任何厂商 → Adapter 的映射表，而是扫描 `app/infrastructure/adapters/` 下的
子包，找出其中**可无参构造**的 `EngineeringSoftwareAdapter` 实现，读它自己的
`manifest` 得到 `(vendor, product)`。

发现规则（约定优于配置）
------------------------
1. 遍历 `app.infrastructure.adapters` 的直接子包（跳过 `base` / `mock` / 私有包）；
2. 导入子包，取出其中**定义在该模块**、且是 `EngineeringSoftwareAdapter` 子类、
   非抽象的具体类；
3. 无参构造成功后读 `.manifest`（`AdapterManifest`），以 `(vendor, product)` 为键。

⚠️ 构造只做内存初始化（所有 Adapter 的构造函数都**不**做 I/O，`docs/02` §54），
因此发现过程不会连接任何软件、不会读凭据。
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import Any, Final

from app.infrastructure.adapters.base.adapter import EngineeringSoftwareAdapter

__all__ = ["discover_adapters", "adapter_class_for"]

_ADAPTERS_PACKAGE: Final[str] = "app.infrastructure.adapters"
_SKIP: Final[frozenset[str]] = frozenset({"base", "mock"})


def discover_adapters() -> dict[tuple[str, str], type[Any]]:
    """扫描适配器子包，返回 `{(vendor, product): Adapter 类}`。

    Returns:
        可无参构造的 Adapter 实现；导入 / 构造失败的子包**跳过**（单包失败不得
        拖垮发现过程，`docs/07` §14.4）。
    """
    package = importlib.import_module(_ADAPTERS_PACKAGE)
    found: dict[tuple[str, str], type[Any]] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if not info.ispkg or info.name.startswith("_") or info.name in _SKIP:
            continue
        module = _import(f"{_ADAPTERS_PACKAGE}.{info.name}")
        if module is None:
            continue
        for _, candidate in inspect.getmembers(module, inspect.isclass):
            adapter_class = _as_concrete_adapter(candidate, module.__name__)
            if adapter_class is None:
                continue
            manifest = _manifest_of(adapter_class)
            if manifest is None:
                continue
            found[(str(manifest.vendor), str(manifest.product))] = adapter_class
    return found


def adapter_class_for(vendor: str, product: str) -> type[Any] | None:
    """按 `(vendor, product)` 找 Adapter 类（精确匹配优先，其次同厂商）。

    同厂商回退用于「一个 Adapter 承载多个产品」的情形（产品由连接配置选择）：
    注册键是 Adapter 的主产品，实例可以是同厂商的另一个产品。

    Args:
        vendor: 实例的软件厂商。
        product: 实例的软件产品。

    Returns:
        Adapter 类；找不到返回 `None`（**不**猜）。
    """
    adapters = discover_adapters()
    exact = adapters.get((str(vendor), str(product)))
    if exact is not None:
        return exact
    for (candidate_vendor, _), adapter_class in sorted(adapters.items()):
        if candidate_vendor == str(vendor):
            return adapter_class
    return None


# ===== 内部 =====


def _import(name: str) -> Any:
    """导入子包（失败返回 `None`）。"""
    try:
        return importlib.import_module(name)
    except Exception:  # noqa: BLE001 - 单包导入失败不影响其它 Adapter
        return None


def _as_concrete_adapter(candidate: Any, package_name: str) -> type[Any] | None:
    """是「该子包内定义的具体 Adapter」才返回，否则 `None`。

    ⚠️ Adapter 类通常定义在子包的 `adapter.py` 里（包 `__init__` 只做再导出），
    故按**子包前缀**判断归属，而不是要求定义在包模块本身。
    """
    if not inspect.isclass(candidate):
        return None
    module = str(getattr(candidate, "__module__", ""))
    if module != package_name and not module.startswith(package_name + "."):
        return None
    if candidate is EngineeringSoftwareAdapter:
        return None
    if not issubclass(candidate, EngineeringSoftwareAdapter):
        return None
    if inspect.isabstract(candidate):
        return None
    return candidate


def _manifest_of(adapter_class: type[Any]) -> Any:
    """无参构造并读取 Manifest（失败返回 `None`）。"""
    try:
        return adapter_class().manifest
    except Exception:  # noqa: BLE001 - 构造失败视作不可用
        return None
