# P149-C —— 只读 L4 收口 `availability` 与写路径解锁 v1.0

> 批次：**P149-C** · 实例：`gen-local`（GEN NX，`http://localhost:3030/gen`）·
> 专用空项目声明：`MIDAS_LIVE_PROJECT=p149c-gen-blank-dev-project` · 产品：`MIDAS_LIVE_PRODUCT=GEN_NX`
> 提交：见 `docs/08` §3。

## 0. 一句话结论

把 **R111** 的恢复条件**落地**：先用**只读** L4 实测（零副作用）收口 `availability`（**49/49** 逐条
「响应顶层键 == `read_root`」证实），再用**分块**写路径实测（3 块 20 / 20 / 9，块间只读健康检查）
取得结论 —— **2** `PASSED` · **47** `FAILED`（**全部** `400 software_api_error`）。
⇒ 覆盖率 **`70 / 633` → `72 / 633`**、`availability == verified` **247 → 296**、
**零残留**、**未崩溃**（P149-B2 的两次崩溃教训已被分块流程吸收）。

| 结论 | 条数 | 处置 |
| --- | --- | --- |
| 只读 L4：`read_root` 逐条证实 | **49** | `availability: untested → verified` + `verified_on: ["gen-local"]`（**只升不降**） |
| 写路径三步链 **`PASSED`** | **2** | 模板**保留** ⇒ 覆盖率分子 **70 → 72** |
| 写路径 **`400 software_api_error`** | **47** | 留缺（**R110**，模板**撤**） |
| 残留 / 崩溃 | **0 / 0** | 跑前 == 跑后（哨兵 + 本批 `DB.*` 端点**全空**） |

## 1. 为什么卡在 `availability`（闸门的精确判据）

写路径三步链的**第 1 步**是只读 `LIST`，而 `client.guard_verified()` 要求
`verification_status == VERIFIED`，该状态**只**由 `availability` 机械映射（`docs/07` §7.2 / R78）——
`availability: untested` ⇒ `registry_mapping_not_verified` ⇒ 写路径**根本无法开始**。

而 `availability` 的**语义**是**实测可用性**：`registry/README.md` §4 ——
「`availability == verified`（**至少一个实例 GET 成功**）」。故恢复条件 = **只读**实测 + 据实收口
（P134 的 L4 口径：**响应顶层键 == `read_root`**）。

## 2. 数据侧产物（全部可复算）

| 产物 | 说明 |
| --- | --- |
| `registry/tools/sync_availability.py`（**新**） | `--probe`（**只发 GET**）/ `--write`（**只升不降**）/ `--check`；证据 = `registry/live/live_read_probe.json` |
| `registry/live/live_read_probe.json`（**新**） | **只读** L4 证据：**49** 条（uri / read_root / status / top_keys / verdict），**不含任何凭据** |
| `registry/live/write_batch_p149c.json`（**新**） | 解锁后的**分块**写路径实测：**49** 条四态 + 跑前 / 跑后残留核对 + `clean: true` |
| `registry/**/*.yaml`（**49** 个） | `availability: untested → verified` + `verified_on: ["gen-local"]`（一行替换 + 一行插入，其余逐字节不变） |
| `registry/manifest.json` | 重派生（`sync_manifest.py --write`；字段差异 **98** 处 = 49 × 2） |
| `registry/schema/**`（**49** 个） | `sync_response_schemas.py --write` **只追加** `response` 块（`l4_measured_envelope`；+784 行） |
| `tests/test_midas_availability_p149c.py`（**新**，7 项） | 工具复算 / 读映射逐条 / 只升不降 / 分块实测如实 / 留缺与逐字节 / 级联 / 不泄密 |

## 3. 只读 L4 实测（**零副作用**）

- **范围**：`availability != verified` ∧ 有 `GET` ∧ 有 `read_root` ∧ 已启用 —— 本次只跑
  R111 记录的 **49** 个（`--only`）；其余 **317** 个未验证的只读端点可用**同一工具**后续扫。
