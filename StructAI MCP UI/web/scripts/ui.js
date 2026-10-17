/* 通用渲染片段 */
(function () {
  const esc = function (s) {
    return String(s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  };

  const STATUS = {
    running: { text: '运行中', cls: 'pill-blue', dot: 'dot-blue', bar: '' },
    done: { text: '已完成', cls: 'pill-green', dot: 'dot-green', bar: 'is-done' },
    failed: { text: '失败', cls: 'pill-red', dot: 'dot-red', bar: 'is-fail' },
    queued: { text: '排队中', cls: 'pill-gray', dot: 'dot-orange', bar: '' }
  };

  const LEVEL = { ok: 'dot-green', info: 'dot-blue', error: 'dot-red', warn: 'dot-orange' };

  window.UI = {
    esc: esc,

    /* 状态徽标 */
    pill: function (status) {
      const s = STATUS[status] || STATUS.queued;
      return '<span class="pill ' + s.cls + '"><span class="dot ' + s.dot + '"></span>' + s.text + '</span>';
    },

    /* 进度条 */
    progress: function (row) {
      const s = STATUS[row.status] || STATUS.queued;
      const w = Math.max(0, Math.min(100, row.progress));
      return '<div class="progress"><div class="progress-track">' +
        '<div class="progress-fill ' + s.bar + '" style="width:' + w + '%"></div></div>' +
        '<span class="progress-text">' + w + '%</span></div>';
    },

    /* 指标卡 */
    statCard: function (s) {
      return '<article class="stat-card">' +
        '<div class="stat-top">' +
        '<div class="stat-icon" data-icon="' + s.icon + '"></div>' +
        '<div class="stat-body">' +
        '<div class="stat-label">' + esc(s.label) + '</div>' +
        '<div class="stat-value ' + (s.valueClass || '') + '">' + (s.valueHtml || '') + '</div>' +
        '</div></div>' +
        '<div class="stat-foot">' + (s.footHtml || '') + '</div>' +
        '</article>';
    },

    /* 卡片头（标题 + 右侧扩展） */
    cardHead: function (title, right) {
      return '<div class="card-head"><h2 class="card-title">' + esc(title) + '</h2>' +
        (right || '') + '</div>';
    },

    moreLink: function (text) {
      return '<a class="link-more" href="javascript:void(0)" data-more="' + esc(text) + '">' +
        esc(text) + '<span class="chev" data-icon="chevR"></span></a>';
    },

    /* 事件行 */
    eventRow: function (e) {
      return '<li class="event-item is-' + (e.level === 'error' ? 'error' : 'info') + '">' +
        '<span class="dot ' + (LEVEL[e.level] || 'dot-blue') + '"></span>' +
        '<span class="event-time">' + esc(e.time) + '</span>' +
        '<span class="event-text">' + esc(e.text) + '</span></li>';
    },

    /* 任务表 */
    taskTable: function (tasks) {
      const head = '<tr>' + tasks.columns.map(function (c) {
        return '<th' + (c === '操作' ? ' class="col-actions"' : '') + '>' + esc(c) + '</th>';
      }).join('') + '</tr>';
      const body = tasks.rows.map(function (r) {
        return '<tr>' +
          '<td class="col-id">' + esc(r.id) + '</td>' +
          '<td>' + esc(r.type) + '</td>' +
          '<td class="col-muted">' + esc(r.client) + '</td>' +
          '<td>' + UI.pill(r.status) + '</td>' +
          '<td>' + UI.progress(r) + '</td>' +
          '<td class="col-time">' + esc(r.start) + '</td>' +
          '<td class="col-actions"><button class="row-more" type="button" title="更多操作" ' +
          'data-task="' + esc(r.id) + '" data-icon="more"></button></td>' +
          '</tr>';
      }).join('');
      return '<table class="table"><thead>' + head + '</thead><tbody>' + body + '</tbody></table>';
    }
  };
})();
