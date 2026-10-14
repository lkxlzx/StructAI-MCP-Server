# P164-d 报告：`VIEW.RESULTGRAPHIC` 的**变体取值表**（R150 成因更正 = R155）

> 批次：**P164-d**（**离线**取证；零请求、零副作用）｜ 状态：✅ **已交付（离线部分）**
> 关联：**R150**（成因更正）· **R155**（新登记）· **R156**（R132 过期口径更正）· `docs/07` §16.1
> 纪律：**铁律 ⓪**（判据 = 效果）· **不**臆造取值 · **不**升级 `availability` · **不**碰实例

---

## 0. 一句话结论

**R150 的「成因未定」有答案了**：`VIEW.RESULTGRAPHIC` 是**多变体端点**，
`Argument.CURRENT_MODE` 是**变体选择子**（手册 **36** 个取值）；
P160d 实测被拒的 **`"displacement"` 不是合法取值** ⇒
那一次的 `400`（`MIDAS GEN NX second query is wrong`）= **取值非法**，
**不是**「缺分析结果」。

⚠️ **顺带暴露一个数据侧缺口**：该端点的**请求 Schema** 的 `Argument` **只**声明
`TYPE_OF_DISPLAY`（= 36 个变体里的**一个**）⇒ **R140 的 `spec_guard` 抓不到非法的
`CURRENT_MODE`**（没有枚举可查）。**本批只登记、不修**（补全 Schema 须裁决）。

---

## 1. 怎么定案的（**离线、可复算**）

| 步 | 做什么 | 判据 |
| --- | --- | --- |
| 1 | 从手册取 `input_uri` 末段 = `resultgraphic` 的**全部**条目 | **34** 篇文章（不是 1 篇） |
| 2 | 逐条解析示例体的 `Argument.CURRENT_MODE` | **56** 条示例 ⇒ **36** 个取值 |
| 3 | 检查 P160d 用过的 `"displacement"` 是否在表里 | ❌ **不在** ⇒ 成因 = 取值非法 |
| 4 | 检查请求 Schema 是否声明了 `CURRENT_MODE` | ❌ **未声明** ⇒ `spec_guard` 无从校验 |

**工具**：`registry/tools/extract_result_modes.py`（幂等；**零请求**）
**证据**：`registry/live/view_result_modes.json`（每个取值都带**文章标题 + 示例名 + URL**）

### 1.1 取值表的形态

| 观察 | 值 |
| --- | --- |
| 文章数 / 示例数 / 取值数 | **34** / **56** / **36** |
| 文章族（按标题，**逐条可复算**） | `… - Result Display` **20** · `… - Moving Tracer Display` **6** · `… - Heat of Hydration Display` **5** · `… - Mode Shapes Display` **2** · `Type of Display` **1** |
| 与 `"displacement"` 最接近的**合法**取值 | `DisplacementContour` · `MVLTRC_Displacements` |
| 大小写 / 形态**不统一**（**如实照抄**） | `beamdiagrams`（全小写）· `DeformedShape`（Pascal）· `BeamForces/Moments`（带斜杠）· `BeamStresses(Equivalent)`（带括号）· `ReactionForces/Moments` **与** `reactionforces/moments`（**两个都存在**）· `"Resultant Force Diagram"` / `"Buckling Mode Shapes"`（**带空格**） |

**`Argument` 兄弟键的**实测**覆盖（56 条示例逐条统计）**：

| 键 | 出现次数 | 判读 |
| --- | --- | --- |
| `LOAD_CASE_COMB` | **56 / 56** | ✅ **唯一**的公共字段（现有 Schema **没有**声明它） |
| `TYPE_OF_DISPLAY` | **53 / 56** | ⚠️ **不是**必填 —— 有 **2** 个变体**一条都没有** |
| `COMPONENTS` | **52 / 56** | 高频但非公共 |
| `OPTIONS` | **25 / 56** | 按变体 |
| `OUTPUT_SECT_LOCATION` | **13 / 56** | 按变体（梁 / 桁架类） |
| `DISPLAY_OPTIONS` | **7 / 56** | 按变体（Diagram 类） |
| `CUTTING_NAME` | **2 / 56** | 仅 `PlateCuttingLineDiagram` |

