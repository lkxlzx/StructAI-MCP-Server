"""Application · Execution（`docs/07` §3.3 冻结结构；`docs/02` §30–§39）。

本包是执行管线的 Application 层落点（`docs/07` §9 的执行流水线顺序冻结）：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `validation.py` | `SchemaEngine`：Schema → 参数校验（`docs/02` §13 / §16） | **P09 ✅** |
| `engineering_validator.py` | `EngineeringValidator`：工程语义校验（`docs/02` §18–§22） | P14–P18 |
| `context.py` | `ExecutionContext`（`docs/02` §6） | P14–P18 |
| `pipeline.py` | Validation Pipeline（`docs/02` §30） | P14–P18 |
| `preconditions.py` · `postconditions.py` | 前置 / 后置条件（`docs/02` §32） | P14–P18 |
| `service.py` | `ExecutionService`（`docs/07` §9 的 15 步主干） | P36 |
| `confirmation.py` | Confirmation Token（`docs/07` §8.4） | P14–P18 |

顺序红线（`docs/02` §13 / §30）：`Schema Validation` **先于** `Engineering Validation`
（结构合法才做工程语义校验）；本批只落地前者。

分层红线（`docs/07` §14.1 / §2.2）：本包只依赖标准库、`jsonschema` 与 `app.domain`；
**不得**依赖 `app.infrastructure` / `app.interfaces`，也不得出现任何厂商专属内容。
"""

from __future__ import annotations

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
    "DEFAULT_DIALECT",
    "DRAFT7_URI",
    "SCHEMA_2020_12_URI",
    "SUPPORTED_DIALECTS",
    "SchemaEngine",
    "SchemaLookup",
    "dialect_of",
    "validator_for",
]
