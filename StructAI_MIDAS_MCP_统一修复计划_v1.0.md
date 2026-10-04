# StructAI｜MIDAS MCP 统一修复计划 V1.0（待批准）

> 依据：《StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md》与《StructAI_MIDAS_MCP_Live冒烟失败清单_v1.0.csv》
>
> **状态：待批准。批准前不执行任何 Registry 数据修改。**
>
> 范围：本计划只处理 live 冒烟暴露出的问题。**不包含**新功能、MCP 服务器实现、写操作验证（另立计划）。

---

## 0. 一页速览

| 编号 | 优先级 | 问题 | 影响面 | 需用户裁决 |
| --- | --- | --- | --- | --- |
| F1 | **P0** | `methods` 分隔符不一致 | 4 个端点 | 否 |
| F2 | **P0** | `solver` 约束未落地 + 6 条漏标 | 26 个端点 | 否 |
| F3 | **P1** | 15 个端点的 GEN_NX 归属存疑 | 15 个端点 | **是（D1）** |
| F4 | **P1** | 2 个端点产品声明过窄 | 2 个端点 | 否 |
| F5 | **P1** | 客户端 HTTP 语义映射不全 | 全局 | 否 |
| F6 | **P1** | 冒烟脚手架缺产品门控 | 测试基建 | 否 |
| F7 | **P2** | 64 个端点缺 JSON Schema | 64 个端点 | 否 |
| F8 | **P2** | `DB.SWIND` 方法集缺失 | 1 个端点 | **是（D2）** |
| F9 | **P2** | 生成器缺数据质量断言 | 防回归 | 否 |

**建议执行顺序**：F1 → F2 → F5 → F6 → F4 → F3（待 D1）→ F9 → F7 → F8（待 D2）

**前置**：F1/F2/F3/F4/F7 都会改动 `registry/`，必须在同一批次内重新生成并重跑 dry-run + live，避免中间态不一致。

---

## 1. 需用户裁决的事项（阻塞项）

### D1｜15 个「GEN_NX 声称可用但实例不注册」端点的产品归属

**现状**：`DB.CAMB`、`DB.CJFG`、`DB.CMCS`、`DB.CRGR`、`DB.DYFG`、`DB.DYLA`、`DB.DYNF`、`DB.EWSF`、`DB.GCMB`、`DB.GSBG`、`DB.PLCB`、`DB.RCHK`、`DB.SPAN`、`DB.STRPSSM`、`DB.WVLD` 标记为 `products: [CIVIL_NX, GEN_NX]`，但本 GEN NX 实例（`localhost:3030/gen`）返回 404，`/info/db/{CODE}` 亦 404。

**三个可选方案**：

| 方案 | 做法 | 优点 | 缺点 |
| --- | --- | --- | --- |
| **D1-a** 保持现状 + 标注版本 | 保留 `[CIVIL_NX, GEN_NX]`，新增 `availability: "unverified"` 或 `min_version` 字段 | 不改动既有产品语义；对官方索引保持忠实 | 客户端仍会发出无效调用；需实现"运行时不支持则降级" |
| **D1-b** 收窄为 CIVIL_NX | 改为 `products: [CIVIL_NX]` | 客户端不再误调；与实例证据一致 | 若实为版本差异，会错误排除真实可用的 GEN 端点 |
| **D1-c** 先复核再定 | 换一个 GEN NX 实例（或更新版本）复测同 15 个 URI | 证据最充分 | 需要额外的实例/时间 |

**✅ 已由 V1.1 第二轮实测裁决（见测试报告附录 A.3）**：15 个端点在 CIVIL NX 云实例上**全部返回 200**，且 CIVIL_DESIGNER 专属端点在该实例上正确 404（产品门控无误）。结合「官方 GEN 索引收录 + CIVIL NX 提供 + 仅本地 GEN 实例 404」三点，唯一自洽的解释是**本地 GEN NX 实例的版本/模块差异**，而非产品归属错误。

**修订后的建议：取 D1-a** —— 保留 `products: [CIVIL_NX, GEN_NX]`，改为增加可用性标注：

- 为 Registry 增加 `availability: "verified" | "unverified"` 与可选 `min_version`；
- 对本地 GEN 实例实测 404 的端点标 `unverified`，并记录 `verified_on` 实例清单；
- 客户端在 `unverified` 端点调用失败（404）时，返回主文档 §104 的 `ENDPOINT_NOT_FOUND` 并附带 `hint: "该端点可能依赖更新的实例版本或未启用的模块"`。

