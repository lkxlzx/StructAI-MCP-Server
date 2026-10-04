# MIDAS API 手册覆盖对照：Civil Designer 是否被 Online Manual 包含

> 核对日期：2026-10-04  
> 核对对象：
> ① `MIDAS_API_Online_Manual_完整API手册_v1.0.md`（来源：MIDAS API Online Manual，282 个二级页面）  
> ② `G:\midas Civil Designer - API`（midas Civil Designer Open API JSON 手册）

## 结论

**不包含。** Civil Designer 是**第三个独立产品**，不在 MIDAS API Online Manual 的覆盖范围内。

硬证据：

| 检查项 | 结果 |
| --- | --- |
| Online Manual 索引页原始内容中 “Designer” 出现次数 | **0** |
| 生成的手册（282 页）中 “Designer” 出现次数 | **0** |
| 生成的手册中 `OPRT`（Designer 独有命名空间）出现次数 | **0** |
| Online Manual 索引页中 “CIVIL NX” / “GEN NX” 出现次数 | 475 / 113 |
| Designer 手册自述主题 | midas Civil Designer Open API（REST / **WebSocket**）JSON 接口手册 |
| Designer 手册规模 | 54 个页面 · 264 个标题 · 120 张表格 · 108 段代码示例 |

## 1. 三份产品手册的范围对照

| 维度 | MIDAS API Online Manual | Civil Designer API |
| --- | --- | --- |
| 覆盖产品 | CIVIL NX + GEN NX（NX series） | **Civil Designer** |
| 来源 | Zendesk Help Center（英文官方） | wolai `mpkY3qX7PkqYj7pZYK9LVJ`（中文） |
| 二级页面数 | 282 | 54（其中 38 个为 API 端点页） |
| 命名空间 | DOC / DB / **OPE** / VIEW / POST | DOC / DB / **OPRT** / VIEW / POST |
| 传输协议 | REST | REST + **WebSocket** |
| URI 风格 | `doc/NEW`、`db/NODE`（无前导斜杠） | `/DOC/OPEN`、`/DB/NODE`（**有前导斜杠**，全大写） |
| 页面字段 | Input URI / Active Methods / JSON Schema / Examples / Request Examples / Response Examples / Specifications / Available Product | 接口URL / 支持的方法 / 请求示例 / Post请求参数 |
| 产品定位 | 通用结构分析（建筑 + 桥梁） | 桥梁**设计校核与计算书**（依赖 Civil NX） |

> 注意命名空间差异：Online Manual 用 **OPE**（operation），Designer 用 **OPRT**（operation）。两者语义相近但**不是同一套端点**，Registry 中必须分开建模。

## 2. 重叠分析

Designer 共 **38** 个 API 端点，其中：

- URI 名称与 Online Manual 相同：**12** 个
- Online Manual 中完全不存在：**26** 个（68.4%）

### 2.1 URI 同名（12 个）——但参数不同，不能复用 Online Manual 的内容

