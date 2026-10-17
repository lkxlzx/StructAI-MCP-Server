/* 图标库（内联 SVG，无外部依赖） */
(function () {
  const S = (inner, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
    `stroke-linecap="round" stroke-linejoin="round" ${extra || ''}>${inner}</svg>`;
  const F = (inner, extra) => `<svg viewBox="0 0 24 24" fill="currentColor" ${extra || ''}>${inner}</svg>`;

  const GEAR =
    '<circle cx="12" cy="12" r="6.3"/><circle cx="12" cy="12" r="2.5"/>' +
    '<path d="M12 5.7V2.4M12 18.3v3.3M5.7 12H2.4M18.3 12h3.3M7.55 7.55 5.2 5.2' +
    'M16.45 7.55l2.35-2.35M7.55 16.45 5.2 18.8M16.45 16.45l2.35 2.35"/>';

  window.Icons = {
    logo:
      '<svg viewBox="0 0 54 41" fill="none"><defs><linearGradient id="midasGrad" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="#0B63FB"/><stop offset="1" stop-color="#0A93FC"/></linearGradient></defs>' +
      '<path d="M5 38V13.6C5 7.9 8.2 4 13 4c3.3 0 5.6 1.6 7.1 4.6L27 21.5l6.9-12.9C35.4 5.6 37.7 4 41 4' +
      'c4.8 0 8 3.9 8 9.6V38" stroke="url(#midasGrad)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/></svg>',

    footerMark:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round">' +
      '<path d="M12 2.6 20.5 7.4v9.2L12 21.4 3.5 16.6V7.4z"/><path d="M12 2.6v9.2M12 11.8l8.5-4.4M12 11.8 3.5 7.4M12 21.4v-9.6"/></svg>',

    gear: S(GEAR),

    home: S('<path d="M3.6 10.3 12 3.7l8.4 6.6V20a1 1 0 0 1-1 1h-4.5v-5.7H9.1V21H4.6a1 1 0 0 1-1-1z"/>'),
    client: S('<rect x="3" y="4.4" width="18" height="12.4" rx="1.8"/><path d="M9 20.2h6M12 16.8v3.4"/>'),
    server: S('<rect x="3.2" y="4.2" width="17.6" height="6.4" rx="1.6"/>' +
      '<rect x="3.2" y="13.4" width="17.6" height="6.4" rx="1.6"/><path d="M6.9 7.4h.01M6.9 16.6h.01"/>'),
    tools: S('<path d="M20.4 5.3a4.9 4.9 0 0 1-6.6 6.3l-6.9 6.9a1.95 1.95 0 1 1-2.8-2.8l6.9-6.9' +
      'a4.9 4.9 0 0 1 6.3-6.6l-2.9 2.9 2.4 2.4z"/>'),
    task: S('<rect x="4.8" y="4.2" width="14.4" height="16.6" rx="2"/><path d="M9.2 3.2h5.6v3.1H9.2z"/>' +
      '<path d="m9.3 13.4 1.9 1.9 3.6-3.6"/>'),
    logs: S('<path d="M7 3.4h6.6l4.4 4.3V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.4a1 1 0 0 1 1-1z"/>' +
      '<path d="M13.4 3.6v4.4h4.4"/><path d="M9.2 12.4h5.6M9.2 15.9h5.6"/>'),
    settings: S(GEAR),

    'stat-server': S('<rect x="3.4" y="4.6" width="17.2" height="6" rx="1.6"/>' +
      '<rect x="3.4" y="13.4" width="17.2" height="6" rx="1.6"/><path d="M7 7.6h.01M7 16.4h.01"/>', 'stroke-width="1.9"'),
    'stat-client': S('<rect x="2.8" y="4.4" width="18.4" height="12.6" rx="1.8"/>' +
      '<path d="M8.6 20.4h6.8M12 17v3.4"/>', 'stroke-width="1.9"'),
    'stat-task': S('<rect x="4.6" y="4" width="14.8" height="17" rx="2"/>' +
      '<path d="M9.2 3h5.6v3H9.2z"/><path d="M9 12.6h6M9 16.2h4"/>', 'stroke-width="1.9"'),
    'stat-check': S('<circle cx="12" cy="12" r="8.6"/><path d="m8.6 12.3 2.4 2.4 4.5-4.8"/>', 'stroke-width="1.9"'),
    'stat-clock': S('<circle cx="12" cy="12" r="8.6"/><path d="M12 7.4V12l3.2 2.1"/>', 'stroke-width="1.9"'),

    chevR: S('<path d="m9.5 5.5 6.5 6.5-6.5 6.5"/>', 'stroke-width="2"'),
    chevD: S('<path d="m5.5 9.5 6.5 6.5 6.5-6.5"/>', 'stroke-width="2"'),
    more: F('<circle cx="12" cy="5.2" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="12" cy="18.8" r="1.6"/>'),
    bulb: S('<path d="M9.2 18.4h5.6M10.4 21.2h3.2"/><path d="M12 2.8a6.3 6.3 0 0 1 3.8 11.3c-.5.4-.7.9-.7 1.5' +
      'v.6H8.9v-.6c0-.6-.2-1.1-.7-1.5A6.3 6.3 0 0 1 12 2.8z"/>', 'stroke-width="1.8"'),
    stop: F('<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>'),
    play: F('<path d="M8 5.4v13.2l10.4-6.6z"/>'),
    refresh: S('<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 4.6V10h-5.4"/>')
  };

  window.Icons.mount = function (root) {
    (root || document).querySelectorAll('[data-icon]').forEach(function (el) {
      const name = el.dataset.icon;
      if (window.Icons[name] && el.childElementCount === 0) el.innerHTML = window.Icons[name];
    });
  };
})();

/* ---------- 追加图标（AI 工程助手等页面使用） ---------- */
(function () {
  const S = (inner, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
    `stroke-linecap="round" stroke-linejoin="round" ${extra || ''}>${inner}</svg>`;
  const F = (inner) => `<svg viewBox="0 0 24 24" fill="currentColor">${inner}</svg>`;

  Object.assign(window.Icons, {
    ai: S('<rect x="3.4" y="6" width="17.2" height="13.4" rx="4"/>' +
      '<path d="M9 12.2h.01M15 12.2h.01M9.6 15.6h4.8"/>' +
      '<path d="M12 3.2v2.8M8.6 3.6 9.4 6M15.4 3.6 14.6 6"/>'),
    chat: S('<path d="M20.4 11.4c0 3.9-3.6 7-8 7-1 0-2-.2-2.9-.5L5 20l1.1-3.2A6.6 6.6 0 0 1 4.4 11.4c0-3.9 3.6-7 8-7s8 3.1 8 7z"/>' +
      '<path d="M9 11.4h.01M12 11.4h.01M15 11.4h.01"/>'),
    tpl: S('<rect x="3.6" y="4" width="16.8" height="16" rx="2.4"/>' +
      '<path d="M3.6 9h16.8M9.4 9v11"/>'),
    demo: S('<rect x="3.4" y="4.6" width="17.2" height="14.8" rx="2.2"/>' +
      '<path d="M9.8 9.4l5 2.6-5 2.6z"/>'),
    hist: S('<circle cx="12" cy="12" r="8.4"/><path d="M12 7.4V12l3.2 1.9"/>'),
    plus: S('<path d="M12 5.6v12.8M5.6 12h12.8"/>'),
    folder: S('<path d="M3.6 7.4a2 2 0 0 1 2-2h3.2l2 2.4h7.6a2 2 0 0 1 2 2v7.4a2 2 0 0 1-2 2H5.6a2 2 0 0 1-2-2z"/>'),
    edit: S('<path d="M16.4 4.6l3 3-9.6 9.6-3.6.6.6-3.6z"/>'),
    info: S('<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5.4M12 7.9h.01"/>'),
    flow: S('<path d="M6 6.6h5.4a3 3 0 0 1 3 3v2.4a3 3 0 0 0 3 3H18"/>' +
      '<circle cx="5" cy="6.6" r="2"/><circle cx="19" cy="15" r="2"/>'),
    model: S('<path d="M12 3.2 19.6 7v10L12 20.8 4.4 17V7z"/><path d="M12 12l7.6-3.8M12 12v8.8M12 12 4.4 8.2"/>'),
    timer: S('<circle cx="12" cy="13" r="7.4"/><path d="M12 9.4V13l2.6 1.6M9.4 3.4h5.2"/>'),
    check: S('<path d="m6.4 12.6 3.4 3.4 7.4-7.8"/>', 'stroke-width="2.4"'),
    clip: S('<path d="M15.6 7.6 8.9 14.3a2.6 2.6 0 0 0 3.7 3.7l7-7a4.4 4.4 0 0 0-6.2-6.2l-7.3 7.3a6 6 0 0 0 8.5 8.5l6.2-6.2"/>'),
    send: S('<path d="M20.4 3.6 3.6 10.2l6 2.6 2.6 6z"/><path d="M20.4 3.6 9.6 12.8"/>', 'stroke-width="1.8"'),
    cube: S('<path d="M12 3.4 19.4 7.2v9.6L12 20.6 4.6 16.8V7.2z"/><path d="M12 12l7.4-3.8M12 12v8.6M12 12 4.6 8.2"/>'),
    axisX: S('<path d="M4.4 19.6 19.6 4.4"/><path d="M19.6 4.4h-5.2M19.6 4.4v5.2"/>'),
    axisY: S('<path d="M12 19.6V4.4"/><path d="M12 4.4 9.4 9.2M12 4.4l2.6 4.8"/>'),
    axisZ: S('<path d="M4.4 12h15.2"/><path d="M19.6 12l-4.8-2.6M19.6 12l-4.8 2.6"/>'),
    zoom: S('<circle cx="11" cy="11" r="6.4"/><path d="m15.8 15.8 4.2 4.2M8.6 11h4.8M11 8.6v4.8"/>'),
    pan: S('<path d="M12 3.6v16.8M3.6 12h16.8"/><path d="M12 3.6 9.8 6.4M12 3.6l2.2 2.8M12 20.4l-2.2-2.8M12 20.4l2.2-2.8"/>' +
      '<path d="M3.6 12l2.8-2.2M3.6 12l2.8 2.2M20.4 12l-2.8-2.2M20.4 12l-2.8 2.2"/>'),
    expand: S('<path d="M4.4 9V4.4H9M15 4.4h4.6V9M19.6 15v4.6H15M9 19.6H4.4V15"/>'),
    stop2: F('<rect x="6.5" y="6.5" width="11" height="11" rx="2"/>')
  });
})();

/* ---------- 追加图标（MIDAS 客户端等页面使用） ---------- */
(function () {
  const S = (inner, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
    `stroke-linecap="round" stroke-linejoin="round" ${extra || ''}>${inner}</svg>`;

  Object.assign(window.Icons, {
    arrowLeft: S('<path d="M19.4 12H5.2"/><path d="m11 5.6-6.4 6.4 6.4 6.4"/>'),
    chevL: S('<path d="m14.5 5.5-6.5 6.5 6.5 6.5"/>', 'stroke-width="2"'),
    search: S('<circle cx="11" cy="11" r="6.4"/><path d="m15.8 15.8 4.2 4.2"/>'),
    copy: S('<rect x="8.6" y="8.6" width="11" height="11" rx="2"/>' +
      '<path d="M5.4 15.4H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h8.4a2 2 0 0 1 2 2v.4"/>'),
    eye: S('<path d="M2.6 12S6 5.8 12 5.8 21.4 12 21.4 12 18 18.2 12 18.2 2.6 12 2.6 12z"/>' +
      '<circle cx="12" cy="12" r="2.8"/>'),
    plug: S('<path d="M10.4 13.6 6.6 17.4a2.8 2.8 0 0 1-4-4l3.8-3.8"/>' +
      '<path d="m13.6 10.4 3.8-3.8a2.8 2.8 0 0 1 4 4l-3.8 3.8"/><path d="m8.6 15.4 6.8-6.8"/>'),
    fileText: S('<path d="M7 3.4h6.6l4.4 4.3V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.4a1 1 0 0 1 1-1z"/>' +
      '<path d="M13.4 3.6v4.4h4.4"/><path d="M9.2 12.4h5.6M9.2 15.9h5.6"/>'),
    trash: S('<path d="M4.6 7.4h14.8M9.4 7.4V4.8h5.2v2.6"/>' +
      '<path d="M6.6 7.4 7.6 20a1 1 0 0 0 1 1h6.8a1 1 0 0 0 1-1l1-12.6"/><path d="M10.4 11v6M13.6 11v6"/>'),
    layers: S('<path d="M12 3.4 21 8l-9 4.6L3 8z"/><path d="m3 12.6 9 4.6 9-4.6"/>')
  });
})();

/* ---------- 追加图标（系统设置等页面使用） ---------- */
(function () {
  const S = (inner, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
    `stroke-linecap="round" stroke-linejoin="round" ${extra || ''}>${inner}</svg>`;

  Object.assign(window.Icons, {
    user: S('<circle cx="12" cy="8.4" r="3.8"/><path d="M4.8 20.2c0-3.6 3.2-6.2 7.2-6.2s7.2 2.6 7.2 6.2"/>'),
    shield: S('<path d="M12 3.2 19.6 6v6c0 4.3-3.1 7.4-7.6 8.8C7.5 19.4 4.4 16.3 4.4 12V6z"/>' +
      '<path d="m9.2 12.2 2 2 3.6-3.8"/>'),
    db: S('<ellipse cx="12" cy="6.4" rx="7.4" ry="3.2"/>' +
      '<path d="M4.6 6.4v11.2c0 1.8 3.3 3.2 7.4 3.2s7.4-1.4 7.4-3.2V6.4"/>' +
      '<path d="M4.6 12c0 1.8 3.3 3.2 7.4 3.2s7.4-1.4 7.4-3.2"/>'),
    bell: S('<path d="M18.2 16.4V11a6.2 6.2 0 1 0-12.4 0v5.4L4.2 18.8h15.6z"/>' +
      '<path d="M9.8 21.2h4.4"/>'),
    layout: S('<rect x="3.4" y="4.2" width="17.2" height="15.6" rx="2.2"/>' +
      '<path d="M3.4 9.4h17.2M9.6 9.4v10.4"/>'),
    sliders: S('<path d="M4 8h9M17 8h3M4 16h3M11 16h9"/>' +
      '<circle cx="15" cy="8" r="2.2"/><circle cx="9" cy="16" r="2.2"/>'),
    archive: S('<rect x="3.4" y="4.4" width="17.2" height="4.4" rx="1.4"/>' +
      '<path d="M5.2 8.8v9.4a1.6 1.6 0 0 0 1.6 1.6h10.4a1.6 1.6 0 0 0 1.6-1.6V8.8"/>' +
      '<path d="M10 12.6h4"/>'),
    restore: S('<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4.4V10h-5.6"/>' +
      '<path d="M12 8.4V12l3 1.8"/>'),
    reset: S('<circle cx="12" cy="12" r="8.2"/><path d="M12 7.6V12l3.4 2"/>' +
      '<path d="M4.4 5.4v4h4"/>')
  });
})();

/* ---------- 补充图标（系统设置子页） ---------- */
(function () {
  const S = (inner, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ` +
    `stroke-linecap="round" stroke-linejoin="round" ${extra || ''}>${inner}</svg>`;
  Object.assign(window.Icons, {
    lock: S('<rect x="4.6" y="10.4" width="14.8" height="9.4" rx="2.2"/>' +
      '<path d="M8.2 10.4V7.8a3.8 3.8 0 0 1 7.6 0v2.6"/><path d="M12 14.2v2.2"/>'),
    download: S('<path d="M12 3.6v11.2"/><path d="m7.6 10.6 4.4 4.4 4.4-4.4"/>' +
      '<path d="M4.6 19.4h14.8"/>'),
    upload: S('<path d="M12 20.4V9.2"/><path d="m7.6 13.4 4.4-4.4 4.4 4.4"/>' +
      '<path d="M4.6 4.6h14.8"/>'),
    star: S('<path d="m12 3.6 2.6 5.4 5.9.8-4.3 4.2 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.8l5.9-.8z"/>'),
    play2: S('<circle cx="12" cy="12" r="8.4"/><path d="m10.2 8.8 5 3.2-5 3.2z"/>'),
    trashX: S('<path d="M4.6 7.4h14.8M9.4 7.4V4.8h5.2v2.6"/>' +
      '<path d="M6.6 7.4 7.6 20a1 1 0 0 0 1 1h6.8a1 1 0 0 0 1-1l1-12.6"/>'),
    edit2: S('<path d="M16.4 4.6l3 3-9.6 9.6-3.6.6.6-3.6z"/>'),
    check2: S('<path d="m6.4 12.6 3.4 3.4 7.4-7.8"/>', 'stroke-width="2.4"'),
    warn: S('<path d="M12 4.2 21 19.4H3z"/><path d="M12 9.6v4.2M12 16.6h.01"/>'),
    clock2: S('<circle cx="12" cy="12" r="8.4"/><path d="M12 7.4V12l3.2 1.9"/>'),
    key: S('<circle cx="8.4" cy="12" r="3.6"/><path d="M12 12h8.4M17.6 12v3M20.4 12v2"/>'),
    globe: S('<circle cx="12" cy="12" r="8.4"/><path d="M3.6 12h16.8"/>' +
      '<path d="M12 3.6c2.4 2.6 3.6 5.4 3.6 8.4s-1.2 5.8-3.6 8.4c-2.4-2.6-3.6-5.4-3.6-8.4S9.6 6.2 12 3.6z"/>')
  });
})();
