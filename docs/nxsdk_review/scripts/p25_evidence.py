"""Generate the evidence JSON consumed by registry/tools/import_nxsdk_evidence.py, plus errata CSV."""
import csv
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
LOCAL = Path(r"E:\MCP\MMCP")
OUT = LOCAL / "docs" / "nxsdk_review"
OUT.mkdir(parents=True, exist_ok=True)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


manifest = load(LOCAL / "registry" / "manifest.json")
by_key = {e["key"]: e for e in manifest["endpoints"]}

# ---------- evidence JSON for the import tool ----------
pm = load(LOCAL / ".tmp_analysis" / "product_matrix_v2.json")
TODB = {"/DB/IEHG-GL-M1", "/DB/IEHG-PSS-M1", "/DB/IEHG-TRUSS-M1"}

corrections = []
for r in pm["tier1"]:
    key = r["key"]
    e = by_key.get(key)
    if not e:
        continue
    note = r.get("note", "")
    corrections.append({
        "key": key,
        "definition": e["definition"],
        "field": "products",
        "from": e["products"],
        "to": ["CIVIL_NX"],
        "tier": "A",
        "solver": e["solver"],
        "availability": e["availability"],
        "unavailable_on": e["unavailable_on"],
        "evidence": [
            "instances.yaml 第 16 行：gen-local「缺 21 个 Hyper-S 变体」",
            f"本条目 unavailable_on={e['unavailable_on']}（该产品实例上 404）",
            "SDK docs/CLAUDE.md：Hyper-S (-M1) endpoints are Civil NX only; they 404 under Gen",
            "SDK schema/hyper-s-info.json：product=civil，8 端点由 Civil NX 抓取",
            f"服务端 GET /info{key}：gen 无 Schema civil 有 Schema" + ("（/info 已知例外）" if key in TODB else ""),
            "SDK contracts/endpoints/*.yaml：18 个 -M1 契约全部 products: [civil]",
        ],
        "requires_adjudication": True,
    })

for r in pm["tier2_under"]:
    e = by_key.get(r["key"])
    if not e:
        continue
    to = sorted(set(e["products"]) | {"CIVIL_NX"})
    corrections.append({
        "key": r["key"], "definition": e["definition"], "field": "products",
        "from": e["products"], "to": to, "tier": "B",
        "solver": e["solver"], "availability": e["availability"],
        "unavailable_on": e["unavailable_on"],
        "evidence": [f"服务端 GET /info{r['route']}：两产品均有 Schema；我方只声明 {e['products']}",
                     "SDK 契约 products 含 civil"],
        "requires_adjudication": True,
    })

for r in pm["tier2_over"]:
    e = by_key.get(r["key"])
    if not e:
        continue
    to = sorted(set(e["products"]) - {"CIVIL_NX"})
    if not to:
        continue
    corrections.append({
        "key": r["key"], "definition": e["definition"], "field": "products",
        "from": e["products"], "to": to, "tier": "C",
        "solver": e["solver"], "availability": e["availability"],
        "unavailable_on": e["unavailable_on"],
        "evidence": [f"服务端 GET /info{r['route']}：civil 无 Schema，gen 有 Schema",
                     "SDK 契约 products 不含 civil"],
        "requires_adjudication": True,
    })

# ---- non-/db/* disagreements, sourced from the SDK contracts' `products` ----
import yaml
PROD = {"gen": "GEN_NX", "civil": "CIVIL_NX"}
by_uri = {}
for e in manifest["endpoints"]:
    by_uri.setdefault(("/" + e["uri"].strip("/")).upper(), []).append(e)

