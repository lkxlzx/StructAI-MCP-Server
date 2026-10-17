"""Application · Management —— Web UI 的数据端口（P181）。

为什么需要它
------------
原型 UI 要的是**普通 REST**（状态 / 客户端 / 任务 / 日志 / 注册表 / 模板），
而 Core 的对外面是 MCP Tool。两者之间**不能**让接口层直连数据库
（`docs/02` §57：`UI → SQLAlchemy` 禁止；`docs/07` §14.1：Interface 不依赖 Infrastructure）。

本模块只定义**端口**（`ManagementPort`）：接口层依赖它，容器提供实现。
端口的方法返回**纯 JSON 形状**（`Mapping` / `Sequence`），因此：
- 接口层不做业务判断，只转发（与 `engineering_doc` 的 thin wrapper 同口径）；
- Application 层不 import SQLAlchemy / FastAPI / `app.infrastructure`。

⚠️ 本模块**不**出现任何厂商名（`docs/07` §14.2）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

__all__ = ["ManagementPort"]


@runtime_checkable
class ManagementPort(Protocol):
    """Web UI 的数据端口（一次调用 = 一个短会话；实现方负责事务边界）。"""

    async def login(self, username: str, password: str) -> Mapping[str, Any]:
        """口令登录 → `{token, user, tenant, roles, permissions}`（**不回显口令**）。"""
        ...

    async def logout(self, token: str) -> bool:
        """注销会话（幂等：未知 token 返回 `False`）。"""
        ...

    async def identity(self, token: str) -> Mapping[str, Any]:
        """校验 token → 身份摘要（**不含** token 本身）。

        Raises:
            PermissionDeniedError: `STRUCTAI-4000` —— token 无效 / 过期。
        """
        ...

    async def overview(self) -> Mapping[str, Any]:
        """首页 / 侧栏：服务状态、任务计数、客户端计数、注册表 / 模板摘要。"""
        ...

    async def clients(self) -> Sequence[Mapping[str, Any]]:
        """已登记的软件实例（名称 / 产品 / 地址 / 状态 / 版本；**不含**凭据）。"""
        ...

    async def tasks(self, *, limit: int, offset: int) -> Mapping[str, Any]:
        """任务列表（租户作用域；`{total, items}`）。"""
        ...

    async def task(self, task_id: str) -> Mapping[str, Any]:
        """单个任务及其步骤。

        Raises:
            NotFoundError: 任务不存在或不属于当前租户。
        """
        ...

    async def cancel(self, task_id: str) -> Mapping[str, Any]:
        """请求取消任务（返回取消结果，不伪造终态）。"""
        ...

    async def events(self, *, limit: int) -> Sequence[Mapping[str, Any]]:
        """审计链最近 N 条（只读；append-only）。"""
        ...

    async def call(
        self,
        *,
        tool: str,
        operation: str,
        parameters: Mapping[str, Any],
        context: Mapping[str, Any],
        token: str,
    ) -> Mapping[str, Any]:
        """把一次 UI 请求转成**同一条** MCP 执行链（9 Tool 契约，不复制业务逻辑）。

        Returns:
            统一响应信封（`docs/02` §71 的 13 键）。
        """
        ...

    async def registry(self) -> Mapping[str, Any]:
        """端点目录摘要（命名空间计数 / 总数）。"""
        ...

    async def endpoints(
        self, *, namespace: str = "", query: str = "", limit: int = 50, offset: int = 0
    ) -> Mapping[str, Any]:
        """端点列表（过滤 + 分页；**不含** Schema 原文）。"""
        ...

    async def endpoint(self, key: str) -> Mapping[str, Any]:
        """端点详情（含请求 Schema 原文）。"""
        ...

    async def operations(self) -> Sequence[Mapping[str, Any]]:
        """运行时 Operation 清单（名字 + 归属 Tool）。"""
        ...

    async def templates(self) -> Mapping[str, Any]:
        """模板库摘要 + 模板列表。"""
        ...

    async def template(self, name: str) -> Mapping[str, Any]:
        """单个模板的参数表（**不含**整份 model）。"""
        ...

    async def import_template(
        self,
        *,
        name: str,
        overrides: Mapping[str, Any],
        project_path: str,
        token: str,
    ) -> Mapping[str, Any]:
        """模板 → 服务器侧 JSON 文件 → 经 MCP `MODEL.IMPORT` 导入（返回信封）。"""
        ...
