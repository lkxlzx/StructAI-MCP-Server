# StructAI｜MIDAS MCP Registry 真实实例 Live 冒烟测试报告 V1.0

> ⚠️ **非规范性文档（NON-NORMATIVE）** —— 本文件已归档至 `archive/legacy_v1/`，
> 属 StructAI 早期（V1）规范草案 / 实测记录，**不作为开发依据，不作为准则**。
> 开发唯一依据：`docs/01`–`docs/06`（V2 规范）· `docs/07`（开发方案与任务续接）· `registry/`（机器可读端点注册表）。

> 配套文档：《StructAI MIDAS MCP 完整开发文档 V1.0》《GEN NX API 实测补充文档 V1.0》《CIVIL NX API 实测补充文档 V1.0》
>
> 测试对象：`G:\MMCP\registry\`（634 Endpoint 定义 + 570 JSON Schema）与 `G:\MMCP\examples\` 参考客户端
>
> 本报告**只记录实测结果**，不含任何修复动作。修复项汇总见《StructAI_MIDAS_MCP_统一修复计划_v1.0.md》。

---

## 1. 测试环境与方法

| 项 | 值 |
| --- | --- |
| Base URL | `http://localhost:3030/gen`（midas GEN NX 实例） |
| 已加载项目 | `portrait_truss_80m`（80 m 桁架） |
| 项目规模（实例回读） | 节点 3326 / 单元 6901 / 材料 1（Q355, STEEL） |
| 单位（实例回读） | FORCE=KN, DIST=M, HEAT=KJ, TEMPER=C |
| 凭据 | `MAPI-Key` **仅经环境变量传入**，未写入任何文件、报告或日志 |
| 调用方式 | `python smoke_test.py --live`（默认**只调 GET**，不修改模型） |
| 测试日期 | 2026-05-07 |

**范围约束**：本次只调 GET 端点。369 个不含 GET 的端点（含 POST 命名空间全部 199 个）未做 live 调用，以避免修改实例模型。

### 1.1 测试前修复的脚手架缺陷（3 项）

脚手架自身缺陷导致首轮 `live: 调用 0 次`，必须先修正才能取得有效数据。以下修改只涉及 `examples/` 下的参考实现，未改动 Registry 数据。

| # | 文件 | 缺陷 | 影响 | 处置 |
| --- | --- | --- | --- | --- |
| H1 | `smoke_test.py` `live_run()` | `"GET" not in [m.upper() for m in e["methods"]]` —— manifest 的 `methods` 是**字符串** `"POST, GET, PUT, DELETE"`，按字符迭代导致 GET 永不匹配 | live 调用恒为 0 | 新增 `parse_methods()` 统一解析 |
| H2 | `midas_client.py` `resolve()` / `call()` | 同一字符串迭代缺陷；且 `d["methods"][0]` 取到字符 `"P"` | 任何调用都会抛 `METHOD_NOT_ALLOWED` | 复用 `parse_methods()`；方法集为空时抛 `METHODS_UNKNOWN` |
| H3 | `midas_client.py` / `smoke_test.py` `parse_methods()` | 只按 `,` 切分，而 4 个 Registry 条目的 `methods` 用 `/` 分隔（见 §5.2） | 该 4 个端点被静默跳过 | 改为 `re.split(r"[,/\s]+", ...)` |

> 说明：H3 暴露的是 **Registry 数据本身的不一致**（见 §5.2），脚手架只是让它显形。

---

## 2. 测试结果总览

### 2.1 dry-run（不连 MIDAS 的结构校验）

| 口径 | 校验端点数 | 问题数 | 问题明细 |
| --- | --- | --- | --- |
| 全量 | 634 | 1 | `DB.SWIND` → `METHODS_UNKNOWN`（源手册确实未标注方法，预期内） |
| GEN_NX 子集 | 591 | 1 | 同上 |

结论：634 个 YAML 全部可解析、`tool_map` / `execution` / `products` 字段无缺失、`uri` 均以 `/` 开头、570 个 schema 文件引用全部存在。

### 2.2 live（真实调用）

| 口径 | 调用次数 | OK | 失败 | 成功率 |
| --- | --- | --- | --- | --- |
| **GEN_NX 子集**（Registry 声称支持 GEN_NX 的 591 个端点中，含 GET 的 253 个） | 253 | **217** | 36 | 85.8% |
| **全产品**（634 个端点中含 GET 的 265 个） | 265 | **219** | 46 | 82.6% |

**失败码分布**：全部 46 例均为 `HTTP_ERROR / HTTP 404`。**无** `AUTH_FAILED`、`CONNECTION_ERROR`、`EXCEPTION`、`METHOD_NOT_ALLOWED`、`PRODUCT_CAPABILITY_UNSUPPORTED` —— 说明鉴权、连通、URI 解析、方法校验链路全部正常，失败集中在「实例不注册该表」。

### 2.3 按命名空间分解（全产品口径）

| 命名空间 | 端点总数 | 含 GET | 实际调用 | OK | 失败 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| DB | 242 | 237 | 237 | 192 | 45 | 失败全部集中于 DB |
| DOC | 21 | 1 | 1 | 0 | 1 | 唯一含 GET 的 `DOC.UNIT` 属 CIVIL_DESIGNER |
| OPE | 34 | 4 | 4 | **4** | 0 | 全通过 |
| OPRT | 6 | 0 | 0 | 0 | 0 | 全为写方法，按约束跳过 |
| POST | 199 | 0 | 0 | 0 | 0 | 全为 POST，按约束跳过 |
| VIEW | 7 | 1 | 1 | **1** | 0 | 通过 |
| DESIGN | 125 | 22 | 22 | **22** | 0 | 路由连通性 100% 通过 |

### 2.4 方法集分布（规范化后，634 个端点）

| 方法集 | 数量 |
| --- | --- |
| POST（仅写） | 366 |
| POST+GET+PUT+DELETE | 205 |
| GET | 26 |
| GET+PUT | 13 |
| GET+PUT+DELETE | 9 |
| POST+GET+PUT | 5 |
| DELETE+GET+POST+PUT | 3 |
| PUT | 2 |
| GET+POST | 2 |
| GET+POST+DELETE | 1 |
| GET+POST+PUT | 1 |
| （空，`DB.SWIND`） | 1 |

### 2.5 响应体有效性抽样（确认 OK 非误判）

| 请求 | 状态 | 响应体（截断） |
| --- | --- | --- |
| `GET /DB/NODE` | 200 | `{"NODE":{"1":{"X":6.0,"Y":1.5,"Z":0.0},"2":{...}}}` |
| `GET /DB/MATL` | 200 | `{"MATL":{"1":{"TYPE":"STEEL","NAME":"Q355","DAMP_RAT":0.02,"PARAM":[{"ELAST":206000000.0,"POISN":0.3,...}]}}}` |
| `GET /DB/UNIT` | 200 | `{"UNIT":{"1":{"FORCE":"KN","DIST":"M","HEAT":"KJ","TEMPER":"C"}}}` |
| `GET /OPE/PROJECTSTATUS` | 200 | `{"PROJECTSTATUS":{"DATA":[["节点","3326","3326"],["单元","6901","6901"],...]}}` |
| `GET /OPE/SECTPROP` | 200 | `{"SECTPROP":{"2":{"HEAD":["Property","数值","单位"],"DATA":[["面积","0.003054","m2"],...]}}}` |
| `GET /VIEW/SELECT` | 200 | `{"SELECT":{"NODE_LIST":[],"ELEM_LIST":[]}}` |
| `GET /DESIGN/RC/DRC` | 200 | `{"DCON":{}}` |
| `GET /DESIGN/STEEL/DSTL` | 200 | `{"DSTL":{}}` |
| `GET /VIEW/CAPTURE` | **405** | 空体（该端点仅支持 POST，见 §6.2） |

结论：OK 判定可信，返回体为真实模型/结果数据。DESIGN 端点返回空对象属正常（未运行设计计算）。

### 2.6 其它实测事实

| 事实 | 证据 |
| --- | --- |
| 命名空间/URI **大小写不敏感** | `/db/NODE` 与 `/DB/NODE` 均返回 200 |
| 错误方法返回 **405** 而非 404 | `GET /VIEW/CAPTURE` → 405（Registry 中该端点仅 POST） |
| Schema 自省接口**仅对 DB 命名空间有效** | `/info/db/{CODE}` 可用；`/info/ope/{CODE}`、`/info/doc/{CODE}`、`/info/view/{CODE}`、`/info/oprt/{CODE}` **全部 404** |

---

## 3. 46 个失败的根因归因

失败清单见附件 `StructAI_MIDAS_MCP_Live冒烟失败清单_v1.0.csv`（46 行，含归因分组列）。

### A 组｜Hyper-S 求解器变体（21 个）—— 实例能力约束，非数据错误

