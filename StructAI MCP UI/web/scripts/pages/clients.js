/* MIDAS 客户端 */
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

  function render() {
    const d = D;
    const rows = d.rows.map(function (r) {
      return '<tr data-client="' + r.id + '">' +
        '<td><div class="name-cell"><span class="letter-avatar" style="background:' + r.color + '">' + r.letter + '</span>' +
        '<span class="name-text">' + r.name + '</span></div></td>' +
        '<td class="muted">' + r.kind + '</td>' +
        '<td class="muted">' + r.api + '</td>' +
        '<td><span class="state-cell ' + (r.online ? 'on' : 'off') + '">' +
        '<span class="dot ' + (r.online ? 'dot-green' : 'dot-gray') + '"></span>' +
        (r.online ? '已连接' : '未连接') + '</span></td>' +
        '<td class="muted">' + r.ver + '</td>' +
        '<td class="col-ops"><button class="row-more" type="button" data-more="客户端操作" data-icon="more"></button></td>' +
        '</tr>';
    }).join('');

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
            '<span class="select-like filter-select"><select aria-label="状态筛选">' +
            '<option>' + d.search.filter + '</option><option>已连接</option><option>未连接</option>' +
            '</select><span class="chev" data-icon="chevD"></span></span>' +
          '</div>' +
          '<div class="client-table-wrap">' +
            '<table class="client-table"><thead><tr>' + cols + '</tr></thead><tbody>' + rows + '</tbody></table>' +
          '</div>' +
          '<div class="pager">' +
            '<span class="total">' + d.pager.total + '</span>' +
            '<button class="pg-btn" type="button" data-page="-1"><span class="pi" data-icon="chevL"></span></button>' +
            '<button class="pg-btn is-current" type="button" data-page="1">' + d.pager.page + '</button>' +
            '<button class="pg-btn" type="button" data-page="+1"><span class="pi" data-icon="chevR"></span></button>' +
            '<span class="select-like pg-size"><select aria-label="每页条数">' +
            '<option>' + d.pager.size + '</option><option>20 条/页</option><option>50 条/页</option>' +
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

          '<section class="detail-card">' +
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

          '<section class="detail-card">' +
            '<div class="side-card-title" style="margin-bottom:12px"><span class="si" data-icon="layers"></span>' +
            dt.features.title + '</div>' +
            '<div class="feats">' + feats + '</div>' +
          '</section>' +

          '<div class="quick">' +
            '<h3 class="quick-title">' + dt.quick.title + '</h3>' +
            '<div class="quick-btns">' + quickBtns + '</div>' +
          '</div>' +
        '</aside>' +

      '</div>';
  }

  function mount(root) {
    const search = root.querySelector('#clientSearch');
    const rows = root.querySelectorAll('.client-table tbody tr');
    if (search) search.addEventListener('input', function () {
      const q = search.value.trim().toLowerCase();
      rows.forEach(function (tr) {
        tr.style.display = !q || tr.textContent.toLowerCase().indexOf(q) >= 0 ? '' : 'none';
      });
    });
    rows.forEach(function (tr) {
      tr.addEventListener('click', function (e) {
        if (e.target.closest('[data-more]')) return;
        root.querySelectorAll('.client-table tbody tr').forEach(function (x) { x.classList.remove('is-active'); });
        tr.classList.add('is-active');
        window.Toast.show('已选择客户端：' + tr.querySelector('.name-text').textContent);
      });
    });
    root.querySelectorAll('[data-dtab]').forEach(function (b) {
      b.addEventListener('click', function () {
        root.querySelectorAll('.detail-tab').forEach(function (x) { x.classList.remove('is-active'); });
        b.classList.add('is-active');
        window.Toast.show('切换到：' + b.dataset.dtab);
      });
    });
    root.querySelectorAll('[data-quick]').forEach(function (b) {
      b.addEventListener('click', function () { window.Toast.show('执行：' + b.dataset.quick); });
    });
    root.querySelectorAll('[data-rowico]').forEach(function (b) {
      b.addEventListener('click', function () { window.Toast.show(b.dataset.rowico); });
    });
  }

  window.PageClients = { data: function () { return D; }, render: render, mount: mount };
})();