**`TYPE_OF_DISPLAY` 完全缺席的变体**（**恰好 2 个**，且**没有**任何变体是「部分有、部分无」）：
`PlateCuttingLineDiagram` · `Resultant Force Diagram`。

⚠️ **这就是现有 Schema 站不住脚的地方**：它**只**声明 `TYPE_OF_DISPLAY` ——
**既漏了**唯一公共的 `LOAD_CASE_COMB` **与**变体选择子 `CURRENT_MODE`，
**又把**一个只有 53/56 的字段**当成了全部**。

### 1.2 旁证（**不是我方实例**）

`docs/nxsdk_review` 的实测摘要记：`/view/RESULTGRAPHIC` 在 **Civil** 上用**合法**取值
（`CURRENT_MODE=reactionforces/moments`）对**空文档**得到的是**业务级**
`MidasResultError`（`MIDAS CIVIL NX Empty Load Case Type`），**会话存活**。
⇒ **合法取值**的失败形态（业务级、可读）与**非法取值**的失败形态
（`second query is wrong`）**明显不同** —— 与 §1 的定案一致。

---

## 1bis. 顺带更正一处**过期口径**（R156：R132 **早已闭环**）

P164-b 收尾时写的续接提示词把

```text
③ 【R132 复核】接口层**没有**创建工况的 Operation ⇒ POST /DB/CNLD → 400 Not Found Key
   ⇒ **需在真机上复验**该闭环是否真的生效
```

列为下一批任务。**P164-d 只读复核既有证据**（**零**新实测）后确认这是**过期口径**：

| 项 | 内容 |
| --- | --- |
| **R132 行自己就写着** | 「✅ **P157 已按改法 A 落地** … **实测**：② `PASSED`（`POST /DB/STLD` → `POST /DB/CNLD`，两条 `200`，两个端点都**再读**确认在）」 |
| **证据** | `registry/live/flagship_chain_probe.json` 的 `substituted[7]`：`MODEL.LOAD.ASSIGN` · 两条请求 `status: 200` · `readback` = `DB.STLD` id `"1"` **present** + `DB.CNLD` id `"2"` **present** |
| **判据** | **铁律 ⓪**：不是状态码，是「**工况真的被建出来**」 |
| **判定用例** | `tests/test_midas_flagship_chain_p157.py::test_p157_r132_the_load_case_is_created_then_the_load_is_assigned` |

⚠️ **为什么值得单列一条**：若下一会话照着**过期**提示词去跑，就是**为一件已经验过的事
再动用户的真机** —— 而本批刚刚因为真机操作崩了 **4** 次。

**处置**：`docs/08` §4 的第 ① 项改为「✅ **已闭环，不必再跑**」+ 逐条给出证据路径与用例名；
`docs/07` 的 **R132 行原文保留**（**只改现状声称、不篡改历史记录**）。

---

## 2. 交付物

| 项 | 内容 |
| --- | --- |
| 工具 | `registry/tools/extract_result_modes.py`（离线 / 幂等 / 逐条可回溯） |
| 证据 | `registry/live/view_result_modes.json`（**36** 个取值 + 出处） |
| 判定 | `tests/test_midas_view_result_modes_p164d.py`（**10** 项） |
| 数据侧更正 | `registry/common/view/RESULTGRAPHIC.yaml` 头部写明**更正后的成因** + 缺口 + 恢复条件（`availability` **一行未改**） |
| 裁决登记 | `docs/07` §16.1 新增 **R155** + **R156**；**R150** 行加「成因已定 ⇒ 见 R155」指针（**原文保留**，不篡改历史） |
| 续接更正 | `docs/08` §4 第 ① 项（R132 **已闭环**）；§3 新增 **P164-d** 行 |
| `app/**` | **一行未改** |
| 实例 | **零请求**（本批**不**碰真机） |