`DB.ACTL-M1`、`BCGA-M1`、`BCGD-M1`、`EIGV-M1`、`EPMT-M1`、`HHCT-M1`、`IEHG-BEAM-M1`、`IEHG-GL-M1`、`IEHG-PSS-M1`、`IEHG-TRUSS-M1`、`IMFM-M1`、`MATL-M1`、`NLCT-M1`、`NLNK-M1`、`POGD-M1`、`POLC-M1`、`STCT-M1`、`STYP-M1`、`THGC-M1`、`THIS-M1`、`THOO-M1`

- 官方索引对这些 URI 标记上标 `ᴴˢ⁾`（Hyper-S 专属），URI 与标准版**并存**（`/db/STYP` 与 `/db/STYP-M1`）。
- 本实例运行标准求解器，故 404 属**预期行为**。
- 但 Registry **完全没有 `solver` 字段**（0/634），客户端无法在调用前拦截 → 见 §5.1。

### B 组｜Registry 声称 GEN_NX 可用、但实例不注册（15 个）—— **需裁决**

| Registry key | URI | 标题 | 官方 GEN 索引 |
| --- | --- | --- | --- |
| `DB.CAMB` | `/db/CAMB` | FCM Camber Control | ✅ 收录（Bridge Specialization Results） |
| `DB.CJFG` | `/db/CJFG` | Concurrent Joint Force Group | ✅ 收录（Moving Loads） |
| `DB.CMCS` | `/db/CMCS` | Camber for Construction Stage | ✅ 收录（Construction Stage Loads） |
| `DB.CRGR` | `/db/CRGR` | Concurrent Reaction Group | ✅ 收录（Moving Loads） |
| `DB.DYFG` | `/db/DYFG` | Railway Dynamic Factor | ✅ 收录（Moving Loads） |
| `DB.DYLA` | `/db/DYLA` | Dynamic Load Allowance | ✅ 收录（Moving Loads） |
| `DB.DYNF` | `/db/DYNF` | Railway Dynamic Factor by Element | ✅ 收录（Moving Loads） |
| `DB.EWSF` | `/db/EWSF` | Effective Width Scale Factor | ✅ 收录（Properties） |
| `DB.GCMB` | `/db/GCMB` | General Camber Control | ✅ 收录（Bridge Specialization Results） |
| `DB.GSBG` | `/db/GSBG` | Bridge Girder Diagrams | ✅ 收录（另有 `/ope/GSBG`） |
| `DB.PLCB` | `/db/PLCB` | Pre-composite Section | ✅ 收录（Miscellaneous Loads） |
| `DB.RCHK` | `/db/RCHK` | Rebar Input for Checking - Beam/Column | ✅ 收录（Design） |
| `DB.SPAN` | `/db/SPAN` | Span Information | ✅ 收录（Structure） |
| `DB.STRPSSM` | `/db/STRPSSM` | Section Manager - Stress Points | ✅ 收录（Properties） |
| `DB.WVLD` | `/db/WVLD` | Wave Loads | ✅ 收录（Miscellaneous Loads） |

**冲突点**：Registry 的 `products: [CIVIL_NX, GEN_NX]` 忠实于官方 GEN 索引，但实例 `/info/db/{CODE}` 与 `GET /db/{CODE}` 均为 404。

已排除的可能原因：
- ❌ URI 拼写/大小写问题 —— `/db/CAMB`、`/DB/CAMB`、`/db/camb` 全部 404，且其它同前缀端点正常。
- ❌ 项目未加载 —— 同一实例上 `/db/NODE`、`/db/MATL` 等 200。
- ❌ 鉴权/连通 —— 无任何 401/403/连接错误。

剩余两种解释，**需用户裁决**：
1. **版本差异**：实例版本早于手册收录版本；
2. **产品归属错误**：这些是 Civil NX 专属（桥梁/铁路/PSC/钢筋专项）表，官方索引在共享的 Civil/Gen NX 文档中一并列出，实际 GEN NX 不提供。

> 观察支持解释 2：该 15 个端点全部属桥梁/铁路/PSC/钢筋专项功能，且其中 `DB.SPAN` 在 CIVIL NX 补充手册中归类为「结构Structure / PSC桥梁」。

### C 组｜产品不匹配（10 个）—— 冒烟脚手架未按产品门控，属预期 404

| 归属产品 | 数量 | 端点 |
| --- | --- | --- |
| CIVIL_DESIGNER | 8 | `DB.BTCP`、`DB.CAPSIZE`、`DB.CWRC`、`DB.DCOD`、`DB.LCOM`、`DB.MODULE`、`DB.TRPT`、`DOC.UNIT` |
| CIVIL_NX | 2 | `DB.UFTR`、`DB.UTBL` |

全产品口径的冒烟未传 `--product`，因此把非 GEN 端点也发给了 GEN 实例。**GEN_NX 子集口径（253 次调用）中这 10 个不出现**，即产品门控在指定 `--product` 时有效。

---

## 4. 未覆盖范围（本次测试的边界）

| 未覆盖项 | 数量/说明 | 原因 |
| --- | --- | --- |
| 不含 GET 的端点 | 369 个（含 POST 命名空间全部 199 个） | 需写操作，按约束跳过 |
| DESIGN 端点的数据正确性 | 22 个仅验证路由连通（返回空对象） | 未在实例上运行设计计算 |
| WebSocket 长任务推送 | `open_ws()` 骨架未测 | 需触发长任务 |
| 无 JSON Schema 的端点 | 64 个（见 §5.4） | 源手册无 schema |
| 12 个模板占位用例 | 未纳入 `cases.json`（实测 `cases.json` 505 用例中 **0 个**含 `{占位符}`） | 已在生成阶段排除，非缺陷 |

---

## 5. Registry 侧数据缺陷

### 5.1 `solver` 约束完全未落地（0/634）

- 官方索引用上标标记约束：`ᴴˢ⁾` = Hyper-S 专属，`ᴶ⁾` = 网格模型分析专属，**共 26 行带标记**。
- 中间产物 `StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv` 的 `solver` 列**只落了 20 条**（全为 `HYPER_S`）。
- **Registry YAML 与 manifest 中 `solver` 字段出现 0 次** —— §8 的「在 Registry 增加 `solver` 字段」仍是回写建议，未实施。

漏标明细（6 条）：

| 源索引原文 | 应落值 | 漏标原因 |
| --- | --- | --- |
| `db/HHCT-M1ᴴˢ⁾` | `HYPER_S` | 该行**缺前导 `/`**，正则未匹配 |
| `/db/GALD ᴶ⁾` | `GRID_MODEL` | 标记前有**空格**，正则未匹配 |
| `Elastic Modulus Retention Rate ᴶ⁾` | `GRID_MODEL` | 标记出现在标题字段（`POST.TABLE.FIBR_ELASTREMAIN`） |
| `Maximum Strain of The Cell ᴶ⁾` | `GRID_MODEL` | 同上（`POST.TABLE.FIBR_MAXCONTRACT`） |
| `Event Step ᴶ⁾` | `GRID_MODEL` | 同上（`POST.TABLE.FIBR_EVENTSTEP`） |
| `Average Compression Strain ᴶ⁾` | `GRID_MODEL` | 同上（`POST.TABLE.FIBR_MEANCOMPCONTRACT`） |

**影响**：客户端无法实现主文档 §104 要求的 `SOLVER_UNSUPPORTED` 前置拦截；A 组 21 个端点在标准求解器实例上会产生无效调用。

### 5.2 `methods` 分隔符不一致（4 个端点）

| Registry key | `methods` 原值 | 产品 |
| --- | --- | --- |
| `DB.CPSETTINGS` | `GET/POST/PUT` | CIVIL_NX |
| `DB.NUCS` | `DELETE/GET/POST/PUT` | CIVIL_NX |
| `DB.UFTR` | `DELETE/GET/POST/PUT` | CIVIL_NX |
| `DB.UTBL` | `DELETE/GET/POST/PUT` | CIVIL_NX |

其余 630 个端点均使用 `, ` 分隔（另有 31 个值为 `Post`，大小写不规范但不影响解析）。这 4 个均源自 CIVIL NX 补充手册，说明**两个来源的录入格式未归一化**。

**影响**：任何按 `,` 切分的消费方都会把它们当作单一方法 `GET/POST/PUT`，导致方法校验失败或静默跳过。

### 5.3 `DB.SWIND` 方法集缺失

`methods: ""` + `methods_unknown: true`。源手册确实未标注方法，属**已知缺口**而非录入错误。冒烟 dry-run 显式报出 `METHODS_UNKNOWN`，行为符合设计。

### 5.4 无 JSON Schema 的端点（64 个）

> 注：早期记录为 27 个，实测为 **64** 个（634 − 570）。

