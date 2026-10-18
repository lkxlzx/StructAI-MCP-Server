/* MCP 服务器 */
(function () {
  const D = {
    head: { title: 'MCP 服务器', sub: '配置和管理 MCP 服务，支持多种传输方式和客户端连接', action: '重启服务' },
    stats: [
      {
        icon: 'stat-server', label: '服务状态',
        valueHtml: '<span class="dot dot-green"></span>运行中', valueClass: 'is-text is-green',
        footHtml: '<span>v1.0.0</span><span>运行时间 2 天 6 小时</span>'
      },
      {
        icon: 'stat-client', label: '已连接客户端', valueHtml: '2',
        footHtml: '<span>总计 <span class="v">5</span></span>' +
          '<span class="mcp-chip">+12% <span style="font-size:11px">↑</span></span>'
      },
      {
        icon: 'stat-task', label: '活跃任务', valueHtml: '1',
        footHtml: '<span>排队 <span class="v">0</span></span><span class="bar">|</span>' +
          '<span>失败 <span class="bad">1</span></span>'
      },
      {
        icon: 'tools', label: '今日请求数',
        valueHtml: '128<span class="mcp-delta">↑ 12%</span>',
        footHtml: '<span>昨日 <span class="v">114</span></span>'
      },
      {
        icon: 'stat-clock', label: '平均响应时间',
        valueHtml: '45<span class="unit">ms</span><span class="mcp-delta">↓ 18%</span>',
        footHtml: '<span>昨日 <span class="v">55 ms</span></span>'
      }
    ],
    basic: {
      title: '基本配置',
      listen: [
        { key: '监听地址', req: true, value: '0.0.0.0', hint: 'MCP 服务监听的 IP 地址，0.0.0.0 表示所有网络接口' },
        { key: '监听端口', req: true, value: '8765', spin: true, hint: 'MCP 服务监听的端口号' }
      ],
      transports: {
        label: '传输方式',
        items: [
          { name: 'STDI O（本地进程）', desc: '通过标准输入输出与本地客户端通信', on: false },
          { name: 'HTTP（REST）', desc: '通过 HTTP 协议提供 MCP 服务', on: true },
          { name: 'SSE（Server-Sent Events）', desc: '支持流式响应和实时状态更新', on: true }
        ]
      },
      service: [
        { key: '服务名称', value: 'StructAI MIDAS MCP', hint: '在客户端中显示的服务名称', wide: true },
        { key: '服务描述', value: 'Connect MIDAS · Empower Engineering with AI', hint: 'MCP 服务的描述信息', wide: true }
      ],
      advanced: {
        title: '高级设置',
        fields: [
          { key: '请求超时（秒）', value: '300', spin: true },
          { key: '最大并发连接', value: '50', spin: true },
          { key: '最大请求体大小（MB）', value: '50', spin: true },
          { key: '日志级别', value: 'INFO', select: ['INFO', 'DEBUG', 'WARN', 'ERROR'] }
        ]
      },
      actions: [{ label: '保存配置', primary: true }, { label: '恢复默认' }]
    },
    side: {
      clients: {
        title: '连接的客户端', link: '查看全部',
        columns: ['客户端名称', '类型', '连接时间', '状态', '操作'],
        rows: [
          { name: 'Cursor AI', kind: 'IDE', time: '2025-08-16 14:20:15', online: true },
          { name: 'StructAI Web', kind: 'Web', time: '2025-08-16 14:22:10', online: true }
        ]
      },
      requests: {
        title: '最近请求', link: '查看全部',
        columns: ['时间', '客户端', '方法', '路径', '状态', '耗时'],
        rows: [
          { time: '14:23:45', client: 'Cursor AI', method: 'POST', path: '/db/NODE', code: 200, ms: '32 ms' },
          { time: '14:22:10', client: 'StructAI Web', method: 'GET', path: '/view/MODEL', code: 200, ms: '28 ms' },
          { time: '14:18:33', client: 'Cursor AI', method: 'POST', path: '/anal/START', code: 202, ms: '125 ms' },
          { time: '14:15:21', client: 'StructAI Web', method: 'GET', path: '/post/RESULT', code: 200, ms: '41 ms' },
          { time: '13:50:12', client: 'Cursor AI', method: 'DELETE', path: '/db/ELEM', code: 200, ms: '37 ms' }
        ]
      },
      ops: {
        title: '服务操作',
        buttons: [
          { label: '停止服务', icon: 'stop', cls: 'btn-danger-outline' },
          { label: '重启服务', icon: 'refresh', cls: 'btn-plain' },
          { label: '查看日志', icon: 'fileText', cls: 'btn-plain' },
          { label: '打开配置文件', icon: 'fileText', cls: 'btn-plain' }
        ]
      }
    }
  };

  function field(f, extraCls) {
    const spin = f.spin ?
      '<span class="spin"><button type="button" tabindex="-1" data-spin="up"><span data-icon="chevD"></span></button>' +
      '<button type="button" tabindex="-1" data-spin="down"><span data-icon="chevD"></span></button></span>' : '';
    let inner;
    if (f.select) {
      inner = '<span class="select-like field-select"><select aria-label="' + f.key + '">' +
        f.select.map(function (o) { return '<option>' + o + '</option>'; }).join('') +
        '</select><span class="chev" data-icon="chevD"></span></span>';
    } else {
      inner = '<span class="field-input"><input type="text" value="' + f.value + '" class="' +
        (f.numeric ? '' : 'is-text') + '">' + spin + '</span>';
    }
    return '<div class="adv-field ' + (extraCls || '') + '">' +
      '<label class="field-label">' + f.key + (f.req ? '<span class="req">*</span>' : '') + '</label>' +
      inner + (f.hint ? '<div class="field-hint">' + f.hint + '</div>' : '') + '</div>';
  }

  function render() {
    const d = D;

    const stats = d.stats.map(function (s) {
      return '<article class="mcp-stat">' +
        '<div class="mcp-stat-top">' +
        '<div class="stat-icon" data-icon="' + s.icon + '"></div>' +
        '<div class="stat-body">' +
        '<div class="mcp-stat-label">' + s.label + '</div>' +
        '<div class="mcp-stat-value ' + (s.valueClass || '') + '">' + s.valueHtml + '</div>' +
        '</div></div>' +
        '<div class="mcp-stat-foot">' + s.footHtml + '</div></article>';
    }).join('');

    const b = d.basic;
    const listen = b.listen.map(function (f) { return field(f); }).join('');
    const transports = b.transports.items.map(function (t) {
      return '<div class="check-row' + (t.on ? ' is-on' : '') + '" data-transport="' + t.name + '">' +
        '<span class="cbx">' + (t.on ? window.Icons.check : '') + '</span>' +
        '<span><span class="cname">' + t.name + '</span><span class="cdesc" style="display:block">' + t.desc + '</span></span>' +
        '</div>';
    }).join('');
    const service = b.service.map(function (f) { return field(f); }).join('');
    const advFields = b.advanced.fields.map(function (f) { return field(f); }).join('');
    const actions = b.actions.map(function (a) {
      return '<button class="' + (a.primary ? 'btn-solid' : 'btn-plain') + '" type="button" data-act="' + a.label + '">' + a.label + '</button>';
    }).join('');

    const sc = d.side.clients;
    const clientCols = sc.columns.map(function (c, i) {
      return '<th' + (i === sc.columns.length - 1 ? ' class="col-ops"' : '') + '>' + c + '</th>';
    }).join('');
    const clientRows = sc.rows.map(function (r) {
      return '<tr><td>' + r.name + '</td><td class="col-mid">' + r.kind + '</td>' +
        '<td class="col-time">' + r.time + '</td>' +
        '<td><span class="state-cell on"><span class="dot dot-green"></span>已连接</span></td>' +
        '<td class="col-ops"><button class="row-more" type="button" data-more="客户端操作" data-icon="more"></button></td></tr>';
    }).join('');

    const sq = d.side.requests;
    const reqCols = sq.columns.map(function (c) { return '<th>' + c + '</th>'; }).join('');
    const reqRows = sq.rows.map(function (r) {
      return '<tr><td class="col-time">' + r.time + '</td><td>' + r.client + '</td>' +
        '<td class="col-mid">' + r.method + '</td><td class="col-mid">' + r.path + '</td>' +
        '<td><span class="code-dot ' + (r.code === 200 ? 'ok' : 'info') + '">' + r.code + '</span></td>' +
        '<td class="col-time">' + r.ms + '</td></tr>';
    }).join('');

    const ops = d.side.ops.buttons.map(function (b2) {
      return '<button class="' + b2.cls + '" type="button" data-op="' + b2.label + '">' +
        '<span class="bi" data-icon="' + b2.icon + '"></span>' + b2.label + '</button>';
    }).join('');

    return '' +
      '<section class="mcp-head">' +
        '<span class="mcp-head-accent"></span>' +
        '<h1 class="mcp-title">' + d.head.title + '</h1>' +
        '<p class="mcp-sub">' + d.head.sub + '</p>' +
        '<div class="mcp-head-actions">' +
          '<button class="btn-outline-blue" type="button" data-act="' + d.head.action + '">' +
          '<span class="bi" data-icon="refresh"></span>' + d.head.action + '</button>' +
        '</div>' +
      '</section>' +

      '<section class="mcp-stats">' + stats + '</section>' +

      '<div class="mcp-split">' +
        '<section class="mcp-card">' +
          '<h2 class="mcp-card-title">' + b.title + '</h2>' +
          '<div class="form-row">' + listen + '</div>' +
          '<div class="transports">' +
            '<div class="transports-label">' + b.transports.label + '</div>' + transports +
          '</div>' +
          '<div class="form-row">' + service + '</div>' +
          '<div class="adv">' +
            '<div class="adv-head" data-adv="toggle"><span class="chev" data-icon="chevD"></span>' +
            b.advanced.title + '</div>' +
            '<div class="adv-body">' + advFields + '</div>' +
          '</div>' +
          '<div class="form-actions">' + actions + '</div>' +
        '</section>' +

        '<aside class="mcp-side">' +
          '<section class="mcp-card">' +
            '<div class="side-card-head2"><h2 class="mcp-card-title">' + sc.title + '</h2>' +
            '<a class="link-more" href="javascript:void(0)" data-more="' + sc.link + '">' + sc.link +
            '<span class="chev" data-icon="chevR"></span></a></div>' +
            '<div class="mini-table-wrap"><table class="mini-table"><thead><tr>' + clientCols + '</tr></thead><tbody>' + clientRows + '</tbody></table></div>' +
          '</section>' +

          '<section class="mcp-card">' +
            '<div class="side-card-head2"><h2 class="mcp-card-title">' + sq.title + '</h2>' +
            '<a class="link-more" href="javascript:void(0)" data-more="' + sq.link + '">' + sq.link +
            '<span class="chev" data-icon="chevR"></span></a></div>' +
            '<div class="mini-table-wrap"><table class="mini-table"><thead><tr>' + reqCols + '</tr></thead><tbody>' + reqRows + '</tbody></table></div>' +
          '</section>' +

          '<section class="mcp-card">' +
            '<h2 class="mcp-card-title">' + d.side.ops.title + '</h2>' +
            '<div class="ops-btns">' + ops + '</div>' +
          '</section>' +
        '</aside>' +
      '</div>';
  }

  function mount(root) {
    root.querySelectorAll('.check-row').forEach(function (row) {
      row.addEventListener('click', function () {
        row.classList.toggle('is-on');
        const box = row.querySelector('.cbx');
        box.innerHTML = row.classList.contains('is-on') ? window.Icons.check : '';
      });
    });
    const adv = root.querySelector('[data-adv]');
    if (adv) adv.addEventListener('click', function () {
      const body = root.querySelector('.adv-body');
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? '' : 'none';
      adv.querySelector('.chev').style.transform = hidden ? '' : 'rotate(-90deg)';
    });
    root.querySelectorAll('[data-act],[data-op]').forEach(function (b) {
      b.addEventListener('click', function () {
        window.Toast.show('执行：' + (b.dataset.act || b.dataset.op));
      });
    });
  }

  window.PageMcp = { data: function () { return D; }, render: render, mount: mount };
})();
