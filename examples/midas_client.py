# -*- coding: utf-8 -*-
"""MIDAS Open API 参考客户端（由 Registry 驱动）。

特性：
  * REST 调用（GET / POST / PUT / DELETE），自动按 Registry 的 risk.retry 决定是否重试
  * 按 Registry 的 wrapper.write 自动包装请求体（Assign / Argument）
  * Registry key -> URI / method 解析，支持 product 维度
  * **产品感知的响应判定**：NX 系与 CIVIL_DESIGNER 的响应封装与错误语义完全不同
  * **破坏性调用护栏**：拒绝不带显式主体的 DELETE（NX 系该操作会删除全表且不报错）
  * `info/db/{CODE}` Schema 自省
  * WebSocket 接收长任务推送（Designer / NX 长任务）

用法：
    from midas_client import MidasClient
    c = MidasClient(base_url="https://moa-engineers.midasit.com:443/gen", mapi_key="...")
    c.call("DB.NODE", method="GET")
    c.call("POST.TABLE.BEAMFORCE", payload={"Argument": {...}})
"""
import json
import os
import re
import time
import urllib.error
import urllib.request

REGISTRY_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "registry")

# 响应封装 → 产品档案
PROFILE_NX = "NX_FAMILY"          # GEN_NX / CIVIL_NX：{"<TABLE>": {...}}，未知 URI 返回 404
PROFILE_DESIGNER = "DESIGNER"     # CIVIL_DESIGNER：{"command","function","result":{...}}，任何 URI 都返回 200

# CIVIL_DESIGNER result.message[].content → 错误码
DESIGNER_MESSAGE_CODES = {
    "不支持该操作方法": "METHOD_NOT_ALLOWED",
    "权限不足": "AUTH_FAILED",
    "未找到": "ENDPOINT_NOT_FOUND",
    "未打开模型": "PROJECT_NOT_OPENED",
    "未打开项目": "PROJECT_NOT_OPENED",
}


def infer_profile(base_url):
    """按 base url 推断产品档案。可用 MidasClient(profile=...) 覆盖。"""
    u = (base_url or "").lower().rstrip("/")
    if u.endswith("/cdn"):
        return PROFILE_DESIGNER
    return PROFILE_NX


def infer_product(base_url):
    """按 base url 推断实例产品（决定请求体包装方式）。"""
    u = (base_url or "").lower().rstrip("/")
    for suffix, prod in (("/gen", "GEN_NX"), ("/civil", "CIVIL_NX"), ("/cdn", "CIVIL_DESIGNER")):
        if u.endswith(suffix):
            return prod
    return None


def parse_methods(raw):
    """manifest 的 methods 多为 'POST, GET, PUT, DELETE' 逗号串（少数用 '/' 分隔）；
    YAML 定义里是 list。统一解析为规范化的大写方法列表。"""
    if not raw:
        return []
    if isinstance(raw, str):
        return [m.upper() for m in re.split(r"[,/\s]+", raw) if m.strip()]
    return [str(m).strip().upper() for m in raw if str(m).strip()]


def classify_response(key, body):
    """按响应封装判定调用结果。返回 (status, code, detail)。

    status ∈ OK / OK_EMPTY / INDETERMINATE / ERROR
    code   仅在 status == ERROR 时有意义（MidasError 错误码）

    实测两种封装：
      * NX 系（GEN_NX / CIVIL_NX）：根键为表名，如 {"NODE": {...}}；
        未知 URI 返回 HTTP 404 + {"error": {...}}；空表返回 200 + {"message": ""}。
      * CIVIL_DESIGNER：{"command","function","result":{"return_value","message"}}；
        **任何 URI 都返回 HTTP 200**，唯一可靠错误信号是 message[].type == "错误"。
        因此 message 为空且无数据时只能判为 INDETERMINATE —— 不得当作成功。
    """
    if not isinstance(body, dict):
        return "OK", "", ""
    if "error" in body:
        txt = str(body["error"])
        low = txt.lower()
        # 客户端/项目状态类错误：与端点缺陷区分（实测见报告附录 G）
        if "project is not opened" in low:
            return "ERROR", "PROJECT_NOT_OPENED", txt[:120]
        if "client does not exist" in low:
            return "ERROR", "CLIENT_NOT_CONNECTED", txt[:120]
        return "ERROR", "MIDAS_ERROR", txt[:120]
    res = body.get("result")
    if isinstance(res, dict):  # CIVIL_DESIGNER 封装
        msgs = res.get("message") or []
        errs = [m for m in msgs if isinstance(m, dict) and m.get("type") == "错误"]
        if errs:
            content = str(errs[0].get("content", ""))
            return ("ERROR", DESIGNER_MESSAGE_CODES.get(content.strip(), "MIDAS_ERROR"),
                    content[:120])
        if any(isinstance(m, dict) and m.get("type") == "正常" for m in msgs):
            return "OK", "", ""
        return "INDETERMINATE", "", "Designer: message 为空，无法判定端点是否存在"
    if list(body.keys()) == ["message"]:  # NX 系：{"message": ""}
        return "OK_EMPTY", "", "端点已路由，返回空 message（表存在但当前无数据）"
    return "OK", "", ""