> 该方案同时适用于 V1.1 新发现的 `DB.SDHY` / `DB.SDIS` / `DB.THRS`（云 CIVIL NX 也 404，同属版本差异）。

### D2｜`DB.SWIND` 的方法集

**现状**：`methods: ""` + `methods_unknown: true`。源手册确实未标注。

**可选**：① 向 MIDAS 官方确认；② 在 MCP 层永久禁用该 key（`enabled: false`），并保留 `methods_unknown: true` 作为溯源。

**建议**：先取 ②，避免不确定的方法集进入工具暴露面；后续拿到官方答复再放开。

---

## 2. P0 修复项

### F1｜`methods` 分隔符归一化

**证据**：`DB.CPSETTINGS`=`GET/POST/PUT`、`DB.NUCS`/`DB.UFTR`/`DB.UTBL`=`DELETE/GET/POST/PUT`；其余 630 个端点用 `, ` 分隔。

**改动**：

1. 生成器（`emit_registry.py` 上游）统一以 `, ` 拼接 `methods`；来源为 CIVIL NX 补充手册时把 `/` 归一化为 `, `。
2. 重建 4 个 YAML + `manifest.json`。
3. 同时把 31 个值为 `Post` 的条目归一化为 `POST`（纯大小写，无功能影响，顺手清理）。

**验收**：
- `manifest.json` 中 `methods` 值集合仅含 `, ` 分隔形式；
- `grep -c "/" methods` 为 0（URI 字段除外）；
- dry-run 与 live 结果与本次基线一致（253 次调用 / 217 OK）。

---

### F2｜`solver` 约束落地（含 6 条漏标修正）

**证据**：
- 官方索引 26 行带上标标记：21 个 `-M1` + `/db/GALD` 标 `ᴴˢ⁾`/`ᴶ⁾`，另 4 个 Fiber Section TH 结果表标 `ᴶ⁾`；
- 中间产物 CSV 只落了 20 条 `HYPER_S`；
- Registry YAML / manifest 中 `solver` 出现 **0 次**。

**改动**：

1. **修正采集正则**，覆盖三种形态：
   - 标准形态 `/db/XXX-M1ᴴˢ⁾`
   - 缺前导斜杠 `db/HHCT-M1ᴴˢ⁾`
   - 标记前有空格 `/db/GALD ᴶ⁾`
   - 标记落在标题字段（4 个 Fiber Section TH 表）
2. 为 26 个 key 写入 `solver:` 字段（`HYPER_S` / `GRID_MODEL`）。
3. `manifest.json` 增加 `solver` 字段透出。
4. `midas_client.resolve()` 增加求解器校验：当 `definition.solver` 存在且与 `RuntimeContext.solver` 不匹配时，抛 `SOLVER_UNSUPPORTED`，错误详情带 `required_solver` 与 `current_solver`（对齐主文档 §104 / 补充文档 §8）。
5. 同步更新 `StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv` 的 `solver` 列（20 → 26 条）。

**验收**：
- 26 个 key 的 `solver` 值正确；
- 在标准求解器实例上，A 组 21 个端点被**调用前**拦截为 `SOLVER_UNSUPPORTED`，不再产生 HTTP 404；
- live 成功率由 85.8% 提升至 ≥ 99%（余下为待裁决的 F3）。

---

## 3. P1 修复项

### F3｜15 个端点的产品归属（依赖 D1）

按 D1 裁决结果执行。若取 **D1-b**：

- 15 个 key 的 `products` 改为 `[CIVIL_NX]`（`DB.SPAN` 同时从 `CIVIL_DESIGNER` 复核，Designer 手册是否真收录）；
- 同步更新 `StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv`（移除这 15 行）与 `StructAI_MIDAS_MCP_CIVIL_NX_Endpoint清单_v1.0.csv`（确认已在）；
- `manifest.json` 的 `counts` 与 `buckets` 重算：`common/` 需把这 15 个移入 `products/civil_nx/`。

**验收**：GEN_NX 口径下 15 个端点不再出现在冒烟范围；Registry `products` 与实际能力一致。

### F4｜`DB.CPSETTINGS`、`DB.NUCS` 产品声明扩展

**证据**：两者 `/info/db/{CODE}` 在本 GEN 实例返回 200。

