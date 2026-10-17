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
