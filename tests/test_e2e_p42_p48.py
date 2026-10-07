"""P42–P48 验收 · 第 7 类：**E2E**（Generic MCP Client 经 STDIO 与 HTTP）＋ 两条定义。

门槛（`docs/08` §4 的本批提示词；`docs/07` §13.1 / §13.2 / §13.5；`docs/02` §97 / §125）
------------------------------------------------------------------------------
① E2E：Generic MCP Client 经**真实子进程** `python -m app.main --transport stdio` 与
   经**真实 uvicorn** `--transport http` 均能 `initialize` → `tools/list`（**恰好 9**）
   → `tools/call`（统一信封）；stdout **只**放协议帧（日志一律 stderr）。
② `docs/07` §13.2 **Definition of Core Alpha**：`MCP Client → 9 Tools → Execution
   Pipeline → RBAC → Capability → Lock → Task Engine → Mock Adapter → Canonical Model
   → Result` 全链路运行，逐跳留下可执行证据。
③ `docs/07` §13.1 **Definition of Source Complete** 的 **11** 项逐条给出**可执行**判定
   （import 可解析 / mypy / ruff / 四类测试可收集 / MCP Client 可连接 / 9 Tool 可发现 /
   Mock Adapter 可执行）。
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

import p42_p48_support as support
from app.infrastructure.adapters.mock.adapter import (
    MOCK_CAPABILITIES,
    MOCK_SUPPORTED_OPERATIONS,
    MockAdapter,
)
from app.infrastructure.database.unit_of_work import UnitOfWork
from app.interfaces.mcp import TOOL_NAMES, MCPServer, build_mcp_server
from app.interfaces.mcp.transport import MCPTransport, build_protocol_server
from app.interfaces.mcp.transport.http import DEFAULT_HTTP_PATH

LAYER_FILES: tuple[str, ...] = (
    "tests/test_unit_p42_p48.py",
    "tests/test_contract_p42_p48.py",
    "tests/test_integration_p42_p48.py",
    "tests/test_security_p42_p48.py",
    "tests/test_concurrency_p42_p48.py",
    "tests/test_recovery_p42_p48.py",
    "tests/test_e2e_p42_p48.py",
)
"""七类测试的落点（`docs/07` §12 P42–P48 的顺序）。"""


async def _session_token(settings: Any) -> str:
    """在测试进程里签发一个真实会话 Token（P10–P13 的登录链）。"""
    from app.container import build_execution_runtime
    from app.infrastructure.database.session import create_session_factory
    from app.infrastructure.registry.capability_registry import CapabilityRegistry
    from app.infrastructure.registry.operation_registry import OperationRegistry

    engine = support.engine_for(settings)
    factory = create_session_factory(engine)
    runtime = build_execution_runtime(
        settings,
        operation_registry=await OperationRegistry.load(engine, factory),
        capability_registry=await CapabilityRegistry.load(engine, factory),
    )
    runtime.session_factory = factory
    async with UnitOfWork.from_session_factory(factory) as uow:
        security = runtime.execution.security_for(uow.session)
        result = await security.guard.login(support.ADMIN_USERNAME, support.TEST_PASSWORD)
    await engine.dispose()
    return result.access_token


# ===== ① STDIO E2E（`docs/03` §40–§43 / §76；`docs/02` §97）=====


async def test_stdio_end_to_end_with_a_generic_mcp_client(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/03` §76）：真实子进程 STDIO 上 `connect → list_tools → call_tool`。"""
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    settings = await support.prepare_database(tmp_path, monkeypatch, name="p42_e2e_stdio.db")
    ids = await support.database_ids(settings)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.main", "--transport", "stdio"],
        env={
            "DATABASE_URL": settings.database_url,
            "ARTIFACT_ROOT": settings.artifact_root,
            "LOG_LEVEL": "WARNING",
        },
        cwd=str(support.REPO_ROOT),
    )
    context = support.client_context(ids)
    async with stdio_client(parameters) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = tuple(tool.name for tool in listed.tools)
            assert len(names) == 9, names
            assert sorted(names) == sorted(support.TOOL_NAMES_SPEC)

            first = await session.call_tool(
                "engineering_model_query",
                support.arguments("MODEL.NODE.QUERY", context=context),
            )
            assert first.is_error is False
            envelope = first.structured_content
            assert isinstance(envelope, Mapping)
            assert set(envelope) == set(support.RESPONSE_KEYS_SPEC)
            assert envelope["success"] is True, envelope.get("errors")
            assert envelope["request_id"].startswith("req_")
            assert envelope["trace_id"].startswith("trace_")

            second = await session.call_tool(
                "engineering_model_query",
                support.arguments("MODEL.NODE.QUERY", context=context),
            )
            assert second.structured_content["request_id"] != envelope["request_id"], (
                "每次请求的关联 id 都由 Core 生成（docs/02 §5）"
            )

            refused = await session.call_tool(
                "engineering_model_build",
                support.arguments(
                    "BUILD.COLUMN",
                    parameters=support.BUILD_COLUMN_PARAMETERS,
                    context=context,
                ),
            )
            assert refused.is_error is True
            assert refused.structured_content["errors"][0]["code"] == (
                support.CONFIRMATION_REQUIRED_CODE
            )

            unknown = await session.call_tool("engineering_nope", {"operation": "MODEL.NODE.QUERY"})
            assert unknown.structured_content["errors"][0]["code"] == support.PROTOCOL_ERROR_CODE
            assert unknown.structured_content["errors"][0]["details"]["reason"] == (
                support.UNKNOWN_TOOL_REASON
            )