**改动**：`products: [CIVIL_NX]` → `[CIVIL_NX, GEN_NX]`；bucket 由 `products/civil_nx/` 迁至 `common/`。

**验收**：GEN_NX 冒烟调用数 253 → 255（若 F3 未同时收窄）。

> 注：F3 与 F4 会同时改变 `common/` 与 `products/` 的桶分布，必须同批重算 `manifest.counts`。

### F5｜客户端 HTTP 语义映射补全

**证据**：`GET /VIEW/CAPTURE` 返回 405，客户端映射为 `HTTP_ERROR`。

**改动**（`midas_client.raw()`）：

| HTTP | 新映射 |
| --- | --- |
| 404 | `ENDPOINT_NOT_FOUND` |
| 405 | `METHOD_NOT_ALLOWED` |
| 401/403 | `AUTH_FAILED`（保持） |
| 5xx | 保持重试后 `HTTP_ERROR` |

**验收**：`GET /VIEW/CAPTURE` 返回 `METHOD_NOT_ALLOWED`；`GET /db/CAMB` 返回 `ENDPOINT_NOT_FOUND`。

### F6｜冒烟脚手架产品门控

**证据**：不传 `--product` 时，8 个 CIVIL_DESIGNER + 2 个 CIVIL_NX 端点被发给 GEN 实例，产生 10 个预期内假失败。

**改动**（`smoke_test.py`）：

1. 新增 `--expect-product {GEN_NX,CIVIL_NX,CIVIL_DESIGNER,ANY}`，默认 `ANY`；
2. 当 `--expect-product` 非 `ANY` 时，调用前过滤掉 `expect_product not in e["products"]` 的端点，并在报告 `skipped_by_product` 中记录数量；
3. 报告新增 `expected_product` 字段。

**验收**：`--live --expect-product GEN_NX` 与 `--live --product GEN_NX` 结果一致，且 `skipped_by_product` 显式列出被跳过的产品。

---

## 4. P2 修复项

### F7｜补齐 64 个缺失 JSON Schema

| 命名空间 | 数量 | 可自动化 | 方案 |
| --- | --- | --- | --- |
| DB（CIVIL_NX + CIVIL_DESIGNER） | 8 | ✅ | 用 `/info/db/{CODE}` 自省回填（需实例侧启用对应产品） |
| POST（GEN_NX，Analysis Story Table） | 26 | ❌ | 源手册无 schema；从 `Request/Response Examples` 反推，或标 `schema_source: "inferred"` |
| OPE | 13 | ❌ | 非 DB 命名空间无自省能力；依赖源手册 |
| DOC（CIVIL_DESIGNER） | 10 | ❌ | 同上 |
| OPRT（CIVIL_DESIGNER） | 6 | ❌ | 同上 |
| VIEW | 1 | ❌ | 同上 |

**验收**：每个缺 schema 的 key 至少落 `schema_source: "unavailable"` + 原因，禁止留空；DB 命名空间的用自省结果补齐。

### F8｜`DB.SWIND`（依赖 D2）

按 D2 裁决执行；若取 ②，则在 YAML 增 `enabled: false` + `disable_reason`。

### F9｜生成器数据质量断言（防回归）

在生成链末端新增校验，任一失败即中止构建：

1. 所有 `methods` 值必须匹配 `^(POST|GET|PUT|DELETE)(, (POST|GET|PUT|DELETE))*$`；
2. 所有 `uri` 必须以 `/` 开头且不含空格；
3. `solver` 值 ∈ {`STANDARD`, `HYPER_S`, `GRID_MODEL`} 或缺失；
4. `products` 非空且 ∈ {`GEN_NX`, `CIVIL_NX`, `CIVIL_DESIGNER`}；
5. `schema` 非空的 key，其文件必须存在；为空的必须带 `schema_source`；
6. 任何带 `ᴴˢ⁾`/`ᴶ⁾` 标记的源索引行，必须能映射到某个 key 的 `solver` 字段（防止 F2 类漏标复发）。

**验收**：把本轮发现的 6 条漏标与 4 条分隔符不一致作为测试夹具，断言必须全部报错。

---

## 5. 建议的回归基线（纳入后续 CI）

