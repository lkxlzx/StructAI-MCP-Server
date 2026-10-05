# archive/legacy_v1 —— 非规范性历史资料

> ⚠️ **本目录下全部文件均为非规范性（NON-NORMATIVE）资料。**
> **不作为开发依据，不作为准则。**

## 1. 为什么归档

本目录文件是 StructAI 项目**早期（V1）**阶段产出的规范草案、实测记录与清单，
其内容已被 **V2 规范体系**与**机器可读 Endpoint Registry**取代。

保留它们只为两件事：

1. **可追溯性** —— 说明 `registry/` 中每个端点的知识来源与实测经过；
2. **审计留痕** —— 保留 live 冒烟原始结论、两次事故与恢复过程、修复项 F1–F21 的实施记录。

## 2. 唯一开发依据（规范性）

| 依据 | 内容 |
| --- | --- |
| `docs/01_STRUCTAI_MCP_V2_ARCHITECTURE.md` | 总体架构、分层解耦、数据库设计 |
| `docs/02_STRUCTAI_MCP_V2_CORE_IMPLEMENTATION.md` | Core 实现规范（Python / 模块 / 蓝图） |
| `docs/03_STRUCTAI_MCP_V2_MCP_RUNTIME.md` | MCP Runtime 与 9 个 Tool 的入参/出参规范 |
| `docs/04_STRUCTAI_MCP_V2_MIDAS_ADAPTER.md` | MIDAS Adapter 规范（种子仅供参考，见下） |
| `docs/05_STRUCTAI_MCP_V2_ADAPTER_SDK.md` | Adapter SDK 规范（多厂商接入） |
| `docs/06_STRUCTAI_MCP_V2_DEPLOYMENT_TEST_ACCEPTANCE.md` | 部署 / 测试 / 验收（无独立内容，为 02+03+04 汇编） |
| `docs/07_开发方案与任务续接_v1.0.md` | 开发方案、Operation→API 映射、P01–P48 任务卡 |
| `registry/` | **MIDAS API 的唯一权威来源**（636 端点定义 + 616 JSON Schema） |

> `docs/04` §14 的 66 条种子全部为 `PARTIAL`，`verification_status != VERIFIED`，
> 生产路径会被 `RegistryMappingNotVerified` 拒绝；**涉及 MIDAS API 一律以 `registry/` 为准**。

## 3. 归档清单

### 3.1 规范草案类（已被 `docs/01`–`docs/07` 取代）

| 文件 | 原用途 | 取代者 |
| --- | --- | --- |
| `StructAI_MIDAS_MCP_完整开发文档_v1.0.md` | V1 主开发文档（产品/连接/Adapter/Registry/工程/设计/图形/计算书） | `docs/01`–`docs/06` |
| `StructAI_MIDAS_MCP_快速响应与实时反馈架构补充文档_v1.0.md` | V1 执行与反馈层 | `docs/02`（执行流水线 26 步）、`docs/03` |
| `StructAI_MIDAS_MCP_项目框架图_v1.0.md` | V1 架构审查用框架图 | `docs/01` §分层 |

### 3.2 知识层实测记录类（已沉淀进 `registry/`）

| 文件 | 原用途 | 现状 |
| --- | --- | --- |
| `StructAI_MIDAS_MCP_GEN_NX_API_实测补充文档_v1.0.md` | GEN NX 知识层补实（501 个逻辑 key 实测） | 已并入 `registry/`（`common/` + `products/gen_nx/`） |
| `StructAI_MIDAS_MCP_CIVIL_NX_API_实测补充文档_v1.0.md` | CIVIL NX 知识层 + 产品差异矩阵 | 已并入 `registry/`（`products/civil_nx/`） |
| `StructAI_MIDAS_MCP_GEN_NX_Endpoint清单_v1.0.csv` | GEN NX 501 行端点清单（生成器输入） | 已由 `registry/manifest.json` 取代 |
| `StructAI_MIDAS_MCP_CIVIL_NX_Endpoint清单_v1.0.csv` | CIVIL NX 379 行端点清单 | 同上 |

### 3.3 实测与修复留痕类（证据性，非准则）

| 文件 | 原用途 | 现状 |
| --- | --- | --- |
| `StructAI_MIDAS_MCP_Live冒烟测试报告_v1.0.md` | 3 个真实实例逐端点实测报告（附录 A–G） | 证据留痕；结论已写入 `registry/` 的 `availability` / `verified_on` |
| `StructAI_MIDAS_MCP_Live冒烟失败清单_v1.0.csv` | 46 个失败端点及归因分组 | 同上 |
| `StructAI_MIDAS_MCP_统一修复计划_v1.0.md` | 修复项 F1–F21 汇总与实施记录 | 全部已落地，实施记录见 §11 |

## 4. 使用约束

- ❌ **不得**把本目录任何结论当作实现依据、接口契约或验收准则；
- ❌ **不得**用本目录的端点清单替代 `registry/`；
- ✅ 仅可用于**追溯来源**与**审计核对**；
- ✅ 若本目录与 `docs/` / `registry/` 冲突，**一律以 `docs/` / `registry/` 为准**。

---

| 项 | 值 |
| --- | --- |
| 归档日期 | 2026-10-05 |
| 归档范围 | 根目录 `StructAI_MIDAS_MCP_*` 全部文件（7 `.md` + 3 `.csv`） |
| 归档原因 | 项目定位与规范体系升级至 V2；根目录 V1 文档不再作为开发依据 |
