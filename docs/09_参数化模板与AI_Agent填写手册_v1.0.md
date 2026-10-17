# 09 · 参数化模板与 AI Agent 填写手册 v1.0

> 目标：**官方模型 → JSON 模板 → 改参数 → 经 MCP 导入 MIDAS → 跑通**。
> 模板库：`templates/gen_verification/`（156 个，来自 `D:\Program\MIDAS\MIDAS GEN NX\Gen Verification`）。

---

## 1. 这条链路是什么

```
Gen Verification/*.mgbx                官方样本（156 个，只读）
        │  DOC.OPEN（副本） + DOC.EXPORT
        ▼
.tmp_p180/exports/*.json               原生快照 {"DBG": {表: {id: 行}}}
        │  build_template（抽取工程参数，其余原样保留）
        ▼
templates/gen_verification/*.json      参数化模板（改 parameters 里的 value 即可）
        │  materialize（填回占位符）
        ▼
filled.json                            {"DBG": {...}}（可直接导入）
        │  MCP: engineering_doc / MODEL.IMPORT
        ▼
MIDAS 当前模型                          按写入值读回 = 判据
```

两个入口，**同一份模板**：

| 入口 | 谁来做 | 怎么做 |
| --- | --- | --- |
| AI Agent | 分析提示词 → 选模板 → 改参数 | 读 `index.json` 选族 → `--show` 看参数 → `--set` 填值 → `--fill` 出 JSON |
| 参数化前端 | 用户填表单 | 读模板的 `parameters` 渲染表单，提交后等价于 `--set` |

---

## 2. 模板结构

```jsonc
{
  "format": "structai.model_template",
  "version": 1,
  "meta": {
    "name": "Static-02",
    "family": "Static",
    "source": ".tmp_p180/exports/Static-02.json",
    "tables": ["ACTL", "BMLD", "CONS", ...],
    "row_counts": {"NODE": 3, "ELEM": 2, ...}
  },
  "parameters": {
    "material.1.elastic_modulus": {
      "value": 4320000.0,            // ← 默认值 = 样本原值，改这里
      "kind": "number",
      "unit": "force/length^2",
      "description": "弹性模量 E",
      "source": "MATL/1/PARAM[0].ELAST"
    }
  },
  "model": {                         // 原生 DBG 块，可参数化的标量用 ${参数名} 占位
    "MATL": {"1": {"PARAM": [{"ELAST": "${material.1.elastic_modulus}"}]}},
    ...
  }
}
```

**三条口径**：

1. `model` 里除了 `${...}` 占位符，其余**逐字保留**（含隐藏表 `THIK` / `RIGD` / `NMAS` / `SDSP` …）⇒ 导入后模型行为与样本一致。
2. `PJCF` / `CO_M` / `CO_S` / `CO_T` **不在模板内**：它们是会话元数据 / 颜色表，导入会污染当前项目。
3. 未知参数、类型不匹配、未知占位符一律**报错**（不猜、不静默忽略）。

---

## 3. 参数命名规则（AI Agent 必读）