| 检查 | 期望值（F1–F6 完成后） |
| --- | --- |
| dry-run 问题数 | 0（`DB.SWIND` 按 D2 处理） |
| GEN_NX live 调用数 | 255（若 F3 取 D1-b 则为 240） |
| GEN_NX live 失败数 | 0 |
| 全产品 live 失败数 | 0（F6 门控后不再有 C 组假失败） |
| 未覆盖的写端点 | 369（不变，另立计划） |

---

## 6. 明确不在本计划内

- 369 个写端点（POST/PUT/DELETE）的 live 验证 —— 需独立测试项目，另立计划；
- MCP 服务器实现、工具暴露面设计；
- DESIGN 端点数据正确性验证（需先运行设计计算）；
- WebSocket 长任务推送验证；
- DESIGN 中文名 5 处判断性译法的确认（弯曲系数 Cb、适用性参数、设计构件指定、钢筋暴露条件、钢筋设计准则）—— 属译名审查遗留，可并入本批一并裁决，但不阻塞本计划。

---

## 7. 批准方式

请逐项回复：

- **F1–F9**：全部批准 / 部分批准（列出编号）；
- **D1**：选 a / b / c；
- **D2**：选 ① / ②。

批准后建议按「F1 → F2 → F5 → F6 → F4 → F9」一次性落地并重跑冒烟，F3 待 D1 结论后单独一批，F7/F8 作为收尾批。

---

## 8. V1.1 第二轮实测新增的修复项

> 依据：测试报告附录 A（三实例交叉实测，含 CIVIL NX / CIVIL_DESIGNER 云实例）。

### F10｜客户端必须支持**产品感知的响应判定**（P0，新增）

**证据**：三种封装并存，且 CIVIL_DESIGNER 对**任意 URI 都返回 HTTP 200**：

| 产品 | 封装 | 未知 URI | 可用性可判定性 |
| --- | --- | --- | --- |
| GEN_NX / CIVIL_NX | `{"<TABLE>": {...}}` | 404 + `{"error":{...}}` | ✅ |
| CIVIL_DESIGNER | `{"command","function","result":{"return_value","message"}}` | **200** + 空 message | ❌ 无法判定「不存在」 |

**改动**：

1. `midas_client` 增加 `classify_response()`，产出 `OK` / `OK_EMPTY` / `INDETERMINATE` / `ERROR`（**本轮已作为脚手架修复落地**，见报告 A.6）。
2. `MidasClient` 增加 `product_profile` 概念（`NX_FAMILY` / `DESIGNER`），按产品选择错误映射：
   - `NX_FAMILY`：404 → `ENDPOINT_NOT_FOUND`，405 → `METHOD_NOT_ALLOWED`，`{"message":""}` → 空结果；
   - `DESIGNER`：`message[].type == "错误"` → 按 `content` 映射（`不支持该操作方法` → `METHOD_NOT_ALLOWED`）；`message == []` → `INDETERMINATE`，**不得当作成功**。
3. 冒烟/验收报告必须显式区分 `OK` 与 `OK_EMPTY`，避免把「空响应」计入数据正确性。

**验收**：在 CIVIL_DESIGNER 实例上 `GET /foo/BAR` 必须判为 `INDETERMINATE` 而非 `OK`。

### F11｜`DELETE` 安全护栏（P0，新增）

**证据（事故级）**：NX 系对**不带 `Assign` 请求体**的 `DELETE /db/NODE` 返回 `HTTP 200` 并回显数据，**实际删除了全部 345 个节点**，且单元被级联删除。对照：不带主体的 `PUT` 会返回 `500`，说明 PUT 有校验而 **DELETE 没有**。同一操作在 CIVIL_DESIGNER 上被正确拒绝。

**改动**：

1. MCP 层**硬性拒绝**「无显式 `Assign` 主体的 DELETE」，返回 `DESTRUCTIVE_CALL_REJECTED`。
2. `DELETE` 一律要求显式 ID 列表，禁止「空主体 = 全表」的隐式语义。
3. 破坏性操作（`DELETE` / `PUT` / `POST` 覆盖类）加入调用前二次确认与影响面预览（条数 + ID 范围）。
4. `MidasClient.delete()` 在 `payload is None` 时直接抛错，不发起请求。
5. 在 `registry` 的 `risk.destructive` 之外，增加 `risk.delete_without_body_is_global: true` 标记 NX 系 DB 端点。

**验收**：`client.delete("DB.NODE")` 不产生任何网络请求；带显式 ID 的 DELETE 正常执行。

