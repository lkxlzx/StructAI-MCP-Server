"""Infrastructure · Adapters · CSI ETABS · Lifecycle —— COM 会话生命周期（P127 / P133）。

权威来源
--------
- `docs/01` §20 L915 / `docs/03` §106 L3178 —— 协议族是 `COM`。
- `docs/02` §10 / §11（adapter）—— 生命周期：`CREATED → CONNECTING → CONNECTED → READY
  → DISCONNECTING → DISCONNECTED`（由 `BaseAdapter` 承载），本模块只承载**协议层**的
  会话状态。
- `docs/07` §8.5 / §14.3 —— 凭据**只**经注入的 CredentialProvider 解析；
  **绝不**落库 / 落日志 / 落文件 / 进异常 message。

落地裁决（只补实现手段，不改契约）
--------------------------------
1. **`ComDispatch` 是「协议 / 生命周期」层面的端口，不是厂商 API**：本仓库**没有**
   COM 实现的依赖（`docs/07` §3.1 技术栈冻结，**不**允许新增 `pywin32`），
   因此原生派发必须由部署方**注入**。端口只声明四件事：attach / detach /
   is_attached / invoke —— 其中只有 `invoke` 的 `method` 携带**可追溯**的原生方法名。
2. **没有 dispatch 就明确失败**：`attach()` 在未注入 dispatch 时抛
   `EtabsConnectionError("dispatch_not_configured")`（`2000`），
   **不**伪造连接、**不**静默降级为「本地空实现」。
3. **凭据只在 attach 那一刻解析、只在内存里**：`ComSession` 只保存**引用名**
   （`credential_reference`），值既不缓存也不进 `repr`；每次 attach 重新解析，
   因此「轮换环境变量 + 重连」即完成凭据轮换（P133 的可执行判定）。
4. **会话状态与 Adapter 状态分开**：Adapter 的 `AdapterState` 归 `BaseAdapter`，
   本模块的 `ComSessionState` 只描述 COM 会话（诊断用）。

分层红线：只依赖标准库与同包的 `errors.py`；**不**引用 SQLAlchemy / FastAPI / MCP SDK /
httpx，**不**依赖 `app.interfaces` / `app.application`。
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Final, Protocol

from app.infrastructure.adapters.etabs.errors import EtabsConnectionError

__all__ = [
    "CREDENTIAL_REFERENCE_KEY",
    "ComDispatch",
    "ComSession",
    "ComSessionState",
    "CredentialProviderLike",
]

CREDENTIAL_REFERENCE_KEY: Final[str] = "credential_reference"
"""连接配置里凭据**引用名**的键（值只经注入的 CredentialProvider 解析；见裁决 3）。"""


class CredentialProviderLike(Protocol):
    """凭据提供者契约（`docs/07` §8.5；既有 `EnvironmentCredentialProvider` 结构上满足）。"""

    async def get_secret(self, reference: str) -> str:
        """按**引用名**读取凭据值。"""
        ...


class ComDispatch(Protocol):
    """COM 派发端口（见裁决 1；实现由部署方注入）。

    ⚠️ 端口只承载**协议 / 生命周期**语义；`invoke` 的 `method` 必须来自
    `catalogue.CATALOGUE`（可追溯的原生事实），Adapter 侧不存在第二条取值路径。
    """

    async def attach(self, *, secret: str | None = None) -> None:
        """建立 COM 会话（生命周期；`secret` 为 `None` 表示该部署无需凭据）。"""
        ...

    async def detach(self) -> None:
        """释放 COM 会话（必须幂等）。"""
        ...

    async def is_attached(self) -> bool:
        """会话当前是否可用（健康检查的**唯一**探针；零副作用）。"""
        ...

    async def invoke(self, *, method: str, arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        """调用一个原生方法，返回原生返回值（**不**解释语义）。"""
        ...


class ComSessionState(StrEnum):
    """COM 会话状态（诊断用；与 `AdapterState` 分开，见裁决 4）。"""

    DETACHED = "DETACHED"
    ATTACHING = "ATTACHING"
    ATTACHED = "ATTACHED"
    DETACHING = "DETACHING"
    ERROR = "ERROR"


class ComSession:
    """COM 会话（`docs/01` §20 的协议层；见裁决 1–4）。

    Attributes:
        dispatch: 注入的原生派发端口（未注入 → 连接明确失败）。
        credential_reference: 凭据**引用名**（非 secret；值不缓存、不进 `repr`）。
    """

    def __init__(
        self,
        dispatch: ComDispatch | None,
        *,
        credential_provider: CredentialProviderLike | None = None,
        credential_reference: str = "",
    ) -> None:
        """绑定派发端口与凭据引用（**不**做任何 I/O，**不**取凭据）。"""
        self._dispatch = dispatch
        self._credentials = credential_provider
        self._credential_reference = str(credential_reference)
        self._state: ComSessionState = ComSessionState.DETACHED

    # ===== 只读视图（绝不暴露凭据值）=====

    @property
    def state(self) -> ComSessionState:
        """当前 COM 会话状态。"""
        return self._state

    @property
    def attached(self) -> bool:
        """会话是否处于 `ATTACHED`。"""
        return self._state is ComSessionState.ATTACHED

    @property
    def credential_reference(self) -> str:
        """凭据**引用名**（非 secret；值不暴露，见裁决 3）。"""
        return self._credential_reference

    @property
    def credential_configured(self) -> bool:
        """是否配置了凭据引用（诊断用；**不**回显值）。"""
        return bool(self._credential_reference)

    async def configure(self, credential_reference: str) -> None:
        """更新凭据**引用名**（P133 的凭据轮换；见裁决 3）。

        Args:
            credential_reference: 新的引用名（值仍在 `attach()` 时解析、**不**缓存）。

        Note:
            引用名变化且会话已 `ATTACHED` → **先释放**（`detach()`），使下一次
            `attach()` 用新引用重建会话；引用名未变 → **无操作**（幂等）。
        """
        reference = str(credential_reference)
        if reference == self._credential_reference:
            return
        if self._state is ComSessionState.ATTACHED:
            await self.detach()
        self._credential_reference = reference

    def __repr__(self) -> str:
        """诊断表示：只含状态与「是否配置凭据」，**不含**任何值（见裁决 3）。"""
        return (
            f"ComSession(state={self._state.value!r}, "
            f"credential_configured={self.credential_configured})"
        )

    # ===== 生命周期 =====

    async def attach(self) -> None:
        """建立 COM 会话（幂等；见裁决 2 / 3）。

        Raises:
            EtabsConnectionError: `STRUCTAI-2000` —— 未注入 dispatch，或原生 attach 失败。
        """
        if self._state is ComSessionState.ATTACHED:
            return
        dispatch = self._dispatch
        if dispatch is None:
            raise EtabsConnectionError("dispatch_not_configured")
        self._state = ComSessionState.ATTACHING
        try:
            secret = await self._resolve_secret()
            await dispatch.attach(secret=secret)
        except Exception:
            self._state = ComSessionState.ERROR
            raise
        self._state = ComSessionState.ATTACHED

    async def detach(self) -> None:
        """释放 COM 会话（幂等；失败也把状态置为 `DETACHED`，**不**掩盖异常）。"""
        if self._state in {ComSessionState.DETACHED, ComSessionState.ERROR}:
            self._state = ComSessionState.DETACHED
            return
        self._state = ComSessionState.DETACHING
        try:
            if self._dispatch is not None:
                await self._dispatch.detach()
        finally:
            self._state = ComSessionState.DETACHED

    async def is_attached(self) -> bool:
        """会话当前是否可用（健康探针；未注入 dispatch → `False`）。"""
        if self._dispatch is None:
            return False
        try:
            return bool(await self._dispatch.is_attached())
        except Exception:
            return False

    async def _resolve_secret(self) -> str | None:
        """解析凭据值（**只**在 attach 那一刻；未配置引用 → `None`，见裁决 3）。"""
        if not self._credential_reference:
            return None
        if self._credentials is None:
            raise EtabsConnectionError("credential_provider_not_configured")
        return await self._credentials.get_secret(self._credential_reference)
