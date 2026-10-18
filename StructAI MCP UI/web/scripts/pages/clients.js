/* MIDAS 客户端（P185）
   - 列表 / 详情 / 新增 / 编辑 / 删除 / 测试连接全部走 /api/clients*
   - 后端不可达时保留原型数据（离线可看界面），但动作会提示「未连接后端」
   - 详情页签：基本信息 / 连接配置 / 功能支持 / 连接日志 / 操作历史 */
(function () {
  const D = {
    crumbs: ['首页', 'MIDAS 客户端'],
    head: { title: 'MIDAS 客户端', sub: '管理 MIDAS 软件客户端连接，支持多实例、多版本', action: '添加客户端' },
    search: { placeholder: '搜索客户端名称、软件类型或 API 地址...', filter: '全部状态' },
    columns: ['名称', '软件类型', 'API 地址', '状态', '版本', '操作'],
    rows: [
      { id: 'civil', letter: 'C', color: '#0D72F7', name: 'CIVIL NX (本机)', kind: 'CIVIL NX', api: 'http://127.0.0.1:4010', online: true, ver: '2024' },
      { id: 'gen', letter: 'G', color: '#0054F3', name: 'GEN NX (服务器)', kind: 'GEN NX', api: 'http://192.168.1.100:4010', online: true, ver: '2024' },
      { id: 'fea', letter: 'F', color: '#8936F5', name: 'FEA NX', kind: 'FEA NX', api: 'http://192.168.1.101:4010', online: false, ver: '2024' },
      { id: 'nfx', letter: 'N', color: '#FE620F', name: 'midas NFX', kind: 'NFX', api: 'http://192.168.1.102:4010', online: false, ver: '2023' },
      { id: 'mesh', letter: 'M', color: '#09A96E', name: 'midas MeshFree', kind: 'MeshFree', api: 'http://192.168.1.103:4010', online: false, ver: '2023' }
    ],
    pager: { total: '共 5 条', page: 1, size: '10 条/页' },
    detail: {
      back: '返回',
      title: 'CIVIL NX (本机)',
      connected: true,
      actions: ['编辑'],
      tabs: ['基本信息', '连接配置', '功能支持', '连接日志', '操作历史'],
      identity: { letter: 'C', color: '#0C73FE', name: 'CIVIL NX (本机)', sub: 'CIVIL NX', badge: '已连接' },
      rows: [
        { k: '软件版本', v: '2024 (v1.2.0)' },
        { k: 'API 地址', v: 'http://127.0.0.1:4010', ico: 'copy', title: '复制' },
        { k: 'MAPI-Key', v: '••••••••••••••••••', cls: 'mask-key', ico: 'eye', title: '显示' },
        { k: '服务器时间', v: '2025-08-16 14:23:45' },
        { k: '响应时间', v: '45 ms' },
        { k: '描述', v: '本机的 CIVIL NX 实例' }
      ],
      features: {
        title: '支持的功能',
        items: ['项目管理（DOC）', '数据库操作（DB）', '计算分析（ANAL）', '结果查询（POST）',
          '图形生成（VIEW）', '设计校核（DESIGN）', '计算书生成（REPORT）', '参数化建模（OPE）']
      },
      quick: {
        title: '快捷操作',
        buttons: [
          { label: '测试连接', icon: 'plug', primary: true },
          { label: '刷新 Key', icon: 'refresh' },
          { label: '查看日志', icon: 'fileText' },
          { label: '删除', icon: 'trash', danger: true }
        ]
      }
    }
  };

  const COLORS = ['#0D72F7', '#0054F3', '#8936F5', '#FE620F', '#09A96E', '#0AA6B8'];

  function pageSize() {
    const prefs = window.Preferences ? window.Preferences.get() : { page_size: 10 };
    return Math.max(1, Number(prefs.page_size) || 10);
  }

  let clients = null;        // 实时列表；null = 后端不可达（保留 mock）
  let options = null;        // /api/clients/options
  let selectedId = '';
  let page = 1;
  let keyword = '';
  let statusFilter = '';

  function ok(result) { return !!(result && result.ok); }
  function toast(message) { if (window.Toast) window.Toast.show(message); }
  function fail(result, fallback) {
    const message = (result && result.data && result.data.message) || fallback;
    toast(message || '操作失败');
  }
  function esc(value) { return window.UI.esc(value === null || value === undefined ? '' : value); }
  function colorOf(name, index) {
    const text = String(name || '');
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
    return COLORS[(hash + (index || 0)) % COLORS.length];
  }
  function isOnline(row) {
    return row.online !== undefined ? !!row.online : String(row.status || '').toUpperCase() === 'CONNECTED';
  }
  function rowsSource() {
    if (clients === null) return D.rows.map(function (row) { return Object.assign({}, row); });
    return clients.map(function (row, index) {
      const name = String(row.name || row.id);
      return {
        id: row.id,
        letter: name.slice(0, 1).toUpperCase(),
        color: colorOf(name, index),
        name: name,
        kind: row.product || row.vendor || '',
        api: row.endpoint || '—',
        online: isOnline(row),
        ver: row.version || '—',
        vendor: row.vendor || '',
        product: row.product || '',
        endpoint: row.endpoint || '',
        credential: row.credential_reference || '',
        description: row.description || '',
        status: row.status || ''
      };
    });
  }
  function filtered() {
    const needle = keyword.trim().toLowerCase();
    return rowsSource().filter(function (row) {
      if (statusFilter === 'online' && !row.online) return false;
      if (statusFilter === 'offline' && row.online) return false;
      if (!needle) return true;
      return [row.name, row.kind, row.api, row.ver].join(' ').toLowerCase().indexOf(needle) >= 0;
    });
  }

  /* ---------------- 渲染 ---------------- */

  function renderRows() {
    const rows = filtered();
    const size = pageSize();
    const pages = Math.max(1, Math.ceil(rows.length / size));
    page = Math.min(Math.max(1, page), pages);
    const visible = rows.slice((page - 1) * size, page * size);
    return {
      html: visible.map(function (r) {
        return '<tr data-client="' + esc(r.id) + '">' +
          '<td><div class="name-cell"><span class="letter-avatar" style="background:' + r.color + '">' +
          esc(r.letter) + '</span><span class="name-text">' + esc(r.name) + '</span></div></td>' +
          '<td class="muted">' + esc(r.kind) + '</td>' +
          '<td class="muted">' + esc(r.api) + '</td>' +
          '<td><span class="state-cell ' + (r.online ? 'on' : 'off') + '">' +
          '<span class="dot ' + (r.online ? 'dot-green' : 'dot-gray') + '"></span>' +
          (r.online ? '已连接' : '未连接') + '</span></td>' +
          '<td class="muted">' + esc(r.ver) + '</td>' +
          '<td class="col-ops"><button class="row-more" type="button" data-client-menu="' +
          esc(r.id) + '" data-icon="more"></button></td></tr>';
      }).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--text-3)">暂无软件实例</td></tr>',
      total: rows.length,
      pages: pages,
      page: page
    };
  }

  function render() {
    const d = D;
    const initial = renderRows();
    const cols = d.columns.map(function (c) {
      const cls = c === '状态' ? ' class="col-status"' : c === '版本' ? ' class="col-ver"' : c === '操作' ? ' class="col-ops"' : '';
      return '<th' + cls + '>' + c + '</th>';
    }).join('');

    const dt = d.detail;
    const tabs = dt.tabs.map(function (t, i) {
      return '<button class="detail-tab' + (i === 0 ? ' is-active' : '') + '" type="button" data-dtab="' + t + '">' + t + '</button>';
    }).join('');

    const detailRows = dt.rows.map(function (r) {
      return '<div class="detail-row"><dt>' + r.k + '</dt><dd class="' + (r.cls || '') + '">' + r.v + '</dd>' +
        (r.ico ? '<button class="row-ico" type="button" title="' + r.title + '" data-rowico="' + r.title + '" data-icon="' + r.ico + '"></button>' : '') +
        '</div>';
    }).join('');

    const feats = dt.features.items.map(function (f) {
      return '<span class="feat"><span class="ck" data-icon="check"></span>' + f + '</span>';
    }).join('');

    const quickBtns = dt.quick.buttons.map(function (b) {
      const cls = b.primary ? 'btn-primary sm' : 'btn-outline' + (b.danger ? ' danger' : '');
      return '<button class="' + cls + '" type="button" data-quick="' + b.label + '">' +
        '<span class="bi" data-icon="' + b.icon + '"></span>' + b.label + '</button>';
    }).join('');

    return '' +
      '<div class="clients-split">' +

        '<section class="client-list-card">' +
          '<nav class="crumbs">' +
            '<span class="back" data-icon="arrowLeft"></span>' +
            '<a href="#/home">' + d.crumbs[0] + '</a>' +
            '<span class="sep">›</span><span class="cur">' + d.crumbs[1] + '</span>' +
          '</nav>' +
          '<header class="client-head">' +
            '<div class="client-head-main">' +
              '<span class="client-head-accent"></span>' +
              '<h1 class="client-title">' + d.head.title + '</h1>' +
              '<p class="client-sub">' + d.head.sub + '</p>' +
            '</div>' +
            '<button class="btn-primary" type="button" data-act="' + d.head.action + '">' +
            '<span class="bi" data-icon="plus"></span>' + d.head.action + '</button>' +
          '</header>' +
          '<div class="client-search">' +
            '<label class="search-box"><span class="si" data-icon="search"></span>' +
            '<input type="text" id="clientSearch" placeholder="' + d.search.placeholder + '"></label>' +
            '<span class="select-like filter-select"><select id="clientFilter" aria-label="状态筛选">' +
            '<option value="">' + d.search.filter + '</option><option value="online">已连接</option>' +
            '<option value="offline">未连接</option></select><span class="chev" data-icon="chevD"></span></span>' +
          '</div>' +
          '<div class="client-table-wrap">' +
            '<table class="client-table"><thead><tr>' + cols + '</tr></thead><tbody>' + initial.html + '</tbody></table>' +
          '</div>' +
          '<div class="pager">' +
            '<span class="total">共 ' + initial.total + ' 条</span>' +
            '<button class="pg-btn" type="button" data-page="-1"><span class="pi" data-icon="chevL"></span></button>' +
            '<button class="pg-btn is-current" type="button" data-page="1">' + initial.page + '</button>' +
            '<button class="pg-btn" type="button" data-page="+1"><span class="pi" data-icon="chevR"></span></button>' +
            '<span class="select-like pg-size"><select id="clientPageSize" aria-label="每页条数">' +
            ['10', '20', '50'].map(function (size) {
              return '<option value="' + size + '"' +
                (Number(size) === pageSize() ? ' selected' : '') + '>' + size + ' 条/页</option>';
            }).join('') +
            '</select><span class="chev" data-icon="chevD"></span></span>' +
          '</div>' +
        '</section>' +

        '<aside class="client-detail">' +
          '<button class="detail-back" type="button" data-back="1">' +
          '<span class="bi" data-icon="arrowLeft"></span>' + dt.back + '</button>' +
          '<div class="detail-title-row">' +
            '<h2 class="detail-title">' + dt.title + '</h2>' +
            (dt.connected ? '<span class="badge-conn"><span class="dot dot-green"></span>已连接</span>' : '') +
            '<div class="detail-actions">' +
              '<button class="btn-ghost" type="button" data-act="编辑">编辑</button>' +
              '<button class="btn-icon" type="button" title="更多" data-icon="more"></button>' +
            '</div>' +
          '</div>' +
          '<nav class="detail-tabs">' + tabs + '</nav>' +

          '<section class="detail-card" data-pane="基本信息">' +
            '<div class="detail-identity">' +
              '<span class="avatar-lg" style="background:' + dt.identity.color + '">' + dt.identity.letter + '</span>' +
              '<div class="identity-text">' +
                '<div class="identity-name">' + dt.identity.name + '</div>' +
                '<div class="identity-sub">' + dt.identity.sub + '</div>' +
              '</div>' +
              '<span class="badge-conn identity-badge"><span class="dot dot-green"></span>' + dt.identity.badge + '</span>' +
            '</div>' +
            '<dl class="detail-rows">' + detailRows + '</dl>' +
          '</section>' +

          '<section class="detail-card" data-pane="连接配置" style="display:none"></section>' +
          '<section class="detail-card" data-pane="功能支持" style="display:none">' +
            '<div class="side-card-title" style="margin-bottom:12px"><span class="si" data-icon="layers"></span>' +
            dt.features.title + '</div>' +
            '<div class="feats">' + feats + '</div>' +
          '</section>' +
          '<section class="detail-card" data-pane="连接日志" style="display:none"></section>' +
          '<section class="detail-card" data-pane="操作历史" style="display:none"></section>' +

          '<div class="quick">' +
            '<h3 class="quick-title">' + dt.quick.title + '</h3>' +
            '<div class="quick-btns">' + quickBtns + '</div>' +
          '</div>' +
        '</aside>' +

      '</div>';
  }

  /* ---------------- 详情 ---------------- */

  function paintList(root) {
    const body = root.querySelector('.client-table tbody');
    if (!body) return;
    const result = renderRows();
    body.innerHTML = result.html;
    const total = root.querySelector('.pager .total');
    if (total) total.textContent = '共 ' + result.total + ' 条';
    const current = root.querySelector('.pager .pg-btn.is-current');
    if (current) current.textContent = String(result.page);
    const pagerButtons = root.querySelectorAll('.pager [data-page]');
    if (pagerButtons.length >= 2) {
      pagerButtons[1].dataset.page = String(result.page);
    }
    window.Icons.mount(body);
    bindRows(root);
  }

  function showDetail(root, row) {
    const aside = root.querySelector('.client-detail');
    if (!aside || !row) return;
    selectedId = row.id;
    const title = aside.querySelector('.detail-title');
    if (title) title.textContent = row.name;
    const badge = aside.querySelector('.detail-title-row .badge-conn');
    if (badge) badge.innerHTML = '<span class="dot ' + (row.online ? 'dot-green' : 'dot-gray') + '"></span>' +
      (row.online ? '已连接' : '未连接');
    const avatar = aside.querySelector('.avatar-lg');
    if (avatar) { avatar.textContent = row.letter; avatar.style.background = row.color; }
    const name = aside.querySelector('.identity-name');
    if (name) name.textContent = row.name;
    const sub = aside.querySelector('.identity-sub');
    if (sub) sub.textContent = row.kind;
    const identityBadge = aside.querySelector('.identity-badge');
    if (identityBadge) identityBadge.innerHTML = '<span class="dot ' + (row.online ? 'dot-green' : 'dot-gray') + '"></span>' +
      (row.online ? '已连接' : '未连接');
    const pairs = [
      ['软件版本', row.ver || '-'],
      ['API 地址', row.api || '-'],
      ['凭据引用', row.credential || '-'],
      ['实例标识', row.id || '-'],
      ['连接状态', row.online ? '已连接' : '未连接'],
      ['描述', row.description || '-']
    ];
    const dl = aside.querySelector('.detail-rows');
    if (dl) dl.innerHTML = pairs.map(function (pair) {
      return '<div class="detail-row"><dt>' + esc(pair[0]) + '</dt>' +
        '<dd class="' + (pair[0] === '凭据引用' ? 'mask-key' : '') + '">' + esc(pair[1]) + '</dd></div>';
    }).join('');

    const configPane = aside.querySelector('[data-pane="连接配置"]');
    if (configPane) {
      const settings = [
        ['软件厂商', row.vendor || '-'],
        ['软件产品', row.product || '-'],
        ['版本', row.ver || '-'],
        ['连接地址', row.endpoint || '未配置'],
        ['凭据引用', row.credential || '未配置（由运行环境注入）'],
        ['实例状态', row.status || '-']
      ];
      configPane.innerHTML = '<div class="side-card-title" style="margin-bottom:12px">' +
        '<span class="si" data-icon="plug"></span>连接配置</div>' +
        '<dl class="detail-rows">' + settings.map(function (pair) {
          return '<div class="detail-row"><dt>' + esc(pair[0]) + '</dt><dd>' + esc(pair[1]) + '</dd></div>';
        }).join('') + '</dl>';
    }

    const logPane = aside.querySelector('[data-pane="连接日志"]');
    if (logPane) {
      logPane.innerHTML = '<div class="side-card-title" style="margin-bottom:12px">' +
        '<span class="si" data-icon="fileText"></span>连接日志</div>' +
        '<div class="ui-browser-empty">正在读取…</div>';
    }
    const historyPane = aside.querySelector('[data-pane="操作历史"]');
    if (historyPane) {
      historyPane.innerHTML = '<div class="side-card-title" style="margin-bottom:12px">' +
        '<span class="si" data-icon="hist"></span>操作历史</div>' +
        '<div class="ui-browser-empty">正在读取…</div>';
    }

    root.querySelectorAll('.client-table tbody tr').forEach(function (tr) {
      tr.classList.toggle('is-active', tr.dataset.client === row.id);
    });
    loadEvents(root, row);
  }

  async function loadEvents(root, row) {
    const aside = root.querySelector('.client-detail');
    if (!aside || !window.Api || !window.Api.token()) return;
    const result = await window.Api.clientEvents(row.id);
    const items = ok(result) ? (result.data.items || []) : [];
    const eventHtml = items.length ? items.map(function (event) {
      const tone = String(event.result || '').toUpperCase() === 'SUCCESS' ? 'dl-up' : 'dl-bad';
      const time = String(event.time || '').slice(0, 19).replace('T', ' ');
      return '<div class="detail-row"><dt>' + esc(time) + '</dt>' +
        '<dd><span class="' + tone + '">' + esc(event.action || '-') + '</span> · ' +
        esc(event.detail || '') + '</dd></div>';
    }).join('') : '<div class="ui-browser-empty">暂无连接记录（点击「测试连接」生成）</div>';
    const logPane = aside.querySelector('[data-pane="连接日志"]');
    if (logPane) {
      logPane.innerHTML = '<div class="side-card-title" style="margin-bottom:12px">' +
        '<span class="si" data-icon="fileText"></span>连接日志</div>' +
        '<dl class="detail-rows">' + eventHtml + '</dl>';
    }
    const tests = items.filter(function (event) {
      return event.action === 'test_connection';
    });
    const historyPane = aside.querySelector('[data-pane="操作历史"]');
    if (historyPane) {
      historyPane.innerHTML = '<div class="side-card-title" style="margin-bottom:12px">' +
        '<span class="si" data-icon="hist"></span>操作历史</div>' +
        '<dl class="detail-rows">' + (items.length ? items.map(function (event) {
          const time = String(event.time || '').slice(0, 19).replace('T', ' ');
          return '<div class="detail-row"><dt>' + esc(time) + '</dt><dd>' +
            esc(event.action || '-') + ' · ' + esc(event.result || '') + '</dd></div>';
        }).join('') : '<div class="ui-browser-empty">暂无操作记录</div>') +
        '</dl>' +
        (tests.length ? '<div class="field-hint" style="margin-top:8px">共 ' + tests.length +
          ' 次连接测试</div>' : '');
    }
  }

  /* ---------------- 动作 ---------------- */

  async function reload(root) {
    if (!window.Api || !window.Api.token()) { clients = null; paintList(root); return; }
    const result = await window.Api.clients();
    if (!ok(result)) { clients = null; paintList(root); return; }
    clients = result.data.items || [];
    paintList(root);
    const current = clients.find(function (row) { return row.id === selectedId; }) || clients[0];
    if (current) showDetail(root, rowOf(current, 0));
    else {
      const aside = root.querySelector('.client-detail');
      if (aside) aside.style.opacity = '.55';
    }
  }

  function rowOf(row, index) {
    return rowsSource().find(function (item) { return item.id === row.id; }) || {
      id: row.id, name: row.name, kind: row.product || '', api: row.endpoint || '—',
      online: isOnline(row), ver: row.version || '—', letter: String(row.name || '?')[0],
      color: colorOf(row.name, index), vendor: row.vendor, product: row.product,
      endpoint: row.endpoint, credential: row.credential_reference, description: row.description
    };
  }

  async function openEditor(root, row) {
    if (!window.Api || !window.Api.token()) { toast('未连接后端，无法保存客户端'); return; }
    if (!options) {
      const result = await window.Api.clientOptions();
      options = ok(result) ? result.data : { software: [], products: [], versions: [], statuses: [] };
    }
    const vendors = {};
    (options.software || []).forEach(function (item) { vendors[item.vendor] = true; });
    const products = {};
    (options.products || []).forEach(function (item) { products[item.product] = true; });
    const versions = {};
    (options.versions || []).forEach(function (item) { versions[item.version] = true; });
    const statuses = options.statuses || ['DISCONNECTED', 'CONNECTED', 'DEGRADED', 'UNAVAILABLE'];
    const values = await window.UI.form({
      title: row ? '编辑客户端' : '添加客户端',
      submitLabel: row ? '保存' : '添加',
      note: '厂商 / 产品 / 版本相同的实例会复用同一条软件注册链；凭据引用只保存名称，密钥由运行环境注入。',
      fields: [
        { key: 'name', label: '客户端名称', value: row ? row.name : '', required: true, wide: true,
          placeholder: '例如：CIVIL NX (本机)' },
        { key: 'vendor', label: '软件厂商', value: row ? row.vendor : (Object.keys(vendors)[0] || ''),
          required: true, placeholder: '例如：MIDAS' },
        { key: 'product', label: '软件产品', value: row ? row.product : (Object.keys(products)[0] || ''),
          required: true, placeholder: '例如：CIVIL NX' },
        { key: 'version', label: '版本', value: row ? row.ver : (Object.keys(versions)[0] || ''),
          required: true, placeholder: '例如：2024' },
        { key: 'endpoint', label: 'API 地址', value: row ? row.endpoint : '',
          placeholder: 'http://127.0.0.1:4010' },
        { key: 'credential_reference', label: '凭据引用', value: row ? row.credential : '',
          placeholder: '例如：MIDAS_MAPI_KEY' },
        { key: 'status', label: '初始状态', type: 'select', value: row ? row.status : 'DISCONNECTED',
          options: statuses.map(function (status) {
            const label = status === 'CONNECTED' ? '已连接' : status === 'DISCONNECTED' ? '未连接'
              : status === 'DEGRADED' ? '降级' : status === 'UNAVAILABLE' ? '不可用'
              : status === 'CONNECTING' ? '连接中' : '重连中';
            return { value: status, label: label + '（' + status + '）' };
          }) },
        { key: 'description', label: '描述', type: 'textarea', value: row ? row.description : '',
          wide: true, rows: 3, placeholder: '实例用途、所在机器等' }
      ]
    });
    if (!values) return;
    const result = row
      ? await window.Api.updateClient(row.id, values)
      : await window.Api.createClient(values);
    if (!ok(result)) { fail(result, row ? '保存失败' : '添加失败'); return; }
    toast(row ? '客户端已更新' : '客户端已添加');
    await reload(root);
    const saved = clients && clients.find(function (item) {
      return row ? item.id === row.id : item.name === values.name;
    });
    if (saved) showDetail(root, rowOf(saved, 0));
  }

  async function removeClient(root, row) {
    if (!row) return;
    if (!window.Api || !window.Api.token()) { toast('未连接后端，无法删除'); return; }
    const answer = await window.UI.dialog({
      title: '删除客户端',
      body: '<p>确定删除 <b>' + esc(row.name) + '</b>？</p>' +
        '<p style="color:var(--text-3)">只删除该实例；若同一版本链下没有其它实例，版本 / 产品 / 软件行会一并清理。</p>',
      actions: [
        { label: '取消', value: null, plain: true },
        { label: '删除', value: 'delete', danger: true }
      ]
    }).result;
    if (answer !== 'delete') return;
    const result = await window.Api.deleteClient(row.id);
    if (!ok(result)) { fail(result, '删除失败'); return; }
    toast('客户端已删除');
    selectedId = '';
    await reload(root);
  }

  async function testClient(root, row) {
    if (!row) return;
    if (!window.Api || !window.Api.token()) { toast('未连接后端，无法测试'); return; }
    toast('正在测试连接…');
    const result = await window.Api.testClient(row.id);
    if (!ok(result)) { fail(result, '测试失败'); return; }
    const data = result.data || {};
    if (data.reachable) {
      toast('连接成功' + (data.latency_ms !== null && data.latency_ms !== undefined
        ? '（' + data.latency_ms + ' ms）' : ''));
    } else {
      const reasons = {
        endpoint_not_configured: '未配置 API 地址',
        health_check_failed: '健康检查未通过',
        ConnectError: '无法连接该地址',
        ConnectTimeout: '连接超时'
      };
      toast('连接失败：' + (reasons[data.reason] || data.reason || '未知原因'));
    }
    loadEvents(root, row);
  }

  async function copyEndpoint(root, row) {
    if (!row || !row.endpoint) { toast('该客户端未配置 API 地址'); return; }
    try {
      await navigator.clipboard.writeText(row.endpoint);
      toast('已复制：' + row.endpoint);
    } catch (error) {
      toast('复制失败，请手动选择地址');
    }
  }

  function bindRows(root) {
    root.querySelectorAll('.client-table tbody tr[data-client]').forEach(function (tr) {
      tr.addEventListener('click', function (event) {
        if (event.target.closest('[data-client-menu]')) return;
        const row = filtered().find(function (item) { return item.id === tr.dataset.client; });
        if (row) showDetail(root, row);
      });
    });
    root.querySelectorAll('[data-client-menu]').forEach(function (button) {
      button.addEventListener('click', async function (event) {
        event.stopPropagation();
        const row = filtered().find(function (item) { return item.id === button.dataset.clientMenu; });
        if (!row) return;
        const action = await window.UI.dialog({
          title: row.name,
          body: '<p style="color:var(--text-3)">选择要执行的操作</p>',
          actions: [
            { label: '测试连接', value: 'test' },
            { label: '编辑', value: 'edit' },
            { label: '删除', value: 'delete', danger: true },
            { label: '取消', value: null, plain: true }
          ]
        }).result;
        if (action === 'test') await testClient(root, row);
        else if (action === 'edit') await openEditor(root, row);
        else if (action === 'delete') await removeClient(root, row);
      });
    });
  }

  function selectedRow(root) {
    const rows = filtered();
    return rows.find(function (item) { return item.id === selectedId; }) || rows[0] || null;
  }

  function mount(root) {
    const search = root.querySelector('#clientSearch');
    if (search) search.addEventListener('input', function () {
      keyword = search.value;
      page = 1;
      paintList(root);
      const first = filtered()[0];
      if (first) showDetail(root, first);
    });
    const filter = root.querySelector('#clientFilter');
    if (filter) filter.addEventListener('change', function () {
      statusFilter = filter.value;
      page = 1;
      paintList(root);
    });
    root.querySelectorAll('.pager [data-page]').forEach(function (button) {
      button.addEventListener('click', function () {
        const raw = button.dataset.page;
        if (raw === '+1') page += 1;
        else if (raw === '-1') page -= 1;
        else page = Number(raw) || 1;
        paintList(root);
      });
    });
    const sizeSelect = root.querySelector('#clientPageSize');
    if (sizeSelect) sizeSelect.addEventListener('change', function () {
      if (window.Preferences) window.Preferences.set({ page_size: Number(sizeSelect.value) || 10 });
      page = 1;
      paintList(root);
    });
    root.querySelectorAll('.detail-tab').forEach(function (tab) {
      tab.addEventListener('click', function () {
        root.querySelectorAll('.detail-tab').forEach(function (x) { x.classList.remove('is-active'); });
        tab.classList.add('is-active');
        root.querySelectorAll('[data-pane]').forEach(function (pane) {
          pane.style.display = pane.dataset.pane === tab.dataset.dtab ? '' : 'none';
        });
      });
    });
    root.querySelectorAll('[data-quick]').forEach(function (button) {
      button.addEventListener('click', async function () {
        const row = selectedRow(root);
        const label = button.dataset.quick;
        if (label === '测试连接') await testClient(root, row);
        else if (label === '删除') await removeClient(root, row);
        else if (label === '刷新 Key') {
          if (!row) return;
          toast('凭据由运行环境注入；请更新 STRUCTAI_SECRET_ 环境变量后重启服务');
        } else if (label === '查看日志') {
          const tab = root.querySelector('.detail-tab[data-dtab="连接日志"]');
          if (tab) tab.click();
        }
      });
    });
    root.querySelectorAll('[data-act]').forEach(function (button) {
      button.addEventListener('click', async function () {
        const label = button.dataset.act;
        if (label === '添加客户端') await openEditor(root, null);
        else if (label === '编辑') await openEditor(root, selectedRow(root));
      });
    });
    root.querySelectorAll('[data-rowico]').forEach(function (button) {
      button.addEventListener('click', async function () {
        const row = selectedRow(root);
        if (button.dataset.rowico === '复制') await copyEndpoint(root, row);
        else toast('凭据只显示引用名，密钥由运行环境注入');
      });
    });
    bindRows(root);
    const first = filtered()[0];
    if (first) showDetail(root, first);
    reload(root);
  }

  window.PageClients = { data: function () { return D; }, render: render, mount: mount, reload: reload };
})();