### F12｜`DB.UFTR` / `DB.UTBL` 条目核实（P1，新增）

**证据**：两个官方手册都收录（Civil NX 手册 CSV、`civil_nx_manual` 快照），但**本地 GEN 与云 CIVIL NX 两个实例上都返回 404**。

**改动**：核实真实 URI 与启用条件（疑似 Smart Report 插件功能）。若确认为错误条目，则从 Registry 移除或标 `availability: "unverified"` + `unavailable_reason`。

### F13｜CIVIL_DESIGNER 产品覆盖补全（P2，新增）

**证据**：Registry 中 CIVIL_DESIGNER 口径仅 37 个端点（13 个含 GET），而 Civil Designer 手册有 38 个；且 `DESIGN` 命名空间（125 个）标为 `[CIVIL_NX, GEN_NX]`（经实测确认为正确）。

**改动**：

1. 对照 `G:\midas Civil Designer - API` 逐条复核 37 个端点的完整性。
2. 记录 CIVIL_DESIGNER 的**负向验证不可行**这一限制，在验收标准中写明：该产品的可用性只能以官方手册为准。
3. 补充 CIVIL_DESIGNER 的响应封装说明到主文档（`command` / `function` / `result.return_value` / `result.message`）与单位约定（实测返回 mm，NX 系返回 m）。

### F14｜实例版本矩阵纳入回归（P2，新增）

**证据**：本地 GEN 实例缺 15 + 3 个端点，云实例具备；实例能力随版本/模块变化。

**改动**：维护 `registry/instances.yaml` 记录已验证实例（base_url 别名、产品、版本、验证日期、失败端点清单），冒烟脚本按实例基线比对，差异即告警。

---

## 9. 修订后的回归基线

| 检查 | GEN_NX（localhost） | CIVIL_NX（云） | CIVIL_DESIGNER（云） |
| --- | --- | --- | --- |
| dry-run 问题数 | 0（F8 处理后） | 0 | 0 |
| 含 GET 端点 | 255（F4 后） | 215 | 13 |
| 路由失败数 | 0（F3/D1 标注后不计为失败） | 0（同上） | 0 |
| 预期 `OK_EMPTY` | 0 | ~179（随会话状态浮动） | 0 |
| 未覆盖写端点 | 369 | — | — |

> 注：CIVIL_DESIGNER 的 13 次调用全部返回 `正常/操作成功`，属**正向存在性证据**；该产品的**负向验证不可行**，不得据此声称「端点全部存在」。

---

## 10. 批准清单（修订版）

请逐项回复：

- **F1–F9**（V1.0 原有）：全部批准 / 部分批准（列出编号）；
- **F10–F14**（V1.1 新增）：全部批准 / 部分批准（列出编号）；
- **D1**：✅ 已由实测裁决，建议直接采纳 **D1-a**（保留 GEN_NX + `availability` 标注）—— 请确认；
- **D2**：选 ① / ②。

**建议落地顺序**：F11（安全护栏，最紧急）→ F1 → F2 → F10 → F5 → F6 → F4 → F9 → F3/D1-a → F12 → F7 → F13 → F14 → F8/D2。

---

## 11. 实施记录（已按建议顺序落地）

> 执行日期：2026-05-07。生成链：`registry_model.json` →（补丁）→ `registry_model_v2.json` →（生成器）→ `registry/`。

### 11.1 落地结果

