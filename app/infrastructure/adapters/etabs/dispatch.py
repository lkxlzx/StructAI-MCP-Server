"""Infrastructure · Adapters · CSI ETABS · Dispatcher entry point（P135，R88 裁决落地）。

权威来源
--------
- `docs/07` §16 **R88** —— 「ETABS 生产路径没有原生派发实现；**下一批**显式裁决
  『COM 派发的落点』（独立 entry point 包 / 由部署方注入），并同步 §3.2 依赖清单
  与 §14.5 扩展性口径。**不得**引入新依赖」。
- `docs/07` §3.1 / §3.2 —— 技术栈冻结：本仓库**不**引入 `pywin32` / `comtypes` 等 COM 依赖。
- `docs/07` §14.2 —— 厂商专属代码只出现在各自子包；Core 中不出现任何厂商字样。
- `docs/02` §19 / `docs/07` §16 R81 —— 「注册 / 派发」由部署方**显式**接入，
  Core 装配形状不变（`AppContainer` 仍 7 字段）。

落地裁决（P135d 的 R88 裁决）
------------------------------
1. **落点 = 独立 entry point 包 + 由部署方注入**（两条同时成立，互不冲突）：
   ① 本模块提供 `load_dispatch()`，用**标准库** `importlib.metadata.entry_points`
   发现 entry point group `structai.adapters.etabs.dispatch`，加载其中的工厂并调用它
   得到一个 `ComDispatch`；
   ② 部署方也可以完全绕过 entry point，直接
   `install(manager, factory=lambda: EtabsAdapter(dispatch=<自己的 dispatch>))`。
   **两条路径都落在本子包内** —— Core（`app/container.py` / `app/main.py`）一行未改，
   `docs/07` §14.2 的厂商红线因此仍成立。
2. **不新增依赖**：`importlib.metadata` 属标准库，`pyproject.toml` 的依赖清单**不变**
   （`docs/07` §3.2）。**分发方**（独立的 dispatcher 包）自行声明它需要的 COM 依赖 ——
   那是**另一个包**的依赖，不是本仓库的依赖。本仓库因此既不引入 `pywin32`，
   也仍然能在没有 COM 的平台上完整跑 CI（缺 entry point → 明确失败）。
3. **缺 entry point 即明确失败**：`load_dispatch()` 在没有任何已注册 entry point 时
   返回 `None`，`EtabsAdapter.connect()` 随即以 `STRUCTAI-2000`
   （`details.reason = "dispatch_not_configured"`）拒绝 —— **不**伪造连接、
   **不**静默降级为「本地空实现」（`lifecycle.py` 裁决 2 的同一口径）。
4. **entry point 的取值是工厂，不是实例**：每次 `load_dispatch()` 都**重新**调用工厂，
   使「每个软件实例一个独立 COM 会话」在结构上成立（`docs/02` §14：
   Adapter Instance ≠ Software Instance）；工厂返回非 `ComDispatch` 形状时同样明确失败。
5. **异常信息绝不带出第三方内容**：加载失败只报**entry point 名**与**异常类名**，
   不回显第三方异常 message（它可能带出安装路径 / 凭据引用），也不把值写进 `details`。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库与同包的 `errors.py` / `lifecycle.py`；**不**引用 SQLAlchemy /
FastAPI / MCP SDK / httpx，**不**依赖 `app.interfaces` / `app.application` /
`app.infrastructure` 的其它子包。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any, Final, Protocol, runtime_checkable

from app.infrastructure.adapters.etabs.errors import EtabsConnectionError
from app.infrastructure.adapters.etabs.lifecycle import ComDispatch

__all__ = [
    "DISPATCH_ENTRY_POINT_GROUP",
    "DispatchFactory",
    "DispatchLoader",
    "load_dispatch",
    "registered_dispatch_entry_points",
]

DISPATCH_ENTRY_POINT_GROUP: Final[str] = "structai.adapters.etabs.dispatch"
"""COM 派发的 entry point group（见裁决 1；分发方在自己的包里注册这一组）。

分发方的 `pyproject.toml` 只需声明：

    [project.entry-points."structai.adapters.etabs.dispatch"]
    com = "my_etabs_dispatcher:create_dispatch"

`create_dispatch()` 返回一个满足 `lifecycle.ComDispatch` 的对象
（`attach` / `detach` / `is_attached` / `invoke` 四方法）。
"""


@runtime_checkable
class DispatchFactory(Protocol):
    """entry point 指向的**工厂**（见裁决 4）。"""

    def __call__(self) -> Any:
        """构造一个 `ComDispatch`（**每次调用都新建**）。"""
        ...


DispatchLoader = Callable[[], ComDispatch | None]
"""可注入的加载器（缺省 = `load_dispatch`）；验收测试据此避免真实 entry point。"""


def registered_dispatch_entry_points(
    *,
    group: str = DISPATCH_ENTRY_POINT_GROUP,
) -> tuple[EntryPoint, ...]:
    """当前环境中该 group 的已注册 entry point（**只**读元数据，不导入第三方）。"""
    discovered: Iterable[EntryPoint] = entry_points(group=group)
    return tuple(sorted(discovered, key=lambda point: point.name))


def load_dispatch(*, group: str = DISPATCH_ENTRY_POINT_GROUP) -> ComDispatch | None:
    """加载部署方注册的 COM 派发（见裁决 1–5）。

    Args:
        group: entry point group 名；缺省 `DISPATCH_ENTRY_POINT_GROUP`。

    Returns:
        工厂新建的 `ComDispatch`；**没有**已注册 entry point 时返回 `None`
        （调用方据此明确失败，见裁决 3）。

    Raises:
        EtabsConnectionError: `STRUCTAI-2000` —— entry point 存在但加载 / 构造失败，
            或工厂返回值不满足 `ComDispatch` 的形状。`details` 只含 entry point 名
            与异常**类名**（见裁决 5），**绝不**回显第三方异常 message。
    """
    points = registered_dispatch_entry_points(group=group)
    if not points:
        return None
    point = points[0]
    try:
        factory = point.load()
    except Exception as error:  # noqa: BLE001 - 第三方导入失败的分类由本层决定
        raise EtabsConnectionError(
            "dispatch_entry_point_unloadable",
            entry_point=str(point.name),
            error=type(error).__name__,
        ) from error
    if not callable(factory):
        raise EtabsConnectionError(
            "dispatch_entry_point_not_callable",
            entry_point=str(point.name),
        )
    try:
        dispatch = factory()
    except Exception as error:  # noqa: BLE001 - 同上：只报类名，不回显 message
        raise EtabsConnectionError(
            "dispatch_factory_failed",
            entry_point=str(point.name),
            error=type(error).__name__,
        ) from error
    if not isinstance(dispatch, ComDispatch):
        raise EtabsConnectionError(
            "dispatch_shape_invalid",
            entry_point=str(point.name),
        )
    return dispatch
