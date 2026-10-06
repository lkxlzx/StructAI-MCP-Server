"""Application · Resource · ResourceResolver（`docs/07` §12 P14–P18；`docs/02` §8–§12 / §25）。

权威来源
--------
- `docs/02` §8（`exec`）—— 职责链：`Client Resource ID → Database → Resource →
  Tenant Validation → Project Validation → Resource Context`；Resolver **不**负责
  `permission` / `adapter` / `task` / `MCP`。
- `docs/02` §9（`exec`）—— 接口：`resolve_project` / `resolve_model` / `resolve_document` /
  `resolve_software_instance`，以及 `verify_access`（`blue` §9 的同一组签名）。
- `docs/02` §10 / §11 / §12（`exec`）—— 租户边界：`project.tenant_id != identity.tenant_id`
  → 拒绝；`Model ↓ Project ↓ Tenant` 必须逐级追；`SoftwareInstance` 的租户归属必须补齐，
  **不能允许跨租户实例被直接执行**。
- `docs/02` §25（`source9`）—— 验证项：Tenant ownership / Project membership /
  Model ownership / Document ownership / Software access。
- `docs/02` §71 / §72 / §73（`exec`）—— Repository 查询必须 `tenant scoped`；
  `ResolvedResource(resource_type, resource_id, tenant_id, project_id=None)`。
- `docs/07` §9 第 7 步 —— `Resolve Resource` = **跨租户唯一拦截点，必须最先**
  （先于 Schema / Engineering / Permission / Lock）。
- `docs/07` §11 —— 跨租户 → **`STRUCTAI-4200` Tenant Access Denied**（20 码契约）。

落地裁决（只补实现手段，不改语义）
----------------------------------
1. **「不存在」与「属于别的租户」返回同一个错误**：`docs/02` §10 的示例对 `None` 抛
   `NotFoundError`、对跨租户抛 `TenantAccessDeniedError`。但 `NotFoundError` **不在**
   20 码契约里（`app/domain/errors.py` 的裁决：它只用于 Registry 装配期的内部查找失败），
   且 `docs/02` §48 要求**不得泄露存在性**。故本模块统一抛
   `TenantAccessDeniedError`（`STRUCTAI-4200`，消息固定 `Tenant access denied`），
   与 P10–P13 的 `ProjectAccessService` / `TenantAccessService` 同一口径。
   判定本身**委托** `TenantAccessService.ensure_access`（同租户即通过；租户不符即拒绝）
   （`docs/07` §12 的「复用已落地件」），因此跨租户判定只有一处实现。
2. **客户端资源标识自相矛盾 → `STRUCTAI-1000`**：客户端同时给 `project_id` 与
   `model_id`（或 `model_id` 与 `document_id`）时，若后者不属于前者，说明请求自相矛盾。
   这不是租户问题（同租户内也可能发生），而是**请求格式非法** → `ProtocolError`
   （`STRUCTAI-1000`，20 码内既有）。**不**新增错误码。
3. **`resolve()` 会校验全部已提供的标识**：`docs/07` §9 第 7 步是**唯一**跨租户拦截点，
   因此只要客户端提供了某个标识，就必须逐个过租户边界（不能因为「最终只用最具体的那个」
   而放过前面的校验）。返回值取**最具体**的一个：`DOCUMENT > MODEL > PROJECT >
   SOFTWARE_INSTANCE`（`docs/02` §73 的 `ResolvedResource` 只能描述一个资源；
   软件实例是执行目标，数据资源优先）。
4. **软件实例的租户归属**：`software_instances` 无 `tenant_id` 列（`docs/07` §4.3 #10–#13），
   `docs/02` §12 要求经「所属 Project / Registry 关系」补齐。本批不改表，故由
   `ResourceStore.tenant_ids_binding_instance` 回答「哪些租户的项目链绑定了该实例」，
   当前租户不在其中即拒绝 —— 未被任何项目绑定的实例**不**属于任何租户，
   任何租户都不得直接执行（`docs/02` §12 的禁止项）。
5. **多级锁（`SoftwareInstance ↓ Model ↓ Document`，`docs/02` §75）不在本批**：
   本批的 `LockPolicy` 对**一个**已解析资源出锁（`docs/02` §74 / §58）；
   多级锁获取属 Task Engine 批次（P22–P28）。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库、`app.domain` 与**同层**的 `app.application.security` /
`app.application.resource`：**不**引用 SQLAlchemy / FastAPI / MCP SDK / httpx，
**不**依赖 `app.infrastructure`（持久化经 Domain 契约 `ResourceStore` 注入），
也**不**出现任何厂商专属内容。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.application.resource.lock_policy import ResourceKey
from app.application.security.context import IdentityContext
from app.application.security.permission import TENANT_ACCESS_DENIED_MESSAGE, TenantAccessService
from app.domain.enums import ResourceType
from app.domain.errors import ProtocolError, TenantAccessDeniedError
from app.domain.protocols import ResourceStore
from app.domain.value_objects import ResourceRef

__all__ = ["RESOLUTION_PRECEDENCE", "ResolvedResource", "ResourceResolver"]

RESOLUTION_PRECEDENCE: tuple[ResourceType, ...] = (
    ResourceType.DOCUMENT,
    ResourceType.MODEL,
    ResourceType.PROJECT,
    ResourceType.SOFTWARE_INSTANCE,
)
"""`resolve()` 的返回优先级（最具体者胜；见模块裁决 3）。