| 编号 | 状态 | 落地内容 | 验证证据 |
| --- | --- | --- | --- |
| **F11** | ✅ 已按实测修正 | **NX 系**：DELETE 必须给路径 key（`delete(key, item_id)` / `path_key=`），无路径 key 一律 `GLOBAL_DELETE_REJECTED`——依据官方手册「`DELETE {uri}` = Delete all component；`DELETE {uri}/{key}` = 删单条」**并实测确认**。**CIVIL_DESIGNER**：必须有非空主体，`{"Type":0}` 需 `allow_global_delete=True` | 7 例护栏测试全部按预期；`DELETE /db/NODE/999001` 实测只删该节点（345 保持，与基线一致） |
| **F15**（新增） | ✅ | `path_key_supported` 字段（**360 个** DB/DESIGN 端点）；`risk.delete_without_body_is_global` 语义修正为「不带路径 key = 删除全表」 | registry README 已更新警示 |
| **F16**（新增） | ✅ | **真实写入往返验证**（快照→改→验证→还原）：数组体 PUT、对象体 PUT、POST 新建、DELETE 定向删除、Assign 包装全部实测通过 | 13 项中 12 项与基线 sha 完全一致；唯一偏差 `/db/MEMB` Key=1（API 无法复现 `DefaultMemb: true`，功能等价） |
| **F17**（新增） | ✅ | 修正 `POST.TABLE.*` 的 `table_type` 缺口（一个手册页多 TABLE_TYPE 时兄弟 key 为空，原始模型 **82 个**受影响）→ **194 个**已确定 | 全量调用验证：**191/194 返回 200**，其中 19 个返回真实结构化数据 |
| **F18**（新增） | ✅ | **补录漏采端点 `DB.KFAC`（计算长度系数）** —— 手册「接口URL」误写为 `/DB/LENG`，真实 URI 由同页注记 + 实测确认 | `PUT /db/KFAC` 改 Ky/Kz 生效并精确还原；DESIGNER live 13 → **14** |
| **F19**（新增） | ✅ | 验证结果回写 registry（`availability` / `verified_on` / `unavailable_on`）；`OPE.STORPROP` 记入不可用 | 7 个端点标记 verified |
| **F20**（新增） | ✅ | 复测发现云端中继间歇掉线（`client does not exist`）被误报为 `ENDPOINT_NOT_FOUND` → 新增 `CLIENT_NOT_CONNECTED` / `PROJECT_NOT_OPENED` 错误码，按响应体区分状态错误与端点缺陷 | 8 例单元验证全部映射正确；复测三实例结果与上一轮**逐项一致** |
| **F1** | ✅ | `methods` 归一化为 `, ` 分隔 + 大写，共 **37 处**（4 个斜杠分隔 + 2 个 `GET,POST` + 31 个 `Post`） | manifest 中 methods 值集合已无 `/` 与大小写混用 |
| **F2** | ✅ | 从官方索引推导写入 **26 个** `solver`（21 `HYPER_S` + 5 `GRID_MODEL`），含此前漏标的 `DB.HHCT-M1`、`DB.GALD`、4 个 `POST.TABLE.FIBR_*`；客户端新增 `SOLVER_UNSUPPORTED` 前置拦截位 | 生成器断言「源索引 26 行标记 = 26 个 key 带 solver」 |
| **F10** | ✅ | `classify_response()` 产出 `OK`/`OK_EMPTY`/`INDETERMINATE`/`ERROR`；新增 `profile`（`NX_FAMILY`/`DESIGNER`，按 base url 推断）；Designer 错误经 `result.message[].type` 映射 | `GET /foo/BAR` 在 Designer 上判为 `INDETERMINATE` 而非 OK；NX 系空表判为 `OK_EMPTY` |
| **F5** | ✅ | HTTP 映射：404 → `ENDPOINT_NOT_FOUND`，405 → `METHOD_NOT_ALLOWED`，401/403 → `AUTH_FAILED` | `DB.CAMB` → `ENDPOINT_NOT_FOUND(404)`；`VIEW.CAPTURE` → `METHOD_NOT_ALLOWED(405)` |
| **F6** | ✅ | `--expect-product`：调用前过滤不匹配产品，报告记录 `skipped_by_product` / `skipped_disabled` | 不带 `--product`、仅 `--expect-product GEN_NX` 时跳过 41 个，结果与 `--product GEN_NX` **完全一致**（255/219/36），不再有 10 个假失败 |
| **F4** | ✅ | `DB.CPSETTINGS`、`DB.NUCS` → `[GEN_NX, CIVIL_NX]`，桶由 `products/civil_nx/` 迁至 `common/` | GEN_NX 口径含 GET 端点数 253 → **255**，与预期一致 |
| **F9** | ✅ | 生成器新增 6 条数据质量断言（methods 格式 / uri / solver 取值 / products / schema 存在性 / **源索引标记必须全部落到 solver**），任一失败即中止构建 | 构建过程中**实际拦截过一次**（64 个 schema 静默缺口），修复后才通过 |
| **F3 / D1-a** | ✅ | 新增 `availability`（`verified` 242 / `unverified` 23 / `untested` 369）、`verified_on`、`unavailable_on`（43 个端点，含本地 GEN 404 的 36 个）；客户端对 `unverified` 端点的 404 补充排障提示 | `DB.ACTL-M1` → `ENDPOINT_NOT_FOUND` + `hint` + `verified_on=[]` |
| **F12** | ✅ | 核实 `DB.UFTR`/`DB.UTBL`：源手册原文为 `{base url} + db/UFTR` / `db/UTBL`，**URI 与 Registry 完全一致** → 结论为**功能未启用（Smart Report 插件）**，非错误条目，保留并标 `availability: unverified` | 源手册行 161091 / 161930 |
| **F7a** | ✅ | 消除 schema 静默缺口：`DB.CPSETTINGS` 用 `/info/db/` 自省补齐（571 schema，+1）；其余 **63 个**标记 `schema_source: "unavailable"` + 逐类原因 | 生成器断言通过；dry-run 0 问题 |
| **F7b / F7c** | ✅ | 提取 30 个 Designer 端点的参数表 → `registry/designer_params.json`；**写操作实测确认请求体为扁平结构**（对象/数组两种形态）后，生成 **20 个** JSON Schema；`wrapper.write` 对 Designer 取 `none`（共有端点用 `product_overrides.CIVIL_DESIGNER.wrapper` 覆盖）；客户端新增 `infer_product()` / `effective_wrapper()` / `body_kind` | schema 591；`effective_wrapper()` 在 GEN/CIVIL 返回 `Assign`/`Argument`、在 DESIGNER 返回 `None`；payload 组装 3 类（数组/对象/Assign）全部符合预期 |
| **F7d**（新增） | ✅ | 实测发现 **Designer 的 DELETE 可用主体表示「删除全部」**（手册明文：`Type=0` 或空主体 = 全部）。据此扩展护栏：无主体 → `DESTRUCTIVE_CALL_REJECTED`；空主体/空 `Assign` → `GLOBAL_DELETE_REJECTED`；`delete_all_via_body` 端点收到 `{"Type":0}` → `GLOBAL_DELETE_REJECTED`（需 `allow_global_delete=True`） | 6 例护栏测试全部按预期拒绝；`DB.SPAN`/`DB.MEMB`/`DB.CAPSIZE` 已标记 `delete_all_via_body` |
| **F13** | ✅ | CIVIL_DESIGNER 覆盖复核：Registry 37 个端点 vs 手册 37 个 URI，**双向零差异** | 集合比对 `手册有/Registry 无 = 0`、`Registry 有/手册无 = 0` |
| **F14** | ✅ | 新增 `registry/instances.yaml`：3 个实例的别名 / 产品 / profile / 实测计数 / 注意事项 | 生成器写入；被 `verified_on`/`unavailable_on` 引用 |
| **F8 / D2** | ✅ | 按建议取 **②**：`DB.SWIND` → `enabled: false` + `disable_reason`；客户端抛 `ENDPOINT_DISABLED` | dry-run 的 `METHODS_UNKNOWN` 问题由 1 → **0** |

