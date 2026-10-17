/* 应用装配：外壳渲染 + 路由 + 轻提示 */
(function () {
  const shell = window.Mock.shell;
  const view = document.getElementById('view');

  /* ---------------- 外壳 ---------------- */
  function renderShell() {
    document.getElementById('nav').innerHTML = shell.nav.map(function (it) {
      return '<a class="nav-item" href="' + it.route + '" data-route="' + it.id + '">' +
        '<span class="nav-icon" data-icon="' + it.icon + '"></span><span>' + it.label + '</span></a>';
    }).join('');

    const ss = shell.sideStatus;
    document.getElementById('sideStatus').innerHTML =
      '<div class="side-status-head"><span class="dot dot-green"></span><span>' + ss.title + '</span></div>' +
      '<dl class="side-rows">' + ss.rows.map(function (r) {
        return '<div class="side-row"><dt>' + r.label + '</dt><dd>' + r.value + '</dd></div>';
      }).join('') + '</dl>' +
      '<button class="side-btn" id="sideAction" type="button">' +
      '<span class="side-btn-icon" data-icon="stop"></span><span>' + ss.action + '</span></button>';

    document.getElementById('footerLeft').innerHTML =
      '<span class="footer-logo" data-icon="footerMark"></span>' +
      '<span class="footer-brand">' + shell.footer.brand + '</span>' +
      '<span class="footer-slogan">' + shell.footer.slogan + '</span>';

    document.getElementById('footerRight').innerHTML = shell.footer.right.map(function (t, i) {
      return (i ? '<span class="sep">|</span>' : '') + '<span>' + t + '</span>';
    }).join('');

    document.getElementById('versionBadge').textContent = shell.version;
    window.Icons.mount(document);
  }

  /* ---------------- 路由 ---------------- */
  function currentRoute() {
    const parts = (location.hash || '').replace(/^#\/?/, '').split('/');
    return { name: parts[0] || 'home', sub: parts[1] || '' };
  }

  /* P181：有后端且未登录 ⇒ 强制登录页（登录页本身不渲染外壳导航） */
  function needsLogin() {
    return !!window.Api && !window.Api.token() && location.hash !== '#/login';
  }

  function renderLogin() {
    document.documentElement.classList.add('is-login');
    document.querySelectorAll('.nav-item').forEach(function (a) { a.classList.remove('is-active'); });
    document.title = '登录 · ' + shell.appName;
    view.innerHTML = window.PageLogin.render();
    window.PageLogin.mount(view);
    window.Icons.mount(view);
  }

  function leaveLogin() {
    document.documentElement.classList.remove('is-login');
  }

  /* P181：页面数据先取实时数据，失败则回落 mock（离线也能看界面） */
  const LIVE = {
    home: function () { return window.Live.home(); },
    midas: function () { return window.Live.clients(); }
  };

  async function renderPage(route) {
    if (needsLogin()) { renderLogin(); return; }
    leaveLogin();
    if (route.name === 'login') { location.hash = '#/home'; return; }

    const name = route.name;
    const page = window.Mock.pages[name] || window.Mock.pages.home;
    document.querySelectorAll('.nav-item').forEach(function (a) {
      a.classList.toggle('is-active', a.dataset.route === name);
    });
    document.title = page.title ? page.title + ' · ' + shell.appName : shell.appName;

    if (page.todo) {
      view.innerHTML = '<div class="page"><section class="card card-pad">' +
        '<h2 class="card-title">' + page.title + '</h2>' +
        '<p style="margin-top:12px;color:var(--text-3)">该界面将按编号依次还原（当前为首页实现）。</p>' +
        '</section></div>';
      window.Icons.mount(view);
      return;
    }

    view.innerHTML = '<div class="page">' + page.render(route.sub) + '</div>';
    if (typeof page.mount === 'function') page.mount(view, route.sub);
    window.Icons.mount(view);
    view.scrollTop = 0;

    const loader = LIVE[name];
    if (loader && window.Live) {
      const live = await loader();
      if (live) {
        try {
          window.PageLive && window.PageLive(name, view, live);
        } catch (e) { /* 实时渲染失败时保留 mock 视图 */ }
      }
    }
  }

  /* ---------------- 轻提示 ---------------- */
  window.Toast = {
    show: function (msg) {
      let box = document.getElementById('toast');
      if (!box) {
        box = document.createElement('div');
        box.id = 'toast';
        box.className = 'toast';
        document.body.appendChild(box);
      }
      box.textContent = msg;
      box.classList.add('is-on');
      clearTimeout(box.__t);
      box.__t = setTimeout(function () { box.classList.remove('is-on'); }, 1800);
    }
  };

  /* ---------------- 启动 ---------------- */
  renderShell();
  renderPage(currentRoute());
  window.addEventListener('hashchange', function () { renderPage(currentRoute()); });

  document.getElementById('btnSettings').addEventListener('click', function () {
    location.hash = '#/settings';
  });
  document.addEventListener('click', function (e) {
    const more = e.target.closest('[data-more]');
    if (more) {
      e.preventDefault();
      window.Toast.show('“' + more.dataset.more + '” 详情页待实现');
      return;
    }
    const task = e.target.closest('[data-task]');
    if (task) window.Toast.show('任务 ' + task.dataset.task + ' 操作菜单');
    const act = e.target.closest('#sideAction');
    if (act) window.Toast.show('已请求停止 MCP 服务');
  });
})();