| Designer URI | 中文名 | Online Manual 中同名端点 | 说明 |
| --- | --- | --- | --- |
| `DOC/OPEN` | 打开文件 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DOC/SAVE` | 保存激活文档 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DOC/SAVEAS` | 另存为 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DOC/CLOSE` | 关闭激活文档 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DB/NODE` | 节点 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DB/ELEM` | 单元 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `DB/SPAN` | 跨度 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `VIEW/ACTIVE` | 激活 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `VIEW/ANGLE` | 视角 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `VIEW/DISPLAY` | 显示 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `VIEW/CAPTURE` | 截图 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |
| `POST/TABLE` | 表格提取 | ✅ 存在 | **产品不同**，Designer 的请求示例与参数表须以 Designer 手册为准 |

> 这 12 个仅是**路径字符串巧合**：例如 `DOC/OPEN` 在 Online Manual 中是 `doc/OPEN`（NX 系列项目文件），
> 在 Designer 中是打开 `.cdn` 设计文件（`FilePath` 参数指向 `2-001.cdn`）。**不可跨产品复用。**

### 2.2 Online Manual 中不存在（26 个）

| 命名空间 | URI | 方法 | 中文名 |
| --- | --- | --- | --- |
| DOC | `DOC/IMPORTCML` | Post | 导入Cml文件 |
| DOC | `DOC/IMPORTMRB` | Post | 导入mrb文件 |
| DOC | `DOC/IMPORTFILE` | Post | 导入Cml、mrb文件 |
| DOC | `DOC/UPDATEFILE` | Post | 更新Cml、mrb文件 |
| DOC | `DOC/OUTFLOW` | Post | 更新文件至Civil NX |
| DOC | `DOC/EXPORTFILE` | Post | 导出文件至mct |
| DOC | `DOC/CLOSEALL` | Post | 关闭所有文档 |
| DOC | `DOC/EXIT` | Post | 退出程序 |
| DOC | `DOC/ACTIVE` | Post | 激活文件 |
| DOC | `DOC/UNIT` | Get, Put | 单位 |
| DB | `DB/MODULE` | — | 模块 |
| DB | `DB/DCOD` | — | 规范设置 |
| DB | `DB/MEMB` | — | 构件 |
| DB | `DB/LCOM` | Get | 荷载组合 |
| DB | `DB/LENG` | — | 参数-自由长度 |
| DB | `DB/LENG` | — | 参数-计算长度系数 |
| DB | `DB/CWRC` | — | 参数-裂缝宽度系数 |
| DB | `DB/BTCP` | — | 参数-盖梁验算 |
| DB | `DB/CAPSIZE` | — | 倾覆数据 |
| DB | `DB/TRPT` | — | 整体计算书设置 |
| OPRT | `OPRT/DESIGN` | Post | 运行设计 |
| OPRT | `OPRT/LCOM` | Post | 自动生成荷载组合 |
| OPRT | `OPRT/EFFSECTION` | Post | 自动生成有效截面 |
| OPRT | `OPRT/CAPSIZE` | Post | 自动生成倾覆参数 |
| OPRT | `OPRT/DETAILREPORT` | Post | 生成详细计算书 |
| OPRT | `OPRT/TOTALREPORT` | Post | 生成整体计算书 |

## 3. Civil Designer 全部 API 端点清单

| # | 命名空间 | URI | 方法 | 中文名 | 请求示例 | 参数行数 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | DOC | `DOC/OPEN` | Post | 打开文件 | ✅ | 1 |
| 2 | DOC | `DOC/SAVE` | Post | 保存激活文档 | ✅ | 0 |
| 3 | DOC | `DOC/SAVEAS` | Post | 另存为 | ✅ | 1 |
| 4 | DOC | `DOC/IMPORTCML` | Post | 导入Cml文件 | ✅ | 1 |
| 5 | DOC | `DOC/IMPORTMRB` | Post | 导入mrb文件 | ✅ | 1 |
| 6 | DOC | `DOC/IMPORTFILE` | Post | 导入Cml、mrb文件 | ✅ | 2 |
| 7 | DOC | `DOC/UPDATEFILE` | Post | 更新Cml、mrb文件 | ✅ | 2 |
| 8 | DOC | `DOC/OUTFLOW` | Post | 更新文件至Civil NX | ✅ | 1 |
| 9 | DOC | `DOC/EXPORTFILE` | Post | 导出文件至mct | ✅ | 2 |
| 10 | DOC | `DOC/CLOSE` | Post | 关闭激活文档 | ✅ | 0 |
| 11 | DOC | `DOC/CLOSEALL` | Post | 关闭所有文档 | ✅ | 0 |
| 12 | DOC | `DOC/EXIT` | Post | 退出程序 | ✅ | 0 |
| 13 | DOC | `DOC/ACTIVE` | Post | 激活文件 | ✅ | 1 |
| 14 | DOC | `DOC/UNIT` | Get, Put | 单位 | ✅ | 2 |
| 15 | DB | `DB/NODE` | Get | 节点 | ✅ | 4 |
| 16 | DB | `DB/ELEM` | Get | 单元 | ✅ | 5 |
| 17 | DB | `DB/MODULE` | — | 模块 | ✅ | 10 |
| 18 | DB | `DB/DCOD` | — | 规范设置 | ✅ | 242 |
| 19 | DB | `DB/SPAN` | — | 跨度 | ✅ | 14 |
| 20 | DB | `DB/MEMB` | — | 构件 | ✅ | 16 |
| 21 | DB | `DB/LCOM` | Get | 荷载组合 | ✅ | 12 |
| 22 | DB | `DB/LENG` | — | 参数-自由长度 | ✅ | 0 |
| 23 | DB | `DB/LENG` | — | 参数-计算长度系数 | ✅ | 0 |
| 24 | DB | `DB/CWRC` | — | 参数-裂缝宽度系数 | ✅ | 4 |
| 25 | DB | `DB/BTCP` | — | 参数-盖梁验算 | ✅ | 0 |
| 26 | DB | `DB/CAPSIZE` | — | 倾覆数据 | ✅ | 18 |
| 27 | DB | `DB/TRPT` | — | 整体计算书设置 | ✅ | 35 |
| 28 | OPRT | `OPRT/DESIGN` | Post | 运行设计 | ✅ | 5 |
| 29 | OPRT | `OPRT/LCOM` | Post | 自动生成荷载组合 | ✅ | 46 |
| 30 | OPRT | `OPRT/EFFSECTION` | Post | 自动生成有效截面 | ✅ | 7 |
| 31 | OPRT | `OPRT/CAPSIZE` | Post | 自动生成倾覆参数 | ✅ | 1 |
| 32 | OPRT | `OPRT/DETAILREPORT` | Post | 生成详细计算书 | ✅ | 16 |
| 33 | OPRT | `OPRT/TOTALREPORT` | Post | 生成整体计算书 | ✅ | 4 |
| 34 | VIEW | `VIEW/ACTIVE` | Post | 激活 | ✅ | 3 |
| 35 | VIEW | `VIEW/ANGLE` | Post | 视角 | ✅ | 1 |
| 36 | VIEW | `VIEW/DISPLAY` | Post | 显示 | ✅ | 478 |
| 37 | VIEW | `VIEW/CAPTURE` | Post | 截图 | ✅ | 4 |
| 38 | POST | `POST/TABLE` | Post | 表格提取 | ✅ | 460 |

按命名空间统计：

| 命名空间 | 端点数 |
| --- | --- |
| DB | 13 |
| DOC | 14 |
| OPRT | 6 |
| POST | 1 |
| VIEW | 4 |
| **合计** | **38** |

### 3.1 OPRT 命名空间（Designer 独有，6 个）

这是 Designer 最有价值的部分——**设计校核与计算书生成**：

| URI | 中文名 | 能力 |
| --- | --- | --- |
| `OPRT/DESIGN` | 运行设计 | 触发设计校核 |
| `OPRT/LCOM` | 自动生成荷载组合 | 按规范自动生成组合 |
| `OPRT/EFFSECTION` | 自动生成有效截面 | 有效截面计算 |
| `OPRT/CAPSIZE` | 自动生成倾覆参数 | 倾覆验算参数 |
| `OPRT/DETAILREPORT` | 生成详细计算书 | 构件级计算书 |
| `OPRT/TOTALREPORT` | 生成整体计算书 | 工程级计算书 |

### 3.2 Designer 的 DB 层（13 个）——桥梁设计参数

| URI | 中文名 | 说明 |
| --- | --- | --- |
| `DB/NODE` | 节点 | — |
| `DB/ELEM` | 单元 | — |
| `DB/MODULE` | 模块 | — |
| `DB/DCOD` | 规范设置 | — |
| `DB/SPAN` | 跨度 | — |
| `DB/MEMB` | 构件 | — |
| `DB/LCOM` | 荷载组合 | — |
| `DB/LENG` | 参数-自由长度 | — |
| `DB/LENG` | 参数-计算长度系数 | — |
| `DB/CWRC` | 参数-裂缝宽度系数 | — |
| `DB/BTCP` | 参数-盖梁验算 | — |
| `DB/CAPSIZE` | 倾覆数据 | — |
| `DB/TRPT` | 整体计算书设置 | — |

## 4. 与 GEN / CIVIL Registry key 的比对

| Designer URI | GEN key | CIVIL key | 中文名 |
| --- | --- | --- | --- |
| `DOC/OPEN` | ✅ | ✅ | 打开文件 |
| `DOC/SAVE` | ✅ | ✅ | 保存激活文档 |
| `DOC/SAVEAS` | ✅ | ✅ | 另存为 |
| `DOC/CLOSE` | ✅ | ✅ | 关闭激活文档 |
| `DB/NODE` | ✅ | ✅ | 节点 |
| `DB/ELEM` | ✅ | ✅ | 单元 |
| `DB/SPAN` | ✅ | ✅ | 跨度 |
| `DB/MEMB` | ✅ | — | 构件 |
| `DB/LENG` | ✅ | — | 参数-自由长度 |
| `DB/LENG` | ✅ | — | 参数-计算长度系数 |
| `VIEW/ACTIVE` | ✅ | ✅ | 激活 |
| `VIEW/ANGLE` | ✅ | ✅ | 视角 |
| `VIEW/DISPLAY` | ✅ | ✅ | 显示 |
| `VIEW/CAPTURE` | ✅ | ✅ | 截图 |
| `POST/TABLE` | — | ✅ | 表格提取 |

> 结论同上：**key 名相同不等于语义相同**。这些命中只说明命名一致，参数与行为须以各自手册为准。

## 5. 对 StructAI 架构的影响

1. **Registry 需要第三个 Product**：`registry/products/civil_designer/`（38 个 key），Common 层不变。
2. **命名空间枚举需扩展**：`Namespace` 必须支持 `OPRT`，不能假设只有 `OPE`。
3. **协议层需扩展**：Designer 支持 **WebSocket**，主文档 §126 只定义了 `--stdio` / `--http`；若接入 Designer 的长任务推送，需补 WebSocket 客户端（与补充文档 §40 的「后续新增 WebSocket / SSE」条目呼应）。
4. **URI 风格差异需归一化**：Designer 写 `/DOC/OPEN`（前导斜杠 + 全大写），NX 系列写 `doc/OPEN`。Adapter 层须做归一化，并在 Registry 中保存原文。
5. **产品定位不同**：Designer 是**桥梁设计校核工具**（依赖 Civil NX 的模型），其 `OPRT/DESIGN` + `OPRT/*REPORT` 与主文档 §65 Design Engine、§74 Report Engine 高度重叠。需明确：**是让 StructAI 自己算设计，还是调用 Designer 算？** 这是架构级决策。

## 6. 建议

| 选项 | 说明 |
| --- | --- |
| A. 单独成册 | 按 Online Manual 的 6 段式格式，把 Designer 的 38 个端点整理成 `MIDAS_Civil_Designer_API_手册_v1.0.md`（含接口URL / 支持的方法 / 请求示例 / Post请求参数 + JSON Schema 若有） |
| B. 合并成总手册 | 把三份（Online Manual 282 + Designer 38）合成一份带产品标记的总手册 |
| C. 只入 Registry | 不生成手册，直接把 38 个 key 转成 `registry/products/civil_designer/**.yaml` |

> 本核对只回答问题「是否包含」，未改动任何既有手册内容。