| 前缀 | 含义 | 原生落点 |
| --- | --- | --- |
| `units.force` / `units.dist` / `units.heat` / `units.temper` | 单位系统 | `UNIT/FORCE` … |
| `material.<id>.name` / `.type` | 材料名 / 类型 | `MATL/NAME` / `TYPE` |
| `material.<id>.elastic_modulus` / `.poisson_ratio` / `.density` / `.mass_density` / `.thermal_coefficient` | 材料参数 | `MATL/PARAM[0].ELAST` … |
| `section.<id>.name` / `.shape` | 截面名 / 形状代码 | `SECT/SECT_NAME` / `SECT_BEFORE.SHAPE` |
| `section.<id>.vsize.<i>` | 截面尺寸数组第 i 项 | `SECT_BEFORE.SECT_I.vSIZE[i]` |
| `node.<id>.x` / `.y` / `.z` | 节点坐标（仅 ≤64 节点的小模型） | `NODE/X` … |
| `support.<id>.constraint` | 7 位约束串（DX DY DZ RX RY RZ RW，1=约束；仅 ≤24 行） | `CONS/ITEMS[0].CONSTRAINT` |
| `load_case.<id>.name` | 荷载工况名 | `STLD/NAME` |
| `nodal_load.<node>.0.fx` … `.mz` | 节点荷载分量 | `CNLD/.../FX` … |
| `beam_load.<elem>.0.p.<i>` | 梁荷载数组（UNILOAD 的 P[0] 是均布值） | `BMLD/.../P[i]` |
| `body_force.<id>.fv.<i>` | 自重系数（X/Y/Z） | `BODF/FV[i]` |
| `combination.<id>.name` / `.factor.<j>` | 荷载组合名 / 第 j 项系数 | `LCOM-*/NAME` / `vCOMB[j].FACTOR` |
| `analysis.gravity` | 重力加速度 | `STYP/GRAV` |
| `analysis.eigen.frequency_count` / `.iterations` / `.tolerance` | 特征值控制 | `EIGV/iFREQ` … |
| `analysis.buckling.mode_count` / `.factor.<j>` | 屈曲控制 | `BUCK/MODE_NUM` … |
| `analysis.nonlinear.steps` / `.max_iterations` | 非线性控制 | `NLCT/NUMBER_STEPS` … |

> 大模型（节点 > 64）不做逐坐标参数化 —— 模板里保留字面坐标，改几何请换用小模型模板或直接编辑 `model`。

---

## 4. 模板库索引

`templates/gen_verification/index.json`：

```jsonc
{
  "count": 156,
  "families": {
    "Static":   ["Static-01", ..., "Static-47-2"],
    "Eigen":    ["Eigen-01", ...],
    "Buckling": [...],
    "Cable": [...], "GNL": [...], "MNL": [...], "PDelta": [...],
    "RS": [...], "TH": [...], "TS": [...], ...
  },
  "templates": [
    {"name": "Static-02", "family": "Static", "parameters": 55, "tables": 214,
     "key_parameters": ["units.force", "material.1.elastic_modulus", ...]}
  ]
}
```

选模板的经验规则：

| 提示词特征 | 选什么 |
| --- | --- |
| 静力 / 简支梁 / 桁架 / 框架 | `Static-*` |
| 自振频率 / 模态 | `Eigen-*` |
| 屈曲 / 特征值屈曲 | `Buckling-*` |
| 索 / 悬索 | `Cable *` |
| 几何非线性 / 大变形 | `GNL-*` |
| 材料非线性 | `MNL-*` / `Masonry-*` |
| 二阶效应 | `PDelta-*` |
| 反应谱 | `RS-*` |
| 时程 | `TH-*` / `TS-*` |
| 移动荷载 | `ML-*` |
| 水化热 | `Hydration-01` |

---

## 5. AI Agent 操作流程

### 5.1 选模板 + 看参数

```bash
python registry/tools/model_template_p180.py --show Static-02
```

### 5.2 按提示词填参数并生成导入文件

```bash
python registry/tools/model_template_p180.py --fill Static-02 \
  --set material.1.elastic_modulus=200000000000 \
  --set section.1.vsize.0=0.4 \
  --set section.1.vsize.1=0.2 \
  --set beam_load.1.0.p.0=-25.5 \
  --out .tmp_p180/my-model.json
```

- `--set` 的取值先按 JSON 解析（数字 / 布尔 / 数组），失败才当字符串；
- 未知参数会**报错并给出相近名**；
- 输出只列出**真的改变**的参数（默认值 → 新值）。

### 5.3 经 MCP 导入到 MIDAS

MCP Tool 调用（与探针同一契约）：

