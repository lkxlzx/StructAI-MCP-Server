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

### 3.1 P185：客户端与系统设置（新增）

写操作（`POST` / `PUT` / `DELETE`）与敏感读取要求有效权限含 **`SYSTEM_ADMIN`**；
只读列表仍允许任意已登录用户。访问控制（白 / 黑名单 + 频率限制）在登录与写操作上生效。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/clients/options` | 新增 / 编辑客户端的候选值（软件 / 产品 / 版本 / 状态） |
| POST | `/api/clients` | 登记实例（自动补齐 software → product → version 链） |
| PUT | `/api/clients/{id}` | 更新实例（名称 / 产品 / 版本 / 地址 / 凭据引用 / 状态 / 描述） |
| DELETE | `/api/clients/{id}` | 删除实例（清理不再被引用的孤儿链） |
| POST | `/api/clients/{id}/test` | 连接测试（已绑定 Adapter ⇒ 健康检查；仅地址 ⇒ HTTP 探测） |
| POST | `/api/clients/{id}/connect` | **连接实例**（`plugins.adapter_class_for()` 按需发现/注册 Adapter → 绑定 → 连接 → 健康检查 → 回写 `CONNECTED`/`DEGRADED`）；`SYSTEM_ADMIN` |
| POST | `/api/clients/{id}/disconnect` | **断开实例**（幂等）；`SYSTEM_ADMIN` |
| GET | `/api/clients/{id}/events` | 连接测试 / 生命周期事件（本机运维库） |
| POST | `/api/users/password/check` | 按「密码策略」校验口令（不回显） |
| POST | `/api/roles` / DELETE `/api/roles/{id}` | 新建 / 删除角色（系统管理员、仍被引用的角色拒绝） |
| POST | `/api/data/backups/{id}/restore` | 从备份恢复（先自动生成 pre-restore 备份） |
| GET | `/api/data/backups/{id}/download` | 下载备份（zip） |
| POST | `/api/data/purge` | 清空业务数据（保留管理员 / 角色 / 软件注册表；审计不删） |
| POST | `/api/data/import` | 导入导出的设置分区 |
| GET | `/api/logs` | 运行日志尾部（`STRUCTAI_LOG_DIR` 或 `<数据目录>/logs`） |
| GET | `/api/fs/browse` | 目录浏览（选择目录用） |
| POST | `/api/service/control` | `stop` / `restart`（重启 = 进程内 `execv`） |

### 3.2 P186-C：端点表补全（对齐 `app/interfaces/http/management_routes_*.py`）

> ⚠️ 本节补齐 §3 / §3.1 **此前漏登**、但代码里**实际存在**的端点（P186-C 核对交付）。
> 权限口径同 §3.1：写操作与敏感读取要求 **`SYSTEM_ADMIN`**；只读列表允许任意已登录用户。
> 全部前缀 `/api`；表格列出时省略前缀。

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/users` | 登录用户 | 用户列表 |
| POST | `/users` | SYSTEM_ADMIN | 新建用户（口令策略校验） |
| PUT | `/users/{id}` | SYSTEM_ADMIN | 更新用户（角色 / 状态） |
| DELETE | `/users/{id}` | SYSTEM_ADMIN | 删除用户 |
| POST | `/users/password/check` | SYSTEM_ADMIN | 按密码策略校验口令（不回显） |
| POST | `/auth/password` | 登录用户 | 当前用户改密（校验旧口令 + 策略） |
| GET | `/roles` | 登录用户 | 角色列表 + 权限 |
| PUT | `/roles/{id}` | SYSTEM_ADMIN | 更新角色权限 |
| GET | `/models` | 登录用户 | 模型（LLM）来源列表（**不**回显密钥值，只报是否已配置 + 尾部掩码） |
| PUT | `/models` | SYSTEM_ADMIN | 替换模型配置 |
| POST | `/models/{id}/test` | SYSTEM_ADMIN | 模型连通性测试 |
| GET | `/settings` | 登录用户 | 系统设置（口令策略 / 通知 / 安全；**非** secret 原值） |
| PUT | `/settings/{section}` | SYSTEM_ADMIN | 更新某设置分区 |
| POST | `/settings/reset` | SYSTEM_ADMIN | 重置设置为默认 |
| POST | `/notify/test` | SYSTEM_ADMIN | 发送测试通知（SMTP 凭据只读 `STRUCTAI_SMTP_PASSWORD`） |
| GET | `/updates/check` | 登录用户 | 版本检查（只报当前 + 是否有更新） |
| GET | `/security/overview` | 登录用户 | 安全概览（登录失败 / 告警 / 审计计数） |
| GET | `/data/stats` | 登录用户 | 数据库 / 存储 / 表行数 / 备份摘要 |
| GET | `/data/export` | SYSTEM_ADMIN | 导出设置分区（**不含** secret 值） |
| POST | `/data/backup` | SYSTEM_ADMIN | 立即备份（SQLite backup API；含设置库） |
| GET | `/data/backups` | 登录用户 | 备份记录列表 |
| DELETE | `/data/backups/{id}` | SYSTEM_ADMIN | 删除备份 |
| POST | `/data/cleanup` | SYSTEM_ADMIN | 清理过期备份 / 产物（**不**删审计链） |

> ⚠️ **数据安全底线**：`cleanup` / `purge` **永不**删除审计链（`docs/02` §29 / §45）；
> `purge` 保留管理员 / 角色 / 软件注册表；口令只存 Argon2id 哈希；模型 key / SMTP 口令
> 只经环境变量注入，管理面只报「是否已配置 + 尾部掩码」，**不**回显原值。

**设置落点**：`MANAGEMENT_IMPORT_ROOT/settings.db`（独立 SQLite 文件）。Core 的
24 张表**不新增**（`docs/07` §4.3）；客户端描述、连接事件、口令历史都在该运维库。
口令历史只存 Argon2id 哈希；SMTP 口令只从 `STRUCTAI_SMTP_PASSWORD` 读取。

**前端生效项**：主题（浅色 / 深色 / 跟随系统）、显示密度、每页条数、动画开关、
紧凑侧栏都会立即作用到页面（`scripts/preferences.js`）；通知方式决定页面提示是否弹出。

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
| 客户端 CRUD / 连接测试 / 角色增删 / 口令策略 / 备份恢复 / 导入 / 日志 / 目录浏览 / 管理员门 | `pytest tests/test_management_clients_p185.py -q`（16 项） |
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
- **服务「重启」是进程内 `execv`**：只适用于本进程直接启动的部署；容器 / systemd
  下应由编排层重启（界面会如实返回 `applied=true` 但重启动作交给进程管理器）。
- **访问控制的频率限制是进程内滑动窗口**：多进程 / 多节点部署需要外部限流。
- **SMTP 口令只从环境变量读取**：界面不提供口令输入框，避免明文密钥入库。
- **`desktop/`（Electron）未接入**：它加载同一份 `web/`，但窗口壳仍是原型状态。
- `desktop/node_modules/` 与 `desktop/dist/` **不进仓库**（`.gitignore`）。