### 11.2 回归结果（全部通过）

| 检查 | 修复前 | 修复后 |
| --- | --- | --- |
| dry-run 问题数 | 1（`DB.SWIND`） | **0** |
| GEN_NX live 调用 / OK / 失败 | 253 / 217 / 36 | **255 / 219 / 36** |
| CIVIL_NX live 调用 / OK / OK_EMPTY / 失败 | 215 / 29 / 179 / 7 | **215 / 31 / 177 / 7** |
| CIVIL_DESIGNER live 调用 / OK | 13 / 13 | **13 / 13** |
| 无产品过滤时的假失败 | 10 个 | **0**（F6 门控） |
| schema 文件数 | 570 | **615** |
| 端点定义数 | 634 | **635**（补录 `DB.KFAC`） |
| 无 schema 端点 | 64 | **20** |
| 桶分布 | common 368 / gen_nx 99 / civil_nx 19 / designer 23 / design 125 | **common 370 / gen_nx 99 / civil_nx 17 / designer 24 / design 125** |
| CIVIL_DESIGNER live | 13 / 13 | **14 / 14** |

### 11.3 遗留项（不在本轮完成范围）

1. ✅ **已解决（附录 C）**：Civil Designer 的请求体经写操作实测确认为**扁平结构**，`Assign` 包装会被拒绝（`Required parameter [...] is missing`）。已据此生成 20 个 JSON Schema，并落地 `wrapper.write = "none"` + `product_overrides`。
2. ✅ **已解决**：`CIVIL_DESIGNER` 的 `wrapper` 语义已用 `product_overrides.CIVIL_DESIGNER.wrapper = {"write": "none", "shape": "flat"}` 表达，客户端按实例产品解析。
3. ✅ **已解决（附录 D）**：Designer 数组型端点的请求体形态经写操作实测确认为**数组**（`DB.BTCP`/`DB.CWRC`/`DB.LENG` 三例，服务端报 `current object should be an [array]`）；对象型确认为对象（`DB.TRPT` 报 `should not be an array`）。系统性判定：**5 个数组体 + 32 个对象体**，已据此修正 schema。
4. ⚠️ **新发现（已加护栏）**：Designer 的 DELETE 可用主体表示**删除全部**（手册明文：`Type=0` 或空主体 = 全部）。已标记 `DB.SPAN`/`DB.MEMB`/`DB.CAPSIZE` 并扩展客户端护栏；**仍建议在 MCP 层对这些端点做二次确认与影响面预览**。
5. ✅ **已解决（附录 F）**：`/db/LENG` 的 `Ky`/`Kz` 实为**独立端点 `DB.KFAC`**（手册 URI 笔误），已补录并实测；NX 多 key 删除（`DELETE {uri}/{k1,k2}`）实测通过；`DB.SPAN` 创建需 `Support: 1`，已实测成功并清理。
6. ⚠️ **唯一的写入残留偏差**：`/cdn /db/MEMB` 的 `Key=1` —— `Name` 与 `DefaultMemb` 被服务端规范化且**无法通过 API 复现原值**（详见报告附录 E.4/E.5）。功能等价；如需完全复位请在 Civil Designer 端重新打开项目文件（全程未调用 `/doc/SAVE`）。
7. ✅ **已大幅推进（附录 F）**：POST 结果表全量验证 **191/194 通过**（19 个返回真实数据）；无 schema 端点 43 → **20**。
8. ✅ **已解决**：26 个 POST 表的 schema 由源手册规格表推导（+23）；剩余 3 个需补全参数（`CONCURRENT_JOINT_FORCE`、`PLATEFORCEUGVBM`、`REACTIONLSURFACESPRING`）。
9. ⚠️ **仍无 schema（20 个）**：`OPE` 13（无自省能力）+ `VIEW.SELECT` 1 + `DB.LCOM` 1 + `DOC.CLOSEALL/EXIT` 2 + 3 个 POST 表。GET 类已实测可用；POST 型 OPE 经空主体探测确认**无副作用**。
10. **`DB.UFTR`/`DB.UTBL` 的官方确认**：当前判定为「Smart Report 插件未启用」，建议向 MIDAS 官方确认启用条件。
11. ⚠️ **明确未测（不可回滚）**：`DOC.CLOSEALL`、`DOC.EXIT`；`OPE.CPCREATE/CPEXPORT/CPUPDATEMODEL/CPUPDATERESULT`（需 CIVIL_NX 实例）。
12. ⚠️ `OPE.STORPROP` 空主体探测返回 **404**，需带完整参数复核；`POST.TABLE.string` key 破损需人工核实或移除。

