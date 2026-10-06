"""Application · Execution（`docs/07` §3.3 冻结结构；`docs/02` §6 / §18–§39）。

本包是执行管线的 Application 层落点（`docs/07` §9 的执行流水线顺序冻结）：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `validation.py` | `SchemaEngine`：Schema → 参数校验（`docs/02` §13 / §16） | **P09 ✅** |
| `context.py` | `ExecutionContext` + 三个子上下文 | **P14 ✅** |
| `engineering_validator.py` | `EngineeringValidator`（`docs/02` §18–§22） | **P14 ✅** |
| `preconditions.py` · `postconditions.py` | 前置 / 后置条件（`docs/02` §32） | **P14 ✅** |
| `confirmation.py` | Confirmation Token（`docs/07` §8.4） | **P14 ✅** |
| `idempotency.py` | `IdempotencyService`：原子抢占 / 重放 / 冲突（`docs/07` §10.3） | **P21 ✅** |
| `pipeline.py` | Validation Pipeline 编排（`docs/02` §30） | P36（随 `ExecutionService`） |
| `service.py` | `ExecutionService`（`docs/07` §9 的 15 步主干） | P36 |

顺序红线（`docs/07` §9，**冻结**）
--------------------------------
`Schema Validation` **先于** `Engineering Validation`（结构合法才做工程语义校验）；
`Preconditions` **先于** `Effective Permission`；
`Effective Permission` **先于** `Capability`（避免无授权用户探测软件能力）；
`Postconditions` **先于** `Release Lock`（锁与 Task 生命周期绑定）。
`EXECUTION_PIPELINE_ORDER` 把整条 26 步顺序固化为可断言的常量。

分层红线（`docs/07` §14.1 / §2.2）：本包只依赖标准库、`jsonschema` 与 `app.domain`，
以及**同层**的 `app.application.resource` / `app.application.security`；
**不得**依赖 `app.infrastructure` / `app.interfaces`，也不得出现任何厂商专属内容。
"""

from __future__ import annotations

from typing import Final

from app.application.execution.confirmation import (
    CONFIRMATION_FAILURE_REASONS,
    CONFIRMATION_REQUIRED_RISK_LEVELS,
    DEFAULT_CONFIRMATION_TTL_SECONDS,
    FORBIDDEN_CONFIRMATION_TOKENS,
    INVALID_CONFIRMATION_MESSAGE,
    Confirmation,
    ConfirmationBinding,
    ConfirmationGuard,
    ConfirmationService,
)
from app.application.execution.context import (
    CLIENT_CONTROLLED_IDENTITY_FIELDS,
    CLIENT_PROVIDABLE_RESOURCE_FIELDS,
    ExecutionContext,
    ExecutionContextFactory,
    ProjectContext,
    ResourceContext,
    SoftwareContext,
    ignored_client_identity_fields,
)
from app.application.execution.engineering_validator import (
    ENGINEERING_RULE_OPERATIONS,
    ENGINEERING_RULES,
    MIN_ELEMENT_NODES,
    NODE_COORDINATE_KEYS,
    EngineeringRule,
    EngineeringValidator,
)
from app.application.execution.idempotency import (
    IDEMPOTENCY_CONFLICT_MESSAGE,
    IDEMPOTENCY_FAILURE_REASONS,
    IDEMPOTENCY_HASH_ALGORITHM,
    IDEMPOTENCY_HASH_FIELDS,
    IDEMPOTENCY_IN_FLIGHT_MESSAGE,
    IDEMPOTENCY_STAGE,
    REQUEST_HASH_LENGTH,
    IdempotencyDecision,
    IdempotencyOutcome,
    IdempotencyService,
    canonical_payload,
    decode_response,
    encode_response,
    hash_payload,
)
from app.application.execution.postconditions import (
    POSTCONDITION_OPERATIONS,
    POSTCONDITION_STAGE_ORDER,
    POSTCONDITIONS,
    Postcondition,
    PostconditionCheck,
    PostconditionEvaluator,
    PostconditionReport,
)
from app.application.execution.preconditions import (
    MODEL_COMPLETENESS_KEYS,
    PRECONDITION_OPERATIONS,
    PRECONDITIONS,
    ExecutionFacts,
    Precondition,
    PreconditionCheck,
    PreconditionEvaluator,
    PreconditionReport,
)
from app.application.execution.validation import (
    DEFAULT_DIALECT,
    DRAFT7_URI,
    SCHEMA_2020_12_URI,
    SUPPORTED_DIALECTS,
    SchemaEngine,
    SchemaLookup,
    dialect_of,
    validator_for,
)

