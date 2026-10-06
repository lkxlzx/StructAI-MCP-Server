"""Interface · MCP · 9 个 Tool（`docs/02` §53 / §74；`docs/07` §5.1 / §12 P37–P39）。

`docs/02` §74 的目录（`interfaces/mcp/tools/`）与 `docs/07` §3.3 的冻结结构逐条一致：
`base.py` ＋ 9 个 Tool 模块。本包是它们的**唯一装配入口**（`build_tools`），
使「恰好 9 个」成为**结构性**事实而不是纪律性约定。

⚠️ 9 个 Tool 都是 **thin wrapper**（`docs/02` §53）：只做「参数 → `ExecutionService`」，
**不**承载工程语义、**不**重复 26 步管线中的任何一步、**不**判断权限 / Schema / Capability。
9 Tool Contract **不得修改**（`docs/07` §14.5）—— 新增软件只允许新增 Adapter + Mapping +
API Registry 数据。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from app.application.execution.service import ExecutionService
from app.interfaces.mcp.tools.base import BaseEngineeringTool, ToolRequest
from app.interfaces.mcp.tools.engineering_analysis import EngineeringAnalysisTool
from app.interfaces.mcp.tools.engineering_design import EngineeringDesignTool
from app.interfaces.mcp.tools.engineering_doc import EngineeringDocTool
from app.interfaces.mcp.tools.engineering_model_assign import EngineeringModelAssignTool
from app.interfaces.mcp.tools.engineering_model_build import EngineeringModelBuildTool
from app.interfaces.mcp.tools.engineering_model_delete import EngineeringModelDeleteTool
from app.interfaces.mcp.tools.engineering_model_query import EngineeringModelQueryTool
from app.interfaces.mcp.tools.engineering_result import EngineeringResultTool
from app.interfaces.mcp.tools.engineering_view import EngineeringViewTool

__all__ = [
    "TOOL_CLASSES",
    "TOOL_NAMES",
    "BaseEngineeringTool",
    "EngineeringAnalysisTool",
    "EngineeringDesignTool",
    "EngineeringDocTool",
    "EngineeringModelAssignTool",
    "EngineeringModelBuildTool",
    "EngineeringModelDeleteTool",
    "EngineeringModelQueryTool",
    "EngineeringResultTool",
    "EngineeringViewTool",
    "ToolRequest",
    "build_tools",
]

TOOL_NAMES: Final[tuple[str, ...]] = (
    "engineering_doc",
    "engineering_model_query",
    "engineering_model_assign",
    "engineering_model_delete",
    "engineering_model_build",
    "engineering_view",
    "engineering_result",
    "engineering_design",
    "engineering_analysis",
)
"""**恰好 9 个** MCP Tool 名（`docs/02` §53 / §74 的顺序逐条照抄；`docs/07` §5.1）。

验收测试逐条断言：数量 = 9、与 `docs/02` §53 的清单一致、且每个都真的可注册 + 可分发。
"""

TOOL_CLASSES: Final[Mapping[str, type[BaseEngineeringTool]]] = {
    "engineering_doc": EngineeringDocTool,
    "engineering_model_query": EngineeringModelQueryTool,
    "engineering_model_assign": EngineeringModelAssignTool,
    "engineering_model_delete": EngineeringModelDeleteTool,
    "engineering_model_build": EngineeringModelBuildTool,
    "engineering_view": EngineeringViewTool,
    "engineering_result": EngineeringResultTool,
    "engineering_design": EngineeringDesignTool,
    "engineering_analysis": EngineeringAnalysisTool,
}
"""工具名 → Tool 类（键集合必须**恰好**等于 `TOOL_NAMES`，装配期自检）。"""


def build_tools(execution: ExecutionService) -> tuple[BaseEngineeringTool, ...]:
    """装配 9 个 Tool（`docs/02` §53 / §74；每个都注入**同一个**会话级执行服务）。

    Args:
        execution: 会话级 `ExecutionService`（`app/container.py` 的
            `ExecutionServiceFactory.create()` 产出；Tool **不**自建依赖）。

    Returns:
        按 `TOOL_NAMES` 顺序排列的 9 个 Tool 实例。

    Raises:
        AssertionError: `TOOL_CLASSES` 的键集合与 `TOOL_NAMES` 不一致（装配错误 ——
            「声明了 9 个却只实现 8 个」必须在装配期就炸掉）。
    """
    missing = sorted(set(TOOL_NAMES) - set(TOOL_CLASSES))
    unexpected = sorted(set(TOOL_CLASSES) - set(TOOL_NAMES))
    if missing or unexpected:
        raise AssertionError(f"tool registry mismatch: missing={missing} unexpected={unexpected}")
    return tuple(TOOL_CLASSES[name](execution) for name in TOOL_NAMES)


def tool_names_of(tools: Sequence[BaseEngineeringTool]) -> tuple[str, ...]:
    """一组 Tool 的名字（保持传入顺序；供装配自检与验收断言）。"""
    return tuple(tool.name for tool in tools)
