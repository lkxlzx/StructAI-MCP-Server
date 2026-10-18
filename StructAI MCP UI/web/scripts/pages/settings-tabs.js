/* 系统设置子页（一）：服务配置 / 安全设置 / 关于系统 */
(function () {
  /* ---------- 共享渲染片段 ---------- */
  const sw = function (on) {
    return '<span class="switch' + (on ? ' is-on' : '') + '" role="switch" aria-checked="' + !!on + '"></span>';
  };
  const tag = function (t, cls, dot) {
    return '<span class="tag ' + cls + '">' + (dot ? '<span class="dot"></span>' : '') + t + '</span>';
  };
  const stat4 = function (items) {
    return '<div class="stat4">' + items.map(function (s) {
      return '<article class="sc"><span class="tile ' + (s.tone || 'blue') + '" data-icon="' + s.icon + '"></span>' +
        '<span class="sc-body"><span class="sc-label">' + s.label + '</span>' +
        '<span class="sc-value">' + s.value + (s.unit ? '<span class="u">' + s.unit + '</span>' : '') + '</span>' +
        '<span class="sc-sub">' + (s.sub || '') + '</span></span></article>';
    }).join('') + '</div>';
  };
  const dtable = function (cols, rows) {
    const th = cols.map(function (c) { return '<th' + (c.c ? ' class="c"' : '') + '>' + c.t + '</th>'; }).join('');
    const tr = rows.map(function (r) {
      return '<tr>' + r.map(function (c, i) {
        const cls = cols[i] && cols[i].c ? ' class="c"' : '';
        return '<td' + cls + '>' + c + '</td>';
      }).join('') + '</tr>';
    }).join('');
    /* 包一层横向滚动容器：3 栏卡宽有限，长表头不应把卡片撑宽（`.dtable-wrap`）。 */
    return '<div class="dtable-wrap"><table class="dtable"><thead><tr>' + th +
      '</tr></thead><tbody>' + tr + '</tbody></table></div>';
  };
  const setRow = function (k, v, labelW) {
    return '<div class="set-row"><span class="k"' + (labelW ? ' style="width:' + labelW + 'px"' : '') + '>' + k + '</span>' +
      '<span class="v">' + v + '</span></div>';
  };
  const selRow = function (k, value, opts, w) {
    return setRow(k, '<span class="select-like s-select"' + (w ? ' style="width:' + w + 'px"' : '') + '><select>' +
      (opts || [value]).map(function (o) { return '<option>' + o + '</option>'; }).join('') +
      '</select><span class="chev" data-icon="chevD"></span></span>', 92);
  };
  const numRow = function (k, value, unit, spin, w) {
    return setRow(k, '<span class="s-input"' + (w ? ' style="width:' + w + 'px"' : '') + '><input type="text" value="' + value + '">' +
      (unit ? '<span class="suffix">' + unit + '</span>' : '') +
      (spin ? '<button class="ico-btn" type="button" data-spin="1"><span data-icon="chevD"></span></button>' : '') +
      '</span>', 92);
  };
  const togRow = function (k, on) {
    return '<div class="set-row"><span class="k" style="width:auto;flex:1">' + k + '</span>' + sw(on) + '</div>';
  };
  const featRow = function (icon, title, desc, on) {
    return '<div class="feat-row"><span class="fi" data-icon="' + icon + '"></span>' +
      '<span class="ft"><b>' + title + '</b><span>' + desc + '</span></span>' + sw(on) + '</div>';
  };
  const actRow = function (icon, title, desc) {
    return '<button class="act-row" type="button" data-act2="' + title + '">' +
      '<span class="ai" data-icon="' + icon + '"></span>' +
      '<span class="at"><b>' + title + '</b><span>' + desc + '</span></span>' +
      '<span class="ch" data-icon="chevR"></span></button>';
  };
  const card = function (icon, title, body, extra) {
    return '<section class="settings-card"><h2 class="s-card-title"><span class="ti" data-icon="' + icon + '"></span>' +
      title + (extra || '') + '</h2>' + body + '</section>';
  };
  const grid3 = function (html) { return '<div class="set3">' + html + '</div>'; };
  const grid2 = function (html) { return '<div class="set2">' + html + '</div>'; };

  window.SetUI = { sw: sw, tag: tag, stat4: stat4, dtable: dtable, setRow: setRow, selRow: selRow,
    numRow: numRow, togRow: togRow, featRow: featRow, actRow: actRow, card: card, grid3: grid3, grid2: grid2 };

  /* ============================ 服务配置 ============================ */
  function serviceTab() {
    const S = window.SetUI;
    const status = S.card('server', '服务状态', '' +
      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">' +
      S.tag('运行中', 'green', true) + '</div>' +
      '<div class="field-hint" style="margin:0 0 12px">MCP 服务当前运行状态及基本信息</div>' +
      S.dtable([{ t: '服务名称' }, { t: 'midas-mcp-server' }], []) .replace(/<thead>[\s\S]*?<\/thead><tbody>|<\/tbody>/g, '') +
      '', '');
    /* 服务状态用 KV 列表更贴近原稿 */
    const kv = function (rows) {
      return '<div class="kv-list">' + rows.map(function (r) {
        return '<div class="r"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
      }).join('') + '</div>';
    };
    const statusCard = S.card('server', '服务状态',
      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">' + S.tag('运行中', 'green', true) + '</div>' +
      '<div class="field-hint" style="margin:0 0 10px">MCP 服务当前运行状态及基本信息</div>' +
      kv([['服务名称', 'midas-mcp-server'], ['进程 ID', '32418'], ['启动时间', '2026-09-21 14:20:00'],
        ['运行时长', '2 天 6 小时 12 分钟'], ['当前版本', 'v1.0.0'], ['监听地址', '0.0.0.0:8765']]) +
      '<div class="card-actions" style="justify-content:flex-start;padding-top:14px">' +
      '<button class="btn-w" type="button" data-act2="重启服务"><span class="bi" data-icon="refresh"></span>重启服务</button>' +
      '<button class="btn-red" type="button" data-act2="停止服务"><span class="bi" data-icon="stop"></span>停止服务</button>' +
      '<button class="btn-w" type="button" data-act2="查看日志"><span class="bi" data-icon="fileText"></span>查看日志</button>' +
      '</div>');

    const netCard = S.card('server', '网络与端口配置', '' +
      S.selRow('监听地址', '0.0.0.0', ['0.0.0.0', '127.0.0.1']) +
      '<div class="field-hint" style="margin:2px 0 12px 104px">0.0.0.0 表示监听所有网卡，127.0.0.1 仅本机访问</div>' +
      S.numRow('服务端口', '8765', '', true) +
      '<div style="height:10px"></div>' +
      S.numRow('管理端口', '8766', '', true) +
      '<div style="height:10px"></div>' +
      S.numRow('最大连接数', '100', '', true) +
      '<div class="field-hint" style="margin:2px 0 12px 104px">同时允许的最大客户端连接数</div>' +
      '<div class="set-row"><span class="k" style="width:auto;flex:1">开启 CORS</span>' + S.sw(true) + '</div>' +
      '<div class="field-hint" style="margin:2px 0 12px 104px">允许跨域请求访问 API</div>' +
      '<label class="field-label" style="margin-left:104px">允许的来源</label>' +
      '<span class="s-input" style="margin-left:104px"><input type="text" value="例如: http://localhost:3000"></span>' +
      '<div class="field-hint" style="margin:6px 0 0 104px">多个来源请用逗号分隔，* 表示允许所有</div>' +
      '<div class="card-actions"><button class="btn-blue" type="button" data-act2="保存配置">保存配置</button></div>');

    const featCard = S.card('sliders', '服务功能开关', [
      ['ai', '启用 MCP 协议服务', '提供标准的 MCP 协议接口'],
      ['plug', '启用 REST API 接口', '提供 HTTP RESTful API 接口'],
      ['layout', '启用 Web 管理界面', '提供 Web 管理界面访问'],
      ['flow', '启用任务队列', '支持异步任务处理'],
      ['archive', '启用结果缓存', '缓存计算结果以提升性能'],
      ['fileText', '启用详细日志', '记录详细的调试日志']
    ].map(function (f) { return S.featRow(f[0], f[1], f[2], true); }).join(''));

    const perfCard = S.card('stat-clock', '性能配置', '' +
      S.numRow('工作线程数', '4', '', true) +
      '<div class="field-hint" style="margin:2px 0 10px 104px">处理任务的工作线程数量（建议 2-8）</div>' +
      S.numRow('任务队列大小', '100', '', true) +
      '<div class="field-hint" style="margin:2px 0 10px 104px">最大排队任务数量（建议 50-500）</div>' +
      S.numRow('任务超时时间', '3600', '秒', true) +
      '<div class="field-hint" style="margin:2px 0 10px 104px">单个任务的最大执行时间</div>' +
      S.numRow('结果缓存时间', '3600', '秒', true) +
      '<div class="field-hint" style="margin:2px 0 0 104px">缓存结果的有效期</div>' +
      '<div class="card-actions"><button class="btn-blue" type="button" data-act2="保存配置">保存配置</button></div>');

    const envRows = [
      ['MIDAS_HOME', 'D:\\Program Files\\MIDAS', 'MIDAS 安装目录'],
      ['TEMP_DIR', '/opt/midas-mcp/temp', '临时文件目录'],
      ['LOG_LEVEL', 'INFO', '日志级别'],
      ['MAX_FILE_SIZE', '100', '上传文件大小限制(MB)']
    ].map(function (r) {
      return [r[0], r[1], r[2],
        '<span class="ico-cell"><button class="tbtn icon" type="button" data-act2="编辑变量"><span data-icon="edit"></span></button>' +
        '<button class="tbtn icon danger" type="button" data-act2="删除变量"><span data-icon="trash"></span></button></span>'];
    });
    const envCard = S.card('db', '环境变量',
      S.dtable([{ t: '变量名' }, { t: '变量值' }, { t: '说明' }, { t: '操作' }], envRows),
      '<button class="btn-w" style="margin-left:auto;height:32px;padding:0 12px" type="button" data-act2="添加变量">' +
      '<span class="bi" data-icon="plus"></span>添加变量</button>');
    /* 标题栏按钮放在右侧 */
    const envCard2 = envCard.replace('<h2 class="s-card-title">', '<h2 class="s-card-title" style="justify-content:flex-start">')
      .replace('</h2>', '</h2>');

    const advCard = S.card('sliders', '高级配置', [
      ['shield', 'SSL/TLS 配置', '配置 HTTPS 访问和证书'],
      ['flow', '反向代理配置', '配置 Nginx/Apache 反向代理'],
      ['stat-clock', 'API 限流配置', '设置 API 请求频率限制'],
      ['shield', '健康检查', '配置服务健康检查参数'],
      ['layers', '集群部署', '多节点部署和负载均衡']
    ].map(function (a) { return S.actRow(a[0], a[1], a[2]); }).join(''));

    return S.grid3(statusCard + netCard + featCard) + S.grid3(perfCard + envCard2 + advCard);
  }

  /* ============================ 安全设置 ============================ */
  function securityTab() {
    const S = window.SetUI;
    const stats = S.stat4([
      { icon: 'shield', tone: 'green', label: '安全状态', value: '良好', sub: '未发现风险' },
      { icon: 'lock', tone: 'blue', label: '登录失败（24h）', value: '12', sub: '较昨日 <span class="dl-up">-20% ↓</span>' },
      { icon: 'shield', tone: 'red', label: '安全告警（24h）', value: '3', sub: '较昨日 <span class="dl-up">-50% ↓</span>' },
      { icon: 'db', tone: 'purple', label: '审计日志（24h）', value: '1,284', sub: '较昨日 <span class="dl-bad">+12% ↑</span>' }
    ]);

    const loginCard = S.card('lock', '登录安全', [
      ['启用登录验证', 'sw', true],
      ['登录失败最大尝试次数', 'num', '5', '次'],
      ['账号锁定时长', 'num', '30', '分钟'],
      ['启用验证码', 'sw', true],
      ['验证码有效期', 'num', '10', '分钟'],
      ['启用双因素认证（2FA）', 'sw', false],
      ['会话超时时间', 'num', '8', '小时'],
      ['同一账号最大会话数', 'num', '3', ''],
      ['强制首次登录修改密码', 'sw', true]
    ].map(function (r) {
      if (r[1] === 'sw') return S.togRow(r[0], r[2]);
      return S.numRow(r[0], r[2], r[3], true, 118);
    }).join(''));

    const pwdCard = S.card('lock', '密码策略', [
      ['最小密码长度', '8'],
      ['必须包含大写字母', 'on'],
      ['必须包含小写字母', 'on'],
      ['必须包含数字', 'on'],
      ['必须包含特殊字符', 'on'],
      ['密码有效期', '90', '天'],
      ['禁止使用历史密码', '5', '次'],
      ['账号闲置自动禁用', '180', '天']
    ].map(function (r) {
      if (r[1] === 'on') return S.togRow(r[0], true);
      if (!r[2]) return S.selRow(r[0], r[1], [r[1], '6', '8', '12', '16'], 118);
      return S.numRow(r[0], r[1], r[2], true, 118);
    }).join(''));

    const accessCard = S.card('shield', '访问控制', '' +
      '<div class="set-row"><span class="k" style="width:auto;flex:1">IP 访问白名单</span>' + S.sw(true) + '</div>' +
      '<textarea class="s-textarea mono" style="margin:8px 0 6px">192.168.1.0/24\n10.0.0.0/8\n172.16.0.0/12</textarea>' +
      '<div class="field-hint" style="margin:0 0 14px">每一行一个 IP 地址或网段</div>' +
      '<div class="set-row"><span class="k" style="width:auto;flex:1">IP 访问黑名单</span>' + S.sw(false) + '</div>' +
      '<span class="s-input" style="margin:8px 0 6px"><input type="text" placeholder="输入需要阻止的 IP 地址或网段"></span>' +
      '<div class="field-hint" style="margin:0 0 14px">每一行一个 IP 地址或网段</div>' +
      '<div class="set-row"><span class="k" style="width:auto;flex:1">API 访问频率限制</span>' + S.sw(true) + '</div>' +
      '<div style="height:8px"></div>' +
      S.numRow('每分钟最大请求数', '120', '次', true, 130) +
      '<div style="height:8px"></div>' +
      S.numRow('单 IP 最大请求数', '1000', '次', true, 130));

    const dataCard = S.card('db', '数据安全', [
      ['启用数据加密存储', true], ['启用传输加密（HTTPS）', true], ['敏感信息脱敏', true],
      ['定期备份配置数据', true]
    ].map(function (r) { return S.togRow(r[0], r[1]); }).join('') +
      S.numRow('备份保留天数', '30', '天', false, 118) +
      S.togRow('导出数据脱敏', true));

    const auditCard = S.card('bell', '审计与告警', '' +
      S.togRow('启用操作审计', true) + S.togRow('启用安全告警', true) +
      '<div class="set-row" style="margin:6px 0 10px"><span class="k" style="width:auto">告警通知方式</span>' +
      '<span class="v"><span class="cbx-row">' +
      '<span class="cbx-item is-on" data-channel="系统内通知"><span class="box">' + window.Icons.check + '</span>系统内通知</span>' +
      '<span class="cbx-item is-on" data-channel="邮件通知"><span class="box">' + window.Icons.check + '</span>邮件通知</span>' +
      '<span class="cbx-item" data-channel="Webhook"><span class="box"></span>Webhook</span>' +
      '</span></span></div>' +
      '<div class="field-hint" style="margin:0 0 10px 0">告警阈值</div>' +
      S.numRow('登录失败次数', '10', '次', true, 118) +
      '<div style="height:8px"></div>' +
      S.numRow('异常请求次数', '100', '次', true, 118));

    const logRows = [
      ['2026-09-21 14:22:15', '<span class="dl-up">登录成功</span>', 'zhangsan', '192.168.1.100', '用户登录'],
      ['2026-09-21 13:45:22', '<span class="dl-bad">登录失败</span>', 'test', '10.0.0.5', '密码错误'],
      ['2026-09-21 12:18:03', '<span style="color:#8B5CF6">权限变更</span>', 'admin', '192.168.1.101', '更新用户权限'],
      ['2026-09-21 11:32:18', '<span style="color:var(--brand)">API 访问</span>', 'wangwu', '172.16.0.8', '调用模型接口'],
      ['2026-09-21 09:15:44', '<span class="dl-bad">异常请求</span>', '-', '203.0.113.5', '触发频率限制']
    ];
    const logCard = S.card('fileText', '安全日志',
      S.dtable([{ t: '时间' }, { t: '类型' }, { t: '用户' }, { t: 'IP 地址' }, { t: '描述' }], logRows) +
      '<div class="card-actions">' +
      '<button class="btn-w" type="button" data-act2="重置为默认"><span class="bi" data-icon="refresh"></span>重置为默认</button>' +
      '<button class="btn-blue" type="button" data-act2="保存设置">保存设置</button></div>',
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="查看更多">查看更多<span class="chev" data-icon="chevR"></span></a>');

    return stats + S.grid3(loginCard + pwdCard + accessCard) + S.grid3(dataCard + auditCard + logCard);
  }

  /* ============================ 关于系统 ============================ */
  function aboutTab() {
    const S = window.SetUI;
    const aboutCard = S.card('info', 'MIDAS MCP 管理器', '').replace('<h2 class="s-card-title">', '<div style="display:none">').replace('</h2>', '</div>');
    const heroCard = '<section class="settings-card">' +
      '<div class="ident" style="gap:18px;margin-bottom:14px">' +
      '<span class="ident-logo" style="width:74px;height:74px;font-size:38px;border-radius:16px">M</span>' +
      '<span><span class="ident-name" style="font-size:22px">MIDAS MCP 管理器</span>' +
      '<span class="identity-sub" style="display:block;margin-top:6px">Connect MIDAS · Empower Engineering with AI</span></span>' +
      '</div>' +
      '<p style="font-size:14px;line-height:1.7;color:var(--text-2);margin:6px 0 16px">' +
      'MIDAS MCP 管理器是一个面向工程行业的 AI 工具管理平台，通过 MCP 协议连接 MIDAS 系列软件，提供模型管理、任务调度、工具编排等能力，助力工程设计与分析的智能化升级。</p>' +
      '<div style="display:flex;gap:12px">' +
      '<button class="btn-blue" style="flex:1;justify-content:center" type="button" data-act2="官方网站"><span class="bi" data-icon="plug"></span>官方网站</button>' +
      '<button class="btn-w" style="flex:1;justify-content:center" type="button" data-act2="GitHub"><span class="bi" data-icon="db"></span>GitHub</button>' +
      '</div></section>';

    const verCard = S.card('model', '版本信息',
      '<div class="kv-list">' +
      [['当前版本', 'v1.0.0 ' + S.tag('最新版', 'green')], ['构建时间', '2026-09-21 14:20:15'],
        ['构建编号', '20260921.1420'], ['运行环境', 'Docker / Linux (amd64)'],
        ['前端版本', 'v1.0.0'], ['后端版本', 'v1.0.0'], ['MCP 协议版本', '2024-11-05']]
        .map(function (r) { return '<div class="r"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>'; }).join('') +
      '</div>');

    const btnCol = '<div style="display:flex;flex-direction:column;gap:12px">' +
      '<button class="btn-blue" style="justify-content:center;height:44px" type="button" data-act2="检查更新"><span class="bi" data-icon="refresh"></span>检查更新</button>' +
      ['更新日志|fileText', '使用文档|fileText', '常见问题|info', '技术支持|plug'].map(function (b) {
        const p = b.split('|');
        return '<button class="btn-w" style="justify-content:center;height:44px" type="button" data-act2="' + p[0] + '">' +
          '<span class="bi" data-icon="' + p[1] + '"></span>' + p[0] + '</button>';
      }).join('') + '</div>';

    const compRows = [
      ['MCP Server', 'v1.0.0', S.tag('运行中', 'green', true)],
      ['Web 管理界面', 'v1.0.0', S.tag('运行中', 'green', true)],
      ['任务调度服务', 'v1.0.0', S.tag('运行中', 'green', true)],
      ['日志服务', 'v1.0.0', S.tag('运行中', 'green', true)],
      ['数据库', 'SQLite 3.46', S.tag('正常', 'green', true)],
      ['运行环境', 'Python 3.11', S.tag('正常', 'green', true)],
      ['容器环境', 'Docker 24.0', S.tag('正常', 'green', true)]
    ];
    const compCard = S.card('layers', '系统组件', S.dtable([{ t: '组件名称' }, { t: '当前版本' }, { t: '状态' }], compRows));

    const licenseCard = S.card('fileText', '开源协议',
      '<p style="font-size:14px;color:var(--text-2);line-height:1.7;margin:2px 0 12px">MIDAS MCP 管理器基于开源协议发布，欢迎使用、修改和贡献代码。</p>' +
      '<div style="border:1px solid #EEF2F7;border-radius:8px;padding:14px">' +
      '<div style="display:flex;align-items:center;gap:9px;font-size:15px;font-weight:700;color:var(--text-1)">' +
      '<span class="ai" style="width:22px;height:22px;color:var(--brand)" data-icon="fileText"></span>MIT License</div>' +
      '<div style="font-size:13px;color:var(--text-2);line-height:1.8;margin-top:8px">Copyright (c) 2026 MIDAS MCP<br>' +
      'Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files...</div></div>' +
      '<button class="btn-w" style="width:100%;justify-content:center;margin-top:12px" type="button" data-act2="查看完整协议">' +
      '<span class="bi" data-icon="fileText"></span>查看完整协议</button>');

    const thanksRows = [
      ['MIDAS', '提供强大的结构分析能力'], ['Model Context Protocol', 'AI 工具调用协议标准'],
      ['FastAPI', '高性能的 Python Web 框架'], ['Vue.js', '渐进式前端框架'],
      ['Element Plus', '优秀的企业级 UI 组件库'], ['Docker', '容器化部署与运行环境'],
      ['开源社区', '感谢所有贡献者']
    ];
    const thanksCard = S.card('user', '致谢',
      '<p style="font-size:14px;color:var(--text-3);margin:2px 0 12px">感谢以下开源项目和社区的支持：</p>' +
      thanksRows.map(function (r) {
        return '<div style="display:flex;align-items:center;gap:10px;min-height:32px">' +
          '<span class="ai" style="width:24px;height:24px;border-radius:7px;background:var(--brand-soft);color:var(--brand);display:flex;align-items:center;justify-content:center" data-icon="layers"></span>' +
          '<span style="flex:1;font-size:14px;color:var(--text-1)">' + r[0] + '</span>' +
          '<span style="font-size:13px;color:var(--text-3)">' + r[1] + '</span></div>';
      }).join(''));

    const changelogCard = S.card('fileText', '更新日志',
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">' +
      '<span style="width:10px;height:10px;border-radius:50%;background:var(--brand);flex:none"></span>' +
      '<b style="font-size:15px;color:var(--text-1)">v1.0.0</b>' + S.tag('当前版本', 'green') +
      '<span style="font-size:13px;color:var(--text-3)">2026-09-21</span></div>' +
      '<ul style="margin:0;padding-left:22px;font-size:14px;color:var(--text-2);line-height:2">' +
      ['首次正式发布', '支持 MIDAS MCP 协议服务', '提供模型管理、任务监控、日志中心等核心功能',
        '支持多用户权限管理', '提供完善的系统配置与安全控制', '优化系统性能与稳定性']
        .map(function (t) { return '<li>' + t + '</li>'; }).join('') + '</ul>',
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="查看更多">查看更多<span class="chev" data-icon="chevR"></span></a>');

    return S.grid3(heroCard + verCard + btnCol) + S.grid3(compCard + licenseCard + thanksCard) + changelogCard;
  }

  window.SettingsTabs = window.SettingsTabs || {};
  window.SettingsTabs.service = { render: serviceTab };
  window.SettingsTabs.security = { render: securityTab };
  window.SettingsTabs.about = { render: aboutTab };
})();