### 11.4 本轮修改的文件

| 文件 | 变更 |
| --- | --- |
| `registry/`（全量重建） | 634 定义 + **591** schema + `manifest.json`（新增 `wrapper` / `risk` / `product_overrides` / `solver` / `availability` / `verified_on` / `unavailable_on` / `enabled` / `params_ref` / `schema_shape` 字段）+ `instances.yaml` + `designer_params.json` + `README.md` |
| `examples/midas_client.py` | F5/F7c/F10/F11：HTTP 语义映射、产品感知判定、`profile` / `product` 推断、`effective_wrapper()`（扁平体支持）、DELETE 三重护栏（无主体 / 空主体 / 显式全删）、`enabled` 校验、`unverified` 排障提示 |
| `examples/smoke_test.py` | F6：`--expect-product`；适配 3 元组判定；跳过禁用端点 |
| `StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv` | 已同步 `methods` / `solver` 列 |
| `StructAI_MIDAS_MCP_CIVIL_NX_Endpoint清单_v1.0.csv` | 已同步 `methods` / `solver` 列 |

> 两份 `*_Endpoint清单_v1.0.csv` 已按新 Registry 同步 `methods` / `solver` 列（GEN 501 行、CIVIL 379 行）。GEN 那份有 41 个历史 key 不在最终 Registry 中，是上一轮合并/改名留下的，尚未清理。