class MidasError(Exception):
    """结构化错误，字段对齐主开发文档 §104 的失败模型。"""

    def __init__(self, code, message, details=None, http_status=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.details = details or {}
        self.http_status = http_status

    def to_dict(self):
        return {"success": False,
                "error": {"code": self.code, "message": self.message,
                          "details": self.details, "http_status": self.http_status}}


class MidasClient:
    def __init__(self, base_url, mapi_key, timeout=30, registry_root=REGISTRY_ROOT,
                 max_retry=2, verbose=False, profile=None, product=None,
                 allow_unscoped_delete=False, allow_global_delete=False):
        self.base_url = base_url.rstrip("/")
        self.mapi_key = mapi_key
        self.timeout = timeout
        self.registry_root = registry_root
        self.max_retry = max_retry
        self.verbose = verbose
        # 实例产品：决定请求体包装方式（NX 系 Assign/Argument，Designer 扁平）
        self.product = product or infer_product(base_url)
        self.profile = profile or (
            PROFILE_DESIGNER if self.product == "CIVIL_DESIGNER" else infer_profile(base_url))
        # 逃生舱：默认 False。开启后仍会对 DELETE 要求显式主体。
        self.allow_unscoped_delete = allow_unscoped_delete
        # 显式「删除全部」（Designer 的 Type=0 / 空主体）需单独开启
        self.allow_global_delete = allow_global_delete
        self._defs = None

    # ---------- registry ----------
    def definitions(self):
        if self._defs is None:
            with open(os.path.join(self.registry_root, "manifest.json"), encoding="utf-8") as fh:
                mf = json.load(fh)
            self._defs = {e["key"]: e for e in mf["endpoints"]}
        return self._defs

    def definition(self, key, product=None):
        d = self.definitions().get(key)
        if not d:
            raise MidasError("ENDPOINT_NOT_FOUND", f"registry key not found: {key}",
                             {"key": key})
        if d.get("enabled") is False:
            raise MidasError("ENDPOINT_DISABLED", f"{key} 已被禁用，不对外暴露",
                             {"key": key, "reason": d.get("disable_reason", "")})
        if product and product not in d["products"]:
            raise MidasError("PRODUCT_CAPABILITY_UNSUPPORTED",
                             f"{key} 不支持产品 {product}",
                             {"key": key, "product": product, "products": d["products"]})
        return d

    def resolve(self, key, method, product=None):
        """key + method -> (uri, definition)。方法不在定义内时直接报错，不发请求。"""
        d = self.definition(key, product)
        if method.upper() not in parse_methods(d["methods"]):
            raise MidasError("METHOD_NOT_ALLOWED",
                             f"{key} 不支持 {method}",
                             {"key": key, "method": method, "allowed": d["methods"]})
        return d["uri"], d

    def introspect(self, code):
        """Schema 自省：{base url} + info/db/{CODE}。注意：实测仅 DB 命名空间有效。"""
        return self.raw("GET", f"/info/db/{code}")

    def effective_wrapper(self, d):
        """按实例产品解析请求体包装方式。

        返回 `'Assign'` / `'Argument'`，或 **`None` 表示扁平请求体（不包装）**。
        实测：NX 系为 Assign/Argument 包装；CIVIL_DESIGNER 为扁平结构
        （PUT 扁平体 -> 正常；Assign 包装 -> "Required parameter [...] is missing"）。
        """
        w = dict(d.get("wrapper") or {})
        ov = (d.get("product_overrides") or {}).get(self.product or "", {})
        if ov.get("wrapper"):
            w.update(ov["wrapper"])
        write = w.get("write", "Argument")
        return None if write in (None, "", "none") else write

    # ---------- http ----------
    def raw(self, method, uri, payload=None, retry=None):
        url = self.base_url + (uri if uri.startswith("/") else "/" + uri)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(url, data=body, method=method.upper())
        req.add_header("Content-Type", "application/json")
        req.add_header("MAPI-Key", self.mapi_key)
        attempts = (self.max_retry if retry is None else (self.max_retry if retry is True else 0)) + 1
        last = None
        for i in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    text = r.read().decode("utf-8", "replace")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"_raw": text}
            except urllib.error.HTTPError as e:
                last = MidasError("HTTP_ERROR", f"HTTP {e.code}",
                                  {"uri": uri, "method": method}, e.code)
                try:
                    _body = e.read().decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    _body = ""
                # 云端中继/客户端状态类错误：与「端点不存在」区分开（实测见报告附录 G）
                if "client does not exist" in _body:
                    raise MidasError(
                        "CLIENT_NOT_CONNECTED",
                        "MIDAS 客户端未连接（云端中继返回 client does not exist）——"
                        "请确认对应 MIDAS 应用已启动并登录，稍后重试",
                        {"uri": uri, "method": method, "raw": _body[:200]}, e.code)
                if "project is not opened" in _body.lower():
                    raise MidasError(
                        "PROJECT_NOT_OPENED", "MIDAS 中未打开任何项目",
                        {"uri": uri, "method": method, "raw": _body[:200]}, e.code)
                # HTTP 语义映射（实测：404 = 表不存在；405 = 方法不允许）
                if e.code == 404:
                    raise MidasError("ENDPOINT_NOT_FOUND", f"{method} {uri} 不存在（HTTP 404）",
                                     {"uri": uri, "method": method}, 404)
                if e.code == 405:
                    raise MidasError("METHOD_NOT_ALLOWED", f"{method} {uri} 不被允许（HTTP 405）",
                                     {"uri": uri, "method": method}, 405)
                if e.code in (401, 403):
                    raise MidasError("AUTH_FAILED", "MAPI-Key 无效或权限不足",
                                     {"uri": uri}, e.code)
                if e.code < 500:
                    raise last
            except urllib.error.URLError as e:
                last = MidasError("CONNECTION_ERROR", str(e.reason),
                                  {"uri": uri, "method": method})
            except Exception as e:  # noqa: BLE001
                last = MidasError("MIDAS_REQUEST_FAILED", str(e), {"uri": uri})
            if i < attempts - 1:
                time.sleep(0.5 * (2 ** i))
        raise last

    def call(self, key, method=None, payload=None, product=None, wrap=True,
             path_key=None):
        """按 Registry 定义调用端点。method 缺省时取定义的第一个可用方法。

        `path_key`：NX 系的单条删除/查询把 key 写在 URL 路径里
        （官方手册：删除 10 号节点 → `DELETE {base url}/db/node/10`）。
        """
        d = self.definition(key, product)
        if method is None:
            avail = parse_methods(d["methods"])
            if not avail:
                raise MidasError("METHODS_UNKNOWN", f"{key} 的方法集未标注，请显式指定 method",
                                 {"key": key})
            method = avail[0]
        method = method.upper()
        uri, d = self.resolve(key, method, product)

        # ---- F11 破坏性调用护栏（依据实测，见测试报告附录 E）----
        # NX 系（实测 + 官方手册第 859 行）：
        #   `DELETE <uri>`              → 删除**全表**（手册原文 "Delete all component"）
        #   `DELETE <uri>/<key>`        → 只删该条（手册示例 db/node/10）
        #   ⚠️ 带 `{"Assign": {...}}` 主体但**无路径 key** 同样会删除全表（实测：345 节点被清空）
        # CIVIL_DESIGNER（手册 + 实测）：
        #   DELETE 用主体表达，空主体或 `Type=0` 均表示删除全部
        if method == "DELETE":
            ov = (d.get("product_overrides") or {}).get(self.product or "", {})
            risk = d.get("risk") or {}
            nx_global = (self.profile == PROFILE_NX
                         and bool(risk.get("delete_without_body_is_global")))
            global_by_body = bool(risk.get("delete_all_via_body")
                                  or ov.get("delete_all_via_body"))

            if nx_global and path_key is None and not self.allow_global_delete:
                raise MidasError(
                    "GLOBAL_DELETE_REJECTED",
                    f"拒绝执行 {key} 的 DELETE：NX 系不带路径 key 的 DELETE 会删除**全表**"
                    f"（官方手册：「Delete all component from existed midas Model」；"
                    f"带 Assign 主体亦无效，实测会清空整张表）。"
                    f"单条删除请用 delete(key, item_id) 或 call(..., path_key='<ID>')。",
                    {"key": key, "uri": uri,
                     "hint": "DELETE %s/<key>；确需删除全表请显式 allow_global_delete=True"
                             % uri})

            if not nx_global:
                if payload is None and not self.allow_global_delete:
                    raise MidasError(
                        "DESTRUCTIVE_CALL_REJECTED",
                        f"拒绝执行不带显式主体的 DELETE：{key}。",
                        {"key": key, "uri": uri,
                         "required": "payload={'Assign': {'<ID>': {}}}"})
                if isinstance(payload, dict) and payload in ({}, {"Assign": {}},
                                                            {"Argument": {}}):
                    raise MidasError(
                        "GLOBAL_DELETE_REJECTED",
                        f"拒绝执行主体为空的 DELETE：{key}。"
                        f"Designer 手册注明「空或未设置时删除全部」。",
                        {"key": key, "uri": uri,
                         "hint": "请显式给出要删除的 Key / Name 列表"})
                if (global_by_body and isinstance(payload, dict)
                        and payload.get("Type") == 0 and not self.allow_global_delete):
                    raise MidasError(
                        "GLOBAL_DELETE_REJECTED",
                        f"拒绝执行「删除全部」：{key} 的 Type=0 表示删除全部记录。"
                        f"如确需删除全部，请显式设置 allow_global_delete=True。",
                        {"key": key, "uri": uri, "payload": payload})

        # NX 系的单条删除/查询：key 写在 URL 路径中
        if path_key is not None:
            uri = uri.rstrip("/") + "/" + str(path_key)

        if payload is not None and wrap and isinstance(payload, dict):
            w = self.effective_wrapper(d)
            # w 为 None 表示该产品使用扁平请求体，不做任何包装
            if w and w not in payload and not any(k in payload for k in ("Assign", "Argument")):
                payload = {w: payload}
        retry = (d.get("risk") or {}).get("retry", {}).get(method)
        try:
            resp = self.raw(method, uri, payload, retry=(retry is True))
        except MidasError as ex:
            # F3：对标记为 unverified 的端点补充排障提示
            if ex.code == "ENDPOINT_NOT_FOUND" and d.get("availability") == "unverified":
                ex.details.setdefault(
                    "hint", "该端点可能依赖更新的实例版本或未启用的模块")
                ex.details.setdefault("verified_on", d.get("verified_on", []))
            raise

        # ---- F10 产品感知的响应判定 ----
        status, code, detail = classify_response(key, resp)
        if status == "ERROR":
            raise MidasError(code or "MIDAS_ERROR", detail,
                             {"key": key, "method": method, "uri": uri})
        return resp

    def classify(self, key, resp):
        """对已取得的响应体做产品感知判定，供测试/诊断使用。"""
        return classify_response(key, resp)

    # ---------- convenience ----------
    def get(self, key, product=None, **kw):
        return self.call(key, "GET", product=product, **kw)

    def post(self, key, payload=None, product=None):
        return self.call(key, "POST", payload=payload, product=product)

    def put(self, key, payload=None, product=None):
        return self.call(key, "PUT", payload=payload, product=product)

    def delete(self, key, item_id=None, payload=None, product=None):
        """删除。

        * NX 系：**必须给出 item_id** —— 走 `DELETE <uri>/<id>`；
          不给则被护栏拒绝（`DELETE <uri>` 不带路径 key 会删除全表）。
        * CIVIL_DESIGNER：用 `payload` 表达（如 `{"Type": 2, "KeyList": [1]}`）。
        """
        return self.call(key, "DELETE", payload=payload, product=product,
                         path_key=item_id)

    # ---------- websocket（长任务推送，骨架） ----------
    def open_ws(self, on_message, ws_url=None, headers=None):
        """接收长任务推送。需安装 websocket-client：pip install websocket-client。"""
        try:
            import websocket  # type: ignore
        except ImportError as e:
            raise MidasError("WS_CLIENT_MISSING",
                             "需要 websocket-client：pip install websocket-client",
                             {"cause": str(e)})
        url = ws_url or self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        hdr = headers or {"MAPI-Key": self.mapi_key}
        ws = websocket.WebSocketApp(url, header=[f"{k}: {v}" for k, v in hdr.items()],
                                    on_message=lambda _ws, msg: on_message(json.loads(msg)))
        return ws