| 命名空间 | 产品 | 数量 |
| --- | --- | --- |
| POST | GEN_NX | 26 |
| DOC | CIVIL_DESIGNER | 10 |
| DB | CIVIL_DESIGNER | 7 |
| OPRT | CIVIL_DESIGNER | 6 |
| OPE | CIVIL_NX | 5 |
| OPE | GEN_NX | 5 |
| OPE | CIVIL_NX+GEN_NX | 3 |
| DB | CIVIL_NX | 1 |
| VIEW | CIVIL_NX+GEN_NX | 1 |

其中 DB 命名空间的缺口可用 `/info/db/{CODE}` 自省回填（§2.6）；非 DB 命名空间**无自省能力**，只能依赖源手册。

### 5.5 产品声明偏差（双向）

| 方向 | 数量 | 端点 | 证据 |
| --- | --- | --- | --- |
| **过窄**（实例支持，未标 GEN_NX） | 2 | `DB.CPSETTINGS`、`DB.NUCS` | `/info/db/{CODE}` 返回 200 |
| **过宽**（标了 GEN_NX，实例不支持） | 36 | A 组 21 个 + B 组 15 个 | `GET` 与 `/info/db/{CODE}` 均 404 |

`DB.CPSETTINGS`（协同/设置）与 `DB.NUCS`（命名 UCS）当前标为 `[CIVIL_NX]`，但本 GEN 实例确实提供。

---

## 6. 客户端行为实测

### 6.1 正常路径

`MidasClient.resolve()` 的方法白名单校验、`raw()` 的 401/403 → `AUTH_FAILED` 映射、5xx 重试策略均按设计工作：本次测试 265 次调用中**无一次**误报 `METHOD_NOT_ALLOWED` 或 `PRODUCT_CAPABILITY_UNSUPPORTED`。

### 6.2 待改进：HTTP 语义映射

实测实例的错误码语义：

| 实例返回 | 含义 | 客户端当前映射 | 建议映射（对齐主文档 §104） |
| --- | --- | --- | --- |
| 404 | 表/端点不存在 | `HTTP_ERROR` | `ENDPOINT_NOT_FOUND` |
| **405** | 方法不允许（`GET /VIEW/CAPTURE`） | `HTTP_ERROR` | `METHOD_NOT_ALLOWED` |
| 401/403 | 鉴权失败 | `AUTH_FAILED` ✅ | 保持 |

### 6.3 待改进：产品门控

`smoke_test.py --live` 在不传 `--product` 时会把其他产品的端点发给当前实例，产生 10 个**预期内**的假失败（C 组）。应增加实例产品声明（如 `--expect-product GEN_NX`）并在调用前过滤。

---

## 7. 结论

| 维度 | 结论 |
| --- | --- |
| **Registry 结构完整性** | ✅ 634/634 通过 dry-run；570 个 schema 引用零缺失 |
| **鉴权与连通** | ✅ 265 次调用零鉴权/连接错误 |
| **URI 与命名空间** | ✅ 无一处拼写错误；大小写不敏感已被实测证实 |
| **GEN_NX 覆盖率** | ⚠️ 253 次 GET 调用中 217 次成功（85.8%）；36 次失败中 21 次为求解器变体（预期）、15 次待裁决 |
| **产品能力声明** | ⚠️ 双向偏差：2 个过窄、36 个过宽 |
| **求解器约束** | ❌ 完全未落地（0/634），且采集阶段漏标 6 条 |
| **方法集数据** | ⚠️ 4 个端点分隔符不一致；1 个端点方法集缺失（已知） |
| **Schema 覆盖** | ⚠️ 64/634 缺失（10.1%） |
| **写操作链路** | ⛔ 未验证（按约束跳过 369 个端点） |

**总体判断**：Registry 的 URI 与命名空间层已经可信（零拼写错误、零引用缺失），**主要风险集中在「能力元数据」层** —— 求解器约束、产品归属、方法集规范化。这三类缺陷的共同后果是「客户端会在调用前无法判断端点是否可用」，正是主文档 §104 失败模型要解决的问题。

---

## 8. 附件与复现

### 8.1 附件

| 文件 | 说明 |
| --- | --- |
| `StructAI_MIDAS_MCP_Live冒烟失败清单_v1.0.csv` | 46 个失败端点，含 `归因分组` 列 |
| `StructAI_MIDAS_MCP_统一修复计划_v1.0.md` | 修复项汇总（待批准） |
| `examples/smoke_report_gen.json` | GEN_NX 子集原始结果（253 条） |
| `examples/smoke_report_all.json` | 全产品原始结果（265 条） |
| `examples/smoke_report_dryrun.json` | dry-run 结果 |

### 8.2 复现步骤

```powershell
cd G:\MMCP\examples
$env:MIDAS_BASE_URL = "http://localhost:3030/gen"
$env:MIDAS_MAPI_KEY = "<从密钥管理获取，勿落盘>"

python smoke_test.py                                       # dry-run
python smoke_test.py --live --product GEN_NX --out smoke_report_gen.json
python smoke_test.py --live --out smoke_report_all.json     # 含非 GEN 产品端点，会有预期假失败
```

### 8.3 本轮修改的文件

| 文件 | 变更 |
| --- | --- |
| `examples/midas_client.py` | 新增 `parse_methods()`；`resolve()` / `call()` 改用之；`call()` 在方法集为空时抛 `METHODS_UNKNOWN` |
| `examples/smoke_test.py` | 新增 `parse_methods()`；`live_run()` 改用之 |

> 未修改 `registry/` 下任何数据文件。

---

## 附录 A｜V1.1 增补：三实例交叉实测（第二轮）

> 本轮新增两个云实例，用于裁决 V1.0 遗留的 D1，并验证 CIVIL_NX / CIVIL_DESIGNER 的产品归属。
> 凭据仍仅经环境变量传入，未落盘。

### A.0 ⚠️ 重要事件：测试期间误删 CIVIL NX 云实例的节点与单元（已恢复）

**经过**：在探测 CIVIL NX 实例的错误语义时，对 `/db/NODE` 发起了一次 **不带请求体的 `DELETE`**（目的是验证「错误方法是否被拒绝」）。该实例返回 `HTTP 200` 并回显了 345 个节点的数据，**未报任何错误**；随后 `/db/NODE` 变为 `{"message":""}`，`/ope/PROJECTSTATUS` 的节点数由 `345` 变为 `0`、单元数由 `288` 变为 `0`（单元被级联删除）。

| 项 | 内容 |
| --- | --- |
| 影响实例 | `https://moa-engineers.midasit.cn:443/civil` |
| 影响范围 | 345 个节点 + 288 个单元（几何） |
| 未受影响 | 材料 4、截面 91、荷载工况（`/db/STLD`）、组（`/db/GRUP`）、边界组（`/db/BNGR`）均在 |
| 是否落盘 | **否**。全程未调用 `/doc/SAVE`，服务端项目文件未被覆盖 |
| 恢复方式 | 从 `/cdn`（同一模型的完整副本，345 节点 / 288 单元）读取并写回 |
| 单位换算 | `/cdn` 返回 mm、`/civil` 使用 m，实测比例精确为 1000 |
| 单元类型换算 | Designer 手册「`Type`：1-桁架 2-梁 3-平面应力 4-板 5-墙 6-平面应变 7-轴对称 8-实体 9-只拉 10-只压」→ 全部 288 个单元均为 `2`，映射为 `BEAM` |
| 恢复验证 | **逐点核对通过**：345/345 节点坐标一致、288/288 单元的 `NODE/SECT/MATL` 一致；`PROJECTSTATUS` 恢复为 节点 345、单元 288 |

**残留不确定性**：挂接在节点上的数据（一般支承、节点弹性支承、节点荷载等）无法从 `/cdn` 取回（Designer API 不暴露这些表），因此**无法确认其原始状态、也无法恢复**。恢复脚本保留了 `/db/CONS` 为空的结果。

**建议处置**：在 MIDAS Civil NX 端**重新打开该项目文件**（因未落盘，文件本身完好），即可得到与测试前完全一致的状态。若已保存，则以上述几何恢复结果为准。

**由此得出的产品级结论（已并入修复计划 F12）**：

1. **NX 系的 `DELETE` 语义极度危险**：不带 `Assign` 请求体的 `DELETE /db/NODE` 会**删除全部节点**，且返回 `200` + 回显数据，**不报错**。
2. 同一操作在 CIVIL_DESIGNER 上被正确拒绝（`{"type":"错误","content":"不支持该操作方法"}`）。
3. 对照：不带请求体的 `PUT /db/NODE` 在 NX 系返回 `500 Cannot read properties of null (reading 'Assign')` —— 说明 PUT 有校验，**DELETE 没有**。
4. MCP 层必须**硬性禁止**「无显式 `Assign` 主体的 DELETE」，并在调用前做破坏性操作二次确认。

### A.1 三实例结果对照