```jsonc
{
  "tool": "engineering_doc",
  "operation": "MODEL.IMPORT",
  "parameters": { "project_path": "E:\\MCP\\MMCP\\.tmp_p180\\my-model.json" },
  "confirmation_token": "<HIGH 风险操作需现签>"
}
```

导入后**必须读回**（判据 = 效果，不是状态码）：

```jsonc
// engineering_model_query / MODEL.NODE.QUERY 或裸 GET /db/NODE
{"tool": "engineering_model_query", "operation": "MODEL.NODE.QUERY", "parameters": {}}
```

### 5.4 可选：从当前 MIDAS 模型反向导出新模板

```jsonc
// 1) 导出当前模型
{"tool": "engineering_doc", "operation": "MODEL.EXPORT",
 "parameters": {"project_path": "E:\\...\\export.json"}}
// 2) 生成模板
//    python registry/tools/model_template_p180.py 只处理 .tmp_p180/exports；
//    新模型放到该目录后跑 --build 即可并入模板库
```

---

## 6. 工程注意事项（实测）

| # | 事实 | 后果 |
| --- | --- | --- |
| 1 | `DOC.IMPORT` 是**合并**语义 | 同 id 覆盖；**空表不清空**已有行。要「全新模型」不能靠导入空表。 |
| 2 | 导入 `PJCF` 会改写项目名 | 模板已排除 `PJCF` / `CO_*`。**不要**手工加回去。 |
| 3 | 改工况名（`STLD/NAME`）原生**级联** | `BMLD` / `CNLD` / `LCOM-*` 里引用它的 `LCNAME` 自动改名（引用完整性，不是污染）。 |
| 4 | 未改动的截面导入后派生量有**浮点抖动** | `SECT_I.STIFF.Y/Z` 可能差 1 ulp（原生按尺寸重算）⇒ 对比用数值等价（rel 1e-9），不要逐字节比。 |
| 5 | 单位是**解释前提** | `units.*` 改了，所有数值按新口径解释；先定单位再填数。 |
| 6 | `MODEL.EXPORT` 是 ASYNC（实测 47.8s / 全模型） | 不要按 30s 预算等；小模型 4s 左右。 |
| 7 | 不要在无路径项目上停 | 先 `SAVE_AS`/`OPEN`；`GET /db/PJCF` 的 `FILE_NAME` ≠ `无标题` 才算干净（R144）。 |

---

## 7. 复算与证据

| 动作 | 命令 | 判据 |
| --- | --- | --- |
| 批量导出 156 个样本 | `python registry/tools/export_gen_verification_p180.py --probe` | 156/156 落盘 · 0 失败 · 收尾有路径 |
| 建模板库 | `python registry/tools/model_template_p180.py --build` | 156 模板 · 17 族 |
| 模板自洽 | `python registry/tools/model_template_p180.py --check` | 逐模板往返无损 + 序列化稳定 |
| 端到端 | `python registry/tools/probe_model_template_e2e_p180.py --probe` | 5 个参数按写入值读回 · 4 项阴性对照 · 收尾有路径 |
| 离线复算 | 上述三条加 `--check` | 零请求 |

证据：`registry/live/gen_verification_exports_p180.json` · `registry/live/model_template_e2e_p180.json`；
判定：`tests/test_midas_model_template_p180.py`（12 项）。

---

## 8. 已知边界

- 大模型（节点 > 64）不逐坐标参数化；约束行 > 24 不逐行参数化 —— 这是**可读性**取舍，不是能力缺失（`model` 仍可手改）。
- 模板只覆盖**建模 + 分析控制**；结果读取 / 设计验算仍走既有 `RESULT.*` / `DESIGN.*` Operation。
- `TAPERED` / `COMBINED` 截面的 `vSIZE` 语义未逐一命名，统一用 `dim<i>`（取值含义需查样本）。
- 模板版本 = 1；改结构必须 `TEMPLATE_VERSION + 1` 并提供迁移说明。