# ===== ② Streamable HTTP E2E（`docs/03` §44–§59 / §77；`docs/02` §98）=====


async def test_http_end_to_end_with_a_generic_mcp_client(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ①（`docs/03` §77）：真实 uvicorn 上鉴权 + `initialize → tools/list → call_tool`。"""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    settings = await support.prepare_database(tmp_path, monkeypatch, name="p42_e2e_http.db")
    ids = await support.database_ids(settings)
    token = await _session_token(settings)
    port = support.free_port()
    environment = {
        **os.environ,
        "DATABASE_URL": settings.database_url,
        "ARTIFACT_ROOT": settings.artifact_root,
        "LOG_LEVEL": "WARNING",
        "HOST": "127.0.0.1",
        "PORT": str(port),
        support.ADMIN_PASSWORD_ENV: support.TEST_PASSWORD,
    }
    process = subprocess.Popen(  # noqa: S603, ASYNC220
        [sys.executable, "-m", "app.main", "--transport", "http"],
        cwd=support.REPO_ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    try:
        await support.wait_for_port(port)
        probe = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        accept = {"Accept": "application/json, text/event-stream"}
        async with httpx.AsyncClient(timeout=30.0) as anonymous:
            unauthorized = await anonymous.post(
                f"http://127.0.0.1:{port}{DEFAULT_HTTP_PATH}", json=probe, headers=accept
            )
            assert unauthorized.status_code in {401, 403}
            assert "unauthorized" in unauthorized.text
        headers = {"Authorization": f"Bearer {token}"}
        async with streamable_http_client(
            f"http://127.0.0.1:{port}{DEFAULT_HTTP_PATH}",
            http_client=httpx.AsyncClient(headers=headers, timeout=60.0),
        ) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                listed = await session.list_tools()
                names = tuple(tool.name for tool in listed.tools)
                assert len(names) == 9, names
                assert sorted(names) == sorted(support.TOOL_NAMES_SPEC)
                result = await session.call_tool(
                    "engineering_model_query",
                    support.arguments("MODEL.NODE.QUERY", context=support.client_context(ids)),
                )
                assert result.is_error is False
                envelope = result.structured_content
                assert isinstance(envelope, Mapping)
                assert envelope["success"] is True, envelope.get("errors")
                assert envelope["request_id"].startswith("req_")
    finally:
        process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:  # pragma: no cover - 兜底
            process.kill()
        stdout = process.stdout.read() if process.stdout else ""
        stderr = process.stderr.read() if process.stderr else ""
        assert stdout == "", "stdout 只放协议帧（docs/03 §42）"
        assert "structai" in stderr


# ===== ③ Definition of Core Alpha（`docs/07` §13.2；`docs/02` §127）=====


async def test_definition_of_core_alpha_chain_runs_every_hop(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ②（`docs/07` §13.2）：`MCP Client → 9 Tools → Pipeline → RBAC → Capability
    → Lock → Task Engine → Mock Adapter → Canonical Model → Result` 全链路运行。"""
    runtime, factory, ids = await support.seeded_runtime(
        tmp_path, monkeypatch, name="p42_e2e_core_alpha.db"
    )
    identity = support.identity_context(ids)
    context = support.client_context(ids)
    async with UnitOfWork.from_session_factory(factory) as uow:
        bundle = runtime.execution.create(uow.session)
        server = build_mcp_server(bundle.service)
        assert isinstance(server, MCPServer)
        assert len(server.list_tools()) == 9

        resolved = await bundle.resolver.resolve(
            server.contexts.create(identity, client_context=context).execution
        )
        assert resolved is not None
        token = runtime.confirmation.issue(
            user_id=ids["user_id"],
            tenant_id=ids["tenant_id"],
            operation="BUILD.COLUMN",
            resource_id=resolved.resource_id,
        ).token
        built = await server.handle(
            "engineering_model_build",
            support.arguments(
                "BUILD.COLUMN",
                parameters=support.BUILD_COLUMN_PARAMETERS,
                context=context,
                confirmation_token=token,
            ),
            identity=identity,
        )
        assert built.success is True, built.errors
        assert built.metadata["mcp_steps"] == list(support.MCP_STEPS_SPEC)
        assert built.execution["mode"] == "ASYNC"
        assert "Effective Permission" in built.execution["steps"], "RBAC 闸门"
        assert "Capability Check" in built.execution["steps"], "Capability 闸门"
        assert "Task / Transaction" in built.execution["steps"]
        assert "Adapter" not in built.execution["steps"], "Adapter 在 Worker 里跑（docs/02 §91）"

        task_id = built.execution["task_id"]
        assert isinstance(task_id, str)
        record = await bundle.engine.run_task(task_id)
        assert str(record.status) == "COMPLETED", record.status
        assert record.started_at is not None
        assert await bundle.pipeline.locks.held_count() == 0, "完成后释放资源锁"

        column = json.loads(record.result_json or "{}")
        assert set(column) == {"node_ids", "element_ids"}, "Canonical Model"
        nodes = await server.handle(
            "engineering_model_query",
            support.arguments("MODEL.NODE.QUERY", context=context),
            identity=identity,
        )
        assert nodes.success is True, nodes.errors
        assert nodes.execution["steps"] == list(support.PIPELINE_ORDER_SPEC[4:]), "执行链 22 步"
        assert "Adapter" in nodes.execution["steps"]
        assert nodes.data is not None
        assert {item["id"] for item in nodes.data["items"]} == set(column["node_ids"]), "Result"
        assert bundle.audit.records_written() >= 1, "Audit"
    assert await runtime.outbox.count() >= 1, "Event"


# ===== ④ Definition of Source Complete（`docs/07` §13.1；`docs/02` §126）=====


def _collect_tests(path: Path) -> list[str]:
    """文件里的 `test_*` 函数名（AST 级可执行判定，**不**靠人工检查）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


async def test_definition_of_source_complete_items_are_executable(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """门槛 ③（`docs/02` §126；`docs/07` §13.1）：**11** 项逐条给出可执行判定。"""
    from app.infrastructure.registry.operation_registry import OPERATION_PROFILES

    # ① 所有 import 可解析
    modules: list[str] = []
    for path in support.app_module_paths():
        relative = path.relative_to(support.REPO_ROOT).with_suffix("")
        parts = list(relative.parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        modules.append(".".join(parts))
    assert len(modules) >= 100, len(modules)
    for name in sorted(modules):
        importlib.import_module(name)

    # ② 类型检查通过（mypy）
    mypy = subprocess.run(  # noqa: S603, ASYNC221
        [sys.executable, "-m", "mypy", "app"],
        cwd=support.REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=1800,
    )
    assert mypy.returncode == 0, mypy.stdout[-2000:]

    # ③ Ruff 通过
    lint = subprocess.run(  # noqa: S603, ASYNC221
        [sys.executable, "-m", "ruff", "check", "app", "tests"],
        cwd=support.REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )
    assert lint.returncode == 0, lint.stdout[-2000:]
    formatted = subprocess.run(  # noqa: S603, ASYNC221
        [sys.executable, "-m", "ruff", "format", "--check", "app", "tests"],
        cwd=support.REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )
    assert formatted.returncode == 0, formatted.stdout[-2000:]

    # ④–⑦ 七类测试可收集且逐类有测试（Unit / Contract / Integration / Security /
    #       Concurrency / Recovery / E2E）
    collected = subprocess.run(  # noqa: S603, ASYNC221
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *LAYER_FILES],
        cwd=support.REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=600,
    )
    assert collected.returncode == 0, collected.stdout[-2000:]
    total = 0
    for name in LAYER_FILES:
        tests = _collect_tests(support.REPO_ROOT / name)
        assert tests, name
        total += len(tests)
        assert Path(name).name in collected.stdout, name
    assert total >= 76, total

    # ⑧ MCP Client 可连接（未配备 / 未接客户端两种情形都干净退出且 stdout 0 字节）
    offline_url = f"sqlite+aiosqlite:///{(tmp_path / 'p42_offline.db').as_posix()}"
    offline = support.run_main(database_url=offline_url)
    assert offline.returncode == 0, offline.stderr
    assert offline.stdout == ""
    provisioned = await support.prepare_database(tmp_path, monkeypatch, name="p42_stdio.db")
    stdio = support.run_main(
        "--transport",
        "stdio",
        database_url=provisioned.database_url,
        env={"LOG_LEVEL": "WARNING", "ARTIFACT_ROOT": provisioned.artifact_root},
        stdin_text="",
    )
    assert stdio.returncode == 0, stdio.stderr
    assert stdio.stdout == ""

    # ⑨ 9 Tool 可发现
    assert len(TOOL_NAMES) == 9
    assert tuple(TOOL_NAMES) == support.TOOL_NAMES_SPEC
    assert callable(build_protocol_server)
    assert all(hasattr(MCPTransport, name) for name in ("start", "receive", "send", "close"))

    # ⑩ Mock Adapter 可执行
    adapter = MockAdapter()
    supported = adapter.supported_operations()
    assert "BUILD.COLUMN" in supported
    assert MOCK_SUPPORTED_OPERATIONS == tuple(supported)
    assert set(supported) <= set(OPERATION_PROFILES)
    assert "MODEL.NODE.WRITE" in MOCK_CAPABILITIES

    # ⑪ 七类测试逐类可执行 —— 由本批 `pytest` 门槛（`docs/08` §4）逐类运行，见上方收集判定
