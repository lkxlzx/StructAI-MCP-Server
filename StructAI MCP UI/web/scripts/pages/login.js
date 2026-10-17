/* 登录（P182 重设计 · 方案 A：左右分栏 · 工程感）
   左：深色海军蓝 + 工程网格 + 斜拉桥线稿 + 真实能力数字
   右：无卡片表单，聚焦品牌蓝光晕；支持记住用户名（密码永不存储） */
(function () {
  /* 斜拉桥线稿（单色，透明度由 CSS 控制） */
  const ART =
    '<svg viewBox="0 0 720 900" preserveAspectRatio="xMidYMax slice" aria-hidden="true">' +
      '<g class="lg-grid">' +
        Array.from({ length: 15 }, function (_, i) {
          const x = 24 + i * 48;
          return '<path d="M' + x + ' 0V900"/>';
        }).join('') +
        Array.from({ length: 19 }, function (_, i) {
          const y = 24 + i * 48;
          return '<path d="M0 ' + y + 'H720"/>';
        }).join('') +
      '</g>' +
      '<g class="lg-art">' +
        /* 水面 */
        '<path d="M0 742h720" stroke-width="1.2"/>' +
        '<path d="M0 760h720M0 782h720M0 806h720" stroke-width="1" opacity=".55"/>' +
        /* 桥塔 */
        '<path d="M196 742V300M236 742V300M470 742V262M510 742V262" stroke-width="2.4"/>' +
        '<path d="M190 300h52M464 262h52" stroke-width="2.4"/>' +
        /* 主梁 */
        '<path d="M40 706h640" stroke-width="3"/>' +
        '<path d="M40 722h640" stroke-width="1.4" opacity=".7"/>' +
        /* 斜拉索 */
        '<g stroke-width="1.1" opacity=".8">' +
          '<path d="M216 306 40 706M216 306 96 706M216 306 152 706M216 306 208 706"/>' +
          '<path d="M216 306 272 706M216 306 328 706M216 306 384 706M216 306 440 706"/>' +
          '<path d="M490 268 440 706M490 268 496 706M490 268 552 706M490 268 608 706M490 268 664 706"/>' +
          '<path d="M490 268 384 706M490 268 328 706M490 268 272 706"/>' +
        '</g>' +
        /* 桥墩 */
        '<path d="M204 742h24v96h-24zM478 742h24v96h-24z" stroke-width="1.6"/>' +
        /* 远山 */
        '<path d="M0 690 120 596 210 668 300 612 392 682 520 604 620 672 720 620V742H0z" ' +
          'stroke-width="1.2" opacity=".45"/>' +
      '</g>' +
    '</svg>';

  function render() {
    return '' +
      '<section class="login-shell">' +
        '<aside class="login-hero">' +
          '<div class="login-hero-art">' + ART + '</div>' +
          '<div class="login-hero-inner">' +
            '<div class="login-brand">' +
              '<span class="login-logo" data-icon="logoMark"></span>' +
              '<div class="login-brand-text">' +
                '<span class="login-brand-title">MIDAS MCP 管理器</span>' +
                '<span class="login-brand-sub">Connect MIDAS · Empower Engineering with AI</span>' +
              '</div>' +
            '</div>' +
            '<div class="login-points">' +
              '<div class="login-point"><b>9</b><span>MCP 工具 · 统一契约</span></div>' +
              '<div class="login-point"><b>663</b><span>端点 · 652 份 Schema</span></div>' +
              '<div class="login-point"><b>156</b><span>参数化模板 · 17 族</span></div>' +
            '</div>' +
            '<div class="login-hero-foot">' +
              '<span class="login-hero-line"></span>' +
              '<span>StructAI · AI for a Stronger Built World</span>' +
            '</div>' +
          '</div>' +
        '</aside>' +

        '<main class="login-panel">' +
          '<form class="login-form" id="loginForm" autocomplete="on" novalidate>' +
            '<header class="login-head">' +
              '<h1 class="login-title">登录</h1>' +
              '<p class="login-sub">使用管理员账号进入控制台</p>' +
            '</header>' +

            '<label class="login-field" for="loginUser">' +
              '<span class="login-label">用户名</span>' +
              '<span class="login-input-wrap">' +
                '<span class="login-input-ico" data-icon="user"></span>' +
                '<input id="loginUser" name="username" type="text" autocomplete="username" ' +
                  'spellcheck="false" placeholder="admin">' +
              '</span>' +
            '</label>' +

            '<label class="login-field" for="loginPass">' +
              '<span class="login-label">密码</span>' +
              '<span class="login-input-wrap">' +
                '<span class="login-input-ico" data-icon="lock"></span>' +
                '<input id="loginPass" name="password" type="password" ' +
                  'autocomplete="current-password" placeholder="输入密码">' +
                '<button class="login-eye" type="button" id="loginEye" ' +
                  'aria-label="显示密码" aria-pressed="false"><span data-icon="eye"></span></button>' +
              '</span>' +
            '</label>' +

            '<div class="login-row">' +
              '<label class="login-check">' +
                '<input type="checkbox" id="loginRemember">' +
                '<span class="login-box"></span><span>记住用户名</span>' +
              '</label>' +
              '<span class="login-hint-inline">密码不会被保存</span>' +
            '</div>' +

            '<p class="login-error" id="loginError" role="alert" aria-live="polite"></p>' +

            '<button class="login-submit" id="loginSubmit" type="submit">' +
              '<span class="login-submit-label">登 录</span>' +
              '<span class="login-spinner" aria-hidden="true"></span>' +
            '</button>' +

            '<p class="login-note">凭据只用于换取会话 token；密码不落库、不写日志。</p>' +
          '</form>' +
          '<footer class="login-foot">' +
            '<span>v2.0.0-alpha</span><span class="sep">·</span><span>StructAI MCP Server</span>' +
          '</footer>' +
        '</main>' +
      '</section>';
  }

  function mount(root) {
    window.Icons.mount(root);
    const form = root.querySelector('#loginForm');
    const error = root.querySelector('#loginError');
    const submit = root.querySelector('#loginSubmit');
    const user = root.querySelector('#loginUser');
    const pass = root.querySelector('#loginPass');
    const eye = root.querySelector('#loginEye');
    const remember = root.querySelector('#loginRemember');
    if (!form) return;

    /* 记住用户名（只存用户名） */
    try {
      const saved = localStorage.getItem('structai.ui.username');
      if (saved) { user.value = saved; remember.checked = true; pass.focus(); }
      else { user.focus(); }
    } catch (e) { user.focus(); }

    eye.addEventListener('click', function () {
      const show = pass.type === 'password';
      pass.type = show ? 'text' : 'password';
      eye.setAttribute('aria-pressed', show ? 'true' : 'false');
      eye.setAttribute('aria-label', show ? '隐藏密码' : '显示密码');
      eye.innerHTML = '<span data-icon="' + (show ? 'eye-off' : 'eye') + '"></span>';
      window.Icons.mount(eye);
      pass.focus();
    });

    function fail(message) {
      error.textContent = message;
      form.classList.remove('is-shake');
      void form.offsetWidth;
      form.classList.add('is-shake');
      pass.focus();
      pass.select();
    }

    form.addEventListener('submit', async function (event) {
      event.preventDefault();
      const username = (user.value || '').trim();
      const password = pass.value || '';
      if (!username || !password) { fail('请输入用户名与密码'); return; }

      submit.disabled = true;
      form.classList.add('is-loading');
      error.textContent = '';
      const result = await window.Api.login(username, password);
      submit.disabled = false;
      form.classList.remove('is-loading');

      if (!result.ok) {
        fail(result.status === 401
          ? '用户名或密码错误'
          : '无法连接核心服务（' + (result.status || '网络错误') + '）');
        return;
      }

      try {
        if (remember.checked) localStorage.setItem('structai.ui.username', username);
        else localStorage.removeItem('structai.ui.username');
      } catch (e) { /* 隐私模式：忽略 */ }

      form.classList.add('is-done');
      window.Toast && window.Toast.show('登录成功');
      setTimeout(function () { location.hash = '#/home'; location.reload(); }, 380);
    });
  }

  window.PageLogin = { render: render, mount: mount };
})();