db_routes = {c["key"] for c in corrections}
for p_ in sorted((LOCAL / ".tmp_nxsdk" / "contracts" / "endpoints").glob("*.yaml")):
    c = yaml.safe_load(p_.read_text(encoding="utf-8"))
    route = c["endpoint"].upper()
    if route.startswith("/DB/"):
        continue
    sdk_p = {PROD[x] for x in c.get("products", []) if x in PROD}
    ours = by_uri.get(route, [])
    if not sdk_p or not ours:
        continue
    e = ours[0]
    if e["key"] in db_routes:
        continue
    our_p = {x for x in e["products"] if x in ("GEN_NX", "CIVIL_NX")}
    others = {x for x in e["products"] if x not in ("GEN_NX", "CIVIL_NX")}  # e.g. CIVIL_DESIGNER
    if not our_p or sdk_p == our_p:
        continue
    if sdk_p - our_p:            # tier B: SDK declares a product we lack
        to = sorted((our_p | sdk_p) | others)
        tier = "B"
    else:                        # tier C: we declare a product SDK does not
        to = sorted((our_p & sdk_p) | others)
        tier = "C"
    if not to:
        continue
    corrections.append({
        "key": e["key"], "definition": e["definition"], "field": "products",
        "from": e["products"], "to": to,
        "tier": tier,
        "solver": e["solver"], "availability": e["availability"],
        "unavailable_on": e["unavailable_on"],
        "evidence": [f"SDK 契约 {p_.name}: products={sorted(sdk_p)}",
                     "（非 /db/* 端点，/info 不作为判据）"],
        "requires_adjudication": True,
    })

# ---- the 3 IEHG Hyper-S exceptions: /info 404s on BOTH products, so they are excluded
#      from the /info-based matrix by construction. Their evidence is weaker but still one-directional:
#      they are `-M1` + solver HYPER_S + unavailable_on [gen-local], and the SDK lists them in
#      coverage.json as products ['civil'] and attempted to capture them in hyper-s-info.json (civil).
for key in ("DB.IEHG-GL-M1", "DB.IEHG-PSS-M1", "DB.IEHG-TRUSS-M1"):
    e = by_key.get(key)
    if not e:
        continue
    corrections.append({
        "key": key, "definition": e["definition"], "field": "products",
        "from": e["products"], "to": ["CIVIL_NX"], "tier": "A",
        "solver": e["solver"], "availability": e["availability"],
        "unavailable_on": e["unavailable_on"],
        "evidence": [
            "instances.yaml 第 16 行：gen-local「缺 21 个 Hyper-S 变体」",
            f"本条目 unavailable_on={e['unavailable_on']}（gen-local 上 404）",
            "SDK docs/CLAUDE.md：Hyper-S (-M1) endpoints are Civil NX only; they 404 under Gen",
            "SDK docs/coverage.json：products=['civil']",
            "SDK schema/hyper-s-info.json（product=civil）包含该端点",
            "⚠️ 较弱：GET /info 在该端点的两个产品上都 404（对方明载为 /info 的三个例外之一）",
        ],
        "requires_adjudication": True,
    })

