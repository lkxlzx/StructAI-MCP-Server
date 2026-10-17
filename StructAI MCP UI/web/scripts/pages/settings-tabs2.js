/* 系统设置子页（二）：模型设置 / 数据管理 / 用户与权限 */
(function () {
  const S = window.SetUI;

  /* ---------- 局部补充片段 ---------- */
  const donut = function (items, totalText, totalSub) {
    const r = 60, C = 2 * Math.PI * r;
    let acc = 0;
    const segs = items.map(function (it) {
      const len = C * it.pct / 100;
      const s = '<circle cx="75" cy="75" r="' + r + '" fill="none" stroke="' + it.color +
        '" stroke-width="22" stroke-dasharray="' + len.toFixed(1) + ' ' + (C - len).toFixed(1) +
        '" stroke-dashoffset="' + (-acc).toFixed(1) + '"/>';
      acc += len;
      return s;
    }).join('');
    return '<div class="donut-wrap"><div class="donut">' +
      '<svg viewBox="0 0 150 150"><circle cx="75" cy="75" r="60" fill="none" stroke="#EEF2F7" stroke-width="22"/>' +
      segs + '</svg><div class="center"><b>' + totalText + '</b><span>' + totalSub + '</span></div></div>' +
      '<div class="legend2">' + items.map(function (it) {
        return '<div class="li"><span class="dot" style="background:' + it.color + '"></span>' +
          '<span class="nm">' + it.name + '</span><span class="vl">' + it.text + ' (' + it.pct + '%)</span></div>';
      }).join('') + '</div></div>';
  };
  const sliderRow = function (label, val, min, max, pct) {
    return '<div class="slider-row"><span class="lb">' + label + '</span>' +
      '<span class="slider-wrap"><span class="slider"><span class="fill" style="width:' + pct + '%"></span>' +
      '<span class="knob" style="left:' + pct + '%"></span></span>' +
      '<span class="slider-scale"><span>' + min + '</span><span>' + max + '</span></span></span>' +
      '<span class="slider-val">' + val + '</span></div>';
  };
  const searchBox = function (ph) {
    return '<label class="search-box"><span class="si" data-icon="search"></span>' +
      '<input type="text" placeholder="' + ph + '"></label>';
  };
  const pager = function (total, pages, size) {
    return '<div class="pager" style="padding:12px 0 0">' +
      '<span class="total">' + total + '</span>' +
      '<button class="pg-btn" type="button"><span class="pi" data-icon="chevL"></span></button>' +
      pages.map(function (p, i) {
        return '<button class="pg-btn' + (i === 0 ? ' is-current' : '') + '" type="button">' + p + '</button>';
      }).join('') +
      '<button class="pg-btn" type="button"><span class="pi" data-icon="chevR"></span></button>' +
      '<span class="select-like pg-size"><select><option>' + size + '</option></select>' +
      '<span class="chev" data-icon="chevD"></span></span></div>';
  };

  /* ============================ 模型设置 ============================ */
  function modelTab() {
    const stats = S.stat4([
      { icon: 'model', tone: 'blue', label: '已配置模型', value: '6', sub: '较昨日 <span class="dl-mute">+0</span>' },
      { icon: 'stat-check', tone: 'green', label: '可用模型', value: '5', sub: '83.3%' },
      { icon: 'stat-clock', tone: 'orange', label: '不可用模型', value: '1', sub: '16.7%' },
      { icon: 'db', tone: 'purple', label: '总请求次数', value: '1,284', sub: '较昨日 <span class="dl-bad">+12% ↑</span>' }
    ]);

    const provs = {
      'DeepSeek': 'ai', '通义千问': 'star', '智谱AI': 'layers', 'Anthropic': 'model', 'OpenAI': 'globe'
    };
    const rows = [
      ['1', 'deepseek-v4-flash', 'DeepSeek', '对话模型', '128K', true, true],
      ['2', 'deepseek-v4-pro', 'DeepSeek', '对话模型', '128K', true, false],
      ['3', 'qwen3.8-max', '通义千问', '对话模型', '128K', true, false],
      ['4', 'glm-4.5', '智谱AI', '对话模型', '128K', true, false],
      ['5', 'claude-3-5-sonnet', 'Anthropic', '对话模型', '200K', true, false],
      ['6', 'gpt-4o', 'OpenAI', '对话模型', '128K', false, false]
    ].map(function (r) {
      return ['<input type="checkbox" style="accent-color:var(--brand)">', r[0], '<b style="font-weight:600;color:var(--text-1)">' + r[1] + '</b>',
        '<span style="display:flex;align-items:center;gap:7px"><span style="width:18px;height:18px;border-radius:5px;background:var(--brand-soft);color:var(--brand);display:inline-flex;align-items:center;justify-content:center" data-icon="' + (provs[r[2]] || 'model') + '"></span>' + r[2] + '</span>',
        r[3], r[4],
        r[5] ? S.tag('可用', 'green', true) : S.tag('不可用', 'red', true),
        '<span style="display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;border:1.5px solid ' + (r[6] ? 'var(--brand)' : '#C9D4E4') + '">' + (r[6] ? '<span style="width:8px;height:8px;border-radius:50%;background:var(--brand)"></span>' : '') + '</span>',
        '<span style="display:flex;gap:4px"><button class="tbtn link" type="button" data-act2="测试 ' + r[1] + '">测试</button>' +
        '<button class="tbtn link" type="button" data-act2="编辑 ' + r[1] + '">编辑</button>' +
        '<button class="tbtn icon" type="button" data-act2="更多"><span data-icon="more"></span></button></span>'];
    });
    const listCard = S.card('model', '模型列表',
      '<div class="toolbar">' + searchBox('搜索模型名称、提供商或描述...') +
      '<span class="select-like"><select><option>全部提供商</option></select><span class="chev" data-icon="chevD"></span></span>' +
      '<span class="select-like"><select><option>全部状态</option></select><span class="chev" data-icon="chevD"></span></span>' +
      '<button class="btn-w" type="button" data-act2="刷新列表"><span class="bi" data-icon="refresh"></span>刷新列表</button></div>' +
      S.dtable([{ t: '' }, { t: '#' }, { t: '模型名称' }, { t: '提供商' }, { t: '模型类型' }, { t: '上下文长度' },
        { t: '状态' }, { t: '默认模型' }, { t: '操作' }], rows) +
      pager('共 6 条', ['1'], '10 条/页'));

    const detailCard = S.card('model', '',
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">' +
      '<span style="width:40px;height:40px;border-radius:10px;background:var(--brand-soft);color:var(--brand);display:flex;align-items:center;justify-content:center" data-icon="ai"></span>' +
      '<span><b style="font-size:17px;color:var(--text-1)">deepseek-v4-flash</b>' + S.tag('可用', 'green', true) + '</span></div>' +
      '<div style="font-size:14px;font-weight:600;color:var(--text-2);margin-bottom:4px">DeepSeek</div>' +
      '<div style="font-size:13px;color:var(--text-3);line-height:1.6;margin-bottom:12px">高效快速的对话模型，适用于日常任务和工具调用</div>' +
      '<div class="kv-list">' +
      [['模型类型', '对话模型'], ['上下文长度', '128,000'], ['最大输出长度', '8,192'],
        ['支持功能', '对话 / 工具调用 / JSON 输出'], ['创建时间', '2024-07-01 10:00:00'], ['最后测试', '2026-09-21 14:15:32']]
        .map(function (r) { return '<div class="r"><dt style="width:96px">' + r[0] + '</dt><dd>' + r[1] + '</dd></div>'; }).join('') +
      '</div>' +
      '<div class="card-actions" style="justify-content:flex-start">' +
      '<button class="btn-w" type="button" data-act2="测试模型"><span class="bi" data-icon="play2"></span>测试模型</button>' +
      '<button class="btn-w" type="button" data-act2="设为默认"><span class="bi" data-icon="star"></span>设为默认</button>' +
      '<button class="btn-red" type="button" data-act2="删除"><span class="bi" data-icon="trash"></span>删除</button></div>',
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="编辑">编辑<span class="chev" data-icon="chevR"></span></a>');

    const paramCard = S.card('sliders', '模型参数设置',
      '<div style="display:grid;grid-template-columns:minmax(0,1fr) 200px;gap:24px">' +
      '<div>' + sliderRow('默认温度 (Temperature)', '0.7', '0.0', '2.0', 35) +
      sliderRow('默认最大输出长度', '4096', '256', '8192', 50) +
      sliderRow('Top P', '0.9', '0.0', '1.0', 90) + '</div>' +
      '<div>' + S.togRow('启用流式输出', true) + S.togRow('启用工具调用', true) + S.togRow('自动重试', true) +
      S.numRow('重试次数', '3', '', true, 100) + '</div></div>' +
      '<div class="card-actions"><button class="btn-blue" type="button" data-act2="保存参数">保存参数</button></div>');

    const testCard = S.card('chat', '模型测试',
      S.selRow('选择模型', 'deepseek-v4-flash', ['deepseek-v4-flash', 'deepseek-v4-pro', 'gpt-4o'], 110) +
      '<textarea class="s-textarea" style="margin-top:8px" placeholder="请输入测试内容..."></textarea>' +
      '<div class="card-actions"><button class="btn-blue" type="button" data-act2="发送测试">' +
      '<span class="bi" data-icon="send"></span>发送测试</button></div>');

    const connCard = S.card('plug', '模型接入配置', '' +
      S.setRow('API 地址', '<span class="s-input"><input type="text" value="https://api.deepseek.com/v1"></span>', 88) +
      '<div style="height:10px"></div>' +
      S.setRow('API Key', '<span class="s-input"><input type="text" value="••••••••••••••••••••••">' +
        '<button class="ico-btn" type="button" data-act2="显示 Key"><span data-icon="eye"></span></button></span>', 88) +
      '<div style="height:10px"></div>' +
      S.numRow('请求超时', '60', '秒', false, 88) +
      '<div style="height:10px"></div>' +
      S.selRow('代理设置', '不使用代理', ['不使用代理', '使用系统代理', '自定义代理'], 88) +
      '<div class="card-actions">' +
      '<button class="btn-w" type="button" data-act2="测试连接"><span class="bi" data-icon="plug"></span>测试连接</button>' +
      '<button class="btn-blue" type="button" data-act2="保存配置">保存配置</button></div>');

    return stats + S.grid2(listCard + detailCard) + S.grid3(paramCard + testCard + connCard);
  }

  /* ============================ 数据管理 ============================ */
  function dataTab() {
    const stats = S.stat4([
      { icon: 'db', tone: 'blue', label: '数据库大小', value: '1.24', unit: 'GB', sub: '占用磁盘空间' },
      { icon: 'fileText', tone: 'blue', label: '数据表数量', value: '28', sub: '较昨日 <span class="dl-bad">+2 ↑</span>' },
      { icon: 'stat-clock', tone: 'green', label: '最后备份时间', value: '<span style="font-size:17px">2026-09-21 02:30</span>', sub: S.tag('备份成功', 'green', true) },
      { icon: 'shield', tone: 'orange', label: '数据健康状态', value: '良好', sub: '未发现异常' }
    ]);

    const backupCard = S.card('archive', '数据备份与恢复',
      '<div style="display:flex;gap:10px;margin-bottom:14px">' +
      '<button class="btn-blue" type="button" data-act2="立即备份"><span class="bi" data-icon="plus"></span>立即备份</button>' +
      '<button class="btn-w" type="button" data-act2="从备份恢复"><span class="bi" data-icon="download"></span>从备份恢复</button>' +
      '<button class="btn-w" type="button" data-act2="备份设置"><span class="bi" data-icon="fileText"></span>备份设置</button></div>' +
      S.togRow('自动备份', true) +
      S.selRow('备份频率', '每天', ['每天', '每周', '每月'], 110) +
      S.numRow('保留备份数量', '7', '份', false, 110) +
      S.setRow('备份存储路径', '<span class="s-input"><input type="text" value="/opt/midas-mcp/backups">' +
        '<button class="ico-btn" type="button" data-act2="选择目录"><span data-icon="folder"></span></button></span>', 110));

    const ioCard = S.card('upload', '数据导入与导出',
      '<div style="display:flex;gap:10px;margin-bottom:14px">' +
      '<button class="btn-w" style="flex:1;justify-content:center" type="button" data-act2="导出数据"><span class="bi" data-icon="download"></span>导出数据</button>' +
      '<button class="btn-w" style="flex:1;justify-content:center" type="button" data-act2="导入数据"><span class="bi" data-icon="upload"></span>导入数据</button></div>' +
      '<div class="field-hint" style="margin:0 0 10px">导出范围</div>' +
      '<div class="cbx-row" style="display:grid;grid-template-columns:1fr 1fr;gap:12px">' +
      [['系统配置', true], ['日志数据', false], ['用户数据', true], ['工具接口配置', false],
        ['模型配置', true], ['全部数据', false], ['任务记录', true], ['', null]].map(function (c) {
        if (!c[0]) return '';
        return '<span class="cbx-item' + (c[1] ? ' is-on' : '') + '" data-channel="' + c[0] + '">' +
          '<span class="box">' + (c[1] ? window.Icons.check : '') + '</span>' + c[0] + '</span>';
      }).join('') + '</div>' +
      '<div style="height:14px"></div>' +
      S.selRow('导出格式', 'JSON (推荐)', ['JSON (推荐)', 'CSV', 'Excel'], 88));

    const cleanCard = S.card('trash', '数据清理',
      [['清理任务记录', true, '30'], ['清理日志数据', true, '60'], ['清理审计日志', false, '180'],
        ['清理已删除用户数据', false, ''], ['清理临时文件', true, '']].map(function (r) {
        return '<div class="set-row"><span class="cbx-item' + (r[1] ? ' is-on' : '') + '" data-channel="' + r[0] + '" style="flex:1">' +
          '<span class="box">' + (r[1] ? window.Icons.check : '') + '</span>' + r[0] + '</span>' +
          (r[2] ? '<span class="k" style="width:auto;margin:0 6px">保留最近</span>' +
            '<span class="s-input" style="width:86px"><input type="text" value="' + r[2] + '"><span class="suffix">天</span></span>' : '') +
          '</div>';
      }).join('') +
      '<div class="alert-danger" style="margin-top:12px"><span class="ai" data-icon="warn"></span>' +
      '清理操作不可恢复，请谨慎操作</div>' +
      '<div class="card-actions"><button class="btn-red" type="button" data-act2="立即清理">' +
      '<span class="bi" data-icon="trash"></span>立即清理</button></div>');

    const bkRows = [
      ['1', '2026-09-21 02:30', '自动备份', '256 MB', S.tag('成功', 'green', true)],
      ['2', '2026-09-20 02:30', '自动备份', '248 MB', S.tag('成功', 'green', true)],
      ['3', '2026-09-19 02:31', '自动备份', '245 MB', S.tag('成功', 'green', true)],
      ['4', '2026-09-18 14:20', '手动备份', '260 MB', S.tag('成功', 'green', true)],
      ['5', '2026-09-17 02:30', '自动备份', '242 MB', S.tag('成功', 'green', true)]
    ].map(function (r) {
      return r.concat(['<span class="ico-cell"><button class="tbtn icon" type="button" data-act2="下载"><span data-icon="download"></span></button>' +
        '<button class="tbtn icon danger" type="button" data-act2="删除备份"><span data-icon="trash"></span></button></span>']);
    });
    const bkCard = S.card('stat-clock', '备份记录',
      S.dtable([{ t: '#' }, { t: '备份时间' }, { t: '备份类型' }, { t: '文件大小' }, { t: '状态' }, { t: '操作' }], bkRows) +
      pager('共 12 条', ['1', '2', '3'], '5 条/页'),
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="查看更多">查看更多<span class="chev" data-icon="chevR"></span></a>');

    const dbRows = [
      ['users', '12', '128 KB', '用户信息表'], ['models', '6', '256 KB', '模型配置表'],
      ['tools', '28', '512 KB', '工具接口表'], ['tasks', '1,284', '320 KB', '任务记录表'],
      ['logs', '52,691', '420 KB', '系统日志表'], ['configs', '42', '64 KB', '系统配置表'],
      ['audit_logs', '3,215', '96 KB', '审计日志表']
    ];
    const dbCard = S.card('db', '数据库信息', S.dtable([{ t: '表名' }, { t: '记录数' }, { t: '大小' }, { t: '说明' }], dbRows));

    const storeItems = [
      { name: '任务记录', text: '320 MB', pct: 25.8, color: '#2E90FA' },
      { name: '日志数据', text: '420 MB', pct: 33.9, color: '#12B76A' },
      { name: '模型数据', text: '256 MB', pct: 20.6, color: '#F79009' },
      { name: '系统配置', text: '128 MB', pct: 10.3, color: '#8B5CF6' },
      { name: '其他', text: '116 MB', pct: 9.4, color: '#B4BECD' }
    ];
    const storeCard = S.card('db', '存储使用情况', donut(storeItems, '1.24 GB', '总计'));

    return stats + S.grid3(backupCard + ioCard + cleanCard) + S.grid3(bkCard + dbCard + storeCard);
  }

  /* ============================ 用户与权限 ============================ */
  function usersTab() {
    const stats = S.stat4([
      { icon: 'user', tone: 'blue', label: '用户总数', value: '12', sub: '较昨日 <span class="dl-bad">+1 ↑</span>' },
      { icon: 'user', tone: 'green', label: '启用用户', value: '10', sub: '83.3%' },
      { icon: 'user', tone: 'orange', label: '禁用用户', value: '2', sub: '16.7%' },
      { icon: 'shield', tone: 'purple', label: '角色总数', value: '5', sub: '较昨日 <span class="dl-mute">+0</span>' }
    ]);

    const roleTag = { '超级管理员': 'purple', '工程师': 'blue', '分析师': 'blue', '访客': 'orange' };
    const uRows = [
      ['1', 'admin', '系统管理员', 'admin@local', '超级管理员', '在线', '2026-09-21 14:20:15'],
      ['2', 'zhangsan', '张三', 'zhangsan@company.com', '工程师', '在线', '2026-09-21 13:45:22'],
      ['3', 'lisi', '李四', 'lisi@company.com', '工程师', '离线', '2026-09-20 18:11:03'],
      ['4', 'wangwu', '王五', 'wangwu@company.com', '分析师', '离线', '2026-09-21 11:32:18'],
      ['5', 'zhaoliu', '赵六', 'zhaoliu@company.com', '访客', '离线', '2026-09-19 09:15:44'],
      ['6', 'test', '测试用户', 'test@company.com', '工程师', '禁用', '2026-09-18 16:22:07']
    ].map(function (r) {
      const st = r[5] === '在线' ? S.tag('在线', 'green', true) : r[5] === '禁用' ? S.tag('禁用', 'red', true) : S.tag('离线', 'gray', true);
      return ['<input type="checkbox" style="accent-color:var(--brand)">', r[0], r[1], r[2], r[3],
        S.tag(r[4], roleTag[r[4]] || 'gray'), st, r[6],
        '<span style="display:flex;gap:4px"><button class="tbtn link" type="button" data-act2="编辑用户">编辑</button>' +
        '<button class="tbtn icon" type="button" data-act2="更多"><span data-icon="more"></span></button></span>'];
    });
    const listCard = S.card('user', '用户列表',
      '<div class="toolbar">' + searchBox('搜索用户名、姓名、邮箱或角色...') +
      '<span class="select-like"><select><option>全部角色</option></select><span class="chev" data-icon="chevD"></span></span>' +
      '<button class="btn-blue" type="button" data-act2="新建用户"><span class="bi" data-icon="plus"></span>新建用户</button>' +
      '<button class="btn-w" type="button" data-act2="刷新"><span class="bi" data-icon="refresh"></span>刷新</button>' +
      '<button class="btn-w" type="button" data-act2="导出"><span class="bi" data-icon="download"></span>导出</button></div>' +
      S.dtable([{ t: '' }, { t: '#' }, { t: '用户名' }, { t: '姓名' }, { t: '邮箱' }, { t: '角色' },
        { t: '状态' }, { t: '最后登录时间' }, { t: '操作' }], uRows) +
      pager('共 12 条', ['1', '2'], '10 条/页'));

    const detailCard = S.card('user', '',
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">' +
      '<span style="width:44px;height:44px;border-radius:50%;background:#E9EDF4;color:#5A6884;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:700">Z</span>' +
      '<span><span style="display:flex;align-items:center;gap:8px"><b style="font-size:16px;color:var(--text-1)">zhangsan</b>' +
      S.tag('在线', 'green', true) + '</span>' +
      '<span style="display:block;margin-top:5px">' + S.tag('工程师', 'blue') + '</span></span></div>' +
      '<div style="font-size:14px;color:var(--text-2)">zhangsan@company.com</div>' +
      '<div style="font-size:13px;color:var(--text-3);margin:8px 0 12px">这个用户很懒，什么也没有留下~</div>' +
      '<div class="kv-list">' +
      [['用户名', 'zhangsan'], ['姓名', '张三'], ['邮箱', 'zhangsan@company.com'], ['手机号', '138****1234'],
        ['所属角色', S.tag('工程师', 'blue')], ['账号状态', S.tag('启用', 'green', true)],
        ['创建时间', '2026-08-15 10:20:33'], ['最后登录', '2026-09-21 13:45:22'], ['登录IP', '192.168.1.100']]
        .map(function (r) { return '<div class="r"><dt style="width:80px">' + r[0] + '</dt><dd>' + r[1] + '</dd></div>'; }).join('') +
      '</div>' +
      '<div class="card-actions" style="justify-content:flex-start">' +
      '<button class="btn-w" type="button" data-act2="重置密码"><span class="bi" data-icon="key"></span>重置密码</button>' +
      '<button class="btn-w" type="button" data-act2="禁用用户"><span class="bi" data-icon="lock"></span>禁用用户</button>' +
      '<button class="btn-red" type="button" data-act2="删除用户"><span class="bi" data-icon="trash"></span>删除用户</button></div>',
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="编辑">编辑<span class="chev" data-icon="chevR"></span></a>');

    const roleRows = [
      ['1', '超级管理员', '拥有系统所有权限', '2'], ['2', '工程师', '可访问建模、分析等功能', '6'],
      ['3', '分析师', '可查看结果和数据', '2'], ['4', '访客', '只读权限', '1'],
      ['5', '自定义角色', '自定义权限角色', '1']
    ].map(function (r) {
      return r.concat(['<span style="display:flex;gap:4px"><button class="tbtn link" type="button" data-act2="编辑角色">编辑</button>' +
        '<button class="tbtn icon" type="button" data-act2="更多"><span data-icon="more"></span></button></span>']);
    });
    const roleCard = S.card('shield', '角色管理',
      S.dtable([{ t: '#' }, { t: '角色名称' }, { t: '描述' }, { t: '用户数' }, { t: '操作' }], roleRows),
      '<button class="btn-w" style="margin-left:auto;height:32px;padding:0 12px" type="button" data-act2="新建角色">' +
      '<span class="bi" data-icon="plus"></span>新建角色</button>');

    const tree = function (name, count, children) {
      return '<div class="node on"><span class="ch" data-icon="chevD"></span>' +
        '<span class="cb">' + window.Icons.check + '</span><span class="nm">' + name + '</span>' +
        '<span class="cnt">(' + count + ')</span></div>' +
        (children ? '<div class="child">' + children.map(function (c) {
          return '<div class="node on"><span class="cb">' + window.Icons.check + '</span><span class="nm">' + c + '</span></div>';
        }).join('') + '</div>' : '');
    };
    const permCard = S.card('shield', '权限管理',
      '<div class="tree">' +
      tree('系统管理', 8, ['系统设置', '用户管理', '日志查看']) +
      tree('模型管理', 6) + tree('任务管理', 4) + tree('工具接口', 5) + tree('数据管理', 4) +
      '</div>');

    const policyCard = S.card('lock', '安全策略',
      '<div style="display:grid;grid-template-columns:1fr 1fr;gap:0 20px">' +
      '<div>' + S.togRow('启用登录验证', true) + S.numRow('密码最小长度', '8', '', false, 96) +
      S.numRow('账号登录失败锁定', '5', '', false, 96) + S.numRow('锁定时长（分钟）', '30', '', false, 96) + '</div>' +
      '<div>' + S.togRow('密码登录策略', true) + S.togRow('强制密码复杂度', true) +
      S.togRow('最大失败次数策略', true) + S.togRow('登录日志记录', true) + '</div></div>',
      '<a class="link-more" style="margin-left:auto" href="javascript:void(0)" data-more="编辑">编辑<span class="chev" data-icon="chevR"></span></a>');

    return stats + S.grid2(listCard + detailCard) + S.grid2(roleCard + permCard) + policyCard;
  }

  window.SettingsTabs = window.SettingsTabs || {};
  window.SettingsTabs.model = { render: modelTab };
  window.SettingsTabs.data = { render: dataTab };
  window.SettingsTabs.users = { render: usersTab };
})();
