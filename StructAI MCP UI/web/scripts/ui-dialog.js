/* 通用弹窗（P185）
   - window.UI.dialog({title, body, actions}) → Promise<string|null>
   - window.UI.form({title, fields, submitLabel}) → Promise<object|null>
   与项目其它脚本一致：零依赖、只创建 DOM，不引入框架。 */
(function () {
  const esc = function (value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  function mountLayer() {
    let layer = document.getElementById('ui-dialog-layer');
    if (!layer) {
      layer = document.createElement('div');
      layer.id = 'ui-dialog-layer';
      layer.className = 'ui-dialog-layer';
      document.body.appendChild(layer);
    }
    return layer;
  }

  function close(layer, dialog, resolve, value) {
    layer.classList.remove('is-on');
    dialog.remove();
    if (!layer.childElementCount) layer.remove();
    resolve(value);
  }

  /* ---------------- 通用对话框 ---------------- */

  function dialog(options) {
    const opts = options || {};
    const layer = mountLayer();
    const box = document.createElement('div');
    box.className = 'ui-dialog';
    box.setAttribute('role', 'dialog');
    box.setAttribute('aria-modal', 'true');
    box.innerHTML =
      '<header class="ui-dialog-head"><b>' + esc(opts.title || '') + '</b>' +
      '<button class="ui-dialog-x" type="button" aria-label="关闭">×</button></header>' +
      '<div class="ui-dialog-body">' + (opts.body || '') + '</div>' +
      '<footer class="ui-dialog-foot"></footer>';
    const foot = box.querySelector('.ui-dialog-foot');
    const actions = opts.actions || [{ label: '关闭', value: null, plain: true }];
    let resolveResult = null;
    const result = new Promise(function (resolve) { resolveResult = resolve; });
    actions.forEach(function (action) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = action.primary ? 'btn-blue' : 'btn-w';
      if (action.danger) button.className = 'btn-red';
      button.textContent = action.label;
      button.addEventListener('click', function () {
        if (typeof action.onClick === 'function' && action.onClick(box) === false) return;
        close(layer, box, resolveResult, action.value === undefined ? action.label : action.value);
      });
      foot.appendChild(button);
    });
    box.querySelector('.ui-dialog-x').addEventListener('click', function () {
      close(layer, box, resolveResult, null);
    });
    layer.appendChild(box);
    layer.classList.add('is-on');
    const first = box.querySelector('input, select, textarea');
    if (first) setTimeout(function () { first.focus(); }, 30);
    if (typeof opts.onMount === 'function') opts.onMount(box);
    return { element: box, result: result };
  }

  /* ---------------- 表单 ---------------- */

  /* fields: [{key, label, type, value, options, placeholder, hint, required, min, max, rows}] */
  function fieldHtml(field) {
    const id = 'f-' + field.key;
    let control;
    if (field.type === 'select') {
      control = '<select id="' + id + '" data-key="' + esc(field.key) + '">' +
        (field.options || []).map(function (option) {
          const value = typeof option === 'object' ? option.value : option;
          const label = typeof option === 'object' ? option.label : option;
          return '<option value="' + esc(value) + '"' +
            (String(value) === String(field.value) ? ' selected' : '') + '>' + esc(label) + '</option>';
        }).join('') + '</select>';
    } else if (field.type === 'textarea') {
      control = '<textarea id="' + id + '" data-key="' + esc(field.key) + '" rows="' +
        (field.rows || 4) + '" placeholder="' + esc(field.placeholder || '') + '">' +
        esc(field.value || '') + '</textarea>';
    } else if (field.type === 'switch') {
      control = '<label class="ui-switch"><input type="checkbox" id="' + id + '" data-key="' +
        esc(field.key) + '"' + (field.value ? ' checked' : '') + '><span></span></label>';
    } else {
      control = '<input id="' + id + '" data-key="' + esc(field.key) + '" type="' +
        (field.type || 'text') + '" value="' + esc(field.value === undefined ? '' : field.value) +
        '" placeholder="' + esc(field.placeholder || '') + '"' +
        (field.min !== undefined ? ' min="' + esc(field.min) + '"' : '') +
        (field.max !== undefined ? ' max="' + esc(field.max) + '"' : '') + '>';
    }
    return '<label class="ui-field' + (field.wide ? ' wide' : '') + '">' +
      '<span class="ui-field-label">' + esc(field.label || field.key) +
      (field.required ? '<em>*</em>' : '') + '</span>' + control +
      (field.hint ? '<span class="ui-field-hint">' + esc(field.hint) + '</span>' : '') + '</label>';
  }

  function readField(box, field) {
    const node = box.querySelector('[data-key="' + field.key + '"]');
    if (!node) return undefined;
    if (field.type === 'switch') return node.checked;
    if (field.type === 'number') return node.value === '' ? null : Number(node.value);
    return node.value;
  }

  function form(options) {
    const opts = options || {};
    const fields = opts.fields || [];
    const body = '<div class="ui-form">' + fields.map(fieldHtml).join('') + '</div>' +
      (opts.note ? '<div class="ui-form-note">' + esc(opts.note) + '</div>' : '');
    return dialog({
      title: opts.title || '',
      body: body,
      actions: [
        { label: opts.cancelLabel || '取消', value: null, plain: true },
        {
          label: opts.submitLabel || '保存',
          primary: true,
          onClick: function (box) {
            const values = {};
            for (const field of fields) {
              values[field.key] = readField(box, field);
              if (field.required && (values[field.key] === '' || values[field.key] === null)) {
                window.Toast.show((field.label || field.key) + ' 不能为空');
                return false;
              }
            }
            if (typeof opts.validate === 'function') {
              const message = opts.validate(values);
              if (message) { window.Toast.show(message); return false; }
            }
            opts._values = values;
            return true;
          },
          value: 'submit'
        }
      ],
      onMount: opts.onMount
    }).result.then(function (action) {
      return action === 'submit' ? opts._values : null;
    });
  }

  /* ⚠️ 不要写 `window.UI = {...}`：`ui.js` 已经建立了该命名空间，
     整体赋值会把它覆盖掉（页面上的 pill/progress 等都会失效）。 */
  window.UI = window.UI || {};
  window.UI.dialog = dialog;
  window.UI.form = form;
})();
