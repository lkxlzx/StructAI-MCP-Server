/* 系统设置 · 基础设置 */
(function () {
  const PREVIEW = {
    light: '<svg viewBox="0 0 100 44" preserveAspectRatio="none">' +
      '<rect width="100" height="44" fill="#FFFFFF"/><rect x="0" y="0" width="20" height="44" fill="#EFF4FA"/>' +
      '<rect x="26" y="9" width="62" height="6" rx="3" fill="#E4EBF4"/>' +
      '<rect x="26" y="21" width="46" height="5" rx="2.5" fill="#EDF2F8"/>' +
      '<rect x="26" y="31" width="54" height="5" rx="2.5" fill="#EDF2F8"/></svg>',
    dark: '<svg viewBox="0 0 100 44" preserveAspectRatio="none">' +
      '<rect width="100" height="44" fill="#22334A"/><rect x="0" y="0" width="20" height="44" fill="#1B2D43"/>' +
      '<rect x="26" y="9" width="62" height="6" rx="3" fill="#39506E"/>' +
      '<rect x="26" y="21" width="46" height="5" rx="2.5" fill="#33496A"/>' +
      '<rect x="26" y="31" width="54" height="5" rx="2.5" fill="#33496A"/></svg>',
    system: '<svg viewBox="0 0 100 44" preserveAspectRatio="none">' +
      '<rect width="100" height="44" fill="#22334A"/><rect width="50" height="44" fill="#FFFFFF"/>' +
      '<rect x="0" y="0" width="12" height="44" fill="#EFF4FA"/><rect x="50" y="0" width="12" height="44" fill="#1B2D43"/>' +
      '<rect x="20" y="9" width="22" height="6" rx="3" fill="#E4EBF4"/><rect x="68" y="9" width="24" height="6" rx="3" fill="#39506E"/>' +
      '<rect x="20" y="24" width="18" height="5" rx="2.5" fill="#EDF2F8"/><rect x="68" y="24" width="20" height="5" rx="2.5" fill="#33496A"/></svg>'
  };

  const D = {
    crumbs: ['首页', '系统设置'],
    head: {
      title: '系统设置',
      sub: '管理系统参数、服务器配置、用户偏好和安全设置，让 MIDAS MCP 更好地为您服务',
      tabs: [
        { label: '基础设置', icon: 'settings', active: true },
        { label: '服务配置', icon: 'server' },
        { label: '模型设置', icon: 'model' },
        { label: '用户与权限', icon: 'user' },
        { label: '安全设置', icon: 'shield' },
        { label: '数据管理', icon: 'db' },
        { label: '关于系统', icon: 'info' }
      ]
    },
    info: {
      title: '系统信息', icon: 'settings', logo: 'M',
      name: 'MIDAS MCP 管理器',
      chips: [{ t: 'v1.0.0', cls: 'blue' }, { t: '运行中', cls: 'green', dot: true }],
      rows: [
        ['产品名称', 'MIDAS MCP 管理器'],
        ['版本号', 'v1.0.0'],
        ['构建时间', '2026-09-21 14:20:00'],
        ['运行环境', 'Debian 13 (x86_64)'],
        ['Python', '3.12.5'],
        ['安装路径', '/opt/midas-mcp'],
        ['数据目录', '/opt/midas-mcp/data'],
        ['日志目录', '/opt/midas-mcp/logs']
      ]
    },
    behavior: {
      title: '系统行为设置', icon: 'settings',
      selects: [['默认软件', 'CIVIL NX (本机)'], ['默认版本', '2024 (v1.2.0)']],
      units: [['任务超时时间', '60', '分钟'], ['日志保留天数', '30', '天']],
      toggles: [['自动清理过期任务', true], ['启动时自动检查更新', true], ['最小化到系统托盘', false]]
    },
    ui: {
      title: '界面设置', icon: 'layout',
      theme: {
        label: '主题模式',
        items: [
          { key: 'light', label: '浅色模式', on: true },
          { key: 'dark', label: '深色模式' },
          { key: 'system', label: '跟随系统' }
        ]
      },
      selects: [['语言设置', '简体中文'], ['页面显示密度', '舒适'], ['每页显示条数', '10']],
      toggles: [['显示工具提示', true], ['显示动画效果', true], ['紧凑侧边栏', false]]
    },
    paths: {
      title: '路径设置', icon: 'folder',
      rows: [
        ['MIDAS 安装路径', 'D:\\Program Files\\MIDAS\\CIVIL NX'],
        ['临时文件目录', '/opt/midas-mcp/temp'],
        ['项目文件默认目录', 'D:\\Projects'],
        ['模型文件默认目录', 'D:\\Projects\\Models'],
        ['结果文件默认目录', 'D:\\Projects\\Results']
      ]
    },
    notify: {
      title: '通知设置', icon: 'bell',
      toggles: [['任务完成通知', true], ['任务失败通知', true], ['系统异常通知', true]],
      channels: {
        label: '通知方式',
        items: [{ t: '页面通知', on: true }, { t: '浏览器通知', on: true }, { t: '邮件通知' }]
      },
      mail: { label: '邮件地址', placeholder: '请输入邮箱地址' },
      action: '发送测试邮件'
    },
    ops: {
      title: '系统操作', icon: 'sliders',
      tiles: [
        { t: '检查更新', d: '当前版本：v1.0.0', i: 'refresh' },
        { t: '备份系统配置', d: '备份系统设置、用户数据等', i: 'archive' },
        { t: '恢复系统配置', d: '从备份文件恢复系统配置', i: 'restore' },
        { t: '重置所有设置', d: '将所有设置恢复为默认值', i: 'reset' }
      ],
      danger: { t: '清空所有数据', d: '此操作不可恢复，请谨慎操作' },
      actions: ['取消', '保存设置']
    }
  };

  const sw = function (on) { return '<span class="switch' + (on ? ' is-on' : '') + '" role="switch" aria-checked="' + !!on + '"></span>'; };
  const sel = function (label, value, opts) {
    return '<div class="set-row"><span class="k">' + label + '</span><span class="v">' +
      '<span class="select-like s-select"><select aria-label="' + label + '">' +
      (opts || [value]).map(function (o) { return '<option>' + o + '</option>'; }).join('') +
      '</select><span class="chev" data-icon="chevD"></span></span></span></div>';
  };
  const unitRow = function (label, value, unit) {
    return '<div class="set-row"><span class="k">' + label + '</span><span class="v">' +
      '<span class="s-input"><input type="text" value="' + value + '"><span class="suffix">' + unit + '</span></span></span></div>';
  };
  const toggleRow = function (label, on) {
    return '<div class="set-row"><span class="k" style="width:auto;flex:1">' + label + '</span>' + sw(on) + '</div>';
  };
  const pathRow = function (k, v) {
    return '<div class="path-row"><span class="k">' + k + '</span><span class="v">' +
      '<span class="s-input"><input type="text" value="' + v + '">' +
      '<button class="ico-btn" type="button" title="选择目录" data-pick="' + k + '"><span data-icon="folder"></span></button>' +
      '</span></span></div>';
  };

  const TAB_IDS = ['basic', 'service', 'model', 'users', 'security', 'data', 'about'];

  function render(tab) {
    tab = tab || 'basic';
    const d = D;
    const tabs = d.head.tabs.map(function (t, i) {
      const id = TAB_IDS[i];
      return '<button class="settings-tab' + (id === tab ? ' is-active' : '') + '" type="button" data-stab="' + id + '">' +
        '<span class="ti" data-icon="' + t.icon + '"></span>' + t.label + '</button>';
    }).join('');

    const infoRows = d.info.rows.map(function (r) {
      return '<div class="kv-row"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
    }).join('');
    const chips = d.info.chips.map(function (c) {
      return '<span class="mini-chip ' + c.cls + '">' + (c.dot ? '<span class="dot dot-green"></span>' : '') + c.t + '</span>';
    }).join('');

    const themes = d.ui.theme.items.map(function (t) {
      return '<div class="theme-card' + (t.on ? ' is-on' : '') + '" data-theme="' + t.key + '">' +
        '<span class="theme-preview">' + PREVIEW[t.key] + '</span>' +
        '<span class="theme-label"><span class="theme-radio"></span>' + t.label + '</span></div>';
    }).join('');

    const channels = d.notify.channels.items.map(function (c) {
      return '<span class="cbx-item' + (c.on ? ' is-on' : '') + '" data-channel="' + c.t + '">' +
        '<span class="box">' + (c.on ? window.Icons.check : '') + '</span>' + c.t + '</span>';
    }).join('');

    const tiles = d.ops.tiles.map(function (t) {
      return '<button class="op-tile" type="button" data-op2="' + t.t + '">' +
        '<span class="oi" data-icon="' + t.i + '"></span>' +
        '<span class="ot"><b>' + t.t + '</b><span>' + t.d + '</span></span>' +
        '<span class="ch" data-icon="chevR"></span></button>';
    }).join('');

    const actions = d.ops.actions.map(function (a, i) {
      return '<button class="' + (i ? 'btn-solid-lg' : 'btn-plain-lg') + '" type="button" data-act="' + a + '">' + a + '</button>';
    }).join('');

    const head = '' +
      '<section class="settings-head">' +
        '<nav class="crumbs" style="padding:15px 24px 0">' +
          '<span class="back" data-icon="arrowLeft"></span>' +
          '<a href="#/home">' + d.crumbs[0] + '</a><span class="sep">›</span>' +
          '<span class="cur">' + d.crumbs[1] + '</span></nav>' +
        '<span class="settings-head-accent"></span>' +
        '<h1 class="settings-title">' + d.head.title + '</h1>' +
        '<p class="settings-sub">' + d.head.sub + '</p>' +
        '<nav class="settings-tabs">' + tabs + '</nav>' +
      '</section>';

    const grid = '<div class="settings-grid">' +

        /* 左列 */
        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.info.icon + '"></span>' + d.info.title + '</h2>' +
          '<div class="ident">' +
            '<span class="ident-logo">' + d.info.logo + '</span>' +
            '<div><div class="ident-name">' + d.info.name + '</div>' +
            '<div class="ident-chips">' + chips + '</div></div>' +
          '</div>' +
          '<dl class="kv-table">' + infoRows + '</dl>' +
        '</section>' +

        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.behavior.icon + '"></span>' + d.behavior.title + '</h2>' +
          d.behavior.selects.map(function (s) { return sel(s[0], s[1], s[0] === '默认软件' ? ['CIVIL NX (本机)', 'GEN NX (服务器)', 'FEA NX'] : [s[1], '2023 (v1.1.0)']); }).join('') +
          d.behavior.units.map(function (s) { return unitRow(s[0], s[1], s[2]); }).join('') +
          d.behavior.toggles.map(function (t) { return toggleRow(t[0], t[1]); }).join('') +
        '</section>' +

        /* 中列 */
        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.ui.icon + '"></span>' + d.ui.title + '</h2>' +
          '<div class="set-row" style="align-items:flex-start"><span class="k" style="padding-top:10px">' + d.ui.theme.label + '</span>' +
          '<span class="v"><span class="theme-cards">' + themes + '</span></span></div>' +
          d.ui.selects.map(function (s) {
            const opts = s[0] === '语言设置' ? ['简体中文', 'English', '繁體中文']
              : s[0] === '页面显示密度' ? ['舒适', '标准', '紧凑'] : ['10', '20', '50'];
            return sel(s[0], s[1], opts);
          }).join('') +
          d.ui.toggles.map(function (t) { return toggleRow(t[0], t[1]); }).join('') +
        '</section>' +

        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.paths.icon + '"></span>' + d.paths.title + '</h2>' +
          d.paths.rows.map(function (r) { return pathRow(r[0], r[1]); }).join('') +
        '</section>' +

        /* 右列 */
        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.notify.icon + '"></span>' + d.notify.title + '</h2>' +
          d.notify.toggles.map(function (t) { return toggleRow(t[0], t[1]); }).join('') +
          '<div class="set-row" style="margin-top:6px"><span class="k" style="width:auto">' + d.notify.channels.label + '</span>' +
          '<span class="v"><span class="cbx-row">' + channels + '</span></span></div>' +
          '<div class="set-row" style="margin-top:2px"><span class="k" style="width:auto">' + d.notify.mail.label + '</span>' +
          '<span class="v"><span class="s-input"><input type="text" placeholder="' + d.notify.mail.placeholder + '"></span></span></div>' +
          '<button class="mail-btn" type="button" data-act="' + d.notify.action + '">' +
          '<span class="bi" data-icon="send"></span>' + d.notify.action + '</button>' +
        '</section>' +

        '<section class="settings-card">' +
          '<h2 class="s-card-title"><span class="ti" data-icon="' + d.ops.icon + '"></span>' + d.ops.title + '</h2>' +
          '<div class="ops-grid">' + tiles + '</div>' +
          '<div class="danger-row">' +
            '<span class="di" data-icon="trash"></span>' +
            '<span class="dt"><b>' + d.ops.danger.t + '</b><span>' + d.ops.danger.d + '</span></span>' +
          '</div>' +
          '<div class="ops-actions">' + actions + '</div>' +
        '</section>' +

      '</div>';
    return head + (tab === 'basic' ? grid : (window.SettingsTabs && window.SettingsTabs[tab] ? window.SettingsTabs[tab].render() : ''));
  }

  function mount(root, tab) {
    root.querySelectorAll('.switch').forEach(function (s) {
      s.addEventListener('click', function () {
        s.classList.toggle('is-on');
        s.setAttribute('aria-checked', s.classList.contains('is-on'));
      });
    });
    root.querySelectorAll('.theme-card').forEach(function (c) {
      c.addEventListener('click', function () {
        root.querySelectorAll('.theme-card').forEach(function (x) { x.classList.remove('is-on'); });
        c.classList.add('is-on');
        window.Toast.show('主题已切换为：' + c.querySelector('.theme-label').textContent.trim());
      });
    });
    root.querySelectorAll('.cbx-item').forEach(function (c) {
      c.addEventListener('click', function () {
        c.classList.toggle('is-on');
        c.querySelector('.box').innerHTML = c.classList.contains('is-on') ? window.Icons.check : '';
      });
    });
    root.querySelectorAll('[data-stab]').forEach(function (b) {
      b.addEventListener('click', function () {
        location.hash = '#/settings/' + b.dataset.stab;
      });
    });
    root.querySelectorAll('[data-act],[data-op2],[data-pick],[data-act2]').forEach(function (b) {
      b.addEventListener('click', function () {
        window.Toast.show('执行：' + (b.dataset.act || b.dataset.op2 || b.dataset.pick || b.dataset.act2));
      });
    });
  }
  window.PageSettings = { data: function () { return D; }, render: render, mount: mount };
})();