evidence = {
    "schemaVersion": 1,
    "source": "Dennis5882/MIDAS-API-NX-SDK (shallow clone, .tmp_nxsdk)",
    "source_files": [
        "schema/info-baseline.json (capturedAt 2026-10-11, Civil/Gen NX 2026 v2.2 build 10/10/2026)",
        "schema/hyper-s-info.json (product=civil, 2026-09-02)",
        "contracts/endpoints/*.yaml (384 contracts)",
        "docs/CLAUDE.md",
        "contracts/verification/ledger.yaml (249 records, 397 endpoints)",
    ],
    "generated_by": ".tmp_analysis/p25_evidence.py",
    "note": "外部证据，非本仓库实测。全部条目 requires_adjudication=true；工具默认预演。",
    "corrections": corrections,
}
p = OUT / "nxsdk_product_corrections.json"
p.write_text(json.dumps(evidence, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"wrote {p.name}: {len(corrections)} corrections "
      f"(A={sum(1 for c in corrections if c['tier']=='A')} "
      f"B={sum(1 for c in corrections if c['tier']=='B')} "
      f"C={sum(1 for c in corrections if c['tier']=='C')})")

# ---------- errata CSV ----------
MD_ROWS = [
    ("MD-01", "/db/STYP-M1", "方法/动词错误", "手册三处声明 DELETE，实际三种 DELETE 形式在两个产品上都被拒", "DB.STYP-M1", "methods 含 DELETE", "从 methods 移除 DELETE"),
    ("MD-02", "/db/POLC-M1", "方法/动词错误", "callout 称不提供 POST，实际 POST 建了记录且 GET 能取回", "DB.POLC-M1", "—", "确认 methods 含 POST"),
    ("MD-03", "/db/MATL-M1", "字段结构", "称与 /db/MATL 同结构，实际顶层名不同、字段数 4 vs 9、HE_* 在父端点", "DB.MATL-M1", "已独立建键", "核对字段数"),
    ("MD-04", "/db/IEHC", "类型矛盾", "WAreaSize 表标 Integer，实际 Gen /info 是 string，章节示例发 \"AUTO\"", "DB.IEHC", "我方多出含 WAreaSize 的 9 字段", "复核类型"),
    ("MD-05", "全局", "全局事实错误", "示例仍用 pre-NX 拼写；实际四扩展两对 .mgb/.mcb 与 .mgbx/.mcbz", "DOC.SAVEAS/STAGAS", "—", "全面核对扩展名"),
    ("MD-06", "/db/ELEM", "产品范围未标注", "Gen 接受 WALL，Civil NX v2.2 报不支持单元类型", "DB.ELEM", "verified 三产品", "加产品差异标注"),
    ("MD-07", "/db/FIMP", "字段层级", "Kent & Park 表把三层对象写成十个扁平顶层字段，漏 CONC/STEEL", "DB.FIMP", "verified", "核对我方层级"),
    ("MD-08", "/db/CO_S,/db/CO_T", "多键单元格", "一行压缩九个颜色键为 \"W_R\"~\"HE_B\"，读作两个字面键", "DB.CO_S/DB.CO_T", "verified", "核对是否误当字面键"),
    ("MD-09", "DESIGN DCRM-*/LLRF", "枚举不完整", "enum 只列 5/6 个，同行 description 说 19/11 个 —— 采样冒充完整值集", "DESIGN.RC...DCRM-BEAM 等", "verified", "加\"非完整值集\"标注"),
    ("MD-10", "EPMT/ELEM/RCHK/FIMP", "缺失字段(+工具缺陷)", "表漏掉同节 JSON Schema 声明的根属性；另 5 条实为对方解析器缺陷", "四端点", "verified", "核对根属性完整性"),
    ("MD-11", "SBDO/MATL/AUTOMESH/RCHK", "类型矛盾", "表与同节 schema 类型互相矛盾；AXIS_VECTOR 标 Number 实为数字数组，MATL PARAM 标 Object 实为 array", "DB.SBDO/DB.MATL/OPE.AUTOMESH/DB.RCHK", "SBDO 我方多出 AXIS_VECTOR", "复核类型"),
    ("MD-12", "七个 -M1 节", "章节空壳+/info 缺陷", "章节是空壳，唯一许可来源 /info 自身畸形（\\' 伪转义 + maxItems 位置错）", "七个 -M1", "unverified", "随 §3.1 处理"),
    ("MD-13", "/db/TDME", "键重复/歧义", "一个键 SCALE 给了两行（Number 与 Array[Object]）；/info 定案真名 aDATA", "DB.TDME", "verified", "改键名"),
    ("MD-14", "/db/TDME", "产品范围未标注", "码表混入另一产品（iGen）的值 Japan(hydration)/Japan(elastic) 且未标注", "DB.TDME", "verified", "标注产品范围"),
    ("MD-15", "/db/SECT,/db/SPFC", "必填性/语义歧义", "同一 Create Only 值用于两份不同契约；/db/SPFC 示例按原文被拒", "DB.SECT/DB.SPFC", "verified", "区分语义"),
    ("MD-16", "/db/MVHL", "必填性/条件缺失", "分支必填性写成无条件必填，未提 VEHICLE_LOAD_NUM 分支判别子", "DB.MVHL", "verified", "按分支拆 required"),
    ("MD-17", "/db/PRES", "默认值/必填性错误", "DIRECTION 行标 Optional 默认 \"NORMAL\"，省略与 \"NORMAL\" 都被拒 —— 省略即触发坏默认", "DB.PRES", "verified", "移除默认值，改为显式要求"),
    ("MD-18", "/db/THGC-M1", "枚举字面量错误", "INIT_LOAD_TYPE enum 两个选项都印成字面 0，实际是 0 与 1", "DB.THGC-M1", "unverified", "修 enum"),
    ("MD-19", "/db/THGC-M1", "必填性/条件缺失", "ITER_PARAM.LINE_SEARCH 五个子项全标 Required，同节 Python 示例只发一个（未实测）", "DB.THGC-M1", "unverified", "需 PUT 写操作实测"),
    ("MD-20", "/db/THGC-M1", "多键单元格", "Key 单元格写路径而非属性名，照印会得到 {OPT_USE, VALUE}", "DB.THGC-M1", "unverified", "核对我方 THGC-M1"),
    ("MD-21", "/db/STCT-M1", "多键单元格", "五处 Key 单元格不命名单一 wire 属性；Object 列表达父级；/info 确认真名 bSDLE/vSDLE", "DB.STCT-M1", "unverified", "核对我方 STCT-M1"),
    ("MD-22", "/db/STCT-M1", "缺失字段", "顶层表十四行无一行命名 FINAL_STAGE，/info 声明十六个根属性含它", "DB.STCT-M1", "unverified", "补 FINAL_STAGE"),
    ("MD-23", "/db/THIS-M1", "字段结构/条件缺失", "FREQ1/PERIOD1、FREQ2/PERIOD2 两行各键两个互斥属性，由 COEF_CALC 选择", "DB.THIS-M1", "unverified", "建模为条件分支"),
    ("MD-24", "DESIGN BRD-TABLE/CD-TABLE", "必填性/条件缺失", "两行标 조건부 却全节无一处给出条件", "DESIGN.RC...BRD-TABLE/CD-TABLE", "untested", "补条件"),
    ("MD-25", "/db/MVLDeu", "类型矛盾+缺失成员", "OPT_COMB 标 String 实为整数；两个数组无成员行", "DB.MVLDEU", "verified", "核对类型与成员"),
    ("MD-26", "/db/REBR", "缺失字段+层级错误", "表编号 (1)-(6) 但 ID/ELEMS 无行；第三表四行分属两层未说明", "DB.REBR", "verified", "见 MD-34"),
    ("MD-27", "/db/RCHK", "类型矛盾", "表与同节 schema 在 integer/number 上五个字段全部相反；示例发整数无法定案", "DB.RCHK", "verified", "需实测定案"),
    ("MD-28", "/ope/AUTOMESH", "必填性错误+缺失成员", "互斥二选一的两字段都标 Required；INCLUDE_INTERIOR_LINES 不列成员", "OPE.AUTOMESH", "untested", "改为互斥二选一"),
    ("MD-29", "DESIGN REBB", "字段结构/命名错误", "schema/表与三个示例描述不同 payload，该节自述以示例为准", "DESIGN.RC...REBB", "verified", "以示例为准复核"),
    ("MD-30", "DESIGN REBR", "JSON Schema 关键字误用", "integer 字段 MAIN_BAR.NUM 上写了只对数组有效的 minItems: 4", "DESIGN.RC...REBR", "verified", "移除误用关键字"),
    ("MD-31", "DESIGN TABLE", "缺失成员", "NODE_ELEMS 类型单元格写 Object (oneOf) 且不列任何成员", "DESIGN.RC...TABLE(+BEAM/BRACE)", "untested", "补成员"),
    ("MD-32", "DESIGN SRC OCHECK", "路由错误+致命风险", "文档 URL 干净 404；实际路由移入 /TEMP/，且该路由会终止 NX 会话并占住 license（4 次复现）", "DESIGN.SRC.AIK-SRC2K.OCHECK", "untested, unavailable_on=[gen-local]", "核实 /TEMP/ 前缀；扩展 risk 模型"),
    ("MD-33", "DESIGN CD-TABLE/BRD-TABLE", "必填性/条件缺失", "二者是恰好其一，同章另七节都这么说，只这两节不说", "DESIGN.RC...CD-TABLE/BRD-TABLE", "untested", "补 oneOf"),
    ("MD-34", "/db/REBR", "字段结构/命名错误", "手册形状与 /info 逐字段不符：vMAIN_BAR 数组、D0 非 DO、整数 HOOP_TYPE", "DB.REBR", "verified, HOOP_TYPE=string", "按 /info 重建 item 形状"),
    ("MD-35", "六个 /db/LCOM-*", "缺失字段", "章末比较表说五个\"无额外字段\"，实际六个都有同样四个", "DB.LCOM-GEN/-STEEL/-SRC/-CONC", "verified", "补四个字段"),
    ("MD-36", "LCOM-*/POGD", "本 SDK 工具缺陷(非手册)", "手册用最显式的 (vCOMB) 命名父级形式，对方解析器唯独不读这一种", "—", "—", "不改"),
    ("MD-37", "/db/POGD-M1", "字段命名错误", "ANALYSIS_STOP 四项主张：两处字段名与 /info 不同（手册自相矛盾），两处 /info 完全不声明", "DB.POGD-M1", "unverified", "改 products + 核字段名"),
    ("MD-38", "/db/STRPSSM", "字段命名错误", "POINT1/POINT2 条目把 description 文字当成了键（PY/PZ vs 实际 Y/Z）", "DB.STRPSSM", "verified；我方 4 缺 4 多", "修键名（与 /info 吻合）"),
    ("MD-39", "/db/STOR", "缺失字段", "三处都只给十五个属性，实际有第十六个", "DB.STOR", "verified", "补字段"),
    ("MD-40", "/db/RPSC", "字段层级错误", "行 5 把 MBAR_ITEMS 放在根，实际低一层在 MBARS 数组内", "DB.RPSC", "verified", "修层级"),
    ("MD-41", "九个 /db/* 节/15 字段", "缺失字段", "各节表自称完整，/info 每节多声明一至六个", "跨多节", "—", "逐节核对"),
    ("MD-42", "/db/GRDP", "本 SDK 工具缺陷(非手册)", "手册用散文列出十五个成员且全对，是解析器只读表格行", "—", "—", "不改"),
    ("MD-43", "/db/SLANch", "字段层级错误", "唯一 Parameters 表其实是 LANE_ITEMS 的数组成员表，记录自身八字段无表", "DB.SLANCH", "verified", "修层级"),
    ("MD-44", "五数组+一对象", "本 SDK 工具缺陷(非手册)", "成员都在编号表格行之外陈述，手册全对，解析器全没读到", "—", "—", "不改"),
    ("MD-45", "/db/LLANtr,/db/SLANop", "缺失字段", "两节完全未记录 SPECIAL_LANE_ITEMS、OPT_STRADD、CHINA_ITEMS", "DB.LLANTR/DB.SLANOP", "verified；OPT_STRADD=integer", "补字段 + 修类型"),
    ("MD-46", "十个 /db/* 节/73 字段", "产品差异未标注", "两个产品声明的记录不同，手册每节只有一张无产品限定的表", "跨十节", "—", "核对 product_overrides 覆盖度"),
    ("MD-47", "/db/TDMT", "缺失字段(分支)", "CODE=\"EUROPEAN\" 是第三个分支，带两个表从未命名的字段", "DB.TDMT", "verified", "补分支字段"),
    ("MD-48", "/db/MVHL", "缺失字段", "表只记录 VEH_DEFAULT，/info 多声明十一个 country 对象（共 48 字段）", "DB.MVHL", "verified", "补 country 对象"),
    ("MD-49", "/post/TABLE", "取值/枚举错误", "表与 schema 给 REACTIONSURFACESPRING，只有示例给对的 REACTIONLSURFACESPRING（多一个 L）", "POST.TABLE.*", "199 键", "查 TABLE_TYPE 枚举是否含错拼"),
    ("MD-50", "/db/MVCTch", "本 SDK 工具缺陷(非手册)", "双 Key 列的表只被读了一半；BTYPE 写在粗体引导句里", "—", "—", "不改"),
    ("MD-51", "/ope/MEMB", "拼写错误", "官方表把键拼成 SELETION_TYPE（少一个 C）", "OPE.MEMB", "untested", "核对我方拼写"),
    ("MD-52", "/ope/MEMB", "示例不可运行(locale 分歧)", "同一文章 id、同一 updated_at，两个 locale 给不同请求示例，ko 那个是错的", "OPE.MEMB", "untested", "以 en-us 为准"),
    ("MD-53", "/db/MATD", "示例不可运行", "示例让强度看起来由等级推导，实际强度是必需输入", "DB.MATD", "verified", "手册示例标注"),
    ("MD-54", "/db/FIMP", "示例不可运行(转写引入)", "章节示例的三个数值不满足产品自述关系；文章并未印这些值", "DB.FIMP", "verified", "标注示例为转写引入"),
    ("MD-55", "/db/TDMF", "示例不可运行+缺失字段", "示例在两个产品上都被拒；/info 另有未文档化的 ELAST", "DB.TDMF", "verified", "补 ELAST + 修示例"),
    ("MD-56", "/db/EPMT on Civil", "产品差异未标注", "同一 payload Gen 通过、Civil 答 Wrong Field，而 /info 两产品形状相同", "DB.EPMT", "verified；我方多出 MASONRY 13 字段", "加产品差异标注"),
    ("MD-57", "/db/SPLC", "必填性错误", "行 25-29 六个字段标 Required，实际全部可省略", "DB.SPLC", "verified", "核对我方 required"),
    ("MD-58", "/db/STCT", "必填性错误", "vSDLE 行 9 标 Required 且无条件，实际 bSDLE 关闭时非必需", "DB.STCT", "verified", "改为条件必填"),
    ("MD-59", "/db/ELEM", "必填性错误+产品范围", "四个 Required 行实际都可选；Civil 拒绝所有 WALL", "DB.ELEM", "verified", "与 MD-06 合并处理"),
    ("MD-60", "/db/SPFC", "字段层级错误", "EURO2004 表把三个字段放 OPT，该 body 双产品答 Unknown Error，/info 说在 STR", "DB.SPFC", "verified", "修层级"),
    ("MD-61", "/db/MVHL", "字段语义/选择器错误", "标题说 STANDARD_CODE 选择对象，实际是 MVLD_CODE", "DB.MVHL", "verified", "改选择器名"),
    ("MD-62", "/ope/DIVIDEELEM", "必填性/条件缺失", "Unequal/ParametricUnequal 六个字段标 Required 且无条件，实际按 Equal 行坐标轴规则", "OPE.DIVIDEELEM", "untested", "建模条件"),
]

p = OUT / "nxsdk_manual_errata.csv"
with open(p, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["MD", "受影响端点", "缺陷类型", "手册问题", "我方 registry 键", "我方现状", "建议动作"])
    w.writerows(MD_ROWS)
print(f"wrote {p.name}: {len(MD_ROWS)} rows")
