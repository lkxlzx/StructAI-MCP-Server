/* 实时数据层（P181）：把 /api/* 的响应映射成页面需要的形状。
   每个函数失败都返回 null —— 调用方保留 mock 数据（界面不因后端未启动而空白）。 */
(function () {
  function pick(result) { return result && result.ok ? result.data : null; }

  function taskStatus(value) {
    const status = String(value || '').toUpperCase();
    if (status === 'COMPLETED') return 'done';
    if (status === 'FAILED' || status === 'TIMEOUT' || status === 'CANCELLED') return 'failed';
    if (status === 'QUEUED' || status === 'CREATED' || status === 'VALIDATING') return 'queued';
    return 'running';
  }

  function shortTime(value) {
    if (!value) return '-';
    const text = String(value);
    const match = text.match(/T(\d{2}:\d{2}:\d{2})/);
    return match ? match[1] : text.slice(0, 19);
  }

  window.Live = {
    /* 首页：状态 / 指标卡 / 事件 / 任务 / 趋势（趋势暂无后端，保留 mock） */
    home: async function () {
      const status = pick(await window.Api.get('/api/status'));
      if (!status) return null;
      const stats = pick(await window.Api.get('/api/stats')) || [];
      const events = pick(await window.Api.get('/api/events?limit=10')) || { items: [] };
      const tasks = pick(await window.Api.get('/api/tasks?limit=5')) || { items: [] };
      return {
        status: status,
        registry: status.registry || {},
        templates: status.templates || {},
        stats: stats.map(function (card) {
          return {
            icon: card.key === 'service' ? 'stat-server'
              : card.key === 'clients' ? 'stat-client'
              : card.key === 'tasks' ? 'stat-task'
              : card.key === 'requests' ? 'stat-check' : 'stat-clock',
            label: card.label,
            valueHtml: window.UI.esc(String(card.value)) +
              (card.delta ? '<span class="stat-delta delta-up">' + window.UI.esc(card.delta) + '</span>' : ''),
            valueClass: card.tone === 'green' ? 'is-text is-green' : '',
            footHtml: window.UI.esc(String(card.foot || ''))
          };
        }),
        events: {
          items: (events.items || []).map(function (item) {
            return {
              time: shortTime(item.time),
              text: item.action + (item.resource ? ' · ' + item.resource : ''),
              level: String(item.result || '').toUpperCase() === 'SUCCESS' ? 'ok'
                : String(item.result || '').toUpperCase() === 'FAILED' ? 'error' : 'info'
            };
          })
        },
        tasks: {
          rows: (tasks.items || []).map(function (task) {
            return {
              id: task.id, type: task.operation, client: task.tool,
              status: taskStatus(task.status), progress: task.progress || 0,
              start: shortTime(task.created_at)
            };
          })
        }
      };
    },

    /* MIDAS 客户端页：实例列表 */
    clients: async function () {
      const payload = pick(await window.Api.get('/api/clients'));
      if (!payload) return null;
      return (payload.items || []).map(function (item, index) {
        const name = String(item.name || item.id);
        return {
          id: item.id,
          letter: name.slice(0, 1).toUpperCase(),
          color: ['#0D72F7', '#0054F3', '#8936F5', '#FE620F', '#09A96E'][index % 5],
          name: name,
          kind: item.product || item.vendor || '',
          api: item.endpoint || '-',
          online: !!item.online,
          ver: item.version || '-',
          credential: item.credential_reference || '-'
        };
      });
    },

    /* 工具与接口页：端点列表（按命名空间） */
    endpoints: async function (namespace, query) {
      const path = '/api/endpoints?limit=200'
        + (namespace ? '&namespace=' + encodeURIComponent(namespace) : '')
        + (query ? '&q=' + encodeURIComponent(query) : '');
      const payload = pick(await window.Api.get(path));
      return payload ? payload.items || [] : null;
    },

    endpoint: async function (key) {
      return pick(await window.Api.get('/api/endpoints/' + encodeURIComponent(key)));
    },

    /* 模板库 */
    templates: async function () {
      return pick(await window.Api.get('/api/templates'));
    },

    template: async function (name) {
      return pick(await window.Api.get('/api/templates/' + encodeURIComponent(name)));
    },

    /* 任务 / 日志 */
    tasks: async function (limit) {
      return pick(await window.Api.get('/api/tasks?limit=' + (limit || 50)));
    },

    events: async function (limit) {
      return pick(await window.Api.get('/api/events?limit=' + (limit || 50)));
    }
  };
})();