---

## 2bis. P164-e：把真机那一步**做成一条命令**（工具就绪，**未**跑）

`VIEW.RESULTGRAPHIC` 的收口还差一次真机重测（需实例）。为让用户的一句「跑」变成一条命令，
且**不**重演 R150 的错误，新增探针 `registry/tools/probe_view_result_modes.py`：

| 机制 | 内容 |
| --- | --- |
| **默认零请求** | 不带 `--probe` 只预演（打印**表内**取值构成的请求体） |
| **硬闸门** | `CURRENT_MODE` 必须在 `registry/live/view_result_modes.json` 里，否则**发请求之前**退出码 **3** —— `displacement` 正好被这条挡住 |
| **崩溃族自检** | 探针**自带 `httpx.Client`**（`MidasHttpClient` 的护栏管不到它）⇒ 它**自己**查一次 `app/**` 的路径表；命中崩溃族 ⇒ 退出码 **4**（**不**打崩 MIDAS） |
| **工况名显式** | `--load-case`（默认 `DL`）—— `LOAD_CASE_COMB.NAME` 必须是项目里**真实存在**的工况 |
| **判据边界** | 只到「合法取值是否被接受」；视图的**真实效果**需改前/改后**截图对比**（`VIEW.CAPTURE`，R148 先例）⇒ 收口**由人裁决** |
| **不**动数据 | **不**改任何 `availability` |

判定（**离线、零请求**）= `tests/test_midas_view_result_modes_probe_p164e.py`（**6** 项：
`--check` 自洽 · 表外取值退出码 3 · 崩溃族路径退出码 4 · 自查复用 `app/**` 的表 · 预演不落盘）。

⚠️ **为什么不顺手把 `CURRENT_MODE` 枚举补进 Schema**：手册的 **36** 个取值**未必完整**
（**R151** 的教训：`POST.TABLE` 的枚举就不全）⇒ 补枚举会**误拦**原生其实接受的取值；
而这里要防的只是 `400`、**不是崩溃** ⇒ **代价不对等**。⇒ 如实留缺，等实测到的变体再补。

---

## 3. 闸门

```text
pytest -q                     1361 passed / 11 skipped / 0 failed
                              （P165-a 基线 1315 ⇒ +46 = P164-c 崩溃护栏 30 + P164-d 10 + P164-e 6）
ruff check app tests          All checks passed!
ruff format --check app tests 255 files already formatted
mypy app                      Success: no issues found in 185 source files
sync_manifest                 字段差异总数 = 0（幂等）
check_write_templates         ✅ 来源可复算 / 无未声明字段 / 前置链可执行
check_canonical_field_gap     ✅ 自洽
probe_design_config --check   ✅ 自洽
probe_view_result_modes --check  ✅ 离线自洽（36 个取值 · 被拒取值不在表内 · 不在崩溃族）
extract_result_modes          幂等（哈希不变）
```

---

## 4. 仍未闭环（**须裁决 / 须实例**）

| 项 | 需要什么 | 风险 |
| --- | --- | --- |
| **数据侧**：补全 `VIEW.RESULTGRAPHIC` 的请求 Schema（**36** 个变体：`CURRENT_MODE` 枚举 + 各变体的兄弟键） | **产品裁决**（属**契约 / 数据侧**作业，规模不小） | 无（纯数据） |
| **真机**：用**表内**取值在有分析结果的项目上重测 | 实例（`gen-local`）+ 一个**有结果**的项目 | 低（视图类 `POST`；**不**在原生崩溃护栏名单内） |
| **收益** | 收口后可解锁 **6** 个 `VIEW.*` Operation（`VIEW.RESULTGRAPHIC` 是唯一的挡点） | — |

⚠️ **建议顺序**：先做**真机重测**（拿到 `200` + 结果行 ⇒ 可收口 `availability`），
**再**按实测到的变体补 Schema —— 反过来（先补 36 个变体的 Schema）是**没有实测支撑**的大改。
