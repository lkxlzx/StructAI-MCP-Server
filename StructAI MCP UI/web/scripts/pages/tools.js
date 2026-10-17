/* 工具与接口 · Schema 定义（tools 路由：schema 标签） */
(function () {
  const TOOLS = [
    { id: 'midas_doc', name: 'midas_doc', path: '/doc/OPEN', color: '#0B6BFB', icon: 'fileText' },
    { id: 'midas_db_query', name: 'midas_db_query', path: '/db/NODE', color: '#0B6BFB', icon: 'db' },
    { id: 'midas_db_assign', name: 'midas_db_assign', path: '/db/ASSIGN', color: '#8B5CF6', icon: 'tools' },
    { id: 'midas_db_delete', name: 'midas_db_delete', path: '/db/DELETE', color: '#FE3B36', icon: 'trash' },
    { id: 'midas_ope_build', name: 'midas_ope_build', path: '/ope/BUILD', color: '#06A65A', icon: 'tools' },
    { id: 'midas_view_model', name: 'midas_view_model', path: '/view/MODEL', color: '#8B5CF6', icon: 'eye' },
    { id: 'midas_post_result', name: 'midas_post_result', path: '/post/RESULT', color: '#0B6BFB', icon: 'db' },
    { id: 'midas_design_check', name: 'midas_design_check', path: '/design/CHECK', color: '#8B5CF6', icon: 'tools' },
    { id: 'midas_anal_start', name: 'midas_anal_start', path: '/anal/START', color: '#8B5CF6', icon: 'play' }
  ];

  const DETAIL = {
    id: 'midas_doc', name: 'midas_doc', color: '#0B6BFB', icon: 'fileText',
    chips: [{ t: 'DOC', cls: 'blue' }, { t: '核心工具', cls: 'green' }, { t: '支持多版本', cls: 'green' }],
    desc: '文档操作与模型管理，支持打开、保存、关闭、另存为等操作。',
    kv: [
      ['接口路径', '/doc/OPEN', true], ['请求方法', 'POST', true], ['所属分类', 'DOC', true],
      ['支持软件', 'CIVIL NX / GEN NX / FEA NX', false], ['最低版本', '2020', true]
    ],
    inJson: [
      '{', '  "type": "object",', '  "properties": {',
      '    "command": {', '      "type": "string",',
      '      "description": "操作命令，如 OPEN、SAVE、CLOSE",',
      '      "enum": ["OPEN", "SAVE", "CLOSE"]', '    },',
      '    "file_path": {', '      "type": "string",',
      '      "description": "模型文件路径",',
      '      "example": "D:/Projects/test.mcb"', '    },',
      '    "read_only": {', '      "type": "boolean",',
      '      "description": "是否只读打开",', '      "default": false', '    }',
      '  },', '  "required": ["command", "file_path"]', '}'
    ],
    inParams: {
      cols: ['参数名', '类型', '是否必填', '默认值', '说明'],
      rows: [
        ['command', 'string', '是', '-', '操作命令：OPEN / SAVE / CLOSE'],
        ['file_path', 'string', '是', '-', '模型文件路径'],
        ['read_only', 'boolean', '否', 'false', '是否只读打开']
      ]
    },
    outJson: [
      '{', '  "type": "object",', '  "properties": {',
      '    "success": {', '      "type": "boolean",',
      '      "description": "操作是否成功"', '    },',
      '    "message": {', '      "type": "string",',
      '      "description": "返回消息"', '    },',
      '    "data": {', '      "type": "object",', '      "properties": {',
      '        "model_name": {', '          "type": "string",',
      '          "description": "模型名称"', '        },',
      '        "version": {', '          "type": "string",',
      '          "description": "软件版本"', '        },',
      '        "file_path": {', '          "type": "string",',
      '          "description": "实际文件路径"', '        }',
      '      }', '    }', '  }', '}'
    ],
    outParams: {
      cols: ['参数名', '类型', '说明'],
      rows: [
        ['success', 'boolean', '操作是否成功'],
        ['message', 'string', '返回消息'],
        ['data', 'object', '返回的数据对象'],
        ['model_name', 'string', '模型名称', 1],
        ['version', 'string', '软件版本', 1],
        ['file_path', 'string', '实际文件路径', 1]
      ]
    }
  };

  const TABS = [
    { id: 'mcp', label: 'MCP 工具' },
    { id: 'api', label: 'API 接口' },
    { id: 'matrix', label: '接口能力矩阵' },
    { id: 'examples', label: '请求示例' },
    { id: 'schema', label: 'Schema 定义' }
  ];

  /* JSON 语法着色 */
  function hl(line) {
    let s = line.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    s = s.replace(/"([^"]+)":/g, '\u0001$1\u0002:');
    s = s.replace(/"([^"]*)"/g, '<span class="s">"$1"</span>');
    s = s.replace(/\u0001([^\u0002]+)\u0002/g, '<span class="k">"$1"</span>');
    return s;
  }
  function codeBlock(lines) {
    return '<div class="code-block">' + lines.map(function (l, i) {
      return '<div class="ln"><span class="no">' + (i + 1) + '</span><span class="code">' + hl(l) + '</span></div>';
    }).join('') + '</div>';
  }
  function ptable(cols, rows) {
    const th = cols.map(function (c) { return '<th>' + c + '</th>'; }).join('');
    const tr = rows.map(function (r) {
      const indent = r[3] ? '<span class="tree" data-icon="' + (r[3] ? 'chevD' : '') + '"></span>' : '';
      const req = r[2] === '是' ? '<span class="req">是</span>' : r[2];
      return '<tr><td class="mono">' + indent + r[0] + '</td><td class="mono">' + r[1] + '</td>' +
        (cols.length === 5 ? '<td>' + req + '</td><td class="mono">' + r[3] + '</td><td>' + r[4] + '</td>'
          : '<td>' + r[2] + '</td>') + '</tr>';
    }).join('');
    return '<table class="ptable"><thead><tr>' + th + '</tr></thead><tbody>' + tr + '</tbody></table>';
  }
  const chip = function (c) { return '<span class="tag ' + c.cls + '">' + c.t + '</span>'; };

  /* ---------- 各标签页的页头文案 ---------- */
  const HEADS = {
    schema: { title: 'Schema 定义', crumb: 'Schema 定义', sub: '查看和管理 MCP 工具的输入输出 Schema，支持 JSON Schema 规范' },
    api: { title: 'API 接口', crumb: 'API 接口', sub: '管理 MIDAS 官方 API 接口，支持查看、测试和快速调用' },
    mcp: { title: 'MCP 工具', crumb: 'MCP 工具', sub: '查看和管理 MCP 工具清单与调用方式' },
    matrix: { title: '接口能力矩阵', crumb: '接口能力矩阵', sub: '对比各 MIDAS 软件对接口能力的支持情况' },
    examples: { title: '请求示例', crumb: '请求示例', sub: '查看常用接口的请求与响应示例' }
  };

  /* ---------- API 接口（api 标签） ---------- */
  const API_CATS = [
    { k: '全部接口', n: 286, c: '#0B6BFB', i: 'layers' },
    { k: 'DOC 文档管理', n: 42, c: '#0B6BFB', i: 'fileText' },
    { k: 'DB 数据库操作', n: 68, c: '#0B6BFB', i: 'db' },
    { k: 'OPE 参数化建模', n: 36, c: '#06A65A', i: 'tools' },
    { k: 'VIEW 图形生成', n: 28, c: '#8B5CF6', i: 'eye' },
    { k: 'POST 结果查询', n: 52, c: '#0B6BFB', i: 'db' },
    { k: 'DESIGN 设计校核', n: 38, c: '#8B5CF6', i: 'tools' },
    { k: 'ANAL 分析计算', n: 22, c: '#8B5CF6', i: 'play' }
  ];
  const API_ROWS = [
    ['打开模型（OPEN）', 'POST', '/doc/OPEN', 'DOC', 1],
    ['保存模型（SAVE）', 'POST', '/doc/SAVE', 'DOC', 0],
    ['关闭模型（CLOSE）', 'POST', '/doc/CLOSE', 'DOC', 0],
    ['获取模型信息（INFO）', 'GET', '/doc/INFO', 'DOC', 0],
    ['节点查询（NODE）', 'GET', '/db/NODE', 'DB', 0],
    ['节点写入（NODE）', 'POST', '/db/NODE', 'DB', 0],
    ['节点删除（NODE）', 'DELETE', '/db/NODE', 'DB', 0],
    ['单元查询（ELEM）', 'GET', '/db/ELEM', 'DB', 0],
    ['单元写入（ELEM）', 'POST', '/db/ELEM', 'DB', 0],
    ['荷载工况（LOAD）', 'POST', '/db/LOAD', 'DB', 0]
  ];
  const API_DETAIL = {
    name: '打开模型（OPEN）', cat: 'DOC', soft: 'CIVIL NX',
    tabs: ['基本信息', '请求参数', '响应结果', '示例代码', '相关工具'],
    kv: [
      ['接口路径', '<span style="color:var(--red);font-family:var(--font-num)">/doc/OPEN</span>'],
      ['请求方法', 'POST'], ['所属分类', 'DOC - 文档管理'],
      ['支持版本', 'CIVIL NX 2021 ~ 2026'], ['接口描述', '打开 MIDAS 模型文件，支持 .mcb 格式。']
    ],
    req: ['{', '  "command": "OPEN",', '  "argument": {',
      '    "file_path": "D:/Projects/test.mcb",', '    "read_only": false', '  }', '}'],
    res: ['{', '  "success": true,', '  "message": "模型打开成功",', '  "data": {',
      '    "model_name": "test.mcb",', '    "version": "2024",', '    "units": "kN-m"', '  }', '}']
  };

  function apiTab() {
    const cats = API_CATS.map(function (c, i) {
      return '<button class="tool-item' + (i === 0 ? ' is-active' : '') + '" type="button" data-cat="' + c.k + '">' +
        '<span class="tool-ico" style="background:' + c.c + '" data-icon="' + c.i + '"></span>' +
        '<span class="tool-meta"><span class="tool-name">' + c.k + '</span></span>' +
        '<span class="tool-count">' + c.n + '</span></button>';
    }).join('');

    const rows = API_ROWS.map(function (r) {
      return '<tr' + (r[4] ? ' class="is-sel"' : '') + '>' +
        '<td style="font-weight:600;color:var(--text-1)">' + r[0] + '</td>' +
        '<td class="mut">' + r[1] + '</td>' +
        '<td class="num mut">' + r[2] + '</td>' +
        '<td><span class="tag blue">' + r[3] + '</span></td>' +
        '<td><span class="api-ok"><span class="dot dot-green"></span>支持</span></td>' +
        '<td class="c"><button class="tbtn icon" type="button" data-act2="接口操作"><span data-icon="more"></span></button></td></tr>';
    }).join('');

    const left = '<section class="tools-card">' +
      '<label class="search-box tool-search"><span class="si" data-icon="search"></span>' +
      '<input type="text" placeholder="搜索 API 接口..."></label>' +
      '<div class="tool-list-title">API 分类</div>' + cats + '</section>';

    const mid = '<section class="tools-card">' +
      '<div class="sec-head"><span class="t">API 接口列表</span>' +
      '<span style="margin-left:auto;font-size:13px;color:var(--text-3)">共 286 个接口</span></div>' +
      '<div class="toolbar" style="margin-bottom:12px">' +
      '<span class="select-like" style="width:130px"><select><option>全部类型</option></select><span class="chev" data-icon="chevD"></span></span>' +
      '<span class="select-like" style="width:130px"><select><option>全部状态</option></select><span class="chev" data-icon="chevD"></span></span>' +
      '<label class="search-box" style="flex:1;min-width:160px;height:38px"><span class="si" data-icon="search"></span>' +
      '<input type="text" placeholder="搜索接口名称或路径..."></label></div>' +
      '<table class="dtable"><thead><tr><th>接口名称</th><th>方法</th><th>路径</th><th>分类</th><th>状态</th><th class="c">操作</th></tr></thead>' +
      '<tbody>' + rows + '</tbody></table>' +
      '<div class="pager" style="padding:14px 0 0"><span class="total">共 286 条</span>' +
      '<button class="pg-btn" type="button"><span class="pi" data-icon="chevL"></span></button>' +
      ['1', '2', '3', '4', '5', '…', '29'].map(function (p, i) {
        return '<button class="pg-btn' + (i === 0 ? ' is-current' : '') + '" type="button">' + p + '</button>';
      }).join('') +
      '<button class="pg-btn" type="button"><span class="pi" data-icon="chevR"></span></button>' +
      '<span class="select-like pg-size"><select><option>10 条/页</option></select>' +
      '<span class="chev" data-icon="chevD"></span></span></div></section>';

    const d = API_DETAIL;
    const right = '<section class="tools-card">' +
      '<div style="display:flex;align-items:center;gap:12px">' +
      '<span style="font-size:19px;font-weight:700;color:var(--text-1)">' + d.name + '</span>' +
      '<button class="btn-blue" style="margin-left:auto;height:36px;padding:0 14px" type="button" data-act2="在测试面板中运行">' +
      '<span class="bi" data-icon="play"></span>在测试面板中运行</button></div>' +
      '<div class="chip-row" style="margin:12px 0 4px">' +
      '<span class="tag blue">' + d.cat + '</span><span class="tag gray">' + d.soft + '</span>' +
      '<span class="tag green" style="margin-left:auto"><span class="dot"></span>支持</span></div>' +
      '<div class="api-tabs">' + d.tabs.map(function (t, i) {
        return '<button class="api-tab' + (i === 0 ? ' is-active' : '') + '" type="button" data-atab="' + t + '">' + t + '</button>';
      }).join('') + '</div>' +
      '<div class="kv-list" style="margin-top:14px">' + d.kv.map(function (r) {
        return '<div class="r"><dt style="width:88px">' + r[0] + '</dt><dd>' + r[1] + '</dd></div>';
      }).join('') + '</div>' +
      '<div class="sec-head" style="margin-top:18px"><span class="t" style="font-size:15px">请求示例</span>' +
      '<button class="btn-w" style="margin-left:auto" type="button" data-copy="请求示例"><span class="bi" data-icon="copy"></span>复制</button></div>' +
      codeBlock(d.req) +
      '<div class="sec-head" style="margin-top:16px"><span class="t" style="font-size:15px">响应示例</span>' +
      '<button class="btn-w" style="margin-left:auto" type="button" data-copy="响应示例"><span class="bi" data-icon="copy"></span>复制</button></div>' +
      codeBlock(d.res) + '</section>';

    return '<div class="tools-split">' + left + mid + right + '</div>';
  }
  /* ---------- MCP 工具（mcp 标签） ---------- */
  const MCP_TOOLS = [
    { id: 'midas_doc', name: 'midas_doc', desc: '文档操作与模型管理', color: '#0B6BFB', icon: 'fileText' },
    { id: 'midas_db_query', name: 'midas_db_query', desc: '数据库查询操作', color: '#0B6BFB', icon: 'db' },
    { id: 'midas_db_assign', name: 'midas_db_assign', desc: '数据库写入与修改', color: '#8B5CF6', icon: 'tools' },
    { id: 'midas_db_delete', name: 'midas_db_delete', desc: '数据库删除操作', color: '#FE3B36', icon: 'trash' }
  ];
  const MCP_DETAIL = {
    id: 'midas_doc', name: 'midas_doc', color: '#0B6BFB', icon: 'fileText',
    desc: '文档操作与模型管理，支持打开、保存、关闭、另存为等操作',
    chips: [{ t: 'DOC', cls: 'blue' }, { t: '核心工具', cls: 'green' }],
    note: '提供 MIDAS 文档相关操作，包括打开模型、保存模型、关闭模型、另存为、获取文档信息等。',
    soft: [
      { k: 'C', n: 'CIVIL NX', c: '#0B6FFE' },
      { k: 'G', n: 'GEN NX', c: '#06A65A' },
      { k: 'F', n: 'FEA NX', c: '#8B5CF6' },
      { k: 'N', n: 'NFX', c: '#F79009' }
    ],
    inJson: [
      '{', '  "type": "object",', '  "properties": {',
      '    "command": { "type": "string",',
      '      "description": "操作命令，如 OPEN、SAVE、CLOSE" },',
      '    "argument": { "type": "object",',
      '      "description": "命令参数" }',
      '  },', '  "required": ["command"]', '}'
    ],
    outJson: [
      '{', '  "type": "object",', '  "properties": {',
      '    "success": { "type": "boolean" },',
      '    "message": { "type": "string" },',
      '    "data": { "type": "object" }',
      '  }', '}'
    ]
  };
  const MCP_EXAMPLE = {
    models: ['打开模型（OPEN）', '保存模型（SAVE）', '关闭模型（CLOSE）', '获取模型信息（INFO）'],
    req: [
      '{', '  "command": "OPEN",', '  "argument": {',
      '    "file_path": "D:/Projects/test.mcb"', '  }', '}'
    ],
    res: [
      '{', '  "success": true,', '  "message": "模型打开成功",', '  "data": {',
      '    "file_path": "D:/Projects/test.mcb",',
      '    "model_name": "Test Model",',
      '    "version": "2024"', '  }', '}'
    ]
  };
  const MCP_REGISTRY = [
    ['OPEN', 'POST', '/doc/OPEN', '打开模型文件'],
    ['SAVE', 'POST', '/doc/SAVE', '保存当前模型'],
    ['SAVEAS', 'POST', '/doc/SAVEAS', '另存为模型'],
    ['CLOSE', 'POST', '/doc/CLOSE', '关闭当前模型'],
    ['INFO', 'GET', '/doc/INFO', '获取文档信息']
  ];
  const MCP_TIPS = [
    '文件路径请使用绝对路径。',
    '确保 MIDAS 软件已启动并启用 API 服务。',
    '大文件操作可能需要较长时间，请关注任务状态。'
  ];

  /* 标签行（mcp / schema 等页共用同一组标签，位置由外层容器决定） */
  function tabsNav(sub) {
    return TABS.map(function (t) {
      return '<button class="tools-tab' + (t.id === sub ? ' is-active' : '') +
        '" type="button" data-ttab="' + t.id + '">' + t.label + '</button>';
    }).join('');
  }

  /* 无行号的代码块（MCP 工具页） */
  function codeLines(lines) {
    return '<div class="tm-code">' + lines.map(function (l) {
      return '<div class="cl">' + hl(l) + '</div>';
    }).join('') + '</div>';
  }

  function mcpPage() {
    const d = MCP_DETAIL;
    const ex = MCP_EXAMPLE;

    const head = '<section class="tm-head">' +
      '<span class="tm-accent"></span>' +
      '<h1 class="tm-title">工具与接口</h1>' +
      '<p class="tm-sub">管理 MCP 工具、MIDAS API 接口和能力映射，支持多软件、多版本</p>' +
      '<button class="tm-io" type="button" data-more="导入 / 导出">' +
        '<span class="bi" data-icon="upload"></span>导入/导出</button>' +
      '</section>' +
      '<nav class="tm-tabs">' + tabsNav('mcp') + '</nav>';

    /* ---- 左：MCP 工具列表 ---- */
    const items = MCP_TOOLS.map(function (t) {
      return '<button class="tm-item' + (t.id === d.id ? ' is-active' : '') +
        '" type="button" data-tool="' + t.id + '">' +
        '<span class="tm-ico" style="background:' + t.color + '" data-icon="' + t.icon + '"></span>' +
        '<span class="tm-meta"><span class="tm-name">' + t.name + '</span>' +
        '<span class="tm-desc">' + t.desc + '</span></span>' +
        '<span class="ch" data-icon="chevR"></span></button>';
    }).join('');
    const left = '<section class="tm-card tm-list">' +
      '<label class="tm-search"><span class="si" data-icon="search"></span>' +
      '<input type="text" placeholder="搜索工具名称或描述..."></label>' +
      '<div class="tm-list-title">MCP 工具列表</div>' + items + '</section>';

    /* ---- 中：工具详情 ---- */
    const soft = d.soft.map(function (s) {
      return '<span class="tm-soft"><span class="k" style="background:' + s.c + '">' + s.k +
        '</span><span class="n">' + s.n + '</span></span>';
    }).join('');
    const mid = '<section class="tm-card tm-detail">' +
      '<div class="tm-dhead"><span class="t">工具详情</span>' +
        '<span class="tm-badge"><span class="dot"></span>启用</span></div>' +
      '<div class="tm-panel">' +
        '<span class="tm-bigico" style="background:' + d.color + '" data-icon="' + d.icon + '"></span>' +
        '<div class="tm-ptxt">' +
          '<div class="tm-pname">' + d.name + '</div>' +
          '<div class="tm-pdesc">' + d.desc + '</div>' +
          '<div class="tm-chips">' + d.chips.map(chip).join('') + '</div>' +
        '</div></div>' +
      '<div class="tm-kv">' +
        '<div class="r"><div class="k">工具名称</div><div class="v mono">' + d.name + '</div></div>' +
        '<div class="r"><div class="k">工具说明</div><div class="v">' + d.note + '</div></div>' +
        '<div class="r last"><div class="k">支持的软件</div><div class="v"><div class="tm-softrow">' +
          soft + '</div></div></div>' +
      '</div>' +
      '<div class="tm-sec"><span class="t">输入参数 Schema</span>' +
        '<button class="tm-btnw" type="button" data-more="完整 Schema">查看完整 Schema</button></div>' +
      '<div class="tm-codewrap">' + codeLines(d.inJson) +
        '<button class="tm-copy" type="button" data-copy="输入参数 Schema" data-icon="copy"></button></div>' +
      '<div class="tm-sec sec2"><span class="t">输出结果 Schema</span>' +
        '<button class="tm-btnw" type="button" data-more="完整 Schema">查看完整 Schema</button></div>' +
      '<div class="tm-codewrap">' + codeLines(d.outJson) +
        '<button class="tm-copy" type="button" data-copy="输出结果 Schema" data-icon="copy"></button></div>' +
      '</section>';

    /* ---- 右：示例请求 / 示例响应 / 相关接口 / 使用提示 ---- */
    const opts = ex.models.map(function (m) {
      return '<option>' + m + '</option>';
    }).join('');
    const regRows = MCP_REGISTRY.map(function (r) {
      return '<tr><td class="n1">' + r[0] + '</td><td class="n2">' + r[1] + '</td>' +
        '<td class="n3">' + r[2] + '</td><td class="n4">' + r[3] + '</td>' +
        '<td class="n5"><span class="ok"><span class="dot"></span>支持</span></td></tr>';
    }).join('');
    const tips = MCP_TIPS.map(function (t, i) {
      return '<li><span class="no">' + (i + 1) + '.</span>' + t + '</li>';
    }).join('');
    const right = '<section class="tm-card tm-right">' +
      '<div class="tm-row"><span class="t">示例请求</span>' +
        '<span class="tm-select"><select>' + opts + '</select>' +
        '<span class="chev" data-icon="chevD"></span></span></div>' +
      '<div class="tm-codewrap">' + codeLines(ex.req) +
        '<button class="tm-copy" type="button" data-copy="示例请求" data-icon="copy"></button></div>' +
      '<div class="tm-runrow"><button class="tm-run" type="button" data-more="测试面板">' +
        '<span class="bi" data-icon="play"></span>在测试面板中运行</button></div>' +
      '<div class="tm-row row2"><span class="t">示例响应</span></div>' +
      '<div class="tm-codewrap">' + codeLines(ex.res) +
        '<button class="tm-copy" type="button" data-copy="示例响应" data-icon="copy"></button></div>' +
      '<div class="tm-row row3"><span class="t">相关接口（Registry）</span>' +
        '<a class="tm-link" href="javascript:void(0)" data-more="所有接口">查看所有接口' +
        '<span class="chev" data-icon="chevR"></span></a></div>' +
      '<table class="tm-table"><thead><tr><th>接口名称</th><th>方法</th><th>路径</th>' +
        '<th>说明</th><th></th></tr></thead><tbody>' + regRows + '</tbody></table>' +
      '<div class="tm-tips"><span class="ic" data-icon="bulb"></span>' +
        '<div class="bd"><div class="tt">使用提示</div><ul>' + tips + '</ul></div></div>' +
      '</section>';

    return '<div class="tools-page">' + head +
      '<div class="tm-split">' + left + mid + right + '</div></div>';
  }

  function render(sub) {
    sub = sub || 'schema';
    if (sub === 'mcp') return mcpPage();
    const d = DETAIL;
    const HD = HEADS[sub] || HEADS.schema;
    const tabs = tabsNav(sub);

    const head = '<section class="tools-head">' +
      '<span class="tools-head-accent"></span>' +
      '<nav class="crumbs" style="padding:15px 24px 0;position:absolute;left:0;top:0">' +
        '<span class="back" data-icon="arrowLeft"></span>' +
        '<a href="#/home">首页</a><span class="sep">›</span>' +
        '<a href="#/tools">工具与接口</a><span class="sep">›</span>' +
        '<span class="cur">' + HD.crumb + '</span></nav>' +
      '<h1 class="tools-title">' + HD.title + '</h1>' +
      '<p class="tools-sub">' + HD.sub + '</p>' +
      '<div class="tools-head-right">' +
        '<span class="fld"><span class="lb">选择软件</span>' +
          '<span class="select-like"><span class="sw-row"><span class="sw-ico">C</span>' +
          '<select><option>CIVIL NX (本机)</option></select></span><span class="chev" data-icon="chevD"></span></span></span>' +
        '<span class="fld"><span class="lb">选择版本</span>' +
          '<span class="select-like"><select><option>2024 (v1.2.0)</option></select>' +
          '<span class="chev" data-icon="chevD"></span></span></span>' +
      '</div>' +
      '<nav class="tools-tabs">' + tabs + '</nav></section>';

    if (sub === 'api') return head + apiTab();
    if (sub !== 'schema') {
      return head + '<section class="tools-card" style="padding:40px;text-align:center">' +
        '<p style="color:var(--text-3)">该标签页（' + HD.title + '）将按原稿依次还原。</p></section>';
    }

    const list = TOOLS.map(function (t) {
      return '<button class="tool-item' + (t.id === d.id ? ' is-active' : '') + '" type="button" data-tool="' + t.id + '">' +
        '<span class="tool-ico" style="background:' + t.color + '" data-icon="' + t.icon + '"></span>' +
        '<span class="tool-meta"><span class="tool-name">' + t.name + '</span>' +
        '<span class="tool-path">' + t.path + '</span></span>' +
        '<span class="ch" data-icon="chevR"></span></button>';
    }).join('');

    const kv = d.kv.map(function (r) {
      return '<div class="cell"><div class="k">' + r[0] + '</div>' +
        '<div class="v' + (r[2] ? '' : ' txt') + '">' + r[1] + '</div></div>';
    }).join('');

    const left = '<section class="tools-card">' +
      '<label class="search-box tool-search"><span class="si" data-icon="search"></span>' +
      '<input type="text" placeholder="搜索工具名称或路径..."></label>' +
      '<div class="tool-list-title">MCP 工具列表</div>' + list + '</section>';

    const mid = '<section class="tools-card">' +
      '<div class="detail-head">' +
        '<span class="big-ico" style="background:' + d.color + '" data-icon="' + d.icon + '"></span>' +
        '<span class="nm">' + d.name + '</span>' +
        '<span class="badge tag green"><span class="dot"></span>已启用</span>' +
      '</div>' +
      '<div class="chip-row">' + d.chips.map(chip).join('') + '</div>' +
      '<p class="detail-desc">' + d.desc + '</p>' +
      '<div class="kv-grid">' + kv + '</div>' +
      '<div class="sec-head"><span class="t">输入 Schema</span>' +
        '<span class="select-like"><select><option>JSON Schema (Draft 7)</option></select>' +
        '<span class="chev" data-icon="chevD"></span></span>' +
        '<button class="btn-w" type="button" data-copy="输入 Schema"><span class="bi" data-icon="copy"></span>复制</button></div>' +
      codeBlock(d.inJson) +
      '<div class="sec-head" style="margin-top:16px"><span class="t">输入参数说明</span></div>' +
      ptable(d.inParams.cols, d.inParams.rows) + '</section>';

    const right = '<div style="display:flex;flex-direction:column;gap:11px">' +
      '<section class="tools-card">' +
        '<div class="sec-head"><span class="t">输出 Schema</span>' +
        '<span class="select-like"><select><option>JSON Schema (Draft 7)</option></select>' +
        '<span class="chev" data-icon="chevD"></span></span>' +
        '<button class="btn-w" type="button" data-copy="输出 Schema"><span class="bi" data-icon="copy"></span>复制</button></div>' +
        codeBlock(d.outJson) + '</section>' +
      '<section class="tools-card">' +
        '<div class="sec-head"><span class="t">输出参数说明</span></div>' +
        ptable(d.outParams.cols, d.outParams.rows) + '</section></div>';

    const bottom = '<div class="tools-bottom">' +
      '<section class="verify-card">' +
        '<div style="display:flex;align-items:center;gap:14px">' +
        '<span style="font-size:16px;font-weight:700;color:var(--text-1)">Schema 验证</span>' +
        '<span class="seg"><button class="is-on" type="button" data-seg="输入验证">输入验证</button>' +
        '<button type="button" data-seg="输出验证">输出验证</button></span></div>' +
        '<div class="verify-row"><span class="s-input"><input type="text" placeholder="输入 JSON 数据进行验证..."></span>' +
        '<button class="btn-blue" type="button" data-verify="1"><span class="bi" data-icon="play"></span>验证</button></div>' +
      '</section>' +
      '<section class="result-card">' +
        '<span class="ok" data-icon="check"></span>' +
        '<span class="rt"><b>Schema 验证通过</b><span>输入数据符合 Schema 定义规范。</span>' +
        '<a class="link-more" href="javascript:void(0)" data-more="查看详细结果">查看详细结果' +
        '<span class="chev" data-icon="chevR"></span></a></span></section></div>';

    return head + '<div class="tools-split">' + left + mid + right + '</div>' + bottom;
  }

  function mount(root, sub) {
    root.querySelectorAll('[data-ttab]').forEach(function (b) {
      b.addEventListener('click', function () {
        location.hash = b.dataset.ttab === 'schema' ? '#/tools/schema' : '#/tools/' + b.dataset.ttab;
      });
    });
    root.querySelectorAll('[data-tool]').forEach(function (b) {
      b.addEventListener('click', function () {
        const nm = b.querySelector('.tool-name, .tm-name');
        window.Toast.show('已选择工具：' + (nm ? nm.textContent : b.dataset.tool));
      });
    });
    root.querySelectorAll('[data-seg]').forEach(function (b) {
      b.addEventListener('click', function () {
        b.parentNode.querySelectorAll('button').forEach(function (x) { x.classList.remove('is-on'); });
        b.classList.add('is-on');
      });
    });
    root.querySelectorAll('[data-verify]').forEach(function (b) {
      b.addEventListener('click', function () { window.Toast.show('Schema 验证通过'); });
    });
    root.querySelectorAll('[data-copy]').forEach(function (b) {
      b.addEventListener('click', function () { window.Toast.show('已复制：' + b.dataset.copy); });
    });
  }

  window.PageTools = { data: function () { return { tools: TOOLS, detail: DETAIL, tabs: TABS }; }, render: render, mount: mount };
})();