| 实例 | 产品 | Registry 声称支持 | 含 GET | 实际调用 | OK（有数据） | OK_EMPTY | 404 | 路由成功率 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `http://localhost:3030/gen` | GEN_NX | 591 | 253 | 253 | 217 | 0 | 36 | 85.8% |
| `https://moa-engineers.midasit.cn:443/civil` | CIVIL_NX | 510 | 215 | 215 | 29 | 179 | 7 | **96.7%** |
| `https://moa-engineers.midasit.cn:443/cdn` | CIVIL_DESIGNER | 37 | 13 | 13 | 13 | 0 | 0 | **100%** |

> `OK_EMPTY` = 端点已路由但返回 `{"message":""}`（表存在、当前无数据）。CIVIL NX 云实例上 179/215 为空，与该会话当前的项目状态有关（`PROJECTSTATUS` 一度显示 节点 0/0，且首次探测时 `/db/NODE` 有 345 节点、后续变为空 —— 该共享云账号的会话状态在测试期间发生过变化）。

### A.2 🔴 重大发现：三种响应封装并存，HTTP 状态码可信度不同

| 产品 | 封装 | 未知 URI 的表现 | 可用性可判定性 |
| --- | --- | --- | --- |
| GEN_NX / CIVIL_NX | `{"<TABLE>": {...}}` | **HTTP 404** + `{"error":{"message":"404 Not Found"}}` | ✅ HTTP 状态码可靠 |
| CIVIL_DESIGNER | `{"command","function","result":{"return_value","message"}}` | **HTTP 200** + `{"result":{"return_value":"","message":[]}}` | ❌ **HTTP 状态码完全不可用** |

CIVIL_DESIGNER 实例对**任意** URI 均返回 200，实测证据：

```
GET /foo/BAR          -> 200 {"command":"/foo/BAR","result":{"return_value":"","message":[]}}
GET /db/ZZZZZ         -> 200 {"command":"/db/ZZZZZ","result":{"return_value":"","message":[]}}
GET /DESIGN/XXX/YYY   -> 200 {"command":"/DESIGN/XXX/YYY","result":{"return_value":"","message":[]}}
```

唯一可靠的错误信号是 `result.message[].type == "错误"`；`type == "正常"` + 真实 `return_value` 可作为**存在性的正向证据**，但「无数据」与「不存在」在该封装下**不可区分**。

**对本次测试的影响**：V1.0 的 `ok = not r.get("error")` 判定在 CIVIL_DESIGNER 上会把 `/foo/BAR` 也判为 OK。已为脚手架加入产品感知的 `classify_response()`（见 A.6）。修正后 CIVIL_DESIGNER 的 13 次调用全部返回 `正常/操作成功`，属**有效的存在性正向证据**；但**负向证据（端点不存在）在该产品上无法通过 GET 获得**。

### A.3 D1 裁决证据（V1.0 的 15 个存疑端点）

15 个端点在 CIVIL NX 云实例上**全部返回 200**：

`/db/CAMB`、`/db/CJFG`、`/db/CMCS`、`/db/CRGR`、`/db/DYFG`、`/db/DYLA`、`/db/DYNF`、`/db/EWSF`、`/db/GCMB`、`/db/GSBG`、`/db/PLCB`、`/db/RCHK`、`/db/SPAN`、`/db/STRPSSM`、`/db/WVLD`

同时确认（CIVIL NX 实例）：

| 端点 | CIVIL NX | 说明 |
| --- | --- | --- |
| `/db/CPSETTINGS`、`/db/NUCS`、`/db/GALD` | 200 | 确认属 CIVIL_NX ✅ |
| `/db/CAPSIZE`、`/db/DCOD`、`/db/BTCP`、`/db/MODULE`、`/db/LCOM`、`/db/CWRC`、`/db/TRPT`、`/doc/UNIT` | 404 | 确认属 CIVIL_DESIGNER，产品门控正确 ✅ |
| 全部 `-M1` 变体 | 404 | 确认 Hyper-S 专属 ✅ |

**结论**：15 个端点**不是** CIVIL_NX 专属 —— 官方 GEN 索引收录它们、CIVIL NX 实例提供它们、仅本地 GEN 实例 404。三者只能由**「本地 GEN NX 实例的版本/模块差异」**解释。

> **D1 建议由「D1-b 收窄为 CIVIL_NX」改为「D1-a 保留 GEN_NX + 增加可用性标注」**。

### A.4 CIVIL NX 实例新增的 7 个 404

| Registry key | 来源 | 备注 |
| --- | --- | --- |
| `DB.SDHY` | help_center + repo | 滞回阻尼器 (MSS)；Civil NX 手册收录 |
| `DB.SDIS` | help_center + repo | 隔震器 (MSS)；Civil NX 手册收录 |
| `DB.THRS` | help_center | 时程分析-地震控制装置 |
| `DB.UFTR` | civil_nx_manual | Smart Report 页眉页脚；**两个 NX 实例都 404** |
| `DB.UTBL` | civil_nx_manual | Smart Report 自定义表；**两个 NX 实例都 404** |
| `DESIGN.RC.KDS-41-20-2022.MATD` | repo | 同组其它 DESIGN 端点均 200，仅 MATD 缺失 |
| `DESIGN.SRC.AIK-SRC2K.MATD` | repo | 同上 |

- `DB.SDHY/SDIS/THRS` 属「较新版本新增功能」，与 A.3 的版本差异解释一致。
- `DB.UFTR/UTBL` 在**本地 GEN 与云 CIVIL NX 两个实例上都 404**，但两个官方手册都收录 → 疑为 **URI 错误或功能未启用（Smart Report 插件）**，需单独核实。
- `DESIGN.*.MATD` 是同组内的个例缺失，可能是该实例的路由未实现。

### A.5 其它实测事实（补充 V1.0 §2.6）

| 事实 | 证据 |
| --- | --- |
| NX 系未知 URI → **404**；`/foo/BAR` 同样 404 | `/db/ZZZZZ`、`/foo/BAR` |
| NX 系空表 → **200 + `{"message":""}`** | `/db/NUCS`、`/db/GALD` |
| NX 系 `PUT` 无请求体 → **500** `Cannot read properties of null (reading 'Assign')` | `/db/NODE` |
| NX 系 `DELETE` 无请求体 → **200 + 回显数据，且真的删除** | 见 A.0 |
| CIVIL_DESIGNER 错误方法 → 200 + `{"type":"错误","content":"不支持该操作方法"}` | `DELETE /db/NODE` |
| CIVIL_DESIGNER 坐标单位为 mm，NX 系为 m（同一模型差 1000 倍） | 同一节点 `x=55` vs `X=0.055` |
| DESIGN 命名空间在 **GEN_NX 与 CIVIL_NX 上都可用**（`/DESIGN/NOPE` → 404） | 两实例各抽样 20 个均 200 |
| 上游 repo（`Dennis5882/MIDAS-API`）自述目标产品为 **Gen NX / Civil NX**，非 Civil Designer | 仓库 README「대상 제품: MIDAS Gen NX / Civil NX」 |

### A.6 本轮修改的脚手架文件（V1.0 §8.3 的补充）

| 文件 | 变更 |
| --- | --- |
| `examples/midas_client.py` | 新增 `classify_response(key, body)`：按封装区分 `OK` / `OK_EMPTY` / `INDETERMINATE` / `ERROR` |
| `examples/smoke_test.py` | `live_run()` 改用 `classify_response()`；汇总将 `OK_EMPTY` 计入路由成功 |

> 仍**未修改** `registry/` 下任何数据文件。GEN_NX 回归复跑结果与 V1.0 完全一致（253 次调用 / 217 OK / 36 404），无回归。

### A.7 结论修订

| 维度 | V1.0 结论 | V1.1 修订 |
| --- | --- | --- |
| 15 个存疑端点的归属 | 待裁决（可能属 CIVIL_NX） | **已裁决**：属 GEN_NX 与 CIVIL_NX 共有，本地 GEN 实例为版本差异 |
| 客户端响应判定 | 仅按 `error` 键 | **必须产品感知**：CIVIL_DESIGNER 不能依赖 HTTP 状态码 |
| 实例版本一致性 | 未评估 | 本地 GEN 实例**明显落后于**云实例（缺 15 + 3 个端点） |
| 写操作安全性 | 未评估 | **`DELETE` 无主体会删除全表且不报错**，必须硬性禁止 |
| `DB.UFTR/UTBL` | 视为正常 CIVIL_NX 端点 | **两个实例都 404，疑为错误条目**，需核实 |
| CIVIL_DESIGNER 覆盖 | 未测 | 13/13 返回正常，但**负向验证在该产品上不可行** |

---

## 附录 B｜修复落地结果（2026-05-07）

修复计划中的 **F1–F14** 已按建议顺序落地，实施明细见《StructAI_MIDAS_MCP_统一修复计划_v1.0.md》§11。此处只记录**对测试结论的影响**。

### B.1 回归基线变化

