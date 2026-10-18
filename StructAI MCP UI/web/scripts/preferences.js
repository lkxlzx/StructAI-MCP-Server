/* 界面偏好（P185）：把「界面设置」分区真正作用到页面上。
   - theme: light / dark / system → <html data-theme>
   - density: comfortable / standard / compact → <html data-density>
   - page_size: 列表每页条数（clients 页读取）
   - show_tooltips / show_animations → <html data-tooltips / data-animations>
   偏好缓存在 localStorage（仅界面偏好，不含 token）。 */
(function () {
  const KEY = 'structai.ui.preferences';
  const DEFAULTS = {
    theme: 'light',
    density: 'comfortable',
    page_size: 10,
    show_tooltips: true,
    show_animations: true,
    compact_sidebar: false
  };

  function read() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? Object.assign({}, DEFAULTS, JSON.parse(raw)) : Object.assign({}, DEFAULTS);
    } catch (error) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function write(values) {
    const merged = Object.assign(read(), values || {});
    try { localStorage.setItem(KEY, JSON.stringify(merged)); } catch (error) { /* 隐私模式 */ }
    apply(merged);
    return merged;
  }

  function systemPrefersDark() {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  }

  function apply(values) {
    const prefs = values || read();
    const root = document.documentElement;
    const dark = prefs.theme === 'dark' || (prefs.theme === 'system' && systemPrefersDark());
    root.dataset.theme = dark ? 'dark' : 'light';
    root.dataset.themeChoice = prefs.theme || 'light';
    root.dataset.density = prefs.density || 'comfortable';
    root.dataset.tooltips = prefs.show_tooltips ? 'on' : 'off';
    root.dataset.animations = prefs.show_animations ? 'on' : 'off';
    root.dataset.sidebar = prefs.compact_sidebar ? 'compact' : 'full';
  }

  if (window.matchMedia) {
    try {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
        if (read().theme === 'system') apply();
      });
    } catch (error) { /* 老浏览器 */ }
  }

  window.Preferences = {
    get: read,
    set: write,
    apply: apply,
    defaults: function () { return Object.assign({}, DEFAULTS); }
  };
  apply();
})();