- **结果**：**49 / 49** `HTTP 200` 且**响应顶层键 == `read_root`**（全部 `PARTIAL` —— 块为空，
  空项目下的**正常形态**，与 P134 的 166 个 `PARTIAL` 同口径）。
- **收口**：**只升不降** —— 只把 `untested` 升为 `verified`；`unverified`（实测不可用）与
  `unavailable_on` **一行未动**。

## 4. 解锁后的分块写路径实测（真实 L5）

- **跑前只读核对**：哨兵（4 默认 + `DB.STLD` / `DB.FBLD` / `DB.BMLD`）+ 本批 `DB.*` 端点 ——
  **全空、0 不可读** ⇒ 空项目闸门放行。
- **分块**：**3** 块（20 / 20 / 9），**块间只读健康检查** `GET /DB/NODE`；**没有**崩溃。
- **`PASSED` = 2**：`DESIGN.RC.KDS-41-20-2022.WMAK` · `DESIGN.SRC.AIK-SRC2K.DSRC`
  （三步链全成立：创建 → 读回 → 按路径 key 删除；请求体**逐字节**等于数据侧模板 `body`）。
- **`FAILED` = 47**：**全部** `400 software_api_error`（手册示例被本 build 拒绝 ⇒ **R110**，模板撤）。
- **跑后只读核对**：与跑前**逐条相同**（全空）⇒ **零残留**。

## 5. 计数（可复算）

| 指标 | P149-B2 | **P149-C** |
| --- | --- | --- |
| 覆盖率（分子 / 分母） | `70 / 633` | **`72 / 633`** |
| `model_write_ratio` | `70 / 434` | **`72 / 434`** |
| 候选集（GEN NX / CIVIL NX / CD） | 70 / 60 / 0 | **72 / 62 / 0** |
| blocked（同上三产品） | 503 / 440 / 31 | **501 / 438 / 31** |
| 模板条数 / 复算 body 数 | 69 / 113 | **71 / 115** |
| `availability == verified` | 247 | **296** |
| 响应方向 Schema 行数 | 241 | **290**（`sync_response_schemas.py` 派生） |
| 留缺账本 | 180 | **178**（R110 **164** · R101–R105 **11** · R109 **2** · R113 **1**） |

## 6. 裁决状态

- **R111 闭环**：49 个「因读映射未验证而无法进写路径」的端点**全部取得结论**
  （2 `PASSED` + 47 `400`），且恢复路径已**工具化**（`sync_availability.py`，可复算）。
- **无新裁决**：47 条失败沿用 **R110**（本 build 原生拒绝），与 R101–R105 同形；成因**不是**数据缺陷
  （字段全在数据侧请求 Schema 里声明，`check_write_templates.py` 复算 **0** 错）。
- ⚠️ 仍开放：**R106**（`POST.TABLE.*` **197**）· **R107**（无 `DELETE` 单例表 **14**）·
  **R112**（`request_schema()` 的「按端点代码键控」形状仍空判）· **R113**（`DB.NSPR` 使实例崩溃，
  成因需 MIDAS 侧排查）· 其余 **317** 个未验证只读端点（可用 `sync_availability.py --probe` 扫）。

## 7. 闸门

| 闸门 | 结果 |
| --- | --- |
| `sync_availability.py --check` | **✅**（YAML == 只读证据） |
| `sync_write_templates.py --check` · `check_write_templates.py` | **✅**（71 模板 / 115 body / 0 错） |
| `sync_manifest.py`（预演） | **✅** 字段差异 **0** |
| `sync_response_schemas.py`（预演） | **✅** 仅剩 4 个「无 Schema 文件」跳过 |
| `fix_schema_defects.py --check` · `sync_request_schemas.py --check` · `sync_endpoint_methods.py --check` | **✅** 全绿 |
| `pytest -q` | 见 `docs/08` §3（本批新增 7 + 2 组计数同步） |
| 红线（厂商名 / 分层 / 模板取值 / 依赖 / 9 Tool Contract） | 全 0（`app/**` 一行未改） |