| 检查 | 修复前 | 修复后 | 说明 |
| --- | --- | --- | --- |
| dry-run 问题数 | 1（`DB.SWIND`） | **0** | F8/D2 禁用该端点 |
| GEN_NX 调用 / OK / 失败 | 253 / 217 / 36 | **255 / 219 / 36** | F4 使 `DB.CPSETTINGS`/`DB.NUCS` 纳入 GEN 口径（+2） |
| CIVIL_NX 调用 / OK / OK_EMPTY / 失败 | 215 / 29 / 179 / 7 | **215 / 31 / 177 / 7** | 云会话状态浮动导致 OK/OK_EMPTY 分布微变 |
| CIVIL_DESIGNER 调用 / OK | 13 / 13 | **13 / 13** | — |
| 无产品过滤时的假失败 | 10 | **0** | F6 的 `--expect-product` 门控 |
| 失败错误码 | `HTTP_ERROR` | **`ENDPOINT_NOT_FOUND`** | F5 的 HTTP 语义映射 |

> **关键点**：36 与 7 个失败**不是新问题**，而是同一批端点在更精确的错误码下被重新报出（A 组 21 个 Hyper-S 变体 + B 组 15 个版本差异端点 + CIVIL NX 的 7 个）。它们现在带有 `availability` / `unavailable_on` 标注，客户端在 404 时会附带排障提示。

### B.2 测试结论的修订

| 原结论（附录 A / §7） | 落地后状态 |
| --- | --- |
| 「求解器约束完全未落地（0/634）」 | ✅ 已修复：26 个 key 带 `solver`，并加生成器断言防回归 |
| 「methods 分隔符不一致（4 个）」 | ✅ 已修复：37 处归一化，断言强制 `, ` 格式 |
| 「产品声明过窄（2 个）」 | ✅ 已修复：`DB.CPSETTINGS`/`DB.NUCS` 扩为 GEN_NX + CIVIL_NX |
| 「产品声明过宽（36 个）」 | ✅ 按 D1-a 处理：保留产品声明，新增 `availability: unverified` + `unavailable_on` 溯源 |
| 「64 个端点缺 Schema」 | ⚠️ 部分：1 个自省补齐、30 个有参数表证据（`designer_params.json`）、33 个标记 `unavailable`；**schema 形态受写操作约束未定** |
| 「DELETE 无主体删除全表」 | ✅ 已加硬护栏（`DESTRUCTIVE_CALL_REJECTED`）+ registry 风险标记 |
| 「CIVIL_DESIGNER 响应恒 200 导致判定失真」 | ✅ 已加产品感知判定（`INDETERMINATE` 不再计为成功） |

### B.3 尚未验证的部分（结论仍为「未覆盖」）

- **369 个写端点**（含 POST 命名空间全部 199 个）的 live 行为 —— 未做，受「不改模型」约束。
- **CIVIL_DESIGNER 的请求体包装**（`Assign` vs 扁平）—— 未做，需写操作实测；这同时阻塞了 F7b 的 schema 生成。
- **WebSocket 长任务推送** —— 未做。
- **CIVIL NX 云实例的 `OK_EMPTY`（177/215）** —— 属该共享会话的项目状态，非端点缺陷；`availability` 已按「至少一个实例成功」判定，不受影响。

### B.4 附录 A.0 事故的后续

- 节点与单元已逐点恢复并验证（345/345、288/288）。
- 未调用 `/doc/SAVE`，服务端项目文件未被覆盖 —— **仍建议在 Civil NX 端重新打开项目文件**以复原无法从 API 取回的节点挂接数据。
- 该事故已转化为产品级护栏（F11）与 registry 风险标记，纳入回归基线。

---

## 附录 C｜写操作实测：CIVIL_DESIGNER 请求体形态（2026-05-07）

> 目的：解决修复计划 §11.3 的遗留项 1、2 —— Civil Designer 的请求体究竟是 `Assign` 包装还是扁平结构。
> 这同时决定了 `wrapper.write` 的取值与 F7b 的 JSON Schema 形态。

### C.1 安全策略

**写入的每一个值都与当前值完全相同**，因此无论服务端如何解析，模型状态都不可能改变；每一步都用「读回比对」验证。全程未触发任何实际变更。

### C.2 实测过程

手册中这两个端点的方法为 `Get, Put` / `Get、Put`，且均为可读可写的单例设置端点。

**端点 `/db/MODULE`（当前值 `{"Module": 0, "DgnCode": 3}`）**

| 步骤 | 请求 | 响应 | 读回 |
| --- | --- | --- | --- |
| [0] 基线 | `GET /db/MODULE` | 200 `{"Module":0,"DgnCode":3}` | — |
| [A] **扁平体** | `PUT {"Module":0,"DgnCode":3}` | 200 `{"type":"正常","content":"操作成功"}` | ✅ 与基线一致 |
| [B] **Assign 包装** | `PUT {"Assign":{"1":{...}}}` | 200 `{"type":"错误","content":"Format error: Required parameter [Module] is missing."}` | ✅ 与基线一致 |
| [C] 空体 | `PUT {}` | 200 同上「缺 Module」 | ✅ 与基线一致 |

**端点 `/doc/UNIT`（当前值 `{"Force": "N", "Length": "mm"}`）** —— 结果完全一致：

| 步骤 | 响应 |
| --- | --- |
| [A] 扁平体 | `正常/操作成功` |
| [B] Assign 包装 | `错误: Format error: Required parameter [Force] is missing.` |
| [C] 空体 | 同上 |
| 三次读回 | ✅ 均与基线一致 |

### C.3 结论

1. **CIVIL_DESIGNER 的请求体是扁平结构**（根级属性），**不使用 `Assign` / `Argument` 包装**。
   - 正向证据：扁平体 → `正常/操作成功`
   - 反向证据：`Assign` 包装 → `Required parameter [Module] is missing`（服务端把 `Assign` 当成未知字段，于是找不到必填的 `Module`）
   - 与只读证据一致：`GET /db/MODULE` 返回 `{"Module":0,"DgnCode":3}`（根级扁平），而 NX 系返回 `{"UNIT":{"1":{...}}}`（表名 + ID 两层）
2. **Designer 会校验必填参数**并返回结构化错误（`message[].type == "错误"`）—— 这与 `classify_response()` 的判定路径一致。
3. **NX 系确认为 `Assign` 包装**：此前实测 `PUT /db/NODE` 无主体返回 `500 Cannot read properties of null (reading 'Assign')`，已直接证明服务端读取 `Assign` 键。

### C.4 落地

| 变更 | 内容 |
| --- | --- |
| `wrapper.write` | Designer 独有端点 → `"none"`（扁平）；共有端点 → 保留 NX 的 `Assign`/`Argument`，并通过 `product_overrides.CIVIL_DESIGNER.wrapper` 覆盖为扁平 |
| `schema_ref.shape` | 新增，取 `"flat"`，标明该端点的请求体形态 |
| 客户端 | 新增 `infer_product()` 与 `effective_wrapper()`；`write == "none"` 时**不做任何包装** |
| F7b | 依据扁平形态生成 **20 个** Designer 端点的 JSON Schema（schema 总数 571 → **591**） |

**顺带修复的既有缺陷**：客户端此前从 `manifest.json` 读取 `wrapper` / `risk`，但 manifest **从不携带这两个字段** —— 导致所有端点的请求体都按默认 `Argument` 包装、重试策略恒为空。已在 manifest 中补出 `wrapper` / `risk` / `product_overrides` 三个字段。

### C.5 未覆盖

- **Designer 的实际写入效果**（如 POST 新增节点、DELETE 删除）未验证 —— 本次只验证了「请求体形态」这一件事，且全程零变更。
- **Designer 的数组型端点**（`/db/NODE`、`/db/LENG` 等返回数组）的写入形态：GET 返回数组，但 PUT/POST 的请求体是单对象还是数组**未验证**。生成的 schema 按手册参数表建模为单对象；`DB.LENG` 有两个参数小节，用 `anyOf` 表达。
- 因此**不应对 Designer 的写路径做无验证的批量操作**。

---

## 附录 D｜写操作实测：Designer 数组型端点与「删除全部」语义（2026-05-07）

> 目的：解决附录 C.5 的遗留项 —— Designer 的数组型端点，PUT/POST 的请求体是单对象还是数组。
> 安全策略同附录 C：**写入值与当前值完全相同**，每一步读回比对。

### D.1 关键发现：服务端会明确报出期望的形态

对 `/db/LENG`（GET 返回 288 条数组）实测：

| 步骤 | 请求体 | 响应 | 读回 |
| --- | --- | --- | --- |
| [0] 基线 | `GET /db/LENG` | 288 条，首条 `{"ID":1,"Ly":300,"Lz":300}` | — |
| [A] **数组体**（与 GET 完全相同） | `[{...}, ...]` × 288 | `正常/操作成功` | ✅ 288/288 一致 |
| [B] **单对象体** | `{"ID":1,"Ly":300,"Lz":300}` | **`Format error: current object should be an [array].`** | ✅ 288/288 一致 |
| [C] 空体 | `{}` | 同上「should be an [array]」 | ✅ 288/288 一致 |

