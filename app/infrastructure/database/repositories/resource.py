"""执行期资源读取（`docs/07` §12 P14–P18；`docs/02` §8–§12 / §25 / §71–§73）。

为什么需要这个模块
------------------
P14–P18 的 Application 层服务（`app/application/resource/resolver.py`）**不得**依赖
`app.infrastructure`（`docs/07` §14.1 / §2.2）。`ResourceResolver` 需要读
`projects` / `models` / `documents` / `software_instances` 四张表
（`docs/02` §8–§12 / §25 / §71–§73），故本模块把「需要什么」实现为 Domain 侧的结构化
契约 `app.domain.protocols.ResourceStore`：

| 契约方法 | 本模块的实现 | 权威来源 |
| --- | --- | --- |
| `project` | `projects` 单行（含 `tenant_id`） | `docs/02` §8 / §20 |
| `model` | `models` 单行（含 `project_id`） | `docs/02` §8 / §22 |
| `document` | `documents` 单行（含 `project_id`） | `docs/02` §8 / §22 |
| `software_instance` | `software_instances` + 产品 / 版本链 | `docs/02` §12 / §19 |
| `tenant_ids_binding_instance` | `models.software_instance_id` → `projects.tenant_id` |

软件实例的租户归属（`docs/02` §12）
-----------------------------------
`docs/07` §4.3 #10–#13 的软件注册表（`software` / `software_products` /
`software_versions` / `software_instances`）**没有** `tenant_id` 列，而 `docs/02` §12
要求「如果当前 Schema 还没有该字段，本批次必须通过所属 Project / Registry 关系补齐，
**不能允许跨租户实例被直接执行**」。

本批**不改表**（`docs/07` §14.3），故实例的租户归属由**已有关系推导**：哪些租户的项目
链上有模型绑定了该实例（`models.software_instance_id` → `projects.tenant_id`）。
`ResourceResolver` 据此判定，判定本身不在本模块（本模块只回答「有哪些租户」）。

红线（`docs/07` §14.1 / §14.4 / §14.3）
--------------------------------------
- 只做 persistence：**不**判定租户归属、**不**判定权限、**不**出现任何厂商专属内容；
- 全部方法只 `SELECT`，**绝不** `commit` / `rollback`（事务边界归 P06 `UnitOfWork`）；
- **不得**改表：只使用 P04 已落地的 24 张表；
- `SoftwareInstanceRecord` **不含** `credential_reference`（`docs/02` §21；
  `docs/07` §8.5：凭据只经 `CredentialProvider` 注入，绝不进入执行上下文）。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.protocols import (
    DocumentRecord,
    ModelRecord,
    ProjectRecord,
    ResourceStore,
    SoftwareInstanceRecord,
)
from app.infrastructure.database.models import (
    DocumentORM,
    ModelORM,
    ProjectORM,
    SoftwareInstanceORM,
    SoftwareORM,
    SoftwareProductORM,
    SoftwareVersionORM,
)

__all__ = ["ResourceStoreRepository", "build_resource_store"]


class ResourceStoreRepository:
    """`ResourceStore` 的 SQLAlchemy 实现（`docs/02` §8–§12 / §71–§73）。

    ⚠️ 只读：所有方法只发 `SELECT`，**不** `flush` / `commit`（`docs/07` §14.4）。
    """

    def __init__(self, session: AsyncSession) -> None:
        """绑定一个已存在的会话（`docs/02` §16：会话由上层 / UnitOfWork 提供）。"""
        self._session = session

    @property
    def session(self) -> AsyncSession:
        """当前会话（只读用途；事务边界不在此处决定）。"""
        return self._session

    async def project(self, project_id: str) -> ProjectRecord | None:
        """按主键读取项目（`docs/02` §20）。不存在返回 `None`。"""
        result = await self._session.execute(
            select(ProjectORM).where(ProjectORM.id == str(project_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ProjectRecord(
            id=str(row.id),
            tenant_id=str(row.tenant_id),
            version=int(row.version),
        )

    async def model(self, model_id: str) -> ModelRecord | None:
        """按主键读取工程模型（`docs/02` §22）。

        返回的 `project_id` 是租户归属的唯一通路（`models` 无 `tenant_id` 列，
        `docs/02` §11 / §22）；本方法**不**做租户判定。
        """
        result = await self._session.execute(select(ModelORM).where(ModelORM.id == str(model_id)))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return ModelRecord(
            id=str(row.id),
            project_id=str(row.project_id),
            software_instance_id=(
                None if row.software_instance_id is None else str(row.software_instance_id)
            ),
            version=int(row.version),
        )

    async def document(self, document_id: str) -> DocumentRecord | None:
        """按主键读取文档（`docs/02` §22）。`project_id` 是租户归属通路。"""
        result = await self._session.execute(
            select(DocumentORM).where(DocumentORM.id == str(document_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return DocumentRecord(
            id=str(row.id),
            project_id=str(row.project_id),
            model_id=None if row.model_id is None else str(row.model_id),
            status=str(row.status),
        )

    async def software_instance(self, instance_id: str) -> SoftwareInstanceRecord | None:
        """按主键读取软件实例，并补上产品 / 版本链（`docs/02` §12 / §19）。

        Returns:
            实例快照；实例不存在返回 `None`。产品 / 版本链缺失时相应字段留空
            （与 P08 `SoftwareRegistry` 同口径：缺失链路不抛异常）。
            ⚠️ **不含** `credential_reference`（`docs/07` §8.5 / §14.3）。
        """
        result = await self._session.execute(
            select(SoftwareInstanceORM).where(SoftwareInstanceORM.id == str(instance_id))
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None

        version_row = (
            await self._session.execute(
                select(SoftwareVersionORM).where(SoftwareVersionORM.id == str(row.version_id))
            )
        ).scalar_one_or_none()
        product_row = None
        vendor = ""
        if version_row is not None:
            product_row = (
                await self._session.execute(
                    select(SoftwareProductORM).where(
                        SoftwareProductORM.id == str(version_row.product_id)
                    )
                )
            ).scalar_one_or_none()
        if product_row is not None:
            vendor_row = (
                await self._session.execute(
                    select(SoftwareORM).where(SoftwareORM.id == str(product_row.software_id))
                )
            ).scalar_one_or_none()
            vendor = "" if vendor_row is None else str(vendor_row.vendor)

        return SoftwareInstanceRecord(
            id=str(row.id),
            name=str(row.name),
            version_id=str(row.version_id),
            status=str(row.status),
            vendor=vendor,
            product="" if product_row is None else str(product_row.product),
            version="" if version_row is None else str(version_row.version),
        )

    async def tenant_ids_binding_instance(self, instance_id: str) -> frozenset[str]:
        """绑定该软件实例的租户集合（`docs/02` §12 / §71）。

        通路：`models.software_instance_id = :instance_id` → `projects.tenant_id`。
        这是「不改表」前提下补齐 `software_instances` 缺失租户归属的**唯一**依据
        （见模块 docstring）。

        Returns:
            租户 id 集合；未被任何项目链绑定时为空集。
        """
        result = await self._session.execute(
            select(ProjectORM.tenant_id)
            .join(ModelORM, ModelORM.project_id == ProjectORM.id)
            .where(ModelORM.software_instance_id == str(instance_id))
        )
        return frozenset(str(tenant_id) for tenant_id in result.scalars().all())


def build_resource_store(session: AsyncSession) -> ResourceStore:
    """为一个会话装配执行期资源读取入口（`docs/02` §33 / §123）。

    Args:
        session: 已存在的 `AsyncSession`（通常由 P06 `UnitOfWork` 提供）。

    Returns:
        `ResourceStore`：绑定该会话，因此与同会话的其他仓储共享同一事务。

    ⚠️ 本函数**不**开事务、**不**提交、**不**建立连接（`docs/02` §16；`docs/07` §14.4）。
    """
    return ResourceStoreRepository(session)
