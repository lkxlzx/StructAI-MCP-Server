/* 管理面 API 客户端（P181）
   - 与核心服务同源部署：/api/*（无需 CORS）
   - Token 只存 sessionStorage（关闭标签页即失效；不写 localStorage）
   - 所有请求失败都返回 null，调用方回落到 mock 数据（离线也能看界面） */
(function () {
  const TOKEN_KEY = 'structai.ui.token';
  const BASE = '';

  function token() {
    try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; }
  }

  function setToken(value) {
    try {
      if (value) sessionStorage.setItem(TOKEN_KEY, value);
      else sessionStorage.removeItem(TOKEN_KEY);
    } catch (e) { /* 隐私模式：忽略 */ }
  }

  async function request(method, path, body) {
    const headers = { 'Accept': 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const current = token();
    if (current) headers['Authorization'] = 'Bearer ' + current;
    try {
      const response = await fetch(BASE + path, {
        method: method,
        headers: headers,
        body: body === undefined ? undefined : JSON.stringify(body)
      });
      const text = await response.text();
      let payload = null;
      try { payload = text ? JSON.parse(text) : null; } catch (e) { payload = null; }
      if (response.status === 401) {
        setToken('');
        return { ok: false, status: 401, data: payload };
      }
      return { ok: response.ok, status: response.status, data: payload };
    } catch (e) {
      return { ok: false, status: 0, data: null, offline: true };
    }
  }

  window.Api = {
    token: token,
    setToken: setToken,
    get: function (path) { return request('GET', path); },
    post: function (path, body) { return request('POST', path, body || {}); },
    put: function (path, body) { return request('PUT', path, body || {}); },
    del: function (path) { return request('DELETE', path); },
    /* ===== MIDAS 客户端（P185）===== */
    clientOptions: function () { return request('GET', '/api/clients/options'); },
    createClient: function (payload) { return request('POST', '/api/clients', payload); },
    updateClient: function (id, payload) {
      return request('PUT', '/api/clients/' + encodeURIComponent(id), payload);
    },
    deleteClient: function (id) { return request('DELETE', '/api/clients/' + encodeURIComponent(id)); },
    testClient: function (id) { return request('POST', '/api/clients/' + encodeURIComponent(id) + '/test', {}); },
    clientEvents: function (id) { return request('GET', '/api/clients/' + encodeURIComponent(id) + '/events'); },

    /* ===== 系统设置（P183 / P185）===== */
    clients: function () { return request('GET', '/api/clients'); },
    settings: function () { return request('GET', '/api/settings'); },
    saveSettings: function (section, values) {
      return request('PUT', '/api/settings/' + encodeURIComponent(section), values);
    },
    resetSettings: function (section) {
      return request('POST', '/api/settings/reset', { section: section || '' });
    },
    users: function (query) {
      return request('GET', '/api/users' + (query ? '?q=' + encodeURIComponent(query) : ''));
    },
    createUser: function (payload) { return request('POST', '/api/users', payload); },
    updateUser: function (id, payload) { return request('PUT', '/api/users/' + encodeURIComponent(id), payload); },
    deleteUser: function (id) { return request('DELETE', '/api/users/' + encodeURIComponent(id)); },
    roles: function () { return request('GET', '/api/roles'); },
    createRole: function (payload) { return request('POST', '/api/roles', payload); },
    updateRole: function (id, payload) { return request('PUT', '/api/roles/' + encodeURIComponent(id), payload); },
    deleteRole: function (id) { return request('DELETE', '/api/roles/' + encodeURIComponent(id)); },
    checkPassword: function (password) { return request('POST', '/api/users/password/check', { password: password }); },
    models: function () { return request('GET', '/api/models'); },
    saveModels: function (payload) { return request('PUT', '/api/models', payload); },
    testModel: function (id) { return request('POST', '/api/models/' + encodeURIComponent(id) + '/test', {}); },
    securityOverview: function () { return request('GET', '/api/security/overview'); },
    dataStats: function () { return request('GET', '/api/data/stats'); },
    backupNow: function () { return request('POST', '/api/data/backup', {}); },
    backups: function () { return request('GET', '/api/data/backups'); },
    deleteBackup: function (id) { return request('DELETE', '/api/data/backups/' + encodeURIComponent(id)); },
    restoreBackup: function (id) { return request('POST', '/api/data/backups/' + encodeURIComponent(id) + '/restore', {}); },
    cleanup: function (categories) { return request('POST', '/api/data/cleanup', categories || {}); },
    purgeData: function () { return request('POST', '/api/data/purge', {}); },
    importData: function (payload) { return request('POST', '/api/data/import', payload); },
    exportData: function () { return request('GET', '/api/data/export'); },
    logs: function (level, query) {
      return request('GET', '/api/logs?limit=300'
        + (level ? '&level=' + encodeURIComponent(level) : '')
        + (query ? '&q=' + encodeURIComponent(query) : ''));
    },
    browse: function (path) {
      return request('GET', '/api/fs/browse' + (path ? '?path=' + encodeURIComponent(path) : ''));
    },
    testNotify: function (email) { return request('POST', '/api/notify/test', { email: email }); },
    checkUpdate: function () { return request('GET', '/api/updates/check'); },
    serviceControl: function (action) { return request('POST', '/api/service/control', { action: action }); },
    login: async function (username, password) {
      const result = await request('POST', '/api/auth/login', { username: username, password: password });
      if (result.ok && result.data && result.data.token) {
        setToken(result.data.token);
        return { ok: true, user: result.data };
      }
      return { ok: false, status: result.status, error: result.data };
    },
    logout: async function () {
      const result = await request('POST', '/api/auth/logout', {});
      setToken('');
      return result.ok;
    },
    /* 一次 MCP 调用（与外部 Agent 走同一条链） */
    call: function (tool, operation, parameters, context) {
      return request('POST', '/api/call', {
        tool: tool, operation: operation,
        parameters: parameters || {}, context: context || {}
      });
    },
    importTemplate: function (name, parameters, projectPath) {
      return request('POST', '/api/templates/' + encodeURIComponent(name) + '/import', {
        parameters: parameters || {}, project_path: projectPath || ''
      });
    }
  };
})();