`/db/BTCP`、`/db/CWRC` 结果完全一致（288 条，A 通过 / B、C 报「should be an [array]」）。

**反向确认**（对象型端点）：

| 端点 | 对象体 | 数组体 |
| --- | --- | --- |
| `/db/TRPT` | `正常/操作成功` ✅ | **`Format error: current object should be an [single object, should not be an array.].`** |
| `/db/CAPSIZE` | `{}` → `Required parameter [PierInfo] is missing.` | — |

服务端的校验信息**直接给出了期望类型**，因此「用空/错形主体探测」是一种**零副作用**的形态判定手段（校验失败 → 不写入；实测三次读回均与基线一致）。

### D.2 系统性判定结果（按手册「请求示例」+ 实测）

对 Designer 的 37 个端点逐一判定请求体形态：

| 形态 | 数量 | 端点 |
| --- | --- | --- |
| **数组**（`[{...}, ...]`） | **5** | `DB.BTCP`、`DB.CWRC`、`DB.LENG`、`DB.MEMB`、`DB.SPAN` |
| **对象**（`{...}`） | 32 | 其余全部（含 `DB.MODULE`、`DB.DCOD`、`DB.CAPSIZE`、`DB.TRPT`、`DOC.*`、`OPRT.*`、`VIEW.*`、`POST/TABLE`） |

> 注：`DB.BTCP` / `DB.CWRC` / `DB.LENG` **已由写操作实测确认**为数组；其余按手册「请求示例」判定（示例中出现数组即为数组体）。

### D.3 🔴 新发现：Designer 的 DELETE 可用主体表示「删除全部」

手册原文（`DB.SPAN` / `DB.MEMB` / `DB.CAPSIZE` 的「Delete 请求参数」表）：

- `Type` = `0-全部` / `1-按名称` / `2-按 Key`
- `NameList`：「空或未设置时删除全部」
- `KeyList`：「空或未设置时删除全部」

即 **`DELETE /db/SPAN` + `{"Type": 0}` = 删除全部跨度**；而**空主体同样等于删除全部**。这与附录 A.0 的 NX 系事故是**同一类风险**，但 Designer 是**官方明文记载**的。

### D.4 落地

| 变更 | 内容 |
| --- | --- |
| 请求体形态 | `wrapper_override` / `product_overrides.CIVIL_DESIGNER.wrapper` 新增 `body_kind`（`array` / `object`） |
| `schema_ref.shape` | 取值细化为 `flat_array` / `flat_object`（NX 系端点该字段缺失，表示 `Assign`/`Argument` 包装） |
| JSON Schema | 数组体端点生成 `{"type":"array","items":{...}}`；对象体端点生成 `{"type":"object",...}`。schema 总数仍为 **591**（形态修正而非新增） |
| registry 风险标记 | `DB.SPAN` / `DB.MEMB` / `DB.CAPSIZE` 标 `delete_all_via_body: true`（共有端点放在 `product_overrides.CIVIL_DESIGNER` 下） |
| 客户端护栏扩展 | ① 无主体 DELETE → `DESTRUCTIVE_CALL_REJECTED`；② **空主体 / 空 `Assign` → `GLOBAL_DELETE_REJECTED`**；③ 带 `delete_all_via_body` 标记的端点收到 `{"Type":0}` → `GLOBAL_DELETE_REJECTED`（需显式 `allow_global_delete=True` 才放行） |

护栏验证（不联网，6 例）：

```
GEN  DB.NODE   无主体           -> DESTRUCTIVE_CALL_REJECTED
GEN  DB.NODE   空主体 {}        -> GLOBAL_DELETE_REJECTED
GEN  DB.NODE   空 Assign        -> GLOBAL_DELETE_REJECTED
CDN  DB.SPAN   {"Type": 0}     -> GLOBAL_DELETE_REJECTED
CDN  DB.MEMB   {"Type": 0}     -> GLOBAL_DELETE_REJECTED
CDN  DB.CAPSIZE{"Type": 0}     -> GLOBAL_DELETE_REJECTED
```

请求体组装（拦截 `raw`，不发请求）：

```
CDN  DB.BTCP   (数组) -> [{"ID": 1, "BentCap": false, "SteelFrame": true}]
CDN  DB.MODULE (对象) -> {"Module": 0, "DgnCode": 3}
GEN  DB.NODE          -> {"Assign": {"1": {"X": 0, "Y": 0, "Z": 0}}}
```

### D.5 仍未覆盖

- **Designer 的实际写入效果**（新增/删除记录）仍未验证 —— 本轮只验证了**请求体形态**与**护栏行为**，全程零变更。
- **`DB.LENG` 的第二个参数小节**（计算长度系数 `Ky`/`Kz`）：GET 默认只返回 `Ly`/`Lz`，如何读取/写入另一小节**未验证**；schema 用 `anyOf` 表达两种形态。
- **`DB.SPAN` / `DB.MEMB` 的 POST 与 DELETE 共用同一 URI**：两者请求体形态不同（POST=数组，DELETE=对象），当前 `body_kind` 记录的是**写方法（POST/PUT）**的形态，DELETE 形态由手册的「Delete 请求参数」表单独描述。

---

## 附录 E｜真实写入测试（2026-05-07）

> 授权：本次为测试环境，允许真实写入。方法：**全量快照 → 改 → 验证 → 还原 → 逐项比对**。
> 快照：`write_test_snapshot/baseline.json`（/cdn 10 张表 + /civil 3 张表）。

### E.1 结果总览

| 测试 | 端点 | 结论 |
| --- | --- | --- |
| T1 | `/db/CWRC`（数组体 PUT） | ✅ 改值生效（`C1` 0→0.5），还原后 sha 与基线**完全一致** |
| T2 | `/db/DCOD`（对象体 PUT） | ✅ 改值生效（`fcup` 0.8→0.85），还原后 sha 与基线**完全一致** |
| T3 | `/db/MEMB`（POST 数组 / DELETE 对象） | ⚠️ 新建与定向删除均生效；但见 E.4 的残留偏差 |
| T3 | `/db/SPAN`（POST 数组 / DELETE 对象） | ⚠️ POST 被拒（`未设置支承`），DELETE 无副作用，状态与基线一致 |
| T4 | `/db/LENG`（数组体 PUT） | ✅ 只读写 `Ly`/`Lz`；`Ky`/`Kz` **被服务端静默忽略** |
| T5 | `/civil /db/NODE`（Assign 包装） | 🔴 **发现 DELETE 的真正语义**（见 E.2） |

**最终状态比对：13 项中 12 项与基线完全一致**（见 E.5）。

### E.2 🔴 关键发现：NX 系 DELETE 的单条删除必须把 key 写在 **URL 路径**里

官方手册（`G:\MIDAS-API-Online-Manual`，第 857–859 行）原文：

```
| Delete | Delete all component from existed midas Model |
- Delete each component {base URL} + command/key no.
  example: when you want to delete Key No. 10 node
  → method[Delete] URI: {base URL} + db/node/10 → Press Send button
```

即：

| 请求 | 语义 |
| --- | --- |
| `DELETE /db/NODE` | **删除全表**（"Delete all component"） |
| `DELETE /db/NODE/10` | 只删除 10 号节点 |

**实测验证**（`/civil`，345 节点基线）：

| 步骤 | 结果 |
| --- | --- |
| POST 节点 `999001` | 201，节点数 346 |
| `DELETE /db/NODE/999001` | 200，节点数 **345**，测试节点消失，**与基线完全一致** ✅ |

**并且**：`DELETE /db/NODE` 即使带上 `{"Assign": {"999001": {}}}` 主体，**同样删除全表** —— 实测 345 个节点被清空（本附录 E.3 已完整恢复）。这一点此前未在任何文档中说明，是本轮实测的核心产出。

### E.3 ⚠️ 第二次事故与恢复（已完整恢复）

**经过**：T5 首轮按「显式 Assign 主体」发起 `DELETE /db/NODE`，期望只删除测试节点；实例返回 200 并回显全部节点数据，但**实际清空了 345 个节点与 288 个单元**。

**恢复**：

| 步骤 | 结果 |
| --- | --- |
| `POST /db/NODE`（基线 345 个节点的 Assign 主体） | 201，恢复 345 |
| `POST /db/ELEM`（基线 288 个单元） | 201，恢复 288 |
| 逐点核对 | **缺失 0、坐标不符 0、单元不符 0** |
| `PROJECTSTATUS` | 节点 345 / 单元 288 / 材料 4 / 截面 91 ✅ |

> 与附录 A.0 的第一次事故**同源**：都是「不带路径 key 的 DELETE」。本次找到了官方依据与正确用法，根因已闭环。

### E.4 各端点的实测细节

**`/db/MEMB`（构件）**

