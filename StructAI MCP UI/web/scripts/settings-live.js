/* 系统设置 · 实时数据与保存（P183）
   - 页面先按 mock 渲染（离线可看），拿到 /api/settings 后**只改数据区域**
   - 任何控件改动 → 立即 PUT /api/settings/{section}（失败回滚 UI 并提示）
   - 用户 / 角色 / 模型 / 数据管理走各自的 REST 端点
   ⚠️ 不改布局与样式；找不到对应控件时静默跳过（mock 版本可能少几个字段）。 */
(function () {
  let state = null;          // 最近一次 /api/settings 的响应
  let saveTimer = null;
  let pending = null;        // {section, values}
  let currentRoot = null;    // 当前挂载的视图（弹窗动作回调需要）

  function ok(result) { return !!(result && result.ok); }

  function toast(message) {
    if (window.Toast) window.Toast.show(message);
  }

  function fail(result, fallback) {
    const message = (result && result.data && result.data.message) || fallback;
    toast(message || '操作失败');
  }

  /* ---------------- 界面偏好（主题 / 密度 / 分页 / 提示 / 动画） ---------------- */

  function applyPreferences(ui) {
    if (!window.Preferences) return;
    return window.Preferences.set({
      theme: ui.theme || 'light',
      density: ui.density || 'comfortable',
      page_size: Number(ui.page_size) || 10,
      show_tooltips: ui.show_tooltips !== false,
      show_animations: ui.show_animations !== false,
      compact_sidebar: !!ui.compact_sidebar
    });
  }

  /* 目录选择器：返回 Promise<string|null> */
  async function pickDirectory(start) {
    if (!window.Api || !window.Api.token()) { toast('未连接后端，无法浏览目录'); return null; }
    let current = start || '';
    return new Promise(function (resolve) {
      const handle = window.UI.dialog({
        title: '选择目录',
        body: '<div class="ui-browser">' +
          '<div class="ui-browser-head"><span class="ui-browser-path">' + window.UI.esc(current || '根目录') + '</span>' +
          '<button class="tbtn" type="button" data-browser-up>上一级</button></div>' +
          '<div class="ui-browser-list"><div class="ui-browser-empty">正在读取…</div></div></div>' +
          '<div class="ui-form-note">选择后点击「使用此目录」；也可以直接在路径框里手动填写。</div>',
        actions: [
          { label: '取消', value: null, plain: true },
          { label: '使用此目录', value: 'use', primary: true,
            onClick: function (box) {
              const field = box.querySelector('[data-manual-path]');
              if (field && field.value.trim()) current = field.value.trim();
              resolve(current || null);
              return true;
            } }
        ]
      });
      handle.result.then(function (value) {
        if (value === null) resolve(null);
      });
      const box = handle.element;
      const list = box.querySelector('.ui-browser-list');
      const pathLabel = box.querySelector('.ui-browser-path');
      const upButton = box.querySelector('[data-browser-up]');
      async function load(target) {
        const result = await window.Api.browse(target);
        if (!ok(result)) { fail(result, '目录不可读'); return; }
        current = result.data.path || '';
        pathLabel.textContent = current || '根目录';
        const items = result.data.items || [];
        list.innerHTML = items.length ? items.map(function (item) {
          return '<button class="ui-browser-item" type="button" data-browse="' +
            window.UI.esc(item.path) + '"><span data-icon="folder" style="width:16px;height:16px"></span>' +
            window.UI.esc(item.name) + '</button>';
        }).join('') : '<div class="ui-browser-empty">没有子目录</div>';
        window.Icons.mount(list);
        list.querySelectorAll('[data-browse]').forEach(function (button) {
          button.addEventListener('click', function () { load(button.dataset.browse); });
        });
        upButton.disabled = !result.data.parent;
        upButton.dataset.parent = result.data.parent || '';
      }
      upButton.addEventListener('click', function () {
        if (upButton.dataset.parent) load(upButton.dataset.parent);
      });
      /* 手动路径输入 */
      const manual = document.createElement('input');
      manual.type = 'text';
      manual.dataset.manualPath = '1';
      manual.placeholder = '或直接输入路径';
      manual.value = start || '';
      manual.style.cssText = 'width:100%;height:36px;margin-top:10px;padding:0 10px;border:1px solid #E3E9F2;border-radius:6px';
      box.querySelector('.ui-dialog-body').appendChild(manual);
      load(current);
    });
  }

  /* ---------------- 值写入控件 ---------------- */

  function setSwitch(el, on) {
    if (!el) return;
    el.classList.toggle('is-on', !!on);
    el.setAttribute('aria-checked', String(!!on));
  }

  function setInput(row, value) {
    if (!row) return;
    const input = row.querySelector('input');
    if (input && value !== undefined && value !== null) input.value = String(value);
    /* 滑块：同步填充宽度 / 旋钮位置 / 右侧数值框 */
    const slider = row.querySelector('.slider');
    if (!slider) return;
    const min = Number((row.querySelector('.slider-scale span') || {}).textContent);
    const spans = row.querySelectorAll('.slider-scale span');
    const max = spans.length > 1 ? Number(spans[1].textContent) : min;
    const valueText = row.querySelector('.slider-val');
    if (valueText && value !== undefined && value !== null) valueText.textContent = String(value);
    if (Number.isFinite(min) && Number.isFinite(max) && max > min) {
      const pct = Math.max(0, Math.min(100, ((Number(value) - min) / (max - min)) * 100));
      const fill = slider.querySelector('.fill');
      const knob = slider.querySelector('.knob');
      if (fill) fill.style.width = pct + '%';
      if (knob) knob.style.left = pct + '%';
    }
  }

  function setSelect(row, value) {
    if (!row) return;
    const select = row.querySelector('select');
    if (!select || value === undefined || value === null) return;
    const text = String(value);
    const match = Array.prototype.find.call(select.options, function (option) {
      return option.textContent.trim() === text || option.value === text;
    });
    if (match) select.value = match.value;
    else if (select.options.length && !select.options[0].value) {
      /* 值不在选项里时保留原选项，避免把用户输入吞掉 */
    }
  }

  /* 按标签文字找设置行（标签是 `.k` / `.ft b` / `.lb` / `dt`） */
  function rowByLabel(root, label) {
    const rows = root.querySelectorAll('.set-row, .path-row, .feat-row, .kv-list .r, .slider-row');
    for (const row of rows) {
      const key = row.querySelector('.k, .ft b, .lb, dt');
      if (key && key.textContent.trim() === label) return row;
    }
    return null;
  }

  function toggleByLabel(root, label, value) {
    const row = rowByLabel(root, label);
    if (row) setSwitch(row.querySelector('.switch'), value);
  }

  function inputByLabel(root, label, value) {
    setInput(rowByLabel(root, label), value);
  }

  function selectByLabel(root, label, value) {
    setSelect(rowByLabel(root, label), value);
  }

  /* ---------------- 基础设置 ---------------- */

  function applyBasic(root, settings) {
    const behavior = settings.behavior || {};
    const ui = settings.interface || {};
    const paths = settings.paths || {};
    const notify = settings.notify || {};

    selectByLabel(root, '默认软件', behavior.default_software);
    selectByLabel(root, '默认版本', behavior.default_version);
    inputByLabel(root, '任务超时时间', behavior.task_timeout_minutes);
    inputByLabel(root, '日志保留天数', behavior.log_retention_days);
    toggleByLabel(root, '自动清理过期任务', behavior.auto_cleanup);
    toggleByLabel(root, '启动时自动检查更新', behavior.check_update_on_start);
    toggleByLabel(root, '最小化到系统托盘', behavior.minimize_to_tray);

    /* 默认软件 / 版本：选项来自已登记的软件实例（`/api/clients`） */
    window.Api.clients().then(function (result) {
      if (!ok(result) || !(result.data.items || []).length) return;
      const instances = result.data.items;
      const softwareSelect = rowByLabel(root, '默认软件');
      const versionSelect = rowByLabel(root, '默认版本');
      if (softwareSelect) {
        const select = softwareSelect.querySelector('select');
        if (select) {
          select.innerHTML = instances.map(function (item) {
            return '<option>' + window.UI.esc(item.name) + '</option>';
          }).join('');
          if (behavior.default_software) select.value = behavior.default_software;
          else select.value = instances[0].name;
        }
      }
      if (versionSelect) {
        const select = versionSelect.querySelector('select');
        if (select) {
          select.innerHTML = instances.map(function (item) {
            return '<option>' + window.UI.esc(item.version || '-') + '</option>';
          }).join('');
          const current = behavior.default_version
            ? instances.find(function (item) { return item.name === behavior.default_software; })
            : instances[0];
          if (current && current.version) select.value = current.version;
        }
      }
    });

    /* 主题卡片 */
    root.querySelectorAll('.theme-card').forEach(function (card) {
      card.classList.toggle('is-on', card.dataset.theme === (ui.theme || 'light'));
    });
    selectByLabel(root, '语言设置', ui.language === 'zh-CN' ? '简体中文'
      : ui.language === 'en-US' ? 'English' : ui.language);
    selectByLabel(root, '页面显示密度', ui.density === 'comfortable' ? '舒适'
      : ui.density === 'compact' ? '紧凑' : '标准');
    selectByLabel(root, '每页显示条数', ui.page_size);
    toggleByLabel(root, '显示工具提示', ui.show_tooltips);
    toggleByLabel(root, '显示动画效果', ui.show_animations);
    toggleByLabel(root, '紧凑侧边栏', ui.compact_sidebar);
    /* 界面偏好真正生效（深色 / 密度 / 动画 / 紧凑侧栏） */
    applyPreferences(ui);
    /* 通知通道：页面 / 浏览器 / 邮件 */
    window.Toast.channels = (notify.channels || []).slice();
    if (notify.channels && notify.channels.indexOf('browser') >= 0 && window.Notification
        && Notification.permission === 'default') {
      try { Notification.requestPermission(); } catch (error) { /* 忽略 */ }
    }

    /* 路径：后端返回空串 = 未配置，保留输入框的占位提示（不写假路径） */
    const pathMap = {
      'MIDAS 安装路径': paths.software_home,
      '临时文件目录': paths.temp_dir,
      '项目文件默认目录': paths.project_dir,
      '模型文件默认目录': paths.model_dir,
      '结果文件默认目录': paths.result_dir
    };
    const pathKeys = {
      'MIDAS 安装路径': 'software_home',
      '临时文件目录': 'temp_dir',
      '项目文件默认目录': 'project_dir',
      '模型文件默认目录': 'model_dir',
      '结果文件默认目录': 'result_dir'
    };
    Object.keys(pathMap).forEach(function (key) {
      const row = rowByLabel(root, key);
      if (!row) return;
      const input = row.querySelector('input');
      if (!input) return;
      input.value = pathMap[key] || '';
      input.placeholder = '未配置（点击右侧选择目录）';
      input.dataset.pathKey = pathKeys[key];
    });

    toggleByLabel(root, '任务完成通知', notify.task_done);
    toggleByLabel(root, '任务失败通知', notify.task_failed);
    toggleByLabel(root, '系统异常通知', notify.system_error);
    const channels = notify.channels || [];
    root.querySelectorAll('.cbx-item').forEach(function (item) {
      const name = item.dataset.channel || '';
      const on = channels.some(function (c) { return name.indexOf(
        c === 'page' ? '页面' : c === 'browser' ? '浏览器' : '邮件') >= 0; });
      item.classList.toggle('is-on', on);
      const box = item.querySelector('.box');
      if (box) box.innerHTML = on ? window.Icons.check : '';
    });
    const mailInput = root.querySelector('.settings-card .s-input input[placeholder*="邮箱"]');
    if (mailInput && notify.email) mailInput.value = notify.email;

    /* 系统信息（只读） */
    const system = settings.system || {};
    const rows = root.querySelectorAll('.kv-table .kv-row');
    rows.forEach(function (row) {
      const key = (row.querySelector('dt') || {}).textContent || '';
      const value = row.querySelector('dd');
      if (!value) return;
      if (key === '版本号' && system.version) value.textContent = system.version;
      if (key === '构建时间' && system.build_time) value.textContent = system.build_time;
      if (key === '运行环境' && system.platform) value.textContent = system.platform;
      if (key === 'Python' && system.python) value.textContent = system.python;
      if (key === '安装路径' && system.registry_root) value.textContent = system.registry_root;
      if (key === '数据目录' && system.database) value.textContent = system.database;
      if (key === '日志目录' && system.log_dir) value.textContent = system.log_dir;
    });
    const chips = root.querySelector('.ident-chips .mini-chip.blue');
    if (chips && system.version) chips.textContent = system.version;
  }

  /* ---------------- 服务配置 ---------------- */

  function applyService(root, settings) {
    const service = settings.service || {};
    const features = service.features || {};
    const performance = service.performance || {};
    const system = settings.system || {};

    selectByLabel(root, '监听地址', service.listen_host);
    inputByLabel(root, '服务端口', service.port);
    inputByLabel(root, '管理端口', service.management_port);
    inputByLabel(root, '最大连接数', service.max_connections);
    toggleByLabel(root, '开启 CORS', service.cors_enabled);
    const origin = rowByLabel(root, '允许的来源');
    if (origin) setInput(origin, service.cors_origins);
    const allow = root.querySelector('.s-input input[placeholder*="localhost"]');
    if (allow && service.cors_origins) allow.value = service.cors_origins;

    const featureLabels = {
      mcp: '启用 MCP 协议服务',
      rest: '启用 REST API 接口',
      web: '启用 Web 管理界面',
      queue: '启用任务队列',
      cache: '启用结果缓存',
      verbose_log: '启用详细日志'
    };
    Object.keys(featureLabels).forEach(function (key) {
      toggleByLabel(root, featureLabels[key], features[key]);
    });

    inputByLabel(root, '工作线程数', performance.workers);
    inputByLabel(root, '任务队列大小', performance.queue_size);
    inputByLabel(root, '任务超时时间', performance.task_timeout_seconds);
    inputByLabel(root, '结果缓存时间', performance.cache_seconds);

    /* 服务状态卡（真实运行信息；进程 ID / 启动时间 / 运行时长来自 `/api/status`） */
    const kv = root.querySelector('.kv-list');
    const map = {
      '服务名称': 'structai-mcp-server',
      '当前版本': system.version,
      '监听地址': service.listen_host && service.port ? service.listen_host + ':' + service.port : '',
      '数据目录': system.database
    };
    function paintServiceStatus(extra) {
      if (!kv) return;
      const merged = Object.assign({}, map, extra || {});
      kv.querySelectorAll('.r').forEach(function (row) {
        const key = (row.querySelector('dt') || {}).textContent || '';
        const value = row.querySelector('dd');
        if (value && merged[key]) value.textContent = merged[key];
      });
    }
    paintServiceStatus();
    window.Api.get('/api/status').then(function (result) {
      if (!ok(result)) return;
      const status = result.data || {};
      const running = (status.service || {}).running;
      paintServiceStatus({
        '进程 ID': status.pid ? String(status.pid) : '-',
        '启动时间': status.started_at ? String(status.started_at).slice(0, 19).replace('T', ' ') : '-',
        '运行时长': status.uptime_seconds !== undefined
          ? formatUptime(status.uptime_seconds) : '-'
      });
      const tag = root.querySelector('.settings-card .tag.green, .settings-card .tag.red');
      if (tag) {
        tag.className = 'tag ' + (running ? 'green' : 'red');
        tag.innerHTML = '<span class="dot"></span>' + (running ? '运行中' : '已停止');
      }
    });

    /* 环境变量表 */
    const env = service.env || [];
    const table = root.querySelector('.dtable');
    if (table && env.length) {
      const body = table.querySelector('tbody');
      if (body) {
        body.innerHTML = env.map(function (item) {
          return '<tr><td>' + window.UI.esc(item.name) + '</td>' +
            '<td>' + window.UI.esc(item.value || '') + '</td>' +
            '<td class="mut">' + window.UI.esc(item.description || '') + '</td>' +
            '<td><span class="ico-cell">' +
            '<button class="tbtn icon" type="button" data-act2="编辑变量" data-env-edit="' +
            window.UI.esc(item.name) + '"><span data-icon="edit"></span></button>' +
            '<button class="tbtn icon danger" type="button" data-act2="删除变量" data-env-delete="' +
            window.UI.esc(item.name) + '"><span data-icon="trash"></span></button>' +
            '</span></td></tr>';
        }).join('');
        window.Icons.mount(body);
      }
    }
  }

  /* ---------------- 模型设置 ---------------- */

  function applyModels(root, settings) {
    const models = settings.models || {};
    const items = models.items || [];
    const parameters = models.parameters || {};
    const connection = models.connection || {};

    /* 统计卡 */
    const stats = root.querySelectorAll('.stat4 .sc-value');
    if (stats.length >= 3) {
      const available = items.filter(function (item) { return item.available; }).length;
      stats[0].textContent = String(items.length);
      stats[1].textContent = String(available);
      stats[2].textContent = String(items.length - available);
    }

    /* 列表 */
    const table = root.querySelector('.set2 .dtable');
    if (table) {
      const body = table.querySelector('tbody');
      if (body) {
        body.innerHTML = items.map(function (item, index) {
          return '<tr data-model="' + window.UI.esc(item.id) + '">' +
            '<td><input type="checkbox" style="accent-color:var(--brand)"></td>' +
            '<td>' + (index + 1) + '</td>' +
            '<td><b style="font-weight:600;color:var(--text-1)">' + window.UI.esc(item.name) + '</b></td>' +
            '<td>' + window.UI.esc(item.provider) + '</td>' +
            '<td>' + window.UI.esc(item.kind) + '</td>' +
            '<td>' + window.UI.esc(item.context) + '</td>' +
            '<td>' + (item.available
              ? '<span class="tag green"><span class="dot"></span>可用</span>'
              : '<span class="tag red"><span class="dot"></span>不可用</span>') + '</td>' +
            '<td><span style="display:inline-flex;align-items:center;justify-content:center;width:16px;height:16px;border-radius:50%;border:1.5px solid ' +
            (item.is_default ? 'var(--brand)' : '#C9D4E4') + '">' +
            (item.is_default ? '<span style="width:8px;height:8px;border-radius:50%;background:var(--brand)"></span>' : '') +
            '</span></td>' +
            '<td><span style="display:flex;gap:4px">' +
            '<button class="tbtn link" type="button" data-model-test="' + window.UI.esc(item.id) + '">测试</button>' +
            '<button class="tbtn link" type="button" data-model-default="' + window.UI.esc(item.id) + '">设为默认</button>' +
            '</span></td></tr>';
        }).join('');
        if (!items.length) {
          body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-3)">暂无模型</td></tr>';
        }
      }
      const total = root.querySelector('.set2 .pager .total');
      if (total) total.textContent = '共 ' + items.length + ' 条';
    }

    /* 详情卡：跟随默认模型（点击行也会切换） */
    const detail = root.querySelector('.set2 .settings-card:last-child');
    let detailItem = null;
    function showDetail(item) {
      if (!detail || !item) return;
      detailItem = item;
      root.dataset.selectedModel = item.id;
      const title = detail.querySelector('b[style*="font-size:17px"]');
      if (title) title.textContent = item.name;
      const badge = detail.querySelector('.tag.green, .tag.red');
      if (badge) {
        badge.className = 'tag ' + (item.available ? 'green' : 'red');
        badge.innerHTML = '<span class="dot"></span>' + (item.available ? '可用' : '不可用');
      }
      const provider = detail.querySelector('div[style*="font-size:14px"]');
      if (provider) provider.textContent = item.provider;
      const desc = detail.querySelector('div[style*="font-size:13px"][style*="line-height"]');
      if (desc) desc.textContent = item.description || '';
      const rows = detail.querySelectorAll('.kv-list .r dd');
      if (rows.length >= 6) {
        rows[0].textContent = item.kind || '-';
        rows[1].textContent = item.context || '-';
        rows[2].textContent = '-';
        rows[3].textContent = '对话 / 工具调用 / JSON 输出';
        rows[4].textContent = '-';
        rows[5].textContent = item.available ? '可用' : '不可用';
      }
    }
    const initial = items.find(function (item) { return item.is_default; }) || items[0];
    showDetail(initial);
    const modelTable = root.querySelector('.set2 .dtable');
    if (modelTable) {
      modelTable.querySelectorAll('tbody tr[data-model]').forEach(function (row) {
        row.addEventListener('click', function (event) {
          if (event.target.closest('button')) return;
          showDetail(items.find(function (item) { return item.id === row.dataset.model; }));
        });
      });
    }

    /* 模型测试下拉：选项来自实时列表 */
    const testSelect = root.querySelector('.settings-card .set-row select');
    if (testSelect && items.length) {
      testSelect.innerHTML = items.map(function (item) {
        return '<option>' + window.UI.esc(item.name) + '</option>';
      }).join('');
      testSelect.value = initial ? initial.name : items[0].name;
    }

    /* 参数滑块与输入 */
    inputByLabel(root, '默认温度 (Temperature)', parameters.temperature);
    inputByLabel(root, '默认最大输出长度', parameters.max_tokens);
    inputByLabel(root, 'Top P', parameters.top_p);
    toggleByLabel(root, '启用流式输出', parameters.stream);
    toggleByLabel(root, '启用工具调用', parameters.tools);
    toggleByLabel(root, '自动重试', parameters.retry);
    inputByLabel(root, '重试次数', parameters.retry_count);

    /* 接入配置 */
    inputByLabel(root, 'API 地址', connection.base_url);
    inputByLabel(root, '请求超时', connection.timeout_seconds);
    selectByLabel(root, '代理设置', connection.proxy === 'none' ? '不使用代理'
      : connection.proxy === 'system' ? '使用系统代理' : '自定义代理');
    const keyRow = rowByLabel(root, 'API Key');
    if (keyRow) {
      const input = keyRow.querySelector('input');
      if (input) {
        input.value = connection.api_key_configured
          ? '••••••••••••' + (connection.api_key_hint || '')
          : '';
        input.placeholder = connection.api_key_configured ? '' : '未配置（由运行环境注入）';
      }
    }
  }

  /* ---------------- 用户与权限 ---------------- */

  function roleTone(name) {
    if (name === '超级管理员') return 'purple';
    if (name === '工程师' || name === '分析师') return 'blue';
    if (name === '访客') return 'orange';
    return 'gray';
  }

  const ROLE_DESC = {
    '超级管理员': '拥有系统所有权限',
    '工程师': '可访问建模、分析等功能',
    'AI Agent': '按 Agent Scope 动态求交',
    '访客': '只读权限'
  };

  function applyUsers(root, users, roles) {
    const items = users.items || [];
    const table = root.querySelector('.set2 .dtable');
    if (table) {
      const body = table.querySelector('tbody');
      if (body) {
        body.innerHTML = items.map(function (user, index) {
          const state = user.locked ? 'red' : user.is_active ? 'green' : 'gray';
          const stateText = user.locked ? '锁定' : user.is_active ? '启用' : '禁用';
          return '<tr data-user="' + window.UI.esc(user.id) + '">' +
            '<td><input type="checkbox" style="accent-color:var(--brand)"></td>' +
            '<td>' + (index + 1) + '</td>' +
            '<td>' + window.UI.esc(user.username) + '</td>' +
            '<td>' + window.UI.esc(user.display_name || '-') + '</td>' +
            '<td>' + window.UI.esc(user.email || '-') + '</td>' +
            '<td><span class="tag ' + roleTone(user.role_label) + '">' +
            window.UI.esc(user.role_label || '-') + '</span></td>' +
            '<td><span class="tag ' + state + '"><span class="dot"></span>' + stateText + '</span></td>' +
            '<td class="mut">' + window.UI.esc((user.last_seen_at || '-').slice(0, 19).replace('T', ' ')) + '</td>' +
            '<td><span style="display:flex;gap:4px">' +
            '<button class="tbtn link" type="button" data-user-edit="' + window.UI.esc(user.id) + '">编辑</button>' +
            '<button class="tbtn icon" type="button" data-user-toggle="' + window.UI.esc(user.id) + '">' +
            '<span data-icon="' + (user.is_active ? 'lock' : 'check') + '"></span></button>' +
            '<button class="tbtn icon danger" type="button" data-user-delete="' + window.UI.esc(user.id) + '">' +
            '<span data-icon="trash"></span></button>' +
            '</span></td></tr>';
        }).join('');
        if (!items.length) {
          body.innerHTML = '<tr><td colspan="9" style="text-align:center;color:var(--text-3)">暂无用户</td></tr>';
        }
      }
      const total = root.querySelector('.set2 .pager .total');
      if (total) total.textContent = '共 ' + items.length + ' 条';
      window.Icons.mount(body);
    }

    const stats = root.querySelectorAll('.stat4 .sc-value');
    if (stats.length >= 4) {
      stats[0].textContent = String(items.length);
      stats[1].textContent = String(items.filter(function (u) { return u.is_active; }).length);
      stats[2].textContent = String(items.filter(function (u) { return !u.is_active; }).length);
      stats[3].textContent = String((roles.items || []).length);
    }
    const subs = root.querySelectorAll('.stat4 .sc-sub');
    if (subs.length >= 4) {
      subs[0].textContent = '租户内账号';
      subs[1].textContent = items.length ? (stats[1].textContent / items.length * 100).toFixed(1) + '%' : '0%';
      subs[2].textContent = items.length ? (stats[2].textContent / items.length * 100).toFixed(1) + '%' : '0%';
      subs[3].textContent = 'Core 默认角色';
    }

    /* 权限树：按选中角色的真实权限码分组（不再显示 mock 的 8/6/4/5/4） */
    const tree = root.querySelector('.tree');
    if (tree) {
      const groups = [
        ['系统管理', ['SYSTEM_ADMIN', 'TOOL_TEST', 'API_TEST']],
        ['模型管理', ['MODEL_READ', 'MODEL_WRITE', 'MODEL_DELETE']],
        ['任务管理', ['ANALYSIS_EXECUTE', 'DESIGN_EXECUTE', 'DESIGN_MODIFY']],
        ['工具接口', ['RESULT_READ']],
        ['数据管理', ['DOCUMENT_READ', 'DOCUMENT_WRITE']]
      ];
      function paintTree(role) {
        const granted = new Set((role && role.permissions) || []);
        tree.innerHTML = groups.map(function (group) {
          const total = group[1].length;
          const owned = group[1].filter(function (code) { return granted.has(code); }).length;
          return '<div class="node' + (owned ? ' on' : '') + '">' +
            '<span class="cb">' + (owned ? window.Icons.check : '') + '</span>' +
            '<span class="nm">' + group[0] + '</span>' +
            '<span class="cnt">(' + owned + '/' + total + ')</span></div>' +
            '<div class="child">' + group[1].map(function (code) {
              const on = granted.has(code);
              return '<div class="node' + (on ? ' on' : '') + '">' +
                '<span class="cb">' + (on ? window.Icons.check : '') + '</span>' +
                '<span class="nm">' + code + '</span></div>';
            }).join('') + '</div>';
        }).join('');
      }
      /* 默认展示**第一个用户**的角色（没有用户时退回权限最多的角色） */
      const firstRoleLabel = items.length ? items[0].role_label : '';
      const initialRole = (roles.items || []).find(function (role) {
        return role.label === firstRoleLabel;
      }) || (roles.items || []).slice().sort(function (a, b) {
        return (b.permissions || []).length - (a.permissions || []).length;
      })[0];
      paintTree(initialRole);
      const roleTable = root.querySelectorAll('.set2 .dtable')[1];
      if (roleTable) {
        roleTable.querySelectorAll('tbody tr[data-role]').forEach(function (row) {
          row.addEventListener('click', function (event) {
            if (event.target.closest('button')) return;
            paintTree((roles.items || []).find(function (item) {
              return item.id === row.dataset.role;
            }));
          });
        });
      }
    }

    /* 详情卡跟随选中用户（默认第一个） */
    const detail = root.querySelector('.set2 .settings-card:last-child');
    let detailUser = null;
    function showDetail(user) {
      if (!detail || !user) return;
      detailUser = user;
      root.dataset.selectedUser = user.id;
      const avatar = detail.querySelector('span[style*="border-radius:50%"]');
      if (avatar) avatar.textContent = (user.display_name || user.username || '?').slice(0, 1).toUpperCase();
      const name = detail.querySelector('b[style*="font-size:16px"]');
      if (name) name.textContent = user.username;
      const badge = detail.querySelector('.tag.green, .tag.red, .tag.gray');
      if (badge) {
        const on = user.is_active && !user.locked;
        badge.className = 'tag ' + (on ? 'green' : 'gray');
        badge.innerHTML = '<span class="dot"></span>' + (user.locked ? '锁定' : on ? '启用' : '禁用');
      }
      const roleTag = detail.querySelector('.tag.blue, .tag.purple, .tag.orange, .tag.gray');
      if (roleTag && roleTag !== badge) roleTag.textContent = user.role_label || '-';
      const mail = detail.querySelector('div[style*="font-size:14px"][style*="color:var(--text-2)"]');
      if (mail) mail.textContent = user.email || '-';
      const rows = detail.querySelectorAll('.kv-list .r dd');
      if (rows.length >= 9) {
        rows[0].textContent = user.username;
        rows[1].textContent = user.display_name || '-';
        rows[2].textContent = user.email || '-';
        rows[3].textContent = user.phone || '-';
        rows[4].textContent = user.role_label || '-';
        rows[5].textContent = user.locked ? '锁定' : user.is_active ? '启用' : '禁用';
        rows[6].textContent = (user.created_at || '-').slice(0, 19).replace('T', ' ');
        rows[7].textContent = (user.last_seen_at || '-').slice(0, 19).replace('T', ' ');
        rows[8].textContent = '-';
      }
    }
    showDetail(items[0]);
    if (table) {
      table.querySelectorAll('tbody tr[data-user]').forEach(function (row) {
        row.addEventListener('click', function (event) {
          if (event.target.closest('button,input')) return;
          showDetail(items.find(function (item) { return item.id === row.dataset.user; }));
        });
      });
    }

    /* 角色表 */
    const roleTable = root.querySelectorAll('.set2 .dtable')[1];
    if (roleTable && roles.items) {
      const body = roleTable.querySelector('tbody');
      if (body) {
        body.innerHTML = roles.items.map(function (role, index) {
          return '<tr data-role="' + window.UI.esc(role.id) + '">' +
            '<td>' + (index + 1) + '</td>' +
            '<td>' + window.UI.esc(role.label) + '</td>' +
            '<td class="mut">' + window.UI.esc(ROLE_DESC[role.label] || (role.permissions || []).join(' / ') || '无权限') + '</td>' +
            '<td>' + role.users + '</td>' +
            '<td><span style="display:flex;gap:4px">' +
            '<button class="tbtn link" type="button" data-role-edit="' + window.UI.esc(role.id) + '">编辑</button>' +
            '<button class="tbtn icon danger" type="button" data-role-delete="' + window.UI.esc(role.id) + '">' +
            '<span data-icon="trash"></span></button></span></td>' +
            '</tr>';
        }).join('');
      }
    }

  }

  /* ---------------- 安全设置 ---------------- */

  function applySecurity(root, settings, overview) {
    const security = settings.security || {};
    const login = security.login || {};
    const password = security.password || {};
    const access = security.access || {};
    const data = security.data || {};
    const audit = security.audit || {};

    /* 「用户与权限」页的安全策略卡（与安全设置页共享同一分区） */
    toggleByLabel(root, '启用登录验证', login.enabled);
    toggleByLabel(root, '密码登录策略', login.enabled);
    toggleByLabel(root, '强制密码复杂度', password.require_upper || password.require_digit);
    toggleByLabel(root, '最大失败次数策略', Number(login.max_attempts) > 0);
    toggleByLabel(root, '登录日志记录', audit.audit_enabled);
    inputByLabel(root, '密码最小长度', password.min_length);
    inputByLabel(root, '账号登录失败锁定', login.max_attempts);
    inputByLabel(root, '锁定时长（分钟）', login.lock_minutes);
    inputByLabel(root, '登录失败最大尝试次数', login.max_attempts);
    inputByLabel(root, '账号锁定时长', login.lock_minutes);
    toggleByLabel(root, '启用验证码', login.captcha);
    inputByLabel(root, '验证码有效期', login.captcha_minutes);
    toggleByLabel(root, '启用双因素认证（2FA）', login.two_factor);
    inputByLabel(root, '会话超时时间', login.session_hours);
    inputByLabel(root, '同一账号最大会话数', login.max_sessions);
    toggleByLabel(root, '强制首次登录修改密码', login.force_password_change);

    selectByLabel(root, '最小密码长度', password.min_length);
    toggleByLabel(root, '必须包含大写字母', password.require_upper);
    toggleByLabel(root, '必须包含小写字母', password.require_lower);
    toggleByLabel(root, '必须包含数字', password.require_digit);
    toggleByLabel(root, '必须包含特殊字符', password.require_special);
    inputByLabel(root, '密码有效期', password.expire_days);
    inputByLabel(root, '禁止使用历史密码', password.history);
    inputByLabel(root, '账号闲置自动禁用', password.idle_disable_days);

    toggleByLabel(root, 'IP 访问白名单', access.whitelist_enabled);
    toggleByLabel(root, 'IP 访问黑名单', access.blacklist_enabled);
    toggleByLabel(root, 'API 访问频率限制', access.rate_limit_enabled);
    inputByLabel(root, '每分钟最大请求数', access.rate_per_minute);
    inputByLabel(root, '单 IP 最大请求数', access.rate_per_ip);
    const areas = root.querySelectorAll('.s-textarea');
    if (areas[0]) {
      areas[0].value = access.whitelist || '';
      areas[0].placeholder = '每一行一个 IP 地址或网段';
      areas[0].disabled = !access.whitelist_enabled;
    }
    const blackInput = root.querySelector('.settings-card .s-input input[placeholder*="阻止"]');
    if (blackInput && access.blacklist) blackInput.value = access.blacklist;

    toggleByLabel(root, '启用数据加密存储', data.encrypt_at_rest);
    toggleByLabel(root, '启用传输加密（HTTPS）', data.https);
    toggleByLabel(root, '敏感信息脱敏', data.mask_sensitive);
    toggleByLabel(root, '定期备份配置数据', data.backup_config);
    inputByLabel(root, '备份保留天数', data.backup_keep_days);
    toggleByLabel(root, '导出数据脱敏', data.mask_export);

    toggleByLabel(root, '启用操作审计', audit.audit_enabled);
    toggleByLabel(root, '启用安全告警', audit.alerts_enabled);
    inputByLabel(root, '登录失败次数', audit.login_failure_threshold);
    inputByLabel(root, '异常请求次数', audit.abnormal_request_threshold);

    if (!overview) return;
    const stats = root.querySelectorAll('.stat4 .sc-value');
    if (stats.length >= 4) {
      stats[0].textContent = overview.locked_accounts ? '需关注' : '良好';
      stats[1].textContent = String(overview.failed_login_total || 0);
      stats[2].textContent = String(overview.locked_accounts || 0);
      stats[3].textContent = String(overview.audit_24h || 0);
    }
    /* 副标题改为可核对的事实（去掉 mock 的环比） */
    const subs = root.querySelectorAll('.stat4 .sc-sub');
    if (subs.length >= 4) {
      subs[0].textContent = overview.locked_accounts ? '存在锁定账号' : '未发现风险';
      subs[1].textContent = '累计失败次数（当前账号）';
      subs[2].textContent = '锁定账号数';
      subs[3].textContent = '近 24 小时审计条数';
    }
    const logTable = root.querySelectorAll('.dtable')[root.querySelectorAll('.dtable').length - 1];
    if (logTable && overview.events) {
      const body = logTable.querySelector('tbody');
      if (body) {
        body.innerHTML = overview.events.slice(0, 10).map(function (event) {
          const tone = event.result === 'FAILED' ? 'dl-bad'
            : event.result === 'DENIED' ? 'dl-bad' : 'dl-up';
          return '<tr>' +
            '<td class="mut">' + window.UI.esc((event.time || '').slice(0, 19).replace('T', ' ')) + '</td>' +
            '<td><span class="' + tone + '">' + window.UI.esc(event.action) + '</span></td>' +
            '<td>' + window.UI.esc(event.user || '-') + '</td>' +
            '<td class="mut">-</td>' +
            '<td class="mut">' + window.UI.esc(event.resource || '-') + '</td></tr>';
        }).join('') || '<tr><td colspan="5" style="text-align:center;color:var(--text-3)">暂无审计记录</td></tr>';
      }
    }
  }

  /* ---------------- 数据管理 ---------------- */

  function humanSize(bytes) {
    const value = Number(bytes || 0);
    if (value < 1024) return value + ' B';
    if (value < 1024 * 1024) return (value / 1024).toFixed(1) + ' KB';
    if (value < 1024 * 1024 * 1024) return (value / 1024 / 1024).toFixed(1) + ' MB';
    return (value / 1024 / 1024 / 1024).toFixed(2) + ' GB';
  }

  function applyData(root, settings, stats) {
    const data = settings.data || {};
    const backup = data.backup || {};
    const cleanup = data.cleanup || {};

    toggleByLabel(root, '自动备份', backup.auto);
    selectByLabel(root, '备份频率', backup.frequency === 'daily' ? '每天'
      : backup.frequency === 'weekly' ? '每周' : '每月');
    inputByLabel(root, '保留备份数量', backup.keep);
    const backupPath = rowByLabel(root, '备份存储路径');
    if (backupPath && backup.path) setInput(backupPath, backup.path);

    ['清理任务记录', '清理日志数据', '清理审计日志', '清理已删除用户数据', '清理临时文件']
      .forEach(function (label) {
        const key = label === '清理任务记录' ? 'tasks'
          : label === '清理日志数据' ? 'logs'
          : label === '清理审计日志' ? 'audit'
          : label === '清理已删除用户数据' ? 'deleted_users' : 'temp';
        const item = cleanup[key] || {};
        const row = rowByLabel(root, label);
        if (!row) return;
        const box = row.querySelector('.cbx-item');
        if (box) {
          box.classList.toggle('is-on', !!item.enabled);
          const mark = box.querySelector('.box');
          if (mark) mark.innerHTML = item.enabled ? window.Icons.check : '';
        }
        const input = row.querySelector('input');
        if (input && item.days) input.value = String(item.days);
      });

    if (!stats) return;
    const latest = (stats.backups || [])[0];
    const values = root.querySelectorAll('.stat4 .sc-value');
    if (values.length >= 4) {
      values[0].textContent = humanSize((stats.database || {}).size || 0);
      values[1].textContent = String(Object.keys(stats.tables || {}).length);
      values[2].textContent = latest
        ? String(latest.created_at || latest.id).slice(0, 16).replace('T', ' ')
        : '从未备份';
      values[3].textContent = latest && latest.complete ? '良好' : '待备份';
    }
    /* 自动备份开关与保留数量：按设置值显示，并标注已落库的真实含义 */
    toggleByLabel(root, '自动备份', (settings.data || {}).backup && settings.data.backup.auto);
    /* 统计卡副标题：去掉 mock 的环比，换成可核对的事实 */
    const subs = root.querySelectorAll('.stat4 .sc-sub');
    if (subs.length >= 4) {
      subs[0].textContent = '数据库文件占用';
      subs[1].textContent = 'Core 表（含空表）';
      subs[2].innerHTML = latest
        ? '<span class="tag green"><span class="dot"></span>备份成功</span>'
        : '<span class="tag gray">尚未备份</span>';
      subs[3].textContent = latest && latest.complete ? '最近备份完整' : '建议立即备份';
    }

    const tables = stats.tables || {};
    const secondRow = root.querySelectorAll('.set3')[1];
    if (!secondRow) return;

    /* 备份记录（第 1 张表） */
    const backupTable = secondRow.querySelectorAll('.dtable')[0];
    if (backupTable) {
      const body = backupTable.querySelector('tbody');
      if (body) {
        body.innerHTML = (stats.backups || []).slice(0, 10).map(function (item, index) {
          return '<tr data-backup="' + window.UI.esc(item.id) + '">' +
            '<td>' + (index + 1) + '</td>' +
            '<td class="mut">' + window.UI.esc(String(item.created_at || item.id).slice(0, 19).replace('T', ' ')) + '</td>' +
            '<td>' + (item.type === 'manual' ? '手动备份' : '自动备份') + '</td>' +
            '<td>' + humanSize(item.size) + '</td>' +
            '<td>' + (item.complete ? '<span class="tag green"><span class="dot"></span>成功</span>'
              : '<span class="tag gray">不完整</span>') + '</td>' +
            '<td><span class="ico-cell">' +
            '<button class="tbtn icon" type="button" title="下载" data-backup-open="' + window.UI.esc(item.id) + '"><span data-icon="download"></span></button>' +
            '<button class="tbtn icon" type="button" title="恢复" data-backup-restore="' + window.UI.esc(item.id) + '"><span data-icon="restore"></span></button>' +
            '<button class="tbtn icon danger" type="button" title="删除" data-backup-del="' + window.UI.esc(item.id) + '"><span data-icon="trash"></span></button>' +
            '</span></td></tr>';
        }).join('') || '<tr><td colspan="6" style="text-align:center;color:var(--text-3)">暂无备份</td></tr>';
        window.Icons.mount(body);
      }
      const total = secondRow.querySelector('.pager .total');
      if (total) total.textContent = '共 ' + (stats.backups || []).length + ' 条';
    }

    /* 数据库信息（第 2 张表）：真实表名与行数 */
    const dbTable = secondRow.querySelectorAll('.dtable')[1];
    if (dbTable) {
      const body = dbTable.querySelector('tbody');
      if (body) {
        body.innerHTML = Object.keys(tables).map(function (name) {
          return '<tr><td>' + window.UI.esc(name) + '</td><td>' + tables[name] +
            '</td><td class="mut">-</td><td class="mut">Core 表</td></tr>';
        }).join('');
      }
    }

    /* 存储使用情况：用真实的数据库 + 产物存储重建环图 */
    const donut = secondRow.querySelector('.donut-wrap');
    if (donut) {
      const databaseSize = (stats.database || {}).size || 0;
      const storageSize = (stats.storage || {}).size || 0;
      const total = databaseSize + storageSize;
      const segments = [
        { name: '数据库', size: databaseSize, color: '#2E90FA' },
        { name: '产物存储', size: storageSize, color: '#12B76A' }
      ];
      if (total > 0) {
        const radius = 60;
        const circumference = 2 * Math.PI * radius;
        let acc = 0;
        const circles = segments.map(function (segment) {
          const length = circumference * segment.size / total;
          const circle = '<circle cx="75" cy="75" r="' + radius + '" fill="none" stroke="' +
            segment.color + '" stroke-width="22" stroke-dasharray="' + length.toFixed(1) + ' ' +
            (circumference - length).toFixed(1) + '" stroke-dashoffset="' + (-acc).toFixed(1) + '"/>';
          acc += length;
          return circle;
        }).join('');
        donut.innerHTML =
          '<div class="donut"><svg viewBox="0 0 150 150">' +
          '<circle cx="75" cy="75" r="60" fill="none" stroke="#EEF2F7" stroke-width="22"/>' +
          circles + '</svg><div class="center"><b>' + humanSize(total) + '</b><span>总计</span></div></div>' +
          '<div class="legend2">' + segments.map(function (segment) {
            const pct = total ? (segment.size / total * 100).toFixed(1) : '0.0';
            return '<div class="li"><span class="dot" style="background:' + segment.color + '"></span>' +
              '<span class="nm">' + segment.name + '</span><span class="vl">' +
              humanSize(segment.size) + ' (' + pct + '%)</span></div>';
          }).join('') + '</div>';
      } else {
        donut.innerHTML = '<div class="donut"><div class="center"><b>0 B</b><span>总计</span></div></div>' +
          '<div class="legend2"><div class="li"><span class="nm" style="color:var(--text-3)">暂无存储占用</span></div></div>';
      }
    }
  }

  /* ---------------- 保存（防抖） ---------------- */

  function queueSave(section, values) {
    if (!window.Api || !window.Api.token()) return;
    pending = pending || {};
    pending[section] = Object.assign(pending[section] || {}, values);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(flush, 320);
  }

  async function flush() {
    /* 手动保存会取消已排队的防抖计时器，避免「保存两次 + 两次提示」 */
    clearTimeout(saveTimer);
    if (!pending) { toast('设置已保存'); return; }
    const batch = pending;
    pending = null;
    for (const section of Object.keys(batch)) {
      const result = await window.Api.saveSettings(section, batch[section]);
      if (!ok(result)) {
        fail(result, '设置保存失败');
        return;
      }
      if (state) state[section] = Object.assign(state[section] || {}, batch[section]);
      /* 界面设置保存后立即生效（不必等刷新） */
      if (section === 'interface' && state) applyPreferences(state.interface || {});
      if (section === 'notify' && state) {
        window.Toast.channels = (state.notify.channels || []).slice();
      }
    }
    toast('设置已保存');
  }

  /* ---------------- 控件事件绑定 ---------------- */

  function bind(root) {
    /* 开关：按标签找分区 */
    root.querySelectorAll('.switch').forEach(function (el) {
      if (el.dataset.bound) return;
      el.dataset.bound = '1';
      el.addEventListener('click', function () {
        const row = el.closest('.set-row, .feat-row');
        const label = row ? (row.querySelector('.k, .ft b') || {}).textContent : '';
        const on = el.classList.contains('is-on');
        const section = currentSection(root);
        const values = switchValue(section, (label || '').trim(), on);
        if (values) queueSave(values[0], values[1]);
      });
    });

    /* 输入框：change 时按标签写回（路径行优先用 `data-path-key`） */
    root.querySelectorAll('.set-row input, .path-row input').forEach(function (input) {
      if (input.dataset.bound) return;
      input.dataset.bound = '1';
      input.addEventListener('change', function () {
        if (input.dataset.pathKey) {
          queueSave('paths', { [input.dataset.pathKey]: input.value });
          return;
        }
        const row = input.closest('.set-row, .path-row');
        const label = row ? (row.querySelector('.k') || {}).textContent : '';
        const section = currentSection(root);
        const values = inputValue(section, (label || '').trim(), input.value);
        if (values) queueSave(values[0], values[1]);
      });
    });

    /* 滑块：拖动 / 点击 → 更新填充与数值，并保存 */
    root.querySelectorAll('.slider-row').forEach(function (row) {
      const slider = row.querySelector('.slider');
      if (!slider || slider.dataset.bound) return;
      slider.dataset.bound = '1';
      function applyAt(clientX) {
        const rect = slider.getBoundingClientRect();
        const pct = Math.max(0, Math.min(100, (clientX - rect.left) / rect.width * 100));
        const fill = slider.querySelector('.fill');
        const knob = slider.querySelector('.knob');
        if (fill) fill.style.width = pct + '%';
        if (knob) knob.style.left = pct + '%';
        const spans = row.querySelectorAll('.slider-scale span');
        const min = Number(spans[0] ? spans[0].textContent : 0);
        const max = Number(spans[1] ? spans[1].textContent : 1);
        const value = min + (max - min) * pct / 100;
        const rounded = Math.round(value * 100) / 100;
        const box = row.querySelector('.slider-val');
        if (box) box.textContent = String(rounded);
        const label = (row.querySelector('.lb') || {}).textContent || '';
        const mapped = inputValue('model', label.trim(), String(rounded));
        if (mapped) queueSave(mapped[0], mapped[1]);
      }
      slider.addEventListener('pointerdown', function (event) {
        slider.setPointerCapture(event.pointerId);
        applyAt(event.clientX);
        const move = function (e) { applyAt(e.clientX); };
        const up = function () {
          slider.removeEventListener('pointermove', move);
          slider.removeEventListener('pointerup', up);
          slider.removeEventListener('pointercancel', up);
        };
        slider.addEventListener('pointermove', move);
        slider.addEventListener('pointerup', up);
        slider.addEventListener('pointercancel', up);
      });
    });

    /* 文本域（IP 白名单） */
    root.querySelectorAll('.s-textarea').forEach(function (area) {
      if (area.dataset.bound) return;
      area.dataset.bound = '1';
      area.addEventListener('change', function () {
        if (currentSection(root) !== 'security') return;
        queueSave('security', { access: { whitelist: area.value } });
      });
    });

    /* 下拉 */
    root.querySelectorAll('.set-row select').forEach(function (select) {
      if (select.dataset.bound) return;
      select.dataset.bound = '1';
      select.addEventListener('change', function () {
        const row = select.closest('.set-row');
        const label = row ? (row.querySelector('.k') || {}).textContent : '';
        const section = currentSection(root);
        const values = selectValue(section, (label || '').trim(), select.value);
        if (values) queueSave(values[0], values[1]);
      });
    });

    /* 复选框（通知方式 / 导出范围） */
    root.querySelectorAll('.cbx-item').forEach(function (item) {
      if (item.dataset.bound) return;
      item.dataset.bound = '1';
      item.addEventListener('click', function () {
        const section = currentSection(root);
        const on = item.classList.contains('is-on');
        if (section === 'notify') {
          const channels = Array.prototype.map.call(
            root.querySelectorAll('.settings-card .cbx-item.is-on'),
            function (node) {
              const name = node.dataset.channel || '';
              return name.indexOf('页面') >= 0 ? 'page'
                : name.indexOf('浏览器') >= 0 ? 'browser' : 'email';
            }
          );
          queueSave('notify', { channels: channels });
        } else if (section === 'security') {
          const channels = Array.prototype.map.call(
            root.querySelectorAll('.cbx-item.is-on'),
            function (node) { return node.dataset.channel || ''; }
          );
          queueSave('security', { audit: { channels: channels } });
        } else if (section === 'data') {
          const scope = Array.prototype.map.call(
            root.querySelectorAll('.cbx-item.is-on'),
            function (node) { return node.dataset.channel || ''; }
          );
          queueSave('data', { export: { scope: scope } });
        }
      });
    });

    /* 主题卡片 */
    root.querySelectorAll('.theme-card').forEach(function (card) {
      if (card.dataset.bound) return;
      card.dataset.bound = '1';
      card.addEventListener('click', function () {
        queueSave('interface', { theme: card.dataset.theme });
        toast('主题已切换为：' + card.querySelector('.theme-label').textContent.trim());
      });
    });
  }

  function formatUptime(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days) return days + ' 天 ' + hours + ' 小时 ' + minutes + ' 分钟';
    if (hours) return hours + ' 小时 ' + minutes + ' 分钟';
    if (minutes) return minutes + ' 分钟';
    return '刚刚启动';
  }

  function currentSection(root) {
    const active = root.querySelector('.settings-tab.is-active');
    const id = active ? active.dataset.stab : 'basic';
    /* 标签 id 与设置分区名不完全一致（basic → basic，users → users，
       model → model，security → security，data → data，service → service） */
    return id || 'basic';
  }

  /* 标签 → (section, {key: value}) 映射；未登记返回 null（不保存） */
  function switchValue(section, label, on) {
    const basic = {
      '自动清理过期任务': ['behavior', 'auto_cleanup'],
      '启动时自动检查更新': ['behavior', 'check_update_on_start'],
      '最小化到系统托盘': ['behavior', 'minimize_to_tray'],
      '显示工具提示': ['interface', 'show_tooltips'],
      '显示动画效果': ['interface', 'show_animations'],
      '紧凑侧边栏': ['interface', 'compact_sidebar'],
      '任务完成通知': ['notify', 'task_done'],
      '任务失败通知': ['notify', 'task_failed'],
      '系统异常通知': ['notify', 'system_error']
    };
    const service = {
      '开启 CORS': ['service', 'cors_enabled']
    };
    const features = {
      '启用 MCP 协议服务': 'mcp',
      '启用 REST API 接口': 'rest',
      '启用 Web 管理界面': 'web',
      '启用任务队列': 'queue',
      '启用结果缓存': 'cache',
      '启用详细日志': 'verbose_log'
    };
    const security = {
      '启用登录验证': ['login', 'enabled'],
      '密码登录策略': ['login', 'enabled'],
      '强制密码复杂度': ['password', 'require_upper'],
      '最大失败次数策略': ['login', 'enabled'],
      '登录日志记录': ['audit', 'audit_enabled'],
      '启用验证码': ['login', 'captcha'],
      '启用双因素认证（2FA）': ['login', 'two_factor'],
      '强制首次登录修改密码': ['login', 'force_password_change'],
      '必须包含大写字母': ['password', 'require_upper'],
      '必须包含小写字母': ['password', 'require_lower'],
      '必须包含数字': ['password', 'require_digit'],
      '必须包含特殊字符': ['password', 'require_special'],
      'IP 访问白名单': ['access', 'whitelist_enabled'],
      'IP 访问黑名单': ['access', 'blacklist_enabled'],
      'API 访问频率限制': ['access', 'rate_limit_enabled'],
      '启用数据加密存储': ['data', 'encrypt_at_rest'],
      '启用传输加密（HTTPS）': ['data', 'https'],
      '敏感信息脱敏': ['data', 'mask_sensitive'],
      '定期备份配置数据': ['data', 'backup_config'],
      '导出数据脱敏': ['data', 'mask_export'],
      '启用操作审计': ['audit', 'audit_enabled'],
      '启用安全告警': ['audit', 'alerts_enabled']
    };
    const models = {
      '启用流式输出': ['parameters', 'stream'],
      '启用工具调用': ['parameters', 'tools'],
      '自动重试': ['parameters', 'retry']
    };
    const data = {
      '自动备份': ['backup', 'auto']
    };

    if (section === 'basic') {
      const hit = basic[label];
      return hit ? [hit[0], { [hit[1]]: on }] : null;
    }
    if (section === 'service') {
      if (features[label]) return ['service', { features: { [features[label]]: on } }];
      const hit = service[label];
      return hit ? [hit[0], { [hit[1]]: on }] : null;
    }
    if (section === 'security') {
      const hit = security[label];
      return hit ? ['security', { [hit[0]]: { [hit[1]]: on } }] : null;
    }
    if (section === 'model') {
      const hit = models[label];
      return hit ? ['models', { [hit[0]]: { [hit[1]]: on } }] : null;
    }
    if (section === 'data') {
      const hit = data[label];
      return hit ? ['data', { [hit[0]]: { [hit[1]]: on } }] : null;
    }
    return null;
  }

  function inputValue(section, label, raw) {
    const numeric = Number(raw);
    const value = raw !== '' && !Number.isNaN(numeric) && /^\d+(\.\d+)?$/.test(raw) ? numeric : raw;
    const basic = {
      '任务超时时间': ['behavior', 'task_timeout_minutes'],
      '日志保留天数': ['behavior', 'log_retention_days'],
      'MIDAS 安装路径': ['paths', 'midas_home'],
      '临时文件目录': ['paths', 'temp_dir'],
      '项目文件默认目录': ['paths', 'project_dir'],
      '模型文件默认目录': ['paths', 'model_dir'],
      '结果文件默认目录': ['paths', 'result_dir']
    };
    const service = {
      '服务端口': ['port'],
      '管理端口': ['management_port'],
      '最大连接数': ['max_connections']
    };
    const performance = {
      '工作线程数': 'workers',
      '任务队列大小': 'queue_size',
      '任务超时时间': 'task_timeout_seconds',
      '结果缓存时间': 'cache_seconds'
    };
    const security = {
      '登录失败最大尝试次数': ['login', 'max_attempts'],
      '密码最小长度': ['password', 'min_length'],
      '账号登录失败锁定': ['login', 'max_attempts'],
      '锁定时长（分钟）': ['login', 'lock_minutes'],
      '账号锁定时长': ['login', 'lock_minutes'],
      '验证码有效期': ['login', 'captcha_minutes'],
      '会话超时时间': ['login', 'session_hours'],
      '同一账号最大会话数': ['login', 'max_sessions'],
      '密码有效期': ['password', 'expire_days'],
      '禁止使用历史密码': ['password', 'history'],
      '账号闲置自动禁用': ['password', 'idle_disable_days'],
      '每分钟最大请求数': ['access', 'rate_per_minute'],
      '单 IP 最大请求数': ['access', 'rate_per_ip'],
      '备份保留天数': ['data', 'backup_keep_days'],
      '登录失败次数': ['audit', 'login_failure_threshold'],
      '异常请求次数': ['audit', 'abnormal_request_threshold']
    };
    const models = {
      '默认温度 (Temperature)': ['parameters', 'temperature'],
      '默认最大输出长度': ['parameters', 'max_tokens'],
      'Top P': ['parameters', 'top_p'],
      '重试次数': ['parameters', 'retry_count'],
      'API 地址': ['connection', 'base_url'],
      '请求超时': ['connection', 'timeout_seconds']
    };
    const data = {
      '保留备份数量': ['backup', 'keep']
    };

    if (section === 'basic') {
      const hit = basic[label];
      return hit ? [hit[0], { [hit[1]]: value }] : null;
    }
    if (section === 'service') {
      if (service[label]) return ['service', { [service[label][0]]: value }];
      if (performance[label]) return ['service', { performance: { [performance[label]]: value } }];
      return null;
    }
    if (section === 'security') {
      const hit = security[label];
      return hit ? ['security', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    if (section === 'model') {
      const hit = models[label];
      return hit ? ['models', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    if (section === 'data') {
      const hit = data[label];
      return hit ? ['data', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    return null;
  }

  function selectValue(section, label, raw) {
    const basic = {
      '默认软件': ['behavior', 'default_software'],
      '默认版本': ['behavior', 'default_version'],
      '语言设置': ['interface', 'language'],
      '页面显示密度': ['interface', 'density'],
      '每页显示条数': ['interface', 'page_size']
    };
    const service = { '监听地址': ['listen_host'] };
    const security = { '最小密码长度': ['password', 'min_length'] };
    const models = { '代理设置': ['connection', 'proxy'] };
    const data = { '备份频率': ['backup', 'frequency'] };

    let value = raw;
    if (label === '语言设置') value = raw === '简体中文' ? 'zh-CN' : raw === 'English' ? 'en-US' : 'zh-TW';
    if (label === '页面显示密度') value = raw === '舒适' ? 'comfortable' : raw === '紧凑' ? 'compact' : 'standard';
    if (label === '代理设置') value = raw === '不使用代理' ? 'none' : raw === '使用系统代理' ? 'system' : 'custom';
    if (label === '备份频率') value = raw === '每天' ? 'daily' : raw === '每周' ? 'weekly' : 'monthly';
    if (label === '每页显示条数' || label === '最小密码长度') value = Number(raw);

    if (section === 'basic') {
      const hit = basic[label];
      return hit ? [hit[0], { [hit[1]]: value }] : null;
    }
    if (section === 'service') {
      const hit = service[label];
      return hit ? ['service', { [hit[0]]: value }] : null;
    }
    if (section === 'security') {
      const hit = security[label];
      return hit ? ['security', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    if (section === 'model') {
      const hit = models[label];
      return hit ? ['models', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    if (section === 'data') {
      const hit = data[label];
      return hit ? ['data', { [hit[0]]: { [hit[1]]: value } }] : null;
    }
    return null;
  }

  /* ---------------- 动作（保存 / 测试 / 备份 …） ---------------- */

  let actionsBound = false;

  function bindActions(root) {
    /* 事件委托挂在常驻的 `#view` 上：每次切页都会重新 mount，
       故只允许绑定一次（否则一次点击会触发 N 次保存）。 */
    if (actionsBound) return;
    actionsBound = true;
    currentRoot = root;
    root.addEventListener('click', async function (event) {
      const target = event.target.closest('[data-act],[data-act2],[data-op2]');
      if (!target) return;
      const action = target.dataset.act || target.dataset.act2 || target.dataset.op2;
      if (!action) return;
      if (!window.Api || !window.Api.token()) { toast('未连接后端，操作不可用'); return; }

      /* ---------- 保存 / 还原 ---------- */
      if (/^保存/.test(action)) {
        event.preventDefault();
        /* 先把当前页所有控件的值同步进待保存队列（用户可能没触发 blur） */
        root.querySelectorAll('.set-row input, .path-row input, .set-row select, .s-textarea')
          .forEach(function (input) {
            input.dispatchEvent(new Event('change'));
          });
        await flush();
        return;
      }
      if (action === '取消') {
        await reload(root);
        toast('已还原为已保存的设置');
        return;
      }

      /* ---------- 通知 ---------- */
      if (action === '发送测试邮件') {
        const input = root.querySelector('.s-input input[placeholder*="邮箱"]');
        const result = await window.Api.testNotify(input ? input.value : '');
        if (!ok(result)) { fail(result, '测试失败'); return; }
        const data = result.data || {};
        if (data.delivered) toast('测试邮件已发送到 ' + data.email);
        else if (data.reason === 'invalid_email') toast('邮箱格式不正确');
        else if (data.reason === 'smtp_not_configured') toast('邮箱有效；SMTP 未配置，未实际发送');
        else toast('发送失败：' + (data.reason || '未知原因'));
        return;
      }

      /* ---------- 关于 / 更新 ---------- */
      if (action === '检查更新') {
        const result = await window.Api.checkUpdate();
        toast(ok(result) ? (result.data.update_available ? '发现新版本 ' + result.data.latest : '当前已是最新版本 ' + result.data.current) : '检查更新失败');
        return;
      }
      if (action === '更新日志') {
        window.UI.dialog({
          title: '更新日志',
          body: '<p><b>当前版本 ' + window.UI.esc((state.system || {}).version || '-') + '</b></p>' +
            '<p style="color:var(--text-3)">本部署未配置更新源，无法列出历史版本变更。' +
            '版本信息以「关于系统」页的构建时间为准。</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }
      if (action === '使用文档' || action === '常见问题' || action === '技术支持') {
        window.UI.dialog({
          title: action,
          body: '<p>文档随源码仓库提供：</p>' +
            '<p style="color:var(--text-3)">README.md · docs/10_Web_UI接入与同源部署_v1.0.md</p>' +
            '<p style="color:var(--text-3)">技术支持请联系部署方管理员。</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }
      if (action === '查看完整协议') {
        window.UI.dialog({
          title: 'MIT License',
          body: '<p style="font-size:13px;line-height:1.8">Copyright (c) 2026 StructAI<br><br>' +
            'Permission is hereby granted, free of charge, to any person obtaining a copy ' +
            'of this software and associated documentation files (the "Software"), to deal ' +
            'in the Software without restriction, including without limitation the rights ' +
            'to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies ' +
            'of the Software, and to permit persons to whom the Software is furnished to do so, ' +
            'subject to the following conditions:<br><br>' +
            'The above copyright notice and this permission notice shall be included in all ' +
            'copies or substantial portions of the Software.<br><br>' +
            'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }

      /* ---------- 服务控制 ---------- */
      if (action === '停止服务' || action === '重启服务') {
        const verb = action === '停止服务' ? '停止' : '重启';
        const confirmed = await window.UI.dialog({
          title: verb + '服务',
          body: '<p>确定要' + verb + ' MCP 服务吗？</p>' +
            '<p style="color:var(--text-3)">' + (action === '停止服务'
              ? '停止后 Web 界面与 MCP 端点都会不可用，需要重新启动进程。'
              : '重启会短暂中断正在执行的请求。') + '</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: verb, value: 'go', danger: action === '停止服务' }
          ]
        }).result;
        if (confirmed !== 'go') return;
        const result = await window.Api.serviceControl(action === '停止服务' ? 'stop' : 'restart');
        if (!ok(result)) { fail(result, '服务控制失败'); return; }
        toast(result.data.applied ? action + '：已提交' : action + '：当前部署未接入进程控制');
        return;
      }
      if (action === '查看日志') {
        const result = await window.Api.logs('', '');
        if (!ok(result)) { fail(result, '日志不可读'); return; }
        const items = result.data.items || [];
        window.UI.dialog({
          title: '运行日志',
          body: '<div class="ui-browser"><div class="ui-browser-head"><span class="ui-browser-path">' +
            window.UI.esc(result.data.path || '') + '</span></div>' +
            '<div class="ui-browser-list" style="font-family:var(--font-num);font-size:12px">' +
            (items.length ? items.map(function (item) {
              return '<div class="ui-browser-item" style="cursor:default">' +
                window.UI.esc(item.line) + '</div>';
            }).join('') : '<div class="ui-browser-empty">暂无日志（未启用文件日志）</div>') +
            '</div></div>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }
      if (action === '测试连接') {
        const result = await window.Api.get('/api/status');
        toast(ok(result) ? '连接正常：' + ((result.data.service || {}).version || '') : '无法连接核心服务');
        return;
      }

      /* ---------- 数据管理 ---------- */
      if (action === '立即备份' || action === '备份系统配置') {
        toast('正在备份…');
        const result = await window.Api.backupNow();
        if (!ok(result)) { fail(result, '备份失败'); return; }
        toast('备份完成：' + result.data.backup_id);
        await reload(root);
        return;
      }
      if (action === '从备份恢复') {
        const backups = (state.stats && state.stats.backups) || [];
        if (!backups.length) { toast('没有可用的备份'); return; }
        const choice = await window.UI.form({
          title: '从备份恢复',
          submitLabel: '恢复',
          note: '恢复前会自动生成一份 pre-restore 备份；恢复完成后需要重启服务。',
          fields: [{
            key: 'backup_id', label: '选择备份', type: 'select', wide: true,
            value: backups[0].id,
            options: backups.map(function (item) {
              return {
                value: item.id,
                label: item.id + '（' + String(item.created_at || '').slice(0, 19).replace('T', ' ') +
                  '，' + humanSize(item.size) + '）'
              };
            })
          }]
        });
        if (!choice) return;
        const result = await window.Api.restoreBackup(choice.backup_id);
        if (!ok(result)) { fail(result, '恢复失败'); return; }
        toast('已从 ' + result.data.backup_id + ' 恢复；请重启服务生效');
        return;
      }
      if (action === '备份设置') {
        const result = await window.Api.exportData();
        if (!ok(result)) { fail(result, '导出失败'); return; }
        downloadJson('structai-settings-' + new Date().toISOString().slice(0, 10) + '.json', result.data);
        toast('设置已导出');
        return;
      }
      if (action === '导入数据') {
        const file = await pickJsonFile();
        if (!file) return;
        const result = await window.Api.importData(file);
        if (!ok(result)) { fail(result, '导入失败'); return; }
        toast('已导入分区：' + (result.data.imported || []).join(' / '));
        await reload(root);
        return;
      }
      if (action === '导出数据') {
        const result = await window.Api.exportData();
        if (!ok(result)) { fail(result, '导出失败'); return; }
        downloadJson('structai-settings-export.json', result.data);
        return;
      }
      if (action === '立即清理') {
        const categories = readCleanup(root);
        const result = await window.Api.cleanup(categories);
        if (!ok(result)) { fail(result, '清理失败'); return; }
        const removed = result.data.removed || {};
        toast('清理完成：' + Object.keys(removed).map(function (key) {
          return key + ' ' + removed[key];
        }).join(' · '));
        await reload(root);
        return;
      }
      if (action === '重置为默认') {
        const section = currentSection(root);
        const confirmed = await window.UI.dialog({
          title: '重置为默认',
          body: '<p>把「' + section + '」相关设置恢复为默认值？</p>' +
            '<p style="color:var(--text-3)">用户、角色与数据不会被删除。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '重置', value: 'reset', danger: true }
          ]
        }).result;
        if (confirmed !== 'reset') return;
        const sectionMap = { basic: 'behavior', service: 'service', model: 'models',
          users: 'security', security: 'security', data: 'data', about: '' };
        const target = sectionMap[section] || '';
        const result = await window.Api.resetSettings(target);
        if (!ok(result)) { fail(result, '重置失败'); return; }
        state = result.data;
        await reload(root);
        toast('已恢复默认设置');
        return;
      }
      if (action === '重置所有设置') {
        const confirmed = await window.UI.dialog({
          title: '重置所有设置',
          body: '<p>将所有设置恢复为默认值？</p><p style="color:var(--text-3)">用户、角色与数据不会被删除。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '重置', value: 'reset', danger: true }
          ]
        }).result;
        if (confirmed !== 'reset') return;
        const result = await window.Api.resetSettings('');
        if (!ok(result)) { fail(result, '重置失败'); return; }
        state = result.data;
        await reload(root);
        toast('已恢复默认设置');
        return;
      }
      if (action === '清空所有数据') {
        const confirmed = await window.UI.dialog({
          title: '清空所有数据',
          body: '<p><strong style="color:var(--red)">此操作不可恢复。</strong></p>' +
            '<p>将删除任务、文档、模型、项目、会话与幂等记录；管理员、角色与软件注册表保留，审计链不删除。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '确认清空', value: 'purge', danger: true }
          ]
        }).result;
        if (confirmed !== 'purge') return;
        const result = await window.Api.purgeData();
        if (!ok(result)) { fail(result, '清空失败'); return; }
        const removed = result.data.removed || {};
        toast('已清空：' + Object.keys(removed).filter(function (key) {
          return removed[key];
        }).map(function (key) { return key + ' ' + removed[key]; }).join(' · '));
        await reload(root);
        return;
      }

      /* ---------- 用户 / 角色 ---------- */
      if (action === '新建用户') {
        const values = await window.UI.form({
          title: '新建用户',
          submitLabel: '创建',
          note: '口令按「安全设置 · 密码策略」校验；只保存 Argon2id 哈希。',
          fields: [
            { key: 'username', label: '用户名', required: true },
            { key: 'password', label: '初始密码', type: 'password', required: true },
            { key: 'display_name', label: '姓名' },
            { key: 'email', label: '邮箱', type: 'email' },
            { key: 'phone', label: '手机号' },
            { key: 'role', label: '角色', type: 'select',
              value: (((state.roles || {}).items || [])[0] || {}).name,
              options: ((state.roles || {}).items || []).map(function (role) {
                return { value: role.name, label: role.label };
              }) },
            { key: 'note', label: '备注', type: 'textarea', wide: true, rows: 2 }
          ]
        });
        if (!values) return;
        values.roles = values.role ? [values.role] : [];
        delete values.role;
        const result = await window.Api.createUser(values);
        if (!ok(result)) { fail(result, '新建失败'); return; }
        toast('用户已创建：' + values.username);
        await reload(root);
        return;
      }
      if (action === '新建角色') {
        const values = await window.UI.form({
          title: '新建角色',
          submitLabel: '创建',
          fields: [
            { key: 'name', label: '角色标识', required: true, placeholder: '例如：analyst',
              hint: '英文标识，用作权限判定' },
            { key: 'permissions', label: '权限码（逗号分隔）', wide: true,
              placeholder: ((state.roles || {}).permissions || []).join(', '),
              hint: '可用：' + ((state.roles || {}).permissions || []).join(', ') }
          ],
          validate: function (values) {
            const unknown = (values.permissions || '').split(',').map(function (x) {
              return x.trim();
            }).filter(Boolean).filter(function (code) {
              return ((state.roles || {}).permissions || []).indexOf(code) < 0;
            });
            return unknown.length ? '未知权限码：' + unknown.join(', ') : null;
          }
        });
        if (!values) return;
        const result = await window.Api.createRole({
          name: values.name,
          permissions: (values.permissions || '').split(',').map(function (x) {
            return x.trim();
          }).filter(Boolean)
        });
        if (!ok(result)) { fail(result, '新建失败'); return; }
        toast('角色已创建');
        await reload(root);
        return;
      }
      if (action === '刷新' || action === '刷新列表') {
        await reload(root);
        toast('已刷新');
        return;
      }

      /* ---------- 服务配置：环境变量 / 高级配置 ---------- */
      if (action === '添加变量' || action === '编辑变量') {
        const rows = (state.service && state.service.env) || [];
        const name = action === '编辑变量'
          ? (target.dataset.envEdit || '') : '';
        let index = -1;
        if (name) {
          index = rows.findIndex(function (item) { return item.name === name; });
          if (index < 0) { toast('未找到变量：' + name); return; }
        }
        const current = index >= 0 ? rows[index] : { name: '', value: '', description: '' };
        const values = await window.UI.form({
          title: action === '添加变量' ? '添加环境变量' : '编辑环境变量',
          fields: [
            { key: 'name', label: '变量名', value: current.name, required: true,
              placeholder: '例如：LOG_LEVEL' },
            { key: 'value', label: '变量值', value: current.value },
            { key: 'description', label: '说明', value: current.description, wide: true }
          ]
        });
        if (!values) return;
        const next = rows.slice();
        if (index >= 0) next[index] = values;
        else next.push(values);
        const result = await window.Api.saveSettings('service', { env: next });
        if (!ok(result)) { fail(result, '保存失败'); return; }
        state.service = result.data.values;
        toast('环境变量已保存');
        await reload(root);
        return;
      }
      if (action === '删除变量') {
        const rows = (state.service && state.service.env) || [];
        const name = target.dataset.envDelete || '';
        if (!name) return;
        const next = rows.filter(function (item) { return item.name !== name; });
        if (next.length === rows.length) { toast('未找到变量：' + name); return; }
        const result = await window.Api.saveSettings('service', { env: next });
        if (!ok(result)) { fail(result, '删除失败'); return; }
        state.service = result.data.values;
        toast('已删除变量：' + name);
        await reload(root);
        return;
      }
      if (action === 'SSL/TLS 配置' || action === '反向代理配置' || action === 'API 限流配置'
          || action === '健康检查' || action === '集群部署') {
        const messages = {
          'SSL/TLS 配置': 'HTTPS 由部署层（反向代理 / 证书）提供；本进程只监听 HTTP。可在「安全设置」中记录开关状态。',
          '反向代理配置': '反向代理（Nginx / Apache）在部署层配置；跨域来源请填写「允许的来源」。',
          'API 限流配置': '限流参数在「安全设置 · 访问控制」中配置，保存后立即生效。',
          '健康检查': '健康探针：/livez（存活）、/readyz（就绪）、/health（完整报告）。',
          '集群部署': '当前部署为单进程；多节点需要共享数据库与外部任务队列。'
        };
        window.UI.dialog({
          title: action,
          body: '<p>' + window.UI.esc(messages[action]) + '</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }

      toast('执行：' + action);
    });

    /* 用户 / 角色 / 模型 / 备份行内动作 */
    root.addEventListener('click', async function (event) {
      if (!window.Api || !window.Api.token()) return;
      const editModelButton = event.target.closest('[data-model-edit]');
      if (editModelButton) {
        const id = editModelButton.dataset.modelEdit;
        const items = (state && state.models && state.models.items) || [];
        const current = items.find(function (item) { return item.id === id; });
        if (!current) return;
        const values = await window.UI.form({
          title: '编辑模型：' + current.name,
          fields: [
            { key: 'name', label: '模型名称', value: current.name, required: true },
            { key: 'provider', label: '提供商', value: current.provider },
            { key: 'kind', label: '模型类型', value: current.kind },
            { key: 'context', label: '上下文长度', value: current.context },
            { key: 'available', label: '可用', type: 'switch', value: !!current.available },
            { key: 'description', label: '描述', type: 'textarea', wide: true, rows: 3,
              value: current.description }
          ]
        });
        if (!values) return;
        const next = items.map(function (item) {
          return item.id === current.id ? Object.assign({}, item, values) : item;
        });
        const result = await window.Api.saveModels({ items: next });
        if (!ok(result)) { fail(result, '保存失败'); return; }
        toast('模型已更新');
        await reload(root);
        return;
      }
      const keyToggle = event.target.closest('[data-key-toggle]');
      if (keyToggle) {
        toast('API Key 由运行环境注入（STRUCTAI_SECRET_*），界面只显示是否已配置');
        return;
      }
      const pickBackup = event.target.closest('[data-pick-backup]');
      if (pickBackup) {
        const row = pickBackup.closest('.set-row');
        const input = row ? row.querySelector('input') : null;
        const chosen = await pickDirectory(input ? input.value : '');
        if (chosen && input) {
          input.value = chosen;
          input.dispatchEvent(new Event('change'));
        }
        return;
      }
      const exportUsers = event.target.closest('[data-export-users]');
      if (exportUsers) {
        const users = (state && state.users && state.users.items) || [];
        downloadJson('structai-users-' + new Date().toISOString().slice(0, 10) + '.json', {
          exported_at: new Date().toISOString(),
          items: users.map(function (user) {
            return {
              username: user.username, display_name: user.display_name, email: user.email,
              phone: user.phone, role: user.role_label, is_active: user.is_active,
              locked: user.locked, created_at: user.created_at
            };
          })
        });
        toast('用户列表已导出');
        return;
      }
      const testModel = event.target.closest('[data-model-test]');
      if (testModel) {
        const result = await window.Api.testModel(testModel.dataset.modelTest);
        if (!ok(result)) { fail(result, '测试失败'); return; }
        toast(result.data.reachable ? '模型配置完整' : '模型不可用：' + (result.data.reason || '未配置'));
        return;
      }
      const makeDefault = event.target.closest('[data-model-default]');
      if (makeDefault) {
        const id = makeDefault.dataset.modelDefault;
        const current = (state && state.models && state.models.items) || [];
        const items = current.map(function (item) {
          return Object.assign({}, item, { is_default: item.id === id });
        });
        const result = await window.Api.saveModels({ items: items, default: id });
        if (!ok(result)) { fail(result, '保存失败'); return; }
        state.models = result.data;
        await reload(root);
        toast('已设为默认模型');
        return;
      }
      const editUserButton = event.target.closest('[data-user-edit]');
      if (editUserButton) {
        const id = editUserButton.dataset.userEdit;
        const items = (state && state.users && state.users.items) || [];
        const user = items.find(function (item) { return item.id === id; });
        if (!user) return;
        await editUser(root, user);
        return;
      }
      const toggleUser = event.target.closest('[data-user-toggle]');
      if (toggleUser) {
        const id = toggleUser.dataset.userToggle;
        const items = (state && state.users && state.users.items) || [];
        const user = items.find(function (item) { return item.id === id; });
        if (!user) return;
        const result = await window.Api.updateUser(id, { is_active: !user.is_active });
        if (!ok(result)) { fail(result, '操作失败'); return; }
        await reload(root);
        toast(user.is_active ? '用户已禁用' : '用户已启用');
        return;
      }
      const deleteUser = event.target.closest('[data-user-delete]');
      if (deleteUser) {
        const id = deleteUser.dataset.userDelete;
        const items = (state && state.users && state.users.items) || [];
        const user = items.find(function (item) { return item.id === id; });
        if (!user) return;
        const confirmed = await window.UI.dialog({
          title: '删除用户',
          body: '<p>确定删除用户 <b>' + window.UI.esc(user.username) + '</b>？</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '删除', value: 'delete', danger: true }
          ]
        }).result;
        if (confirmed !== 'delete') return;
        const result = await window.Api.deleteUser(id);
        if (!ok(result)) { fail(result, '删除失败'); return; }
        await reload(root);
        toast('用户已删除');
        return;
      }
      const editRole = event.target.closest('[data-role-edit]');
      if (editRole) {
        const id = editRole.dataset.roleEdit;
        const roles = (state && state.roles) || { items: [] };
        const role = (roles.items || []).find(function (item) { return item.id === id; });
        if (!role) return;
        const codes = roles.permissions || [];
        const values = await window.UI.form({
          title: '编辑角色：' + role.label,
          fields: [{
            key: 'permissions', label: '权限码（逗号分隔）', type: 'textarea', wide: true, rows: 6,
            value: (role.permissions || []).join(', '),
            hint: '可用：' + codes.join(', ')
          }],
          validate: function (input) {
            const unknown = (input.permissions || '').split(',').map(function (x) {
              return x.trim();
            }).filter(Boolean).filter(function (code) { return codes.indexOf(code) < 0; });
            return unknown.length ? '未知权限码：' + unknown.join(', ') : null;
          }
        });
        if (!values) return;
        const permissions = (values.permissions || '').split(',').map(function (x) {
          return x.trim();
        }).filter(Boolean);
        const result = await window.Api.updateRole(id, { permissions: permissions });
        if (!ok(result)) { fail(result, '保存失败'); return; }
        await reload(root);
        toast('角色权限已更新');
        return;
      }
      const deleteRole = event.target.closest('[data-role-delete]');
      if (deleteRole) {
        const id = deleteRole.dataset.roleDelete;
        const confirmed = await window.UI.dialog({
          title: '删除角色',
          body: '<p>确定删除该角色？仍被用户引用的角色不能删除。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '删除', value: 'delete', danger: true }
          ]
        }).result;
        if (confirmed !== 'delete') return;
        const result = await window.Api.deleteRole(id);
        if (!ok(result)) { fail(result, '删除失败'); return; }
        await reload(root);
        toast('角色已删除');
        return;
      }
      const openBackup = event.target.closest('[data-backup-open]');
      if (openBackup) {
        const id = openBackup.dataset.backupOpen;
        const response = await fetch('/api/data/backups/' + encodeURIComponent(id) + '/download', {
          headers: { Authorization: 'Bearer ' + window.Api.token() }
        });
        if (!response.ok) { toast('下载失败'); return; }
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = id + '.zip';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
        return;
      }
      const restoreBackup = event.target.closest('[data-backup-restore]');
      if (restoreBackup) {
        const id = restoreBackup.dataset.backupRestore;
        const confirmed = await window.UI.dialog({
          title: '从备份恢复',
          body: '<p>从 <b>' + window.UI.esc(id) + '</b> 恢复？恢复前会自动生成一份 pre-restore 备份。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '恢复', value: 'restore', danger: true }
          ]
        }).result;
        if (confirmed !== 'restore') return;
        const result = await window.Api.restoreBackup(id);
        if (!ok(result)) { fail(result, '恢复失败'); return; }
        toast('恢复完成；请重启服务生效');
        return;
      }
      const delBackup = event.target.closest('[data-backup-del]');
      if (delBackup) {
        const confirmed = await window.UI.dialog({
          title: '删除备份',
          body: '<p>确定删除该备份目录？</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '删除', value: 'delete', danger: true }
          ]
        }).result;
        if (confirmed !== 'delete') return;
        const result = await window.Api.deleteBackup(delBackup.dataset.backupDel);
        if (!ok(result)) { fail(result, '删除失败'); return; }
        await reload(root);
        toast('备份已删除');
      }
    });

    /* 目录选择：路径行右侧的「选择目录」按钮 */
    root.addEventListener('click', async function (event) {
      const pick = event.target.closest('[data-pick]');
      if (!pick) return;
      const row = pick.closest('.path-row');
      const input = row ? row.querySelector('input') : null;
      const chosen = await pickDirectory(input ? input.value : '');
      if (chosen && input) {
        input.value = chosen;
        input.dispatchEvent(new Event('change'));
      }
    });

    /* 设置页内的「查看更多 / 编辑」链接（阻止全局占位提示） */
    root.addEventListener('click', function (event) {
      const more = event.target.closest('[data-more]');
      if (!more) return;
      const section = currentSection(root);
      const label = more.dataset.more;
      if (section === 'security' && label === '查看更多') {
        event.preventDefault();
        event.stopPropagation();
        const events = (state.securityOverview && state.securityOverview.events) || [];
        window.UI.dialog({
          title: '安全日志',
          body: events.length ? '<div class="ui-browser"><div class="ui-browser-list">' +
            events.map(function (item) {
              return '<div class="ui-browser-item" style="cursor:default">' +
                window.UI.esc(String(item.time || '').slice(0, 19).replace('T', ' ')) + ' · ' +
                window.UI.esc(item.action || '-') + ' · ' + window.UI.esc(item.user || '-') + ' · ' +
                window.UI.esc(item.resource || '-') + '</div>';
            }).join('') + '</div></div>'
            : '<p style="color:var(--text-3)">暂无审计记录</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }
      if (section === 'data' && label === '查看更多') {
        event.preventDefault();
        event.stopPropagation();
        const backups = (state.stats && state.stats.backups) || [];
        window.UI.dialog({
          title: '全部备份',
          body: backups.length ? '<div class="ui-browser"><div class="ui-browser-list">' +
            backups.map(function (item) {
              return '<div class="ui-browser-item" style="cursor:default">' +
                window.UI.esc(item.id) + ' · ' + humanSize(item.size) +
                (item.has_settings ? ' · 含设置' : '') + '</div>';
            }).join('') + '</div></div>'
            : '<p style="color:var(--text-3)">暂无备份</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
        return;
      }
      if (section === 'model' && label === '编辑') {
        event.preventDefault();
        event.stopPropagation();
        editModel(root);
        return;
      }
      if (section === 'users' && label === '编辑') {
        event.preventDefault();
        event.stopPropagation();
        const users = (state.users && state.users.items) || [];
        const user = users.find(function (item) { return item.id === root.dataset.selectedUser; }) || users[0];
        if (user) editUser(root, user);
        return;
      }
      if (section === 'about' && label === '查看更多') {
        event.preventDefault();
        event.stopPropagation();
        window.UI.dialog({
          title: '更新日志',
          body: '<p style="color:var(--text-3)">本部署未配置更新源，无法列出历史版本变更。</p>',
          actions: [{ label: '关闭', value: null, plain: true }]
        });
      }
    });
  }

  async function editModel(root) {
    const items = (state && state.models && state.models.items) || [];
    const current = items.find(function (item) { return item.id === root.dataset.selectedModel; })
      || items.find(function (item) { return item.is_default; }) || items[0];
    if (!current) { toast('没有可编辑的模型'); return; }
    const values = await window.UI.form({
      title: '编辑模型：' + current.name,
      fields: [
        { key: 'name', label: '模型名称', value: current.name, required: true },
        { key: 'provider', label: '提供商', value: current.provider },
        { key: 'kind', label: '模型类型', value: current.kind },
        { key: 'context', label: '上下文长度', value: current.context },
        { key: 'available', label: '可用', type: 'switch', value: !!current.available },
        { key: 'description', label: '描述', type: 'textarea', wide: true, rows: 3,
          value: current.description }
      ]
    });
    if (!values) return;
    const next = items.map(function (item) {
      return item.id === current.id ? Object.assign({}, item, values) : item;
    });
    const result = await window.Api.saveModels({ items: next });
    if (!ok(result)) { fail(result, '保存失败'); return; }
    toast('模型已更新');
    await reload(root);
  }

  async function editUser(root, user) {
    const roles = (state.roles && state.roles.items) || [];
    const values = await window.UI.form({
      title: '编辑用户：' + user.username,
      note: '留空的口令字段不会修改口令；非空时按密码策略与历史校验。',
      fields: [
        { key: 'display_name', label: '姓名', value: user.display_name },
        { key: 'email', label: '邮箱', type: 'email', value: user.email },
        { key: 'phone', label: '手机号', value: user.phone },
        { key: 'role', label: '角色', type: 'select', value: (user.roles || [])[0],
          options: roles.map(function (role) {
            return { value: role.name, label: role.label };
          }) },
        { key: 'password', label: '重置口令', type: 'password', placeholder: '留空则不修改' },
        { key: 'note', label: '备注', type: 'textarea', wide: true, rows: 2, value: user.note },
        { key: 'locked', label: '锁定账号', type: 'switch', value: !!user.locked },
        { key: 'is_active', label: '启用账号', type: 'switch', value: !!user.is_active }
      ]
    });
    if (!values) return;
    if (!values.password) delete values.password;
    values.roles = values.role ? [values.role] : [];
    delete values.role;
    const result = await window.Api.updateUser(user.id, values);
    if (!ok(result)) { fail(result, '保存失败'); return; }
    await reload(root);
    toast('用户已更新');
  }

  function pickJsonFile() {
    return new Promise(function (resolve) {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'application/json,.json';
      input.addEventListener('change', function () {
        const file = input.files && input.files[0];
        if (!file) { resolve(null); return; }
        const reader = new FileReader();
        reader.onload = function () {
          try { resolve(JSON.parse(String(reader.result))); }
          catch (error) { toast('文件不是合法 JSON'); resolve(null); }
        };
        reader.onerror = function () { toast('读取文件失败'); resolve(null); };
        reader.readAsText(file);
      });
      input.click();
    });
  }

  function readCleanup(root) {
    const map = {
      '清理任务记录': 'tasks',
      '清理日志数据': 'logs',
      '清理审计日志': 'audit',
      '清理已删除用户数据': 'deleted_users',
      '清理临时文件': 'temp'
    };
    const result = {};
    root.querySelectorAll('.set-row').forEach(function (row) {
      const box = row.querySelector('.cbx-item');
      if (!box) return;
      const label = box.textContent.trim();
      const key = map[label];
      if (!key) return;
      const input = row.querySelector('input');
      result[key] = {
        enabled: box.classList.contains('is-on'),
        days: input ? Number(input.value) || 0 : 0
      };
    });
    return result;
  }

  function downloadJson(name, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = name;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  /* ---------------- 装配 ---------------- */

  async function reload(root) {
    if (!window.Api || !window.Api.token()) return;
    const [settings, users, roles, security, stats] = await Promise.all([
      window.Api.settings(),
      window.Api.users(),
      window.Api.roles(),
      window.Api.securityOverview(),
      window.Api.dataStats()
    ]);
    if (!ok(settings)) return;
    state = settings.data;
    state.users = ok(users) ? users.data : { items: [] };
    state.roles = ok(roles) ? roles.data : { items: [], permissions: [] };
    state.securityOverview = ok(security) ? security.data : null;
    state.stats = ok(stats) ? stats.data : null;
    apply(root, state);
  }

  /* ⚠️ 每个标签页的结构不同（都有 `.set3` / `.dtable`），必须按**当前标签**
     只覆盖自己的数据区；否则「数据管理」的备份表会写进「服务配置」的环境变量表。 */
  function apply(root, data, tab) {
    const active = tab || currentSection(root);
    if (active === 'basic') {
      applyBasic(root, data);
      return;
    }
    if (active === 'service') {
      applyService(root, data);
      return;
    }
    if (active === 'model') {
      applyModels(root, data);
      return;
    }
    if (active === 'users') {
      applyUsers(root, data.users || { items: [] }, data.roles || { items: [] });
      return;
    }
    if (active === 'security') {
      applySecurity(root, data, data.securityOverview);
      return;
    }
    if (active === 'data') {
      applyData(root, data, data.stats);
      return;
    }
    /* about：版本 / 运行环境等只读信息 */
    applyAbout(root, data);
  }

  function applyAbout(root, data) {
    const system = data.system || {};
    const map = {
      '当前版本': system.version,
      '构建时间': system.build_time,
      '构建编号': system.build_time ? String(system.build_time).replace(/[-: ]/g, '').slice(0, 12) : '',
      '运行环境': system.platform,
      '前端版本': system.version,
      '后端版本': system.version,
      'MCP 协议版本': '2024-11-05'
    };
    root.querySelectorAll('.kv-list .r').forEach(function (row) {
      const key = (row.querySelector('dt') || {}).textContent || '';
      const value = row.querySelector('dd');
      if (value && map[key]) value.textContent = map[key];
    });

    /* 系统组件：状态取自真实运行信息（版本号未知时如实显示 -） */
    const compTable = root.querySelector('.set3 .dtable');
    if (compTable) {
      const database = String(system.database || '');
      const rows = [
        ['MCP Server', system.version || '-', '运行中'],
        ['Web 管理界面', system.version || '-', '运行中'],
        ['任务调度服务', system.version || '-', '运行中'],
        ['日志服务', system.log_dir || '-', system.log_dir ? '运行中' : '未启用文件日志'],
        ['数据库', database.endsWith('.db') ? 'SQLite' : (database || '-'), '正常'],
        ['运行环境', 'Python ' + (system.python || '-'), '正常'],
        ['进程', system.platform || '-', '正常']
      ];
      const body = compTable.querySelector('tbody');
      if (body) {
        body.innerHTML = rows.map(function (row) {
          return '<tr><td>' + window.UI.esc(row[0]) + '</td>' +
            '<td>' + window.UI.esc(row[1]) + '</td>' +
            '<td><span class="tag green"><span class="dot"></span>' + row[2] + '</span></td></tr>';
        }).join('');
      }
    }
  }

  /* ---------------- 详情卡动作（模型 / 用户） ---------------- */

  function bindDetailActions(root) {
    if (root.dataset.detailBound) return;
    root.dataset.detailBound = '1';
    root.addEventListener('click', async function (event) {
      if (!window.Api || !window.Api.token()) return;
      const card = event.target.closest('.set2 .settings-card:last-child');
      if (!card) return;
      /* 只在「模型设置 / 用户与权限」页生效（其它页也有 `.set2` 卡片） */
      const section = currentSection(root);
      if (section !== 'model' && section !== 'users') return;
      const items = (state && state.models && state.models.items) || [];
      const users = (state && state.users && state.users.items) || [];

      if (event.target.closest('[data-model-test-detail]')) {
        const current = items.find(function (item) { return item.id === root.dataset.selectedModel; })
          || items.find(function (item) { return item.is_default; }) || items[0];
        if (!current) { toast('没有可测试的模型'); return; }
        const result = await window.Api.testModel(current.id);
        if (!ok(result)) { fail(result, '测试失败'); return; }
        toast(result.data.reachable ? '模型配置完整：' + current.name
          : '模型不可用：' + (result.data.reason || '未配置'));
        return;
      }
      if (event.target.closest('[data-model-default-detail]')) {
        const current = items.find(function (item) { return item.id === root.dataset.selectedModel; })
          || items.find(function (item) { return item.is_default; }) || items[0];
        if (!current) { toast('没有可设置的模型'); return; }
        const next = items.map(function (item) {
          return Object.assign({}, item, { is_default: item.id === current.id });
        });
        const result = await window.Api.saveModels({ items: next, default: current.id });
        if (!ok(result)) { fail(result, '保存失败'); return; }
        toast('默认模型：' + current.name);
        await reload(root);
        return;
      }
      if (event.target.closest('[data-model-delete]')) {
        const current = items.find(function (item) { return item.id === root.dataset.selectedModel; })
          || items.find(function (item) { return item.is_default; }) || items[0];
        if (!current) { toast('没有可删除的模型'); return; }
        if (items.length <= 1) { toast('至少保留一个模型'); return; }
        const confirmed = await window.UI.dialog({
          title: '删除模型',
          body: '<p>从列表移除 <b>' + window.UI.esc(current.name) + '</b>？</p>' +
            '<p style="color:var(--text-3)">只是从配置列表移除，不影响已保存的 API Key。</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '删除', value: 'delete', danger: true }
          ]
        }).result;
        if (confirmed !== 'delete') return;
        const next = items.filter(function (item) { return item.id !== current.id; });
        const result = await window.Api.saveModels({
          items: next,
          default: (next.find(function (item) { return item.is_default; }) || next[0] || {}).id
        });
        if (!ok(result)) { fail(result, '删除失败'); return; }
        toast('模型已移除');
        await reload(root);
        return;
      }
      if (event.target.closest('[data-user-reset]')) {
        const user = users.find(function (item) { return item.id === root.dataset.selectedUser; }) || users[0];
        if (!user) { toast('没有可操作的用户'); return; }
        const values = await window.UI.form({
          title: '重置口令：' + user.username,
          fields: [{ key: 'password', label: '新口令', type: 'password', required: true, wide: true,
            hint: '按「安全设置 · 密码策略」校验；不会回显口令。' }]
        });
        if (!values) return;
        const result = await window.Api.updateUser(user.id, { password: values.password });
        if (!ok(result)) { fail(result, '重置失败'); return; }
        toast('口令已重置');
        return;
      }
      if (event.target.closest('[data-user-toggle]')) {
        const user = users.find(function (item) { return item.id === root.dataset.selectedUser; }) || users[0];
        if (!user) return;
        const result = await window.Api.updateUser(user.id, { is_active: !user.is_active });
        if (!ok(result)) { fail(result, '操作失败'); return; }
        toast(user.is_active ? '用户已禁用' : '用户已启用');
        await reload(root);
        return;
      }
      if (event.target.closest('[data-user-delete]')) {
        const user = users.find(function (item) { return item.id === root.dataset.selectedUser; }) || users[0];
        if (!user) return;
        const confirmed = await window.UI.dialog({
          title: '删除用户',
          body: '<p>确定删除用户 <b>' + window.UI.esc(user.username) + '</b>？</p>',
          actions: [
            { label: '取消', value: null, plain: true },
            { label: '删除', value: 'delete', danger: true }
          ]
        }).result;
        if (confirmed !== 'delete') return;
        const result = await window.Api.deleteUser(user.id);
        if (!ok(result)) { fail(result, '删除失败'); return; }
        toast('用户已删除');
        await reload(root);
      }
    });
  }

  window.PageSettingsLive = {
    /* 页面渲染完成后调用：先绑事件（mock 控件），再拉实时数据覆盖 */
    mount: function (root) {
      bind(root);
      bindActions(root);
      bindDetailActions(root);
      reload(root);
    },
    reload: reload
  };
})();
