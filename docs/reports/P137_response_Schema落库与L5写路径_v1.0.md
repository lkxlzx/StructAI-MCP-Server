# P137 response Schema 落库与 L5 写路径报告 v1.0

> 本批 = `docs/08` §3 的 **P137**（`docs/07` §12.2 的 MIDAS 批次）。
> 结论一句话：**P137a / P137b 已落地并可复算（CI 可跑）**；
> **P137c（真实 L5 写路径）未执行** —— 缺专用测试项目声明，用例 `pytest.skip`，**不**伪造。

## 1. 口径

| 项 | 值 |
| --- | --- |
| 权威数据源 | `registry/`（`registry/README.md`；本批**一行未改**） |
| 判定点 | `app/infrastructure/adapters/midas/live.py` 的 `seven_and_verdict` / `registry_evidence`（**唯一**） |
| 落库 | `app/infrastructure/adapters/midas/import_registry.py`（`MidasRegistryImporter`） |
| 版本区间 / 产品 | `2025-2026` / `CIVIL NX`（Manifest 口径；数据侧产品键 `CIVIL_NX` / `GEN_NX` / `CIVIL_DESIGNER`） |
| 环境 | `.venv`（Python 3.14.5，`docs/02` §136）：`$env:PATH = "G:\MMCP\.venv\Scripts;$env:PATH"` |

## 2. P137a —— response 方向 Schema 落库（R87 的收口）

| 表 | 改前 | 改后 | 依据 |
| --- | --- | --- | --- |
| `midas_api_schemas` | **615** 行（仅 `direction = "request"`） | **854** 行 = 请求 **615** + 响应 **239** | 数据侧同一份 Schema 文件里的 `response` 块（`registry/README.md` §2.2） |
| `midas_api_endpoints.response_schema_id` | 全 `None` | 已覆盖端点的行**回填**响应方向 Schema 行 id | `docs/04` §11 |
| `midas_api_mappings.response_schema` | 全 `None` | 同上（**存 Schema 行的 id**，与 `request_schema` 同口径） | `docs/04` §17 |
| `midas_api_sources` | **10** 行 | **11** 行（新增 `l4_measured_envelope`） | `response.source`（生成器固定取值） |

- URI 模板：`midas://<product_lower>/<code_lower>/response/v1`
  （`DB.NODE` → `midas://civil/db/node/response/v1`）；**请求方向模板一字未改**。
- `schema_json` **原样**登记（请求方向取文件 `schema`，响应方向取 `response.schema`）；
  未声明 `response` 块 / 取不到本体 → **不**建行（**不**臆造）。
- `DB.MBTP`：请求方向的 `schema` 仍是**非法 JSON 字符串**（R19）→ 仍**没有**请求方向行；
  其 `response` 块是合法对象 → 响应方向**如实**登记（故 854 = 615 + 239）。
- **幂等**：连跑两次第二次 `inserted` 全 0，两个方向的行数逐条不变。

## 3. P137b —— 7 项 AND 只做如实报告（R78 / R87）

`ImportReport.seven_and`（`SevenAndReport`）汇总**同一判定点**的结论；CI 层（无 L4 / L5 结论）：

| 判定项 | 满足数（/ 636） |
| --- | --- |
| `official_endpoint_confirmed` | 636 |
| `http_method_confirmed` | 635（`DB.SWIND` 无任何方法，R9） |
| `request_schema_confirmed` | **615** |
| `response_schema_confirmed` | **239** |
| `product_scope_confirmed` | 636 |
| `version_range_confirmed` | 636 |
| `live_contract_test_passed` | **0**（CI 层无实测 → **如实**为假） |

→ `verdicts = {VERIFIED: 0, PARTIAL: 636}`。显式传入 L4 结论（`seven_and_report(..., live_outcomes=...)`）时，
同一判定点给出 **238** `VERIFIED` + `DB.MBTP` **唯一**例外（缺 `request_schema_confirmed`，R19）。

**纪律（可执行断言）**：写入 L1 记录后再导入，端点 `verification_status` 与报告**逐条不变**；
端点行的状态仍**只**由 `availability` 机械映射（`docs/07` §7.2）。