- POST 数组体可新建（返回 `正常/操作成功`）。
- DELETE `{"Type":2,"KeyList":[999001]}` 可定向删除。
- ⚠️ **服务端会对 POST 的构件做规范化**：名字追加类型后缀（`构件 - 1` → `构件 - 1 (梁)`）、`DefaultMemb` 置为 `false`。
- ⚠️ **每个单元只维护一个构件**：删除用户定义构件后，应用会自动重建「默认构件」，但**分配新 key**（实测 1 → 381），且**不复用原 key**。
- 因此 `DefaultMemb: true` 这一「自动默认构件」状态**无法通过 API 复现**。

**`/db/SPAN`（跨度）**

- POST 返回 `{"type":"警告","content":"跨度[Key=999001]：未设置支承."}` 且**未创建**（列表仍为 0 条）→ 跨度需要有效支承，无法凭空构造。

**`/db/LENG`（长度参数）**

- GET 只返回 `{ID, Ly, Lz}`（自由长度小节）。
- **`/db/LENG/<keys>` 可用**：`GET /db/LENG/1,2,3` 只返回这 3 条（与手册注记一致）。
- PUT `[{"ID":1,"Ky":0.9,"Kz":0.9}]` 返回 `正常` 但 **`Ky`/`Kz` 被静默忽略**（读回仍是 `Ly`/`Lz`）→ 手册中「计算长度系数」小节的写入路径**未能找到**（疑似需要另一个 URI 或未在服务端实现）。

### E.5 最终状态比对（与基线快照）

| 实例 | 端点 | 结果 |
| --- | --- | --- |
| cdn | `/db/CWRC`、`/db/BTCP`、`/db/DCOD`、`/db/MODULE`、`/db/TRPT`、`/db/SPAN`、`/db/LENG`、`/db/CAPSIZE`、`/doc/UNIT` | ✅ 与基线 sha **完全一致** |
| civil | `/ope/PROJECTSTATUS`、`/db/NODE`、`/db/ELEM` | ✅ 与基线 sha **完全一致** |
| cdn | `/db/MEMB` | ⚠️ **唯一偏差**：仅 `Key=1` 的 `Name`（`构件 - 1` → `构件 - 1 (梁)`）与 `DefaultMemb`（`true` → `false`）；key 集合仍为 1..288，`MembType`/`ItrElems` 不变，**功能等价** |

> 该偏差无法通过 API 复原（见 E.4）。若需完全复位，**在 Civil Designer 端重新打开该项目文件**即可（本次全程未调用 `/doc/SAVE`）。

### E.6 护栏重设计（依据本轮实测）

| 产品 | 规则 | 错误码 |
| --- | --- | --- |
| **NX 系** | DELETE **必须**给出路径 key（`delete(key, item_id)` / `call(..., path_key=...)`）；无路径 key 一律拒绝 | `GLOBAL_DELETE_REJECTED` |
| **CIVIL_DESIGNER** | DELETE 必须有非空主体；`{"Type":0}`（全删）需显式 `allow_global_delete=True` | `DESTRUCTIVE_CALL_REJECTED` / `GLOBAL_DELETE_REJECTED` |

验证（不联网，7 例）：

```
GEN DB.NODE 无 path_key                  -> GLOBAL_DELETE_REJECTED
GEN DB.NODE 带 Assign 但无 path_key       -> GLOBAL_DELETE_REJECTED   ← 本次事故场景
GEN DB.NODE path_key=999001              -> 放行  uri=/DB/NODE/999001
GEN DB.NODE path_key=1,2                 -> 放行  uri=/DB/NODE/1,2
CDN DB.SPAN 无主体                        -> DESTRUCTIVE_CALL_REJECTED
CDN DB.SPAN {"Type":0}                   -> GLOBAL_DELETE_REJECTED
CDN DB.SPAN {"Type":2,"KeyList":[1]}     -> 放行
```

### E.7 registry 变更

| 字段 | 说明 |
| --- | --- |
| `path_key_supported` | NX 系端点支持 `{uri}/{key}`；已为 **360 个** DB/DESIGN 端点标记 |
| `risk.delete_without_body_is_global` | 语义明确为「**不带路径 key 的 DELETE = 删除全表**」（此前误述为「不带主体」） |
| README | 新增 `path_key_supported` 字段说明与「DELETE 全表」警示 |

### E.8 仍未验证

- `/db/LENG` 的「计算长度系数（`Ky`/`Kz`）」小节写入路径未找到。
- NX 系 `DELETE {uri}/{key1,key2}` 多 key 删除未测（避免动真实模型）。
- Designer 的 `DB.SPAN` 需有效支承才能创建，未做成功路径验证。
- 其余 43 个无 schema 端点未做写入验证。

---

## 附录 F｜补齐剩余未验证项（2026-05-07 第三轮）

### F.1 🔴 发现并补录漏采端点 `DB.KFAC`（计算长度系数）

**根因**：Civil Designer 手册「参数-计算长度系数」小节的「接口URL」**误写为 `/DB/LENG`**（与上一小节的 URI 相同），导致该端点未被采集，其 `Ky`/`Kz` 字段被错误地挂到了 `DB.LENG` 上（附录 D.5 记为「写入被静默忽略」）。

**线索**：同页「Get请求参数」注记写着「支持通过附加URL查询指定Key列表，如 **/DB/KFAC**/1,2,3」——真实 URI 就藏在注记里。

**实测确认**：

| 请求 | 结果 |
| --- | --- |
| `GET /db/KFAC` | 200，288 条 `{"ID":1,"Ky":1,"Kz":1}` … |
| `GET /db/KFAC/1,2,3` | 200，只返回这 3 条 |
| `PUT /db/KFAC`（改 ID=1 的 Ky/Kz → 0.9） | 200 `正常`，读回 `{"ID":1,"Ky":0.9,"Kz":0.9}` ✅ |
| 还原原值 | 与基线**完全一致** ✅ |

**已补录** `DB.KFAC`（products: `CIVIL_DESIGNER`，schema 由手册参数表生成，`body_kind: array`），并记录该手册勘误。

> 顺带确认：GEN / CIVIL NX 实例对该 URI 亦返回 200（空数据），路由存在但语义未确认 —— 已在 `notes` 中记录。

### F.2 NX 系多 key 删除 —— 已验证

| 步骤 | 结果 |
| --- | --- |
| POST 两个测试节点 `999001`、`999002` | 201，节点数 345 → 347 |
| `DELETE /db/NODE/999001,999002` | 200，节点数 **345**，两个测试节点均消失 |
| 与基线比对 | ✅ **完全一致** |

结论：NX 系支持 `DELETE {uri}/{k1,k2}` 批量定向删除（与附录 E.2 的「路径 key」规则一致）。

### F.3 Designer `/db/SPAN` 创建 —— 已验证

附录 E.4 中 `Support: 0` 被拒（`未设置支承`）。改用 **`Support: 1`**：

| 变体 | 结果 |
| --- | --- |
| `Support: 1`（单单元） | ✅ 200 `正常`，SPAN 条目 0 → 1 |
| `Support: 1`（双单元，同一单元重复） | 警告 `单元已存在` |
| 清理（`DELETE {"Type":2,"KeyList":[…]}`） | ✅ 200，条目回到 0，与基线一致 |

结论：`SpanInfo[].Support` 必须为 `1`（已设置支承）才能创建跨度。

### F.4 POST 结果表 —— 系统性验证与 schema 补齐

**发现两个 registry 缺陷**：

1. **`table_type` 缺口**：一个手册页面覆盖多个 `TABLE_TYPE` 时，只有第一个 key 拿到完整列表，**兄弟 key 的 `table_type` 为空** → 该端点无法调用（原始模型 **82 个** POST 端点受影响）。
2. **schema 误判为「不可得」**：这 26 个 POST 表的源手册**有完整规格表**（`spec_rows` 40+ 行，含 Key / Value Type / Required），完全可以推导 schema，此前被标为 `unavailable`。

**修复与验证**：

| 项 | 结果 |
| --- | --- |
| `table_type` 修正 | **194 个** `POST.TABLE.*` 端点已确定；仅 `POST.TABLE.string`（key 后缀破损，已标 `key_suspect`）无法确定 |
| 判定依据 | **实测确认「key 后缀才是权威值」**：`REACTIONLSURFACESPRING` → 200，而规格表枚举里的 `REACTIONSURFACESPRING` → 400 |
| schema 生成 | 由规格表推导 **23 个** JSON Schema（`schema_source: help_center_spec_table`） |
| **全量调用验证** | **191 / 194 返回 200**；其中 **19 个返回真实结构化数据**（含 `HEAD` + `DATA`） |

失败 3 个（均需额外参数，非端点缺陷）：

| 端点 | 状态 | 备注 |
| --- | --- | --- |
| `POST.TABLE.CONCURRENT_JOINT_FORCE` | 400 | 需更多参数（`LOAD_CASE_NAMES` 不足以构造） |
| `POST.TABLE.PLATEFORCEUGVBM` | 400 | `Unknown Error` |
| `POST.TABLE.REACTIONLSURFACESPRING` | 400 | 需更多参数 |

