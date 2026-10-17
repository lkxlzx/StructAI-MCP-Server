/* 参数化模板（P181）：选模板 → 填参数 → 生成 JSON 并经 MCP 导入 MIDAS。
   数据来自 /api/templates 与 /api/templates/{name}；导入走 /api/templates/{name}/import。 */
(function () {
  const D = {
    head: {
      title: '参数化模板',
      sub: '选择官方验证模型模板，修改参数后经 MCP 导入当前 MIDAS 项目',
      action: '刷新模板库'
    },
    families: [],
    templates: [],
    selected: null,
    parameters: {}
  };

  function familyTabs() {
    const names = Object.keys(D.families);
    return names.map(function (name, index) {
      return '<button class="tpl-tab' + (index === 0 ? ' is-active' : '') + '" type="button" data-family="' +
        window.UI.esc(name) + '">' + window.UI.esc(name) +
        '<span class="tpl-count">' + D.families[name].length + '</span></button>';
    }).join('');
  }

  function templateList(family) {
    const names = D.families[family] || [];
    return names.map(function (name) {
      return '<button class="tpl-item" type="button" data-template="' + window.UI.esc(name) + '">' +
        '<span class="tpl-name">' + window.UI.esc(name) + '</span>' +
        '<span class="chev" data-icon="chevR"></span></button>';
    }).join('');
  }

  function parameterRows() {
    const keys = Object.keys(D.parameters).sort();
    if (!keys.length) {
      return '<p class="tpl-empty">选择左侧模板后显示参数。</p>';
    }
    return keys.map(function (key) {
      const entry = D.parameters[key];
      const unit = entry.unit ? ' <span class="tpl-unit">[' + window.UI.esc(entry.unit) + ']</span>' : '';
      const kind = entry.kind === 'boolean' ? 'boolean' : entry.kind === 'string' ? 'text' : 'number';
      const value = entry.value === null || entry.value === undefined ? '' : String(entry.value);
      let input;
      if (entry.kind === 'boolean') {
        input = '<select class="tpl-input" data-param="' + window.UI.esc(key) + '">' +
          '<option value="true"' + (entry.value ? ' selected' : '') + '>true</option>' +
          '<option value="false"' + (!entry.value ? ' selected' : '') + '>false</option></select>';
      } else {
        input = '<input class="tpl-input" type="' + kind + '" step="any" data-param="' +
          window.UI.esc(key) + '" value="' + window.UI.esc(value) + '">';
      }
      return '<div class="tpl-row">' +
        '<label class="tpl-label" title="' + window.UI.esc(entry.source || '') + '">' +
        window.UI.esc(key) + unit +
        '<span class="tpl-desc">' + window.UI.esc(entry.description || '') + '</span></label>' +
        input + '</div>';
    }).join('');
  }

  function render() {
    return '' +
      '<section class="card card-pad tpl-head">' +
        '<h1 class="card-title">' + window.UI.esc(D.head.title) + '</h1>' +
        '<p class="tpl-sub">' + window.UI.esc(D.head.sub) + '</p>' +
      '</section>' +
      '<div class="tpl-layout">' +
        '<section class="card tpl-side">' +
          '<div class="tpl-tabs">' + familyTabs() + '</div>' +
          '<div class="tpl-list" id="tplList">' + templateList(Object.keys(D.families)[0] || '') + '</div>' +
        '</section>' +
        '<section class="card tpl-main">' +
          '<div class="tpl-main-head">' +
            '<h2 class="tpl-title" id="tplTitle">选择模板</h2>' +
            '<span class="tpl-meta" id="tplMeta"></span>' +
          '</div>' +
          '<div class="tpl-params" id="tplParams">' + parameterRows() + '</div>' +
          '<div class="tpl-actions">' +
            '<button class="btn-primary" type="button" id="tplImport" disabled>生成并导入</button>' +
            '<span class="tpl-hint" id="tplHint">导入会把模板生成的 JSON 合并进当前项目（不会清空已有模型）。</span>' +
          '</div>' +
        '</section>' +
      '</div>';
  }

  async function loadTemplates(root) {
    const library = await window.Live.templates();
    if (!library) {
      root.querySelector('#tplHint').textContent = '无法连接核心服务（模板库不可用）。';
      return;
    }
    D.families = library.families || {};
    D.templates = library.items || [];
    const side = root.querySelector('.tpl-side');
    side.innerHTML = '<div class="tpl-tabs">' + familyTabs() + '</div>' +
      '<div class="tpl-list" id="tplList">' + templateList(Object.keys(D.families)[0] || '') + '</div>';
    bind(root);
    window.Icons.mount(root);
  }

  async function selectTemplate(root, name) {
    const detail = await window.Live.template(name);
    if (!detail) { window.Toast && window.Toast.show('模板详情不可用'); return; }
    D.selected = detail;
    D.parameters = detail.parameters || {};
    root.querySelectorAll('.tpl-item').forEach(function (button) {
      button.classList.toggle('is-active', button.dataset.template === name);
    });
    root.querySelector('#tplTitle').textContent = name;
    root.querySelector('#tplMeta').textContent = detail.family + ' · ' + detail.tables + ' 张表 · ' +
      Object.keys(D.parameters).length + ' 个参数';
    root.querySelector('#tplParams').innerHTML = parameterRows();
    const importButton = root.querySelector('#tplImport');
    importButton.disabled = false;
    window.Icons.mount(root);
  }

  function collect(root) {
    const values = {};
    root.querySelectorAll('[data-param]').forEach(function (input) {
      const key = input.dataset.param;
      const entry = D.parameters[key];
      if (!entry) return;
      if (entry.kind === 'boolean') { values[key] = input.value === 'true'; return; }
      if (entry.kind === 'integer') { values[key] = parseInt(input.value, 10); return; }
      if (entry.kind === 'number') { values[key] = parseFloat(input.value); return; }
      values[key] = input.value;
    });
    return values;
  }

  function bind(root) {
    root.querySelectorAll('[data-family]').forEach(function (button) {
      button.addEventListener('click', function () {
        root.querySelectorAll('.tpl-tab').forEach(function (x) { x.classList.remove('is-active'); });
        button.classList.add('is-active');
        root.querySelector('#tplList').innerHTML = templateList(button.dataset.family);
        bindItems(root);
        window.Icons.mount(root);
      });
    });
    bindItems(root);
  }

  function bindItems(root) {
    root.querySelectorAll('[data-template]').forEach(function (button) {
      button.addEventListener('click', function () { selectTemplate(root, button.dataset.template); });
    });
  }

  function mount(root) {
    window.Icons.mount(root);
    loadTemplates(root);
    bind(root);
    const importButton = root.querySelector('#tplImport');
    if (importButton) importButton.addEventListener('click', async function () {
      if (!D.selected) return;
      importButton.disabled = true;
      importButton.textContent = '导入中…';
      const result = await window.Api.importTemplate(D.selected.name, collect(root), '');
      importButton.disabled = false;
      importButton.textContent = '生成并导入';
      const envelope = result && result.data && result.data.response;
      if (result && result.ok && envelope && envelope.success) {
        window.Toast && window.Toast.show('已导入：' + D.selected.name);
        root.querySelector('#tplHint').textContent = '导入成功（' + (result.data.written || '') + '）';
      } else {
        const message = (envelope && envelope.errors && envelope.errors[0] && envelope.errors[0].message)
          || (result && result.data && result.data.message) || '导入失败';
        root.querySelector('#tplHint').textContent = message;
        window.Toast && window.Toast.show(message);
      }
    });
  }

  window.PageTemplates = { data: function () { return D; }, render: render, mount: mount };
})();
