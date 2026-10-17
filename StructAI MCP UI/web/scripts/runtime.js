/* 运行环境适配
   浏览器（Web 版）：与桌面版完全一致，仅隐藏窗口按钮
   桌面壳（Win 版）：preload 注入 window.midasDesktop，显示并接管窗口按钮 */
(function () {
  const bridge = window.midasDesktop || null;
  /* 浏览器中可用 ?desktop=1 预览桌面版外观（含窗口按钮） */
  const forced = /(^|[?&])desktop=1(&|$)/.test(location.search);
  if (bridge || forced) document.documentElement.classList.add('is-desktop');

  window.Runtime = {
    isDesktop: !!bridge,
    minimize: function () { if (bridge) bridge.minimize(); },
    toggleMaximize: function () { if (bridge) bridge.toggleMaximize(); },
    close: function () { if (bridge) bridge.close(); }
  };

  document.addEventListener('click', function (e) {
    const btn = e.target.closest('[data-win]');
    if (!btn) return;
    const act = btn.dataset.win;
    if (act === 'minimize') window.Runtime.minimize();
    else if (act === 'maximize') window.Runtime.toggleMaximize();
    else if (act === 'close') window.Runtime.close();
  });

  if (bridge) {
    const bar = document.querySelector('.topbar');
    if (bar) bar.addEventListener('dblclick', function (e) {
      if (e.target.closest('button,a,[data-win]')) return;
      window.Runtime.toggleMaximize();
    });
  }
})();
