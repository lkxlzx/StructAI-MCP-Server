/* 实时渲染（P181）：把 Live.* 的数据覆盖到已渲染的 mock 视图上。
   只改**数据区域**（指标卡 / 表格 / 列表），不动布局与样式。 */
(function () {
  function replaceHtml(node, html) { if (node) node.innerHTML = html; }

  function taskRows(rows) {
    return rows.map(function (row) {
      const tone = row.status === 'done' ? 'green' : row.status === 'failed' ? 'red'
        : row.status === 'queued' ? 'gray' : 'blue';
      return '<tr><td class="mono">' + window.UI.esc(row.id) + '</td>' +
        '<td>' + window.UI.esc(row.type) + '</td>' +
        '<td class="muted">' + window.UI.esc(row.client) + '</td>' +
        '<td><span class="badge badge-' + tone + '">' + window.UI.esc(row.status) + '</span></td>' +
        '<td>' + Number(row.progress || 0) + '%</td>' +
        '<td class="muted">' + window.UI.esc(row.start) + '</td></tr>';
    }).join('');
  }

  /* 外壳（顶栏状态 / 版本 / 侧栏服务卡）—— 与首页同一份 /api/status */
  function shell(status) {
    if (!status) return;
    const service = status.service || {};
    const tasks = status.tasks || {};
    const clients = status.clients || {};

    const run = document.getElementById('runState');
    if (run) {
      run.innerHTML = '<span class="dot ' + (service.running ? 'dot-green' : 'dot-gray') + '"></span>' +
        '<span class="run-state-text">' + (service.running ? 'MCP 运行中' : 'MCP 已停止') + '</span>';
    }
    const badge = document.getElementById('versionBadge');
    if (badge && service.version) badge.textContent = service.version;

    const side = document.getElementById('sideStatus');
    if (side) {
      side.innerHTML =
        '<div class="side-status-head"><span class="dot ' + (service.running ? 'dot-green' : 'dot-gray') + '"></span>' +
        '<span>' + (service.running ? 'MCP 服务运行中' : 'MCP 服务已停止') + '</span></div>' +
        '<dl class="side-rows">' +
          '<div class="side-row"><dt>已连接客户端</dt><dd>' + (clients.connected || 0) + '</dd></div>' +
          '<div class="side-row"><dt>活跃任务</dt><dd>' + (tasks.active || 0) + '</dd></div>' +
          '<div class="side-row"><dt>端点总数</dt><dd>' + ((status.registry || {}).endpoints || 0) + '</dd></div>' +
        '</dl>' +
        '<button class="side-btn" id="sideAction" type="button">' +
        '<span class="side-btn-icon" data-icon="stop"></span><span>停止服务</span></button>';
      window.Icons.mount(side);
    }
  }

  function emptyRow(cols, text) {
    return '<tr class="empty-row"><td colspan="' + cols + '">' + text + '</td></tr>';
  }

  window.PageLive = function (name, root, live) {
    if (name === 'home') {
      /* 指标卡：整行替换（数据来自 /api/stats） */
      const stats = root.querySelector('.stat-row');
      if (stats && live.stats && live.stats.length) {
        replaceHtml(stats, live.stats.map(function (card) { return window.UI.statCard(card); }).join(''));
      }
      /* 系统事件 */
      const events = root.querySelector('.events-list');
      if (events && live.events) {
        replaceHtml(events, live.events.items.map(function (item) {
          return window.UI.eventRow(item);
        }).join(''));
      }
      /* 最近任务表体 */
      const tbody = root.querySelector('.table-wrap tbody');
      if (tbody && live.tasks) {
        replaceHtml(tbody, live.tasks.rows.length
          ? taskRows(live.tasks.rows)
          : emptyRow(7, '暂无任务'));
      }
      /* 空事件列表 */
      const eventList = root.querySelector('.events-list');
      if (eventList && live.events && !live.events.items.length) {
        replaceHtml(eventList, '<li class="event-empty">暂无系统事件</li>');
      }
      shell(live.status);
      window.Icons.mount(root);
      return;
    }

    /* MIDAS 客户端页由 `pages/clients.js` 自行管理（P185）。 */
  };
})();