`docs/02` §73 的 `ResolvedResource` 只能描述一个资源，而 `docs/07` §9 第 7 步要求
**所有**已提供的标识都过租户边界。本元组就是「校验全部、返回最具体」的固化。
"""


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    """已解析且已通过租户边界的资源（`docs/02` §73，逐字段照抄）。

    Attributes:
        resource_type: 资源类型（`app.domain.enums.ResourceType` 的取值）。
        resource_id: 资源标识（UUID 字符串）。
        tenant_id: 该资源所属租户。软件实例无 `tenant_id` 列，故取其**绑定租户**
            （即当前身份的租户，见模块裁决 4）。
        project_id: 所属项目；`SOFTWARE_INSTANCE` / `PROJECT` 之外的资源都有值
            （`PROJECT` 自身即项目，故为 `None`）。
    """

    resource_type: str
    resource_id: str
    tenant_id: str
    project_id: str | None = None

    def as_key(self) -> ResourceKey:
        """转成锁键（`docs/02` §37；`docs/02` §74 的 `LockPolicy.resolve` 消费它）。"""
        return ResourceKey(resource_type=self.resource_type, resource_id=self.resource_id)


class ResourceResolver:
    """资源解析 + 跨租户拦截（`docs/07` §9 第 7 步；`docs/02` §8–§12 / §25 / §71–§73）。

    ⚠️ 本服务**只读**：不写任何表、不产生任何日志、不 `commit`
    （`docs/07` §14.4）。这也使它可以安全地排在 Schema / Engineering / Permission /
    Lock 之前 —— 顺序即 `docs/07` §9 的冻结顺序。
    """

    def __init__(
        self,
        store: ResourceStore,
        *,
        tenant_access: TenantAccessService | None = None,
    ) -> None:
        """绑定资源来源与租户判定入口。

        Args:
            store: 满足 `app.domain.protocols.ResourceStore` 的只读来源
                （装配期由 `build_resource_store(session)` 注入，见模块裁决 1 与
                `docs/07` §2.2：Application 不依赖 Infrastructure）。
            tenant_access: 租户判定服务；缺省用 `TenantAccessService()`。
                跨租户判定**只有**这一处实现（`docs/02` §48）。
        """
        self._store = store
        self._tenant_access = tenant_access if tenant_access is not None else TenantAccessService()

    # ===== 主入口（`docs/02` §8 / §25）=====

    async def resolve(self, context: object) -> ResolvedResource | None:
        """把客户端提供的资源标识解析成 `ResolvedResource`（`docs/02` §8）。

        Args:
            context: `ExecutionContext`（`docs/02` §3）。本方法只读取
                `context.identity` / `context.project.project_id` /
                `context.resource.model_id` / `context.resource.document_id` /
                `context.software.instance_id`，因此参数类型放宽为 `object`
                （避免与 `app.application.execution.context` 形成环状导入）。

        Returns:
            **最具体**的一个已解析资源（`RESOLUTION_PRECEDENCE`）；一个标识都没提供时
            返回 `None`。

        Raises:
            TenantAccessDeniedError: `STRUCTAI-4200`，任一提供的标识不属于身份的租户
                （或不存在 —— 两者不区分，`docs/02` §48）。
            ProtocolError: `STRUCTAI-1000`，客户端标识自相矛盾（见模块裁决 2）。
        """

        if _software_instance_id(context) is not None:
            await self.resolve_software_instance(context)

        resolved: ResolvedResource | None = None
        if _project_id(context) is not None:
            resolved = await self.resolve_project(context)
        if _model_id(context) is not None:
            resolved = await self.resolve_model(context)
        if _document_id(context) is not None:
            resolved = await self.resolve_document(context)
        return resolved

    # ===== 四个解析入口（`docs/02` §9）=====

    async def resolve_project(self, context: object) -> ResolvedResource:
        """解析项目并做租户边界（`docs/02` §10）。

        Raises:
            ProtocolError: `STRUCTAI-1000`，context 未提供 `project_id`。
            TenantAccessDeniedError: `STRUCTAI-4200`（见模块裁决 1）。
        """
        project_id = _project_id(context)
        if project_id is None:
            raise ProtocolError(
                "execution context has no project_id to resolve",
                details={"stage": "resource_resolution", "resource_type": "PROJECT"},
            )
        return await self._project(str(project_id), _identity_of(context))

    async def resolve_model(self, context: object) -> ResolvedResource:
        """解析工程模型并做租户边界（`docs/02` §11：`Model ↓ Project ↓ Tenant`）。

        Raises:
            ProtocolError: `STRUCTAI-1000`，context 未提供 `model_id`，或与
                `project_id` 自相矛盾（见模块裁决 2）。
            TenantAccessDeniedError: `STRUCTAI-4200`（见模块裁决 1）。
        """
        model_id = _model_id(context)
        if model_id is None:
            raise ProtocolError(
                "execution context has no model_id to resolve",
                details={"stage": "resource_resolution", "resource_type": "MODEL"},
            )
        return await self._model(str(model_id), _identity_of(context), _project_id(context))

    async def resolve_document(self, context: object) -> ResolvedResource:
        """解析文档并做租户边界（`docs/02` §11：`Document ↓ Project ↓ Tenant`）。

        Raises:
            ProtocolError: `STRUCTAI-1000`，context 未提供 `document_id`，或与
                `project_id` / `model_id` 自相矛盾（见模块裁决 2）。
            TenantAccessDeniedError: `STRUCTAI-4200`（见模块裁决 1）。
        """
        document_id = _document_id(context)
        if document_id is None:
            raise ProtocolError(
                "execution context has no document_id to resolve",
                details={"stage": "resource_resolution", "resource_type": "DOCUMENT"},
            )
        return await self._document(
            str(document_id),
            _identity_of(context),
            _project_id(context),
            _model_id(context),
        )

    async def resolve_software_instance(self, context: object) -> ResolvedResource:
        """解析软件实例并做租户边界（`docs/02` §12；见模块裁决 4）。

        Raises:
            ProtocolError: `STRUCTAI-1000`，context 未提供 `software_instance_id`。
            TenantAccessDeniedError: `STRUCTAI-4200`，实例不存在，或当前租户的
                项目链**没有**绑定该实例（含「未被任何项目绑定」）。
        """
        instance_id = _software_instance_id(context)
        if instance_id is None:
            raise ProtocolError(
                "execution context has no software_instance_id to resolve",
                details={"stage": "resource_resolution", "resource_type": "SOFTWARE_INSTANCE"},
            )
        return await self._software_instance(str(instance_id), _identity_of(context))

    # ===== `docs/02` §9 的 verify_access =====

    async def verify_access(self, resource: ResourceRef, context: object) -> None:
        """校验一个 `ResourceRef` 是否属于身份的租户（`docs/02` §9 / §25）。

        Args:
            resource: `docs/02` §8 的资源引用（`resource_type` + `resource_id`）。
            context: `ExecutionContext`。

        Raises:
            ProtocolError: `STRUCTAI-1000`，`resource_type` 不是冻结取值
                （`app.domain.enums.ResourceType`）。
            TenantAccessDeniedError: `STRUCTAI-4200`（同 `resolve`）。
        """
        try:
            resource_type = ResourceType(resource.resource_type)
        except ValueError as error:
            raise ProtocolError(
                "unknown resource type",
                details={
                    "stage": "resource_resolution",
                    "resource_type": str(resource.resource_type),
                },
            ) from error

        identity = _identity_of(context)
        if resource_type is ResourceType.PROJECT:
            await self._project(str(resource.resource_id), identity)
            return
        if resource_type is ResourceType.MODEL:
            await self._model(str(resource.resource_id), identity, None)
            return
        if resource_type is ResourceType.DOCUMENT:
            await self._document(str(resource.resource_id), identity, None, None)
            return
        await self._software_instance(str(resource.resource_id), identity)

    # ===== 内部：逐类型解析（租户判定委托 `TenantAccessService`）=====

    async def _project(self, project_id: str, identity: IdentityContext) -> ResolvedResource:
        """项目解析（`docs/02` §10）。"""
        record = await self._store.project(project_id)
        if record is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        self._tenant_access.ensure_access(identity, record.tenant_id)
        return ResolvedResource(
            resource_type=ResourceType.PROJECT.value,
            resource_id=record.id,
            tenant_id=record.tenant_id,
        )

    async def _model(
        self,
        model_id: str,
        identity: IdentityContext,
        context_project_id: object,
    ) -> ResolvedResource:
        """模型解析（`docs/02` §11）：`model → project → tenant` 逐级追。"""
        record = await self._store.model(model_id)
        if record is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        project = await self._store.project(record.project_id)
        if project is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        self._tenant_access.ensure_access(identity, project.tenant_id)
        if context_project_id is not None and str(context_project_id) != record.project_id:
            raise ProtocolError(
                "model does not belong to the project in the execution context",
                details={
                    "stage": "resource_resolution",
                    "resource_type": ResourceType.MODEL.value,
                    "resource_id": record.id,
                },
            )
        return ResolvedResource(
            resource_type=ResourceType.MODEL.value,
            resource_id=record.id,
            tenant_id=project.tenant_id,
            project_id=record.project_id,
        )

    async def _document(
        self,
        document_id: str,
        identity: IdentityContext,
        context_project_id: object,
        context_model_id: object,
    ) -> ResolvedResource:
        """文档解析（`docs/02` §11）：`document → project → tenant` 逐级追。"""
        record = await self._store.document(document_id)
        if record is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        project = await self._store.project(record.project_id)
        if project is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        self._tenant_access.ensure_access(identity, project.tenant_id)
        if context_project_id is not None and str(context_project_id) != record.project_id:
            raise ProtocolError(
                "document does not belong to the project in the execution context",
                details={
                    "stage": "resource_resolution",
                    "resource_type": ResourceType.DOCUMENT.value,
                    "resource_id": record.id,
                },
            )
        if (
            context_model_id is not None
            and record.model_id is not None
            and str(context_model_id) != record.model_id
        ):
            raise ProtocolError(
                "document does not belong to the model in the execution context",
                details={
                    "stage": "resource_resolution",
                    "resource_type": ResourceType.DOCUMENT.value,
                    "resource_id": record.id,
                },
            )
        return ResolvedResource(
            resource_type=ResourceType.DOCUMENT.value,
            resource_id=record.id,
            tenant_id=project.tenant_id,
            project_id=record.project_id,
        )

    async def _software_instance(
        self,
        instance_id: str,
        identity: IdentityContext,
    ) -> ResolvedResource:
        """软件实例解析（`docs/02` §12；见模块裁决 4）。

        实例**不存在**与「当前租户未绑定该实例」返回同一个 `STRUCTAI-4200`
        （`docs/02` §48：不泄露存在性）。
        """
        record = await self._store.software_instance(instance_id)
        if record is None:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        bound_tenants = await self._store.tenant_ids_binding_instance(record.id)
        if str(identity.tenant_id) not in bound_tenants:
            raise TenantAccessDeniedError(TENANT_ACCESS_DENIED_MESSAGE)
        return ResolvedResource(
            resource_type=ResourceType.SOFTWARE_INSTANCE.value,
            resource_id=record.id,
            tenant_id=str(identity.tenant_id),
        )


def _identity_of(context: object) -> IdentityContext:
    """取 context 的服务端身份（`docs/02` §3）。

    Raises:
        ProtocolError: `STRUCTAI-1000`，context 未携带服务端 `IdentityContext`
            （装配 / 调用错误：身份只能由 Core 构造，`docs/07` §8.1）。
    """
    identity = getattr(context, "identity", None)
    if not isinstance(identity, IdentityContext):
        raise ProtocolError(
            "execution context has no server identity",
            details={"stage": "resource_resolution"},
        )
    return identity


def _project_id(context: object) -> object | None:
    """取 `context.project.project_id`（`docs/02` §3）。"""
    project = getattr(context, "project", None)
    return getattr(project, "project_id", None)


def _model_id(context: object) -> object | None:
    """取 `context.resource.model_id`（`docs/02` §3）。"""
    resource = getattr(context, "resource", None)
    return getattr(resource, "model_id", None)


def _document_id(context: object) -> object | None:
    """取 `context.resource.document_id`（`docs/02` §3）。"""
    resource = getattr(context, "resource", None)
    return getattr(resource, "document_id", None)


def _software_instance_id(context: object) -> object | None:
    """取 `context.software.instance_id`（`docs/02` §3）。"""
    software = getattr(context, "software", None)
    return getattr(software, "instance_id", None)


def with_resolved_software(
    context: object,
    *,
    product: str | None,
    version: str | None,
) -> object:
    """回填 `SoftwareContext.product` / `version`（`docs/02` §3 / §19）。

    客户端**不得**直接声明这两个字段（`docs/07` §8.1）；它们只能由解析结果回填。
    本函数用 `dataclasses.replace` 产生**新**上下文，因此不会就地改已有对象。

    Args:
        context: `ExecutionContext`。
        product: 解析得到的软件产品名。
        version: 解析得到的软件版本号。

    Returns:
        新的 `ExecutionContext`（同类型）。
    """
    software = getattr(context, "software", None)
    if software is None:
        return context
    return replace(  # type: ignore[type-var]  # 参数类型放宽为 object（见 docstring）
        context,
        software=replace(software, product=product, version=version),
    )
