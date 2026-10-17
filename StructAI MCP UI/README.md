# MIDAS MCP 管理器 · 界面还原工程

按 `ui/` 目录中的 22 张 UI 原稿（1536×1024）逐个还原为可运行产品界面。
**同一份前端代码同时产出两个平台**：

| 平台 | 形态 | 目录 |
| --- | --- | --- |
| Web 版 | 部署在服务器上，浏览器访问 | `web/`（前端）+ `server/`（FastAPI 服务） |
| Win 版 | Windows 桌面程序，UI 与 Web 版逐像素一致 | `desktop/`（Electron 壳，载入同一份 `web/`） |

## 目录结构

```
web/                     共享前端（零依赖、无构建步骤）
  index.html             外壳：顶栏 / 侧栏 / 内容区 / 底栏
  styles/tokens.css      设计变量（颜色、尺寸、字号）—— 全部来自原稿量测
  styles/shell.css       外壳样式
  styles/components.css  通用组件（卡片/表格/徽标/进度条/下拉/轻提示）
  styles/pages/*.css     各界面样式
  scripts/icons.js       内联 SVG 图标库
  scripts/runtime.js     运行环境适配（浏览器 vs 桌面壳）
  scripts/mock.js        模拟数据（后续替换为后端接口）
  scripts/ui.js          通用渲染片段
  scripts/charts.js      SVG 折线图（按容器像素绘制）
  scripts/pages/*.js     各界面渲染与交互
  scripts/app.js         装配、路由、轻提示

server/                  Web 版服务端
  app/main.py            FastAPI：静态托管 + REST API（/api/status、/api/stats、
                         /api/tasks、/api/events、/api/chart/trend、服务启停）
  requirements.txt

desktop/                 Win 版桌面壳
  main.js                无边框窗口（默认 1536×1024）+ 窗口按钮 IPC
  preload.js             contextBridge 暴露 window.midasDesktop
  package.json           electron / electron-builder 配置

docs/                    每个界面的量测规范与验收记录
```

## 运行

### Web 版（服务器部署）

```bash
pip install -r server/requirements.txt
python -m uvicorn server.app.main:app --host 0.0.0.0 --port 8765
```

浏览器打开 `http://<服务器IP>:8765/`，即得与桌面版一致的界面。
也可直接托管 `web/` 为静态站点（无构建步骤，纯静态文件即可）。

### Win 版

```bash
cd desktop
npm install
npm start          # 开发运行
npm run dist       # 打包 NSIS 安装包 / 便携版
```

### 浏览器内预览桌面版外观

访问 `web/index.html?desktop=1` 可显示右上角窗口按钮（浏览器中不可点击），
用于在没有 Electron 时核对两平台的一致性。

## 界面还原方法

原稿是位图，无法直接取到设计参数，因此工程内建立了一套**量测 → 实现 → 复核**闭环：

1. 用无依赖的 PNG 分析工具对原稿取色、取坐标、取文字墨迹包围盒；
2. 把量测值写入 `styles/tokens.css` 与各页面样式；
3. 用无头浏览器按 1536×1024 截图，与原稿做逐像素差异（MAE / 差异网格 / 墨迹包围盒）复核，
   迭代到布局边界一致（误差 ≤2px），剩余差异来自字体栅格化与插画细节。

每个界面的量测数据（色值、坐标、字号、间距）与复核结果记录在 `docs/` 下。

## 进度

| # | 界面 | 状态 |
| --- | --- | --- |
| 01 | 首页（`ui/首页.png`） | ✅ 已完成并复核 |
| 02 | MIDAS 客户端 | ⏳ 待原稿确认 |
| 03 | MCP 服务器 | ⏳ |
| 04-08 | 工具与接口（5 个界面） | ⏳ |
| 09 | 任务监控 | ⏳ |
| 10 | 日志中心 | ⏳ |
| 11-17 | 系统设置（7 个界面） | ⏳ |
| 18-22 | AI 工程助手（5 个界面） | ⏳ |
