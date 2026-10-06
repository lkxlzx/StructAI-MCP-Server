"""Application · Services（`docs/07` §3.3 冻结结构；`docs/02` §43–§48）。

本包是跨执行流程的 Application 层服务落点（`docs/07` §3.3 的 `services/`）：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `capability_resolver.py` | `CapabilityResolver`（`docs/02` §43–§48） | **P14–P18 ✅** |
| `adapter_resolver.py` | `AdapterResolver`（本批由 `AdapterManager` 承担） | P36 |
| `document.py` · `model.py` · `result.py` | 文档 / 模型 / 结果服务 | P29–P36 |
| `quota.py` | `QuotaService`（`docs/07` §9 第 12 步） | P29–P35 |
| `backup.py` | 备份服务 | P29–P35 |

装配形状（`docs/02` §33 / §123）
--------------------------------
`CapabilityResolver` 依赖 P08 的 `CapabilityRegistry`（进程级装配件）与会话级的
`ResourceStore`；它本身是**会话 / 请求级**对象，因此**不**进进程级容器 ——
与 P10–P13 的安全服务、P14–P18 的资源服务同一口径（`docs/02` §33 的冻结容器形状不变）。

P19–P20：`CapabilityResolver` 新增可选的 `runtime=` 参数（`RuntimeCapabilitySource`，
`docs/02` §21 / §23 / §57；`docs/07` §16 R30 的接入点）。运行时清单由
`app/infrastructure/adapters/base/manager.py` 的 `AdapterManager.runtime_capabilities()`
提供 —— 它是**进程级**对象（Adapter 注册与实例绑定都在进程内，见该模块裁决 2），
因此同样**不**进本容器，由 P36 的 `ExecutionService` 持有并注入。
`AdapterResolver`（`docs/07` §3.3 的 `services/adapter_resolver.py`）在 P19–P20 **不**新增：
「按软件实例取 Adapter」已由 `AdapterManager.resolve_for_instance()` 实现（`docs/02` §56），
再包一层纯转发类会违反 `docs/02` §91「严禁 ExecutionService 变成巨型类」的同源原则 ——
Application 侧真正需要的是**收窄契约**（`RuntimeCapabilitySource`），已在本模块给出。

分层红线（`docs/07` §14.1 / §2.2）：本包只依赖标准库与 `app.domain`；
**不得**依赖 `app.infrastructure` / `app.interfaces`，也不得出现任何厂商专属内容。
"""

from __future__ import annotations

from app.application.services.capability_resolver import (
    DEFAULT_CAPABILITY_CACHE_SECONDS,
    CapabilityDecision,
    CapabilityLookup,
    CapabilityResolver,
    CapabilitySupport,
    InstanceLookup,
    RuntimeCapabilitySource,
)

__all__ = [
    "DEFAULT_CAPABILITY_CACHE_SECONDS",
    "CapabilityDecision",
    "CapabilityLookup",
    "CapabilityResolver",
    "CapabilitySupport",
    "InstanceLookup",
    "RuntimeCapabilitySource",
]
