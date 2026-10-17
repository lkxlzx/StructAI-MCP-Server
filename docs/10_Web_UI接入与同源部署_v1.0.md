# 10 · Web UI 接入与同源部署 v1.0

> 目标：**同一个进程、同一个端口**同时提供 MCP、管理 API、健康探针与 Web UI。
> 前端原型：`StructAI MCP UI/web/`（零依赖静态站，无需构建）。

---

## 1. 一张图

```
浏览器
  │
  ├── GET  /                → StructAI MCP UI/web/（静态）
  ├── GET  /api/*           → 管理面（Bearer token）
  ├── GET  /livez /readyz /health
  └── POST /mcp             → MCP Streamable HTTP（Bearer token，9 Tool 不变）

FastAPI（app/interfaces/http/app.py）
  ├── create_health_router(HealthService)
  ├── create_api_router(ManagementPort)
  ├── /mcp  → _RestorePath(MCPHTTPMiddleware) → SDK Streamable HTTP
  └── /     → StaticFiles(ui_root)
```

同源 ⇒ **不需要 CORS**（`UI_CORS_ORIGINS` 留空）；跨源部署时填显式来源。

---

## 2. 启动

```bash
# 1) 首次：建库 + 种子（管理员口令只经环境变量注入）
$env:STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD = "你的口令"
python -m app.infrastructure.database.seed

# 2) 启动（同一端口：UI + API + MCP）
$env:UI_ROOT = "./StructAI MCP UI/web"
python -m app.main --transport http
```

浏览器打开 `http://<主机>:7860/` → 登录页 → 输入管理员账号 → 进入首页。

| 配置项 | 默认 | 说明 |
| --- | --- | --- |
| `UI_ROOT` | 空（不挂载） | 静态 UI 目录；留空 = 纯 API/MCP 模式 |
| `TEMPLATE_ROOT` | `./templates/gen_verification` | 参数化模板库 |
| `MANAGEMENT_IMPORT_ROOT` | `./data/management` | 模板生成的 JSON 落点（`MODEL.IMPORT` 只收服务器本地路径） |
| `UI_CORS_ORIGINS` | 空 | 逗号分隔的显式来源；同源部署留空 |

> ⚠️ 这 4 个字段是 **P181 显式新增**（17 → 21），已同步 `.env.example` 与
> `tests/test_infrastructure_p29_p35.py` 的字段断言（`docs/07` §16 R66 的既定升级路径）。

---

## 3. 管理 API

全部要求 `Authorization: Bearer <token>`；`/api/auth/login` 是唯一匿名端点。

| 方法 | 路径 | 返回 |
| --- | --- | --- |
| POST | `/api/auth/login` | `{token, user, tenant, roles, authentication_method}` |
| POST | `/api/auth/logout` | `{ok}` |
| GET | `/api/auth/me` | 身份 + 有效权限 |
| GET | `/api/status` | 服务 / 任务 / 客户端 / 注册表 / 模板摘要 |
| GET | `/api/stats` | 首页 5 张指标卡（由 `status` 派生） |
| GET | `/api/clients` | 软件实例（**不含**凭据值，只回显引用名） |
| GET | `/api/tasks?limit&offset` | 任务列表（租户作用域） |
| GET | `/api/tasks/{id}` | 任务 + 步骤 |
| POST | `/api/tasks/{id}/cancel` | 取消结果（不伪造终态） |
| GET | `/api/events?limit` | 审计链最近 N 条 |
| GET | `/api/registry` | 端点目录摘要（663 / 652 / 命名空间计数） |
| GET | `/api/endpoints?namespace&q&limit&offset` | 端点列表 |
| GET | `/api/endpoints/{key}` | 端点详情（含请求 Schema 原文） |
| GET | `/api/operations` | 73 个 Operation（名字 / Tool / 风险 / 执行模式） |
| GET | `/api/templates` | 模板库摘要 + 156 条列表 |
| GET | `/api/templates/{name}` | 模板参数表 |
| POST | `/api/templates/{name}/import` | 生成 JSON → `MODEL.IMPORT`（经 MCP） |
| POST | `/api/call` | 任意 Tool 调用（**同一条** 9 Tool 链） |

`/api/call` 的请求体与 MCP `tools/call` 的 arguments 同形：

```json
{"tool": "engineering_model_query", "operation": "MODEL.NODE.QUERY",
 "parameters": {}, "context": {"project_id": "...", "software_instance_id": "...", "model_id": "..."}}
```

响应 = `docs/02` §71 的 **13 键统一信封**（与 MCP 客户端拿到的完全一致）。

---

## 4. 前端接入点

| 文件 | 作用 |
| --- | --- |
| `web/scripts/api.js` | 管理 API 客户端；token 只存 `sessionStorage` |
| `web/scripts/live.js` | 把 `/api/*` 响应映射成页面数据结构；失败返回 `null` |
| `web/scripts/live-pages.js` | 把实时数据覆盖到已渲染视图（指标卡 / 事件 / 任务 / 客户端） |
| `web/scripts/pages/login.js` | 登录页（唯一匿名流程） |
| `web/scripts/pages/templates.js` | **参数化模板**：选族 → 选模板 → 填参数 → 生成并导入 |

**回落策略**：后端未启动 / 未登录时，页面仍按 `mock.js` 渲染（离线可看界面）；
拿到实时数据后只替换**数据区域**，布局与样式不动。

---

## 5. 参数化模板的 UI 流程

```
#/templates
  ├─ 左：族标签（17 个）+ 模板列表（156 个，来自 /api/templates）
  ├─ 右：参数表单（来自 /api/templates/{name} 的 parameters）
  └─ 生成并导入
        └─ POST /api/templates/{name}/import
              ├─ materialize（未知参数 / 类型不匹配 ⇒ 报错）
              ├─ 写服务器侧 JSON（MANAGEMENT_IMPORT_ROOT）
              └─ MCP engineering_doc / MODEL.IMPORT
```

导入是**合并语义**：同 id 覆盖，空表不清空已有行（P175 实测）。
改工况名会触发 MIDAS 级联改写引用它的 `LCNAME`（P180 实测）。

---

## 6. 验收

| 判据 | 命令 |
| --- | --- |
| 管理面鉴权 / 同源路由 / 模板导入 / 只读数据源 | `pytest tests/test_management_api_p181.py -q`（11 项） |
| MCP 传输不回归（含同源挂载） | `pytest tests/test_transport_p40_p41.py -q`（22 项） |
| 模板库 | `pytest tests/test_midas_model_template_p180.py -q`（12 项） |
| 全量 | `pytest -q`（1632 passed / 11 skipped，TEMP 指向可写目录） |
| 静态资源 | `GET /`、`/scripts/api.js`、`/styles/pages/templates.css` 均 200 |

---

## 7. 已知边界

- **AI 助手页仍是 mock**：没有 LLM 后端；`/api/call` 已就绪，接任意模型即可驱动。
- **任务监控 / 日志中心**在原型里是占位页；`/api/tasks`、`/api/events` 已提供数据。
- **文件上传未实现**：`MODEL.IMPORT` 只收服务器本地路径，模板导入由服务端写文件；
  浏览器直接上传模型文件需另开一个上传端点（**未做**）。
- **`desktop/`（Electron）未接入**：它加载同一份 `web/`，但窗口壳仍是原型状态。
- `desktop/node_modules/` 与 `desktop/dist/` **不进仓库**（`.gitignore`）。