## 4. 真实 L5 写路径（P137c）：**未执行**，如实标注

- 条件：`MIDAS_LIVE_L4=1` + `MIDAS_LIVE_PROJECT=<专用测试项目标识>` + `MIDAS_BASE_URL` + `MIDAS_MAPI_KEY`
  （`docs/04` §72 四要素）。
- 本机**未**声明专用测试项目 → `tests/test_midas_registry_p137.py` 的 P137c 用例 `pytest.skip`
  （**不**失败、**不**伪造）；缺声明时 `MidasLiveWriteProbe` 仍 `STRUCTAI-3000 dedicated_test_project_not_declared`
  且**零** transport 调用（P135 的离线断言继续有效）。
- 写路径实测覆盖仍 **11 / 369**（R4 / R14 未收口）。
- 纪律：**只**碰自己创建的编号；`DELETE` **必带**路径 key；绝不触碰生产项目。

## 5. 数据侧可复算（本批**未**改 `registry/**`）

```text
python registry/tools/sync_manifest.py             -> 636 个端点，字段不一致 = 0
python registry/tools/sync_response_schemas.py     -> 已实测端点 245，补 response 块 = 0（无差异）
```

（245 = 239 个有 Schema 文件 + 6 个尚无 Schema 文件：`DB.LCOM` / `OPE.PROJECTSTATUS` /
`OPE.SECTPROP` / `OPE.STORY_IRR_PARAM` / `OPE.STORY_PARAM` / `VIEW.SELECT`。）

## 6. 验收门槛（命令 + 结果）

```text
ruff check app tests                      -> All checks passed!
ruff format --check app tests             -> 212 files already formatted
mypy app                                  -> Success: no issues found in 183 source files
python -m pytest -q                       -> 920 passed, 3 skipped
python -m app.main（未配备 / 已配备）      -> 退出码 0，stdout 0 字节（已配备含 registry ready）
Base.metadata.create_all + inspect        -> 24 张表；SELECT 1 -> 1
厂商名（各自子包之外）/ STRUCTAI 码数      -> 0 处 / 恰好 20 码
commit() / rollback()                     -> 仅 app/infrastructure/database/unit_of_work.py
```

> 3 skipped = P134 的 2 项（L4 / L5 真实实例）+ 本批 P137c 的 1 项（真实 L5 写路径）。
> 1 条 `PytestUnhandledThreadExceptionWarning`（aiosqlite 线程清理）**不**来自本批文件
> —— 单跑 `tests/test_midas_p119_p123.py` + `tests/test_midas_registry_p137.py` 无该 warning。

## 7. 产出

| 文件 | 说明 |
| --- | --- |
| `app/infrastructure/adapters/midas/import_registry.py` | 两个方向落库 + 回填 + `SevenAndReport` / `seven_and_report` |
| `app/infrastructure/adapters/midas/__init__.py` | 导出 `SevenAndReport` / `seven_and_report` |
| `tests/test_midas_registry_p137.py` | **11** 项（P137a 6 / P137b 4 / P137c 1，含 1 项可跳过） |
| `tests/test_midas_p119_p123.py` | 615 → **615 + 239**（逐条更新，**不**放宽） |
| `registry/README.md` §2.2 | 落库口径（数据侧未改） |
| `docs/07` §4.4 / §7.2 / §15.5 / §16 | 实测导入结果 · 两个方向的映射规则 · 批次 23 · **R94** 与 R4 / R14 / R85 / R87 / R90 回填 |

## 8. 下一步（归下一批）

1. **R19 / R5 数据侧缺陷收口**（CI 可跑）：`DB.MBTP` 的请求方向 `schema` 修正为对象
   （615 → 616）、`DESIGN.SRC.AIK-SRC2K.{MATD,MCRD,MRBD}` / `OPE.EDMP` 补成合法 Schema
   （`check_schema` 的 4 个失败 → 0）、**20** 个无 Schema 端点补齐（取不到则如实留缺）。
2. **真实 L5 写路径实测**（需专用测试项目声明）：就绪后跑 P137c 用例，收口 R4 / R14 的写路径覆盖。
3. `DB.SPAN` 的 `GEN_NX` 是否摘除（R85 的遗留裁决）。
