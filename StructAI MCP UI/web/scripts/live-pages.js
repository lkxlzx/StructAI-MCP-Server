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
      if (tbody && live.tasks) replaceHtml(tbody, taskRows(live.tasks.rows));
      window.Icons.mount(root);
      return;
    }

    if (name === 'midas') {
      const tbody = root.querySelector('.client-table tbody');
      if (tbody && Array.isArray(live)) {
        replaceHtml(tbody, live.map(function (row) {
          return '<tr data-client="' + window.UI.esc(row.id) + '">' +
            '<td><div class="name-cell"><span class="letter-avatar" style="background:' + row.color + '">' +
            window.UI.esc(row.letter) + '</span><span class="name-text">' + window.UI.esc(row.name) + '</span></div></td>' +
            '<td class="muted">' + window.UI.esc(row.kind) + '</td>' +
            '<td class="muted">' + window.UI.esc(row.api) + '</td>' +
            '<td><span class="state-cell ' + (row.online ? 'on' : 'off') + '">' +
            '<span class="dot ' + (row.online ? 'dot-green' : 'dot-gray') + '"></span>' +
            (row.online ? '已连接' : '未连接') + '</span></td>' +
            '<td class="muted">' + window.UI.esc(row.ver) + '</td>' +
            '<td class="col-ops"><button class="row-more" type="button" data-more="客户端操作" data-icon="more"></button></td></tr>';
        }).join(''));
        window.Icons.mount(root);
      }
      return;
    }
  };
})();
