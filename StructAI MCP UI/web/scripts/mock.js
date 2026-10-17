/* 模拟数据层（接入后端时只需把 Mock.get 换成 fetch） */
(function () {
  const SHELL = {
    appName: 'MIDAS MCP 管理器',
    version: 'v1.0.0',
    runState: { running: true, text: 'MCP 运行中' },
    nav: [
      { id: 'home', label: '首页', icon: 'home', route: '#/home' },
      { id: 'midas', label: 'MIDAS 客户端', icon: 'client', route: '#/midas' },
      { id: 'mcp', label: 'MCP 服务器', icon: 'server', route: '#/mcp' },
      { id: 'tools', label: '工具与接口', icon: 'tools', route: '#/tools' },
      { id: 'templates', label: '参数化模板', icon: 'tpl', route: '#/templates' },
      { id: 'ai', label: 'AI 工程助手', icon: 'ai', route: '#/ai' },
      { id: 'tasks', label: '任务监控', icon: 'task', route: '#/tasks' },
      { id: 'logs', label: '日志中心', icon: 'logs', route: '#/logs' },
      { id: 'settings', label: '系统设置', icon: 'settings', route: '#/settings' }
    ],
    sideStatus: {
      running: true,
      title: 'MCP 服务运行中',
      rows: [
        { label: '本地端口', value: '8765' },
        { label: '已连接客户端', value: '2' },
        { label: '活跃任务', value: '1' }
      ],
      action: '停止服务'
    },
    footer: {
      brand: 'StructAI',
      slogan: 'AI for a Stronger Built World',
      right: ['MCP 连接中间件', '支持多 MIDAS 软件', 'v1.0.0']
    }
  };

  const HOME = {
    banner: {
      title: '欢迎使用 MIDAS MCP 管理器',
      sub: '连接 MIDAS · 让工程更智能',
      aside1: '更高效的工程设计 · 从 AI 开始',
      aside2: 'Smarter Engineering · A Stronger Tomorrow'
    },
    stats: [
      {
        icon: 'stat-server', label: 'MCP 服务状态',
        valueHtml: '<span class="dot dot-green"></span>运行中',
        valueClass: 'is-text is-green',
        footHtml: 'v1.0.0'
      },
      {
        icon: 'stat-client', label: '已连接客户端',
        valueHtml: '2',
        footHtml: '总计 <span class="v">5</span>'
      },
      {
        icon: 'stat-task', label: '活跃任务',
        valueHtml: '1',
        footHtml: '排队 <span class="v">0</span> <span class="bar">|</span> 失败 <span class="bad">1</span>'
      },
      {
        icon: 'stat-check', label: '今日请求数',
        valueHtml: '128<span class="stat-delta delta-up">↑ 12%</span>',
        footHtml: '昨日 <span class="v">114</span>'
      },
      {
        icon: 'stat-clock', label: '平均响应时间',
        valueHtml: '45<span class="unit">ms</span><span class="stat-delta delta-up">↓ 18%</span>',
        footHtml: '昨日 <span class="v">55 ms</span>'
      }
    ],
    chart: {
      title: '任务执行趋势',
      range: '最近 7 天',
      xLabels: ['08-10', '08-11', '08-12', '08-13', '08-14', '08-15', '08-16'],
      yTicks: [0, 5, 10, 15, 20],
      series: [
        { name: '成功', color: '#06A65A', data: [6, 15, 13, 12, 15, 11, 16] },
        { name: '失败', color: '#FE3B36', data: [1, 3, 2, 4, 2, 2, 1] },
        { name: '运行中', color: '#0065FE', data: [3, 8, 6, 7, 4, 4, 7] }
      ]
    },
    tasks: {
      title: '最近任务',
      columns: ['任务 ID', '类型', '客户端', '状态', '进度', '开始时间', '操作'],
      rows: [
        { id: 'JOB-20250816-001', type: '计算分析', client: 'CIVIL NX (本机)', status: 'running', progress: 60, start: '14:23:45' },
        { id: 'JOB-20250816-002', type: '建模', client: 'GEN NX (服务器)', status: 'running', progress: 30, start: '14:22:10' },
        { id: 'JOB-20250816-003', type: '结果查询', client: 'CIVIL NX (本机)', status: 'done', progress: 100, start: '14:15:21' },
        { id: 'JOB-20250816-004', type: '设计校核', client: 'FEA NX', status: 'done', progress: 100, start: '13:50:12' },
        { id: 'JOB-20250816-005', type: '计算书生成', client: 'CIVIL NX (本机)', status: 'failed', progress: 0, start: '13:30:14' }
      ]
    },
    events: {
      title: '系统事件',
      items: [
        { time: '14:23:45', text: 'MCP 服务启动成功', level: 'ok' },
        { time: '14:22:10', text: 'CIVIL NX 连接成功', level: 'ok' },
        { time: '14:18:33', text: '任务 JOB-20250816-001 开始执行', level: 'info' },
        { time: '14:15:21', text: '任务 JOB-20250816-003 已完成', level: 'info' },
        { time: '14:13:05', text: 'GEN NX 连接断开', level: 'error' },
        { time: '14:10:12', text: '重新连接 GEN NX 成功', level: 'ok' },
        { time: '14:08:44', text: 'MCP 客户端连接: 192.168.1.100', level: 'info' },
        { time: '14:05:21', text: 'API 请求异常: /db/NODE', level: 'error' },
        { time: '14:02:18', text: '系统初始化完成', level: 'ok' },
        { time: '14:00:01', text: 'MCP 服务启动中...', level: 'info' }
      ]
    },
    tips: {
      title: '使用提示',
      text: '通过左侧菜单可以管理 MIDAS 客户端、配置 MCP 服务、查看任务状态和系统日志。'
    }
  };

  const PAGES = {
    home: { title: '首页', render: function () { return window.PageHome.render(SHELL, HOME); },
      mount: function (root) { window.PageHome.mount(root, SHELL, HOME); } },
    midas: { title: 'MIDAS 客户端', render: function () { return window.PageClients.render(); },
      mount: function (root) { window.PageClients.mount(root); } },
    mcp: { title: 'MCP 服务器', render: function () { return window.PageMcp.render(); },
      mount: function (root) { window.PageMcp.mount(root); } },
    tools: { title: '工具与接口', render: function (sub) { return window.PageTools.render(sub); },
      mount: function (root, sub) { window.PageTools.mount(root, sub); } },
    templates: { title: '参数化模板', render: function () { return window.PageTemplates.render(); },
      mount: function (root) { window.PageTemplates.mount(root); } },
    ai: { title: 'AI 工程助手', render: function () { return window.PageAI.render(SHELL, window.PageAI.data()); },
      mount: function (root) { window.PageAI.mount(root); } },
    tasks: { title: '任务监控', todo: true },
    logs: { title: '日志中心', todo: true },
    settings: { title: '系统设置', render: function (sub) { return window.PageSettings.render(sub); },
      mount: function (root, sub) { window.PageSettings.mount(root, sub); } }
  };

  window.Mock = {
    shell: SHELL,
    home: HOME,
    pages: PAGES,
    get: function (key) { return this[key]; }
  };
})();
