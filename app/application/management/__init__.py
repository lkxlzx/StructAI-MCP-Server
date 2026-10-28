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

    async def change_password(self, token: str, current: str, new: str) -> Mapping[str, Any]:
        """当前登录用户修改自己的口令（校验旧口令 + 密码策略 + 历史）。"""
        ...

    async def access_decision(self, ip: str) -> Mapping[str, Any]:
        """访问控制判定（白 / 黑名单 + 频率限制；返回 `{allowed, reason}`）。"""
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

    # ===== 软件客户端（P185）=====

    async def create_client(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """登记一个软件实例（自动补齐 software → product → version 链）。"""
        ...

    async def update_client(self, client_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新软件实例（名称 / 产品 / 版本 / 地址 / 凭据引用 / 状态）。"""
        ...

    async def delete_client(self, client_id: str) -> Mapping[str, Any]:
        """删除软件实例（同时清理不再被引用的产品 / 版本 / 软件行）。"""
        ...

    async def test_client(self, client_id: str) -> Mapping[str, Any]:
        """测试实例连通性（HTTP 端点真实探测；无地址时如实报告未配置）。"""
        ...

    async def connect_client(self, client_id: str) -> Mapping[str, Any]:
        """连接实例（注册 / 绑定 Adapter → 建立连接 → 健康检查）。

        Raises:
            ProtocolError: 未找到可用的 Adapter 实现（`STRUCTAI-1000`）。
        """
        ...

    async def disconnect_client(self, client_id: str) -> Mapping[str, Any]:
        """断开实例（释放 Adapter 会话；幂等）。"""
        ...

    async def client_events(
        self, client_id: str, *, limit: int = 50
    ) -> Sequence[Mapping[str, Any]]:
        """实例的连接测试 / 生命周期事件（本机运维库，最新在前）。"""
        ...

    async def client_options(self) -> Mapping[str, Any]:
        """新增 / 编辑客户端时的候选值（软件 / 产品 / 版本 / 凭据引用）。"""
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

    # ===== 系统设置（P183）=====

    async def settings(self) -> Mapping[str, Any]:
        """全部设置分区（默认值 ⊕ 落库值）＋ 运行时只读信息。"""
        ...

    async def update_settings(self, section: str, values: Mapping[str, Any]) -> Mapping[str, Any]:
        """深合并一个设置分区（未知分区 → `STRUCTAI-1000`）。"""
        ...

    async def users(self, *, query: str = "") -> Mapping[str, Any]:
        """用户列表（用户名 / 角色 / 状态；**不含** `password_hash`）。"""
        ...

    async def create_user(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """新建用户（口令只做 Argon2id 哈希落库，**不回显**）。"""
        ...

    async def update_user(self, user_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新用户（姓名 / 邮箱 / 角色 / 启用状态 / 锁定 / 重置口令）。"""
        ...

    async def delete_user(self, user_id: str) -> Mapping[str, Any]:
        """删除用户及其角色关联（不允许删除最后一个管理员）。"""
        ...

    async def roles(self) -> Mapping[str, Any]:
        """角色列表（角色名 / 权限码 / 用户数）。"""
        ...

    async def update_role(self, role_id: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """更新角色（权限码集合）。"""
        ...

    async def create_role(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """新建角色（角色名租户内唯一；权限码必须是已登记的 12 码）。"""
        ...

    async def delete_role(self, role_id: str) -> Mapping[str, Any]:
        """删除角色（仍有用户关联 / 最后一个系统管理员角色时拒绝）。"""
        ...

    async def models(self) -> Mapping[str, Any]:
        """模型列表（来自设置分区；API Key 只回显「是否已配置」）。"""
        ...

    async def update_models(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """整体替换模型列表（列表语义，不做深合并）。"""
        ...

    async def test_model(self, model_id: str) -> Mapping[str, Any]:
        """测试模型可用性（**不**发起外部网络请求；按已配置项如实报告）。"""
        ...

    async def storage_stats(self) -> Mapping[str, Any]:
        """数据管理统计（数据库大小 / 表行数 / 存储占用）。"""
        ...

    async def create_backup(self, kind: str = "manual") -> Mapping[str, Any]:
        """立即备份（SQLite backup API，落 `backup/<UTC 时间戳>/`；含设置库）。"""
        ...

    async def restore_backup(self, backup_id: str) -> Mapping[str, Any]:
        """从备份恢复 Core 库（恢复前先做一份 `pre-restore` 备份）。"""
        ...

    async def backup_archive(self, backup_id: str) -> Mapping[str, Any]:
        """把备份目录打包成 zip（浏览器下载用；落在临时目录）。"""
        ...

    async def backups(self) -> Sequence[Mapping[str, Any]]:
        """备份记录（目录扫描；含 manifest 摘要）。"""
        ...

    async def cleanup(self, categories: Mapping[str, Any]) -> Mapping[str, Any]:
        """按类别清理（只删**已终结**的任务与会话；审计记录不删）。"""
        ...

    async def security_overview(self) -> Mapping[str, Any]:
        """安全设置页的统计（失败计数 / 锁定账号 / 24h 审计条数 / 最近审计）。"""
        ...

    async def reset_settings(self, section: str = "") -> Mapping[str, Any]:
        """把分区（空串 = 全部）恢复为默认值。"""
        ...

    async def test_notification(self, email: str) -> Mapping[str, Any]:
        """校验通知邮箱并如实报告投递通道是否可用（**不**伪造发送成功）。"""
        ...

    async def check_update(self) -> Mapping[str, Any]:
        """检查更新（无更新源时如实报告，**不**编造新版本）。"""
        ...

    async def delete_backup(self, backup_id: str) -> Mapping[str, Any]:
        """删除一个备份目录（仅允许删除备份根下的直接子目录）。"""
        ...

    async def backup_path(self, backup_id: str) -> str:
        """备份目录的绝对路径（下载用；路径守卫在实现内）。"""
        ...

    async def export_data(self) -> Mapping[str, Any]:
        """导出设置与摘要（**不含**口令哈希 / 明文密钥）。"""
        ...

    async def import_data(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """导入导出的设置（只接受 `settings` 分区；未知分区忽略）。"""
        ...

    async def purge_data(self) -> Mapping[str, Any]:
        """清空业务数据（保留管理员 / 角色 / 权限 / 软件注册表；审计不删）。"""
        ...

    async def logs(
        self, *, level: str = "", query: str = "", limit: int = 200
    ) -> Mapping[str, Any]:
        """运行日志尾部（按级别 / 关键词过滤；**不含** secret）。"""
        ...

    async def browse(self, path: str = "") -> Mapping[str, Any]:
        """目录浏览（选择目录用；只列子目录，拒绝不存在 / 非目录路径）。"""
        ...

    async def verify_password_policy(self, password: str) -> Mapping[str, Any]:
        """按当前密码策略校验口令（新建 / 重置口令时使用）。"""
        ...

    async def service_control(self, action: str) -> Mapping[str, Any]:
        """服务控制（stop / restart；由装配方注入钩子，未注入时如实报告）。"""
        ...