样例（返回真实数据）：

```
POST.TABLE.DISPLACEMENTG  -> {"empty":{"FORCE":"KN","DIST":"M",
                              "HEAD":["Index","Node","Load","DX","DY","DZ","RX","RY","RZ"],
                              "DATA":[["1","1","SW","0...  ]}}
POST.TABLE.MASS_SUMMARY_X -> {"empty":{"HEAD":["Index","Node","Nodal Mass","Load To Masses",...]}}
POST.TABLE.SECTIONALL     -> {"empty":{"HEAD":["Index","ID","Type","Shape","Name","Area",...]}}
```

### F.5 其余无 schema 端点

| 端点 | 类型 | 验证结果 |
| --- | --- | --- |
| `DB.LCOM` | GET | ✅ 200，`return_value: []`（Designer） |
| `OPE.STORY_PARAM` | GET | ✅ 200，`{"COUNTRY_CODE":"NTC2018"}` |
| `OPE.STORY_IRR_PARAM` | GET | ✅ 200，含 `STORY_DRIFT_METHOD` 等 |
| `OPE.SECTPROP` | GET | ✅ 200，含 `HEAD`/`DATA` 的截面属性表 |
| `VIEW.SELECT` | GET | ✅ 200，`{"NODE_LIST":[],"ELEM_LIST":[]}` |

**POST 型 OPE（空主体探测，无副作用）**：

| 端点 | 结果 |
| --- | --- |
| `OPE.BMLD`、`OPE.MEMB`、`OPE.STOR` | 400 `second query is wrong`（参数校验失败，未执行） |
| `OPE.STORYPROP` | 400 `There is no valid story information.` |
| `OPE.STORPROP` | **404**（路由不存在？已记入 `unavailable_on: [gen-local]`，需带完整参数复核） |

**前后对比 `PROJECTSTATUS`：无任何变化**（节点 3326 / 单元 6901 / 材料 1 / 截面 3）→ 探测未产生副作用。

**未测试并说明理由**：

| 端点 | 理由 |
| --- | --- |
| `DOC.CLOSEALL`、`DOC.EXIT` | 会关闭所有文档 / 退出程序，属破坏性操作且**无回滚手段** |
| `OPE.CPCREATE` / `CPEXPORT` / `CPUPDATEMODEL` / `CPUPDATERESULT` | Civil NX 专属，当前无 CIVIL_NX 可用实例承载这些操作 |

### F.6 registry 汇总变化

| 项 | 变化 |
| --- | --- |
| 端点定义 | 634 → **635**（补录 `DB.KFAC`） |
| JSON Schema | 591 → **615**（+23 POST 表 +1 KFAC） |
| 无 schema 端点 | 43 → **20** |
| 桶分布 | `products/civil_designer` 23 → **24** |
| `table_type` | 194 个 `POST.TABLE.*` 已确定；1 个标 `key_suspect` |

### F.7 最终状态与回归

| 检查 | 结果 |
| --- | --- |
| 快照比对（13 项） | **12 项与基线 sha 完全一致**；唯一偏差仍为 `/cdn /db/MEMB` 的 `Key=1`（附录 E.5，功能等价） |
| dry-run | **0 问题**（635 端点） |
| GEN_NX live | 255 / 219 OK / 36 未找到（与之前一致） |
| CIVIL_NX live | 215 / 31 OK / 177 空 / 7 未找到（一致） |
| CIVIL_DESIGNER live | **14 / 14**（+1，含新增 `DB.KFAC`） |
| registry 完整性 | 635 keys / 615 schemas；YAML 解析失败 0、manifest 不一致 0 |

### F.8 仍未验证（明确边界）

1. `DOC.CLOSEALL` / `DOC.EXIT` —— 破坏性且不可回滚，未测试。
2. `OPE.CPCREATE` / `CPEXPORT` / `CPUPDATEMODEL` / `CPUPDATERESULT` —— 需 CIVIL_NX 实例承载。
3. `OPE.STORPROP` 的 404 —— 需带完整参数复核。
4. 3 个 POST 表（`CONCURRENT_JOINT_FORCE`、`PLATEFORCEUGVBM`、`REACTIONLSURFACESPRING`）—— 需补全参数；其 schema 亦未生成。
5. `POST.TABLE.string` —— key 破损，需人工核实或移除。
6. `DB.KFAC` 在 NX 系上的语义（路由存在但返回空数据）。

---

## 附录 G｜复测（用户重启软件后，2026-05-07 第四轮）

### G.1 环境变化

| 实例 | 复测前状态 | 复测后 |
| --- | --- | --- |
| GEN `localhost:3030` | 400 `The project is not opened` | ✅ 已打开模型（**新模型：2 节点 / 1 单元**，非此前的 `portrait_truss_80m`） |
| CIVIL 云 | 404 `client does not exist` | ✅ 已恢复（345 节点 / 288 单元） |
| CDN 云 | 404 `client does not exist` | ✅ 已恢复（同一模型） |

> ⚠️ **发现：云端中继间歇性掉线**。实测连续两轮探测（间隔 15 秒）：第 1 轮 CIVIL/CDN 均返回 404 `client does not exist`，第 2 轮恢复正常。这会导致冒烟结果出现整批假失败。

### G.2 🔴 由此发现并修复的客户端缺陷

**问题**：中继掉线（`client does not exist`）与「未打开项目」被**误报为 `ENDPOINT_NOT_FOUND`**（HTTP 404），与实际「端点不存在」无法区分 —— 会误导排障方向。

**修复**：`midas_client` 新增两类状态错误码，在 404 分支解析响应体后再判定：

| 场景 | 原错误码 | 新错误码 |
| --- | --- | --- |
| 云端中继掉线（`client does not exist`） | `ENDPOINT_NOT_FOUND` | **`CLIENT_NOT_CONNECTED`** |
| 未打开项目（`The project is not opened` / `未打开模型`） | `MIDAS_ERROR` | **`PROJECT_NOT_OPENED`** |
| 真正的端点不存在 | `ENDPOINT_NOT_FOUND` | 不变 |

单元验证（8 例，含 NX 与 Designer 两种封装）全部映射正确。

### G.3 复测结果

**A. 三实例冒烟（与上一轮成功运行完全一致）**

| 实例 | 调用 | 结果 |
| --- | --- | --- |
| GEN_NX | 255 | **219 OK** / 36 `ENDPOINT_NOT_FOUND` |
| CIVIL_NX | 215 | 31 OK / 177 `OK_EMPTY` / 7 `ENDPOINT_NOT_FOUND` |
| CIVIL_DESIGNER | 14 | **14 OK** |
| dry-run | 635 | **0 问题** |

**B. 写入往返复测（全部通过）**

| 测试 | 结果 |
| --- | --- |
| `/db/CWRC` 数组体 PUT（改值→还原） | ✅ 生效，还原后 sha 与基线**完全一致** |
| `/db/DCOD` 对象体 PUT（改值→还原） | ✅ 生效，还原后 sha **完全一致** |
| `/db/KFAC` 数组体 PUT（改值→还原） | ✅ 生效，还原后**完全一致** |
| NX 多 key 删除 `DELETE /db/NODE/999001,999002` | ✅ 347 → **345**，与基线一致 |
| Designer `/db/SPAN` 创建（`Support:1`）+ 定向删除 | ✅ 0 → 1 → **0**，与基线一致 |

**C. POST 结果表全量复测**

`191 / 194 返回 200`，3 个返回 400（需额外参数）—— 与上一轮一致。

**D. 最终状态核对（13 项）**

**13 / 13 与基线 sha 完全一致** ✅

> 附录 E.5 记录的 `/db/MEMB` `Key=1` 残留偏差**已消失** —— 用户重启软件时项目从文件重载，状态自动复位。

### G.4 复测结论

| 维度 | 结论 |
| --- | --- |
| Registry | 635 端点 / 615 schema，dry-run 0 问题 |
| 读路径 | 三实例结果**可复现**（与上一轮逐项一致） |
| 写入路径 | 已测的 11 个端点**全部可复现通过**，且本轮 13/13 状态零偏差 |
| 客户端 | 修复了中继掉线的误报问题；错误码语义更精确 |
| 环境 | 云端中继**间歇性掉线**，需在测试时容忍重试 |

### G.5 建议

1. **冒烟脚本增加重试**：对 `CLIENT_NOT_CONNECTED` / `PROJECT_NOT_OPENED` 做有限次重试（如 3 次、间隔 10 秒），避免中继抖动产生整批假失败。
2. **GEN 实例的模型已更换**（现为 2 节点小模型）—— 若要复现历史基线（`portrait_truss_80m`），需重新打开该项目。
3. 云端中继的稳定性问题建议向 MIDAS 官方反馈。
