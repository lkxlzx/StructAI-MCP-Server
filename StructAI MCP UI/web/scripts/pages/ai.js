/* AI 工程助手 · 智能对话 */
(function () {
  const D = {
    head: {
      title: 'AI 工程助手',
      sub: '用自然语言驱动 MIDAS，从建模到计算书的智能工程助手',
      softwareLabel: '当前软件',
      software: 'CIVIL NX 2026',
      actions: [{ label: '新建工程', icon: 'plus' }, { label: '打开模型', icon: 'folder' }],
      tabs: [
        { id: 'chat', label: '智能对话', icon: 'chat', active: true },
        { id: 'tpl', label: '工程模板', icon: 'tpl' },
        { id: 'demo', label: '示例案例', icon: 'demo' },
        { id: 'hist', label: '历史记录', icon: 'hist' }
      ]
    },
    chat: {
      user: {
        text: '生成一个 6 米高的 Q355B H400×400×13×21 钢柱，底部固定，顶部施加 500kN 轴压力，进行静力分析、稳定验算，并生成计算书。',
        time: '2026-09-22 10:24'
      },
      ai: {
        intro: '好的。我将使用 CIVIL NX 2026 通过 MCP 接口完成以下任务：',
        steps: [
          '创建模型（节点、单元、材料、截面）',
          '设置边界条件与荷载',
          '执行静力分析',
          '进行钢柱稳定设计验算',
          '生成计算书与结果图'
        ],
        done: '任务已完成',
        cost: '耗时 28.6 秒',
        time: '2026-09-22 10:24'
      }
    },
    model: {
      tabs: ['模型视图', '计算结果', '验算结果', '计算书预览'],
      tools: [
        { k: '3d', label: '3D视图', icon: 'cube', active: true },
        { k: 'x', label: 'X方向', icon: 'axisX' },
        { k: 'y', label: 'Y方向', icon: 'axisY' },
        { k: 'z', label: 'Z方向', icon: 'axisZ' },
        { k: 'zoom', label: '缩放', icon: 'zoom' },
        { k: 'pan', label: '平移', icon: 'pan' },
        { k: 'full', label: '全屏', icon: 'expand' }
      ],
      info: {
        title: '模型信息',
        rows: [
          ['结构类型', '钢柱'], ['截面', 'H400×400×13×21'], ['材料', 'Q355B'],
          ['柱高', '6,000 mm'], ['底部约束', '固定'], ['顶部荷载', '轴力 500 kN'],
          ['单元类型', '梁单元（Beam）'], ['节点数', '2'], ['单元数', '1']
        ]
      }
    },
    composer: {
      placeholder: '请输入工程需求，例如：生成一个三层钢框架并进行地震分析...',
      model: 'deepseek-v4-flash'
    },
    side: {
      info: {
        title: '工程信息', link: '编辑', linkIcon: 'edit', icon: 'info',
        rows: [
          ['工程名称', '钢柱示例工程'],
          ['创建时间', '2026-09-22 10:24:15'],
          ['软件版本', 'CIVIL NX 2026'],
          ['模型路径', 'D:/Projects/SteelColumn.mcb'],
          ['工程描述', '单根钢柱静力分析与稳定验算']
        ]
      },
      steps: {
        title: '执行过程', link: '查看详情', icon: 'flow',
        rows: [
          ['创建项目', '2.1s'], ['建立节点', '1.3s'], ['建立单元', '1.8s'],
          ['设置材料与截面', '2.4s'], ['设置边界条件', '1.1s'], ['施加荷载', '1.0s'],
          ['执行静力分析', '6.8s'], ['钢柱稳定验算', '3.2s'], ['生成计算书', '5.9s']
        ]
      },
      chips: {
        title: '常用指令', link: '更多示例', icon: 'bulb',
        items: ['生成钢梁', '三维框架结构', '网架结构', '执行模态分析', '生成计算书', '查看规范条文']
      }
    }
  };

  /* 3D 视图插画：钢柱 + 轴压荷载 + 高度标注 + 坐标轴 */
  const ART =
    '<svg viewBox="0 0 560 300" preserveAspectRatio="xMidYMid meet">' +
    '<defs>' +
    '<linearGradient id="colA" x1="0" y1="0" x2="1" y2="0">' +
    '<stop offset="0" stop-color="#8E98A6"/><stop offset=".5" stop-color="#C6CDD8"/><stop offset="1" stop-color="#7B8595"/></linearGradient>' +
    '<linearGradient id="colB" x1="0" y1="0" x2="1" y2="0">' +
    '<stop offset="0" stop-color="#98A2B0"/><stop offset="1" stop-color="#6F7A8A"/></linearGradient>' +
    '<pattern id="hatch" width="9" height="9" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">' +
    '<line x1="0" y1="0" x2="0" y2="9" stroke="#AEB9C8" stroke-width="1.2"/></pattern>' +
    '</defs>' +
    '<g stroke="#E9EEF6" stroke-width="1">' +
    '<path d="M0 70H560M0 130H560M0 190H560M0 250H560"/>' +
    '<path d="M70 0V300M150 0V300M230 0V300M310 0V300M390 0V300M470 0V300"/>' +
    '</g>' +
    '<rect x="176" y="252" width="170" height="10" fill="url(#hatch)"/>' +
    '<path d="M162 264h198" stroke="#8C97A6" stroke-width="1.6"/>' +
    '<polygon points="200,74 232,58 264,74 232,88" fill="#DCE2EA"/>' +
    '<polygon points="204,74 232,60 260,74 232,86" fill="#C2CAD6"/>' +
    '<rect x="204" y="74" width="13" height="178" fill="url(#colB)"/>' +
    '<rect x="247" y="74" width="13" height="178" fill="url(#colB)"/>' +
    '<rect x="217" y="74" width="30" height="178" fill="url(#colA)"/>' +
    '<polygon points="243,74 253,80 253,254 243,250" fill="#6C7787" opacity=".75"/>' +
    '<path d="M232 16V62" stroke="#E5484D" stroke-width="2.6"/>' +
    '<polygon points="232,72 226,56 238,56" fill="#E5484D"/>' +
    '<text x="248" y="26" font-size="15" font-weight="600" fill="#E5484D">N = 500 kN</text>' +
    '<path d="M300 74v180" stroke="#8C97A6" stroke-width="1"/>' +
    '<path d="M295 74h10M295 254h10" stroke="#8C97A6" stroke-width="1"/>' +
    '<text x="312" y="170" font-size="14" fill="#5A6884">6000</text>' +
    '<g stroke-width="1.8">' +
    '<path d="M60 250h34" stroke="#E5484D"/><polygon points="100,250 90,245 90,255" fill="#E5484D"/>' +
    '<text x="106" y="255" font-size="13" fill="#E5484D">X</text>' +
    '<path d="M60 250l-26-18" stroke="#1AA65E"/><polygon points="30,229 42,232 36,238" fill="#1AA65E"/>' +
    '<text x="16" y="226" font-size="13" fill="#1AA65E">Y</text>' +
    '<path d="M60 250V210" stroke="#0065FE"/><polygon points="60,204 55,214 65,214" fill="#0065FE"/>' +
    '<text x="52" y="200" font-size="13" fill="#0065FE">Z</text>' +
    '</g></svg>';

  const chk = '<span class="ck" data-icon="check"></span>';

  function render(shell, d) {
    const t = d.head;
    const tabs = t.tabs.map(function (x) {
      return '<button class="ai-tab' + (x.active ? ' is-active' : '') + '" type="button" data-aitab="' + x.id + '">' +
        '<span class="ti" data-icon="' + x.icon + '"></span>' + x.label + '</button>';
    }).join('');

    const actions = t.actions.map(function (a) {
      return '<button class="btn-soft" type="button" data-act="' + a.label + '">' +
        '<span class="bi" data-icon="' + a.icon + '"></span>' + a.label + '</button>';
    }).join('');

    const steps = d.chat.ai.steps.map(function (s, i) {
      return '<li>' + chk + '<span>' + (i + 1) + '. ' + s + '</span></li>';
    }).join('');

    const mtabs = d.model.tabs.map(function (x, i) {
      return '<button class="model-tab' + (i === 0 ? ' is-active' : '') + '" type="button" data-mtab="' + x + '">' + x + '</button>';
    }).join('');

    const tools = d.model.tools.map(function (x) {
      return '<button class="vtool' + (x.active ? ' is-active' : '') + '" type="button" data-vtool="' + x.k + '">' +
        '<span class="vi" data-icon="' + x.icon + '"></span>' + x.label + '</button>';
    }).join('');

    const minfo = d.model.info.rows.map(function (r) {
      return '<div class="kv"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
    }).join('');

    const si = d.side.info;
    const infoRows = si.rows.map(function (r) {
      return '<div class="info-kv"><dt>' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
    }).join('');

    const ss = d.side.steps;
    const stepRows = ss.rows.map(function (r) {
      return '<div class="step-row">' + chk + '<span class="nm">' + r[0] + '</span><span class="tm">' + r[1] + '</span></div>';
    }).join('');

    const chips = d.side.chips.items.map(function (c) {
      return '<button class="chip" type="button" data-chip="' + c + '">' + c + '</button>';
    }).join('');

    return '' +
      '<section class="ai-head">' +
        '<span class="ai-head-accent"></span>' +
        '<h1 class="ai-title">' + t.title + '</h1>' +
        '<p class="ai-sub">' + t.sub + '</p>' +
        '<div class="ai-head-right">' +
          '<span class="ai-soft-label">' + t.softwareLabel + '</span>' +
          '<div class="ai-head-row">' +
            '<span class="select-like ai-soft-select"><select aria-label="当前软件"><option>' + t.software + '</option></select>' +
            '<span class="chev" data-icon="chevD"></span></span>' + actions +
          '</div>' +
        '</div>' +
        '<nav class="ai-tabs">' + tabs + '</nav>' +
      '</section>' +

      '<div class="ai-split">' +
        '<div class="ai-main">' +
          '<section class="chat-card">' +
            '<div class="chat-log">' +
              '<div class="msg-user">' +
                '<div class="bubble"><p>' + d.chat.user.text + '</p>' +
                '<span class="stamp">' + d.chat.user.time + '</span></div>' +
                '<span class="avatar avatar-me">我</span>' +
              '</div>' +
              '<div class="msg-ai">' +
                '<span class="ai-avatar" data-icon="logo"></span>' +
                '<div class="msg-ai-body">' +
                  '<p class="msg-ai-text">' + d.chat.ai.intro + '</p>' +
                  '<div class="msg-ai-row">' +
                    '<ul class="task-steps">' + steps + '</ul>' +
                    '<div class="msg-foot">' +
                      '<span class="pill pill-green"><span class="dot dot-green"></span>' + d.chat.ai.done + '</span>' +
                      '<span class="ms"><span class="mi" data-icon="timer"></span>' + d.chat.ai.cost + '</span>' +
                      '<span class="stamp">' + d.chat.ai.time + '</span>' +
                    '</div>' +
                  '</div>' +
                '</div>' +
              '</div>' +
            '</div>' +
            '<div class="model-panel">' +
              '<div class="model-tabs">' + mtabs + '</div>' +
              '<div class="model-body">' +
                '<div class="view-wrap">' +
                  '<div class="view-toolbar">' + tools + '</div>' +
                  '<div class="view-canvas">' + ART + '</div>' +
                '</div>' +
                '<aside class="model-info">' +
                  '<div class="model-info-title"><span class="mi" data-icon="model"></span>' + d.model.info.title + '</div>' +
                  minfo +
                '</aside>' +
              '</div>' +
            '</div>' +
          '</section>' +

          '<section class="composer">' +
            '<span class="clip" data-icon="clip" title="添加附件"></span>' +
            '<input type="text" id="aiInput" placeholder="' + d.composer.placeholder + '">' +
            '<span class="select-like composer-model"><select aria-label="模型">' +
              '<option>' + d.composer.model + '</option><option>gpt-5</option><option>claude-4</option>' +
            '</select><span class="chev" data-icon="chevD"></span></span>' +
            '<button class="btn-send" type="button" id="aiSend"><span class="si" data-icon="send"></span>发送</button>' +
          '</section>' +
        '</div>' +

        '<div class="ai-side">' +
          '<section class="side-card">' +
            '<div class="side-card-head">' +
              '<span class="side-card-title"><span class="si" data-icon="' + si.icon + '"></span>' + si.title + '</span>' +
              '<a class="link-more" href="javascript:void(0)" data-more="' + si.link + '">' +
              '<span class="edit-i" data-icon="' + si.linkIcon + '"></span>' + si.link + '</a>' +
            '</div>' + infoRows +
          '</section>' +

          '<section class="side-card">' +
            '<div class="side-card-head">' +
              '<span class="side-card-title"><span class="si" data-icon="' + ss.icon + '"></span>' + ss.title + '</span>' +
              '<a class="link-more" href="javascript:void(0)" data-more="' + ss.link + '">' + ss.link +
              '<span class="chev" data-icon="chevR"></span></a>' +
            '</div>' +
            '<div class="steps-list">' + stepRows + '</div>' +
          '</section>' +

          '<section class="side-card chips-card">' +
            '<div class="side-card-head">' +
              '<span class="side-card-title"><span class="si" data-icon="' + d.side.chips.icon + '"></span>' + d.side.chips.title + '</span>' +
              '<a class="link-more" href="javascript:void(0)" data-more="' + d.side.chips.link + '">' + d.side.chips.link +
              '<span class="chev" data-icon="chevR"></span></a>' +
            '</div>' +
            '<div class="chips">' + chips + '</div>' +
          '</section>' +
        '</div>' +
      '</div>';
  }

  function mount(root) {
    const log = root.querySelector('.chat-log');
    /* 与原稿一致：对话默认停在顶部，不做自动滚动 */
    const input = root.querySelector('#aiInput');
    const send = root.querySelector('#aiSend');
    if (send && input) send.addEventListener('click', function () {
      if (!input.value.trim()) return;
      window.Toast.show('已发送指令：' + input.value.trim());
      input.value = '';
    });
    if (input) input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') send.click();
    });
    root.querySelectorAll('[data-mtab]').forEach(function (b) {
      b.addEventListener('click', function () {
        root.querySelectorAll('.model-tab').forEach(function (x) { x.classList.remove('is-active'); });
        b.classList.add('is-active');
        window.Toast.show('已切换到：' + b.dataset.mtab);
      });
    });
    root.querySelectorAll('[data-vtool]').forEach(function (b) {
      b.addEventListener('click', function () {
        root.querySelectorAll('.vtool').forEach(function (x) { x.classList.remove('is-active'); });
        b.classList.add('is-active');
      });
    });
    root.querySelectorAll('[data-chip]').forEach(function (b) {
      b.addEventListener('click', function () {
        if (input) { input.value = b.dataset.chip; input.focus(); }
      });
    });
  }

  window.PageAI = { data: function () { return D; }, render: render, mount: mount };
})();