__all__ = [
    "CLIENT_CONTROLLED_IDENTITY_FIELDS",
    "CLIENT_PROVIDABLE_RESOURCE_FIELDS",
    "CONFIRMATION_FAILURE_REASONS",
    "CONFIRMATION_REQUIRED_RISK_LEVELS",
    "DEFAULT_CONFIRMATION_TTL_SECONDS",
    "DEFAULT_DIALECT",
    "DRAFT7_URI",
    "ENGINEERING_RULES",
    "ENGINEERING_RULE_OPERATIONS",
    "EXECUTION_PIPELINE_ORDER",
    "IDEMPOTENCY_CONFLICT_MESSAGE",
    "IDEMPOTENCY_FAILURE_REASONS",
    "IDEMPOTENCY_HASH_ALGORITHM",
    "IDEMPOTENCY_HASH_FIELDS",
    "IDEMPOTENCY_IN_FLIGHT_MESSAGE",
    "IDEMPOTENCY_STAGE",
    "REQUEST_HASH_LENGTH",
    "FORBIDDEN_CONFIRMATION_TOKENS",
    "INVALID_CONFIRMATION_MESSAGE",
    "MIN_ELEMENT_NODES",
    "MODEL_COMPLETENESS_KEYS",
    "NODE_COORDINATE_KEYS",
    "POSTCONDITIONS",
    "POSTCONDITION_OPERATIONS",
    "POSTCONDITION_STAGE_ORDER",
    "PRECONDITIONS",
    "PRECONDITION_OPERATIONS",
    "SCHEMA_2020_12_URI",
    "SUPPORTED_DIALECTS",
    "Confirmation",
    "ConfirmationBinding",
    "ConfirmationGuard",
    "ConfirmationService",
    "EngineeringRule",
    "EngineeringValidator",
    "ExecutionContext",
    "ExecutionContextFactory",
    "ExecutionFacts",
    "Postcondition",
    "PostconditionCheck",
    "PostconditionEvaluator",
    "PostconditionReport",
    "Precondition",
    "PreconditionCheck",
    "PreconditionEvaluator",
    "PreconditionReport",
    "ProjectContext",
    "ResourceContext",
    "SchemaEngine",
    "SchemaLookup",
    "SoftwareContext",
    "dialect_of",
    "ignored_client_identity_fields",
    "validator_for",
    "IdempotencyDecision",
    "IdempotencyOutcome",
    "IdempotencyService",
    "canonical_payload",
    "decode_response",
    "encode_response",
    "hash_payload",
]

EXECUTION_PIPELINE_ORDER: Final[tuple[str, ...]] = (
    "MCP Request",
    "Authenticate",
    "Build Server IdentityContext",
    "Build ExecutionContext",
    "Resolve Tool",
    "Resolve Operation",
    "Resolve Resource",
    "Schema Validation",
    "Engineering Validation",
    "Preconditions",
    "Effective Permission",
    "Quota / Rate Limit",
    "Confirmation",
    "Idempotency",
    "Concurrency / Resource Lock",
    "Capability Check",
    "Task / Transaction",
    "Adapter",
    "Result Normalization",
    "Postconditions",
    "Release Lock",
    "Persist Result",
    "Audit",
    "Trace",
    "Event",
    "MCP Response",
)
"""执行流水线的 **26 步冻结顺序**（`docs/07` §9，逐条照抄）。

⚠️ 这是 `docs/07` §9 的**唯一**顺序权威在代码中的固化形态：本批的
`Schema Validation` / `Engineering Validation` / `Preconditions` /
`Effective Permission` / `Confirmation` / `Resource Lock` / `Capability Check` /
`Postconditions` / `Release Lock` 各自的相对位置都由此元组给出，
验收测试据此断言「顺序冻结」而不是靠文档记忆。

`docs/02` §67（`exec`）给出的是同一链路的 22 步简表（把
`Quota` / `Dry Run` / `Persist Idempotency` 等并入相邻步骤），本常量以
**`docs/07` §9** 为准（它是本项目的开发方案与续接权威）。
"""
