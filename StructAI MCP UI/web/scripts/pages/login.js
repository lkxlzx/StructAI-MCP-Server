/* 登录（P181）：与核心服务同源，`POST /api/auth/login` 换会话 token。
   token 只放 sessionStorage（关闭标签页即失效）；界面沿用原稿配色。 */
(function () {
  function render() {
    return '' +
      '<section class="login-card">' +
        '<div class="login-brand">' +
          '<span class="login-logo" data-icon="logo"></span>' +
          '<div><h1 class="login-title">MIDAS MCP 管理器</h1>' +
          '<p class="login-sub">Connect MIDAS · Empower Engineering with AI</p></div>' +
        '</div>' +
        '<form class="login-form" id="loginForm" autocomplete="on">' +
          '<label class="login-field"><span>用户名</span>' +
            '<input id="loginUser" name="username" type="text" autocomplete="username" placeholder="admin"></label>' +
          '<label class="login-field"><span>密码</span>' +
            '<input id="loginPass" name="password" type="password" autocomplete="current-password" placeholder="••••••••"></label>' +
          '<p class="login-error" id="loginError" role="alert"></p>' +
          '<button class="btn-primary login-submit" id="loginSubmit" type="submit">登录</button>' +
          '<p class="login-hint">凭据只用于换取会话 token；密码不落库、不写日志。</p>' +
        '</form>' +
      '</section>';
  }

  function mount(root) {
    window.Icons.mount(root);
    const form = root.querySelector('#loginForm');
    const error = root.querySelector('#loginError');
    const submit = root.querySelector('#loginSubmit');
    if (!form) return;
    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      const username = (root.querySelector('#loginUser').value || '').trim();
      const password = root.querySelector('#loginPass').value || '';
      if (!username || !password) {
        error.textContent = '请输入用户名与密码';
        return;
      }
      submit.disabled = true;
      submit.textContent = '登录中…';
      const result = await window.Api.login(username, password);
      submit.disabled = false;
      submit.textContent = '登录';
      if (!result.ok) {
        error.textContent = result.status === 401
          ? '用户名或密码错误'
          : '无法连接核心服务（' + (result.status || '网络错误') + '）';
        return;
      }
      error.textContent = '';
      window.Toast && window.Toast.show('登录成功');
      location.hash = '#/home';
      location.reload();
    });
  }

  window.PageLogin = { render: render, mount: mount };
})();
