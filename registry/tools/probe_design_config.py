#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P164-c：`DESIGN.*` **配置端点**的真机验证（写入 → **读回验效果** → 清理）。

为什么需要这个工具
------------------
**R141**（`DESIGN.STEEL`）与 **R153**（`DESIGN.CONCRETE` / `DESIGN.SRC`）的病根是：
这些**配置**端点（手册方法 `GET, PUT, DELETE`）被编排成 `_read` ⇒ 设计**从未被配置**。
P160e-b / P164-b 已把编排改成 `PUT`，但**从未在真机上验证过写入是否真的落库**。

本工具做**只做这一件事**：按手册示例写 4 个配置端点，然后 **`GET` 读回**，
判据是**读回里有那个值**（**铁律 ⓪**：不是看 `200`）。随后 `DELETE` + **再读确认**。

⚠️ **实测已知（本工具会记录，不是 bug）**：`DESIGN.RC.DRC` 与 `DESIGN.SRC.AIK-SRC2K.DSRC`
是**单例且必须存在**的设置 —— `DELETE` **无法**回到"未选"状态
（前者被换成服务端默认 `GB/T50010-10`，后者是静默 no-op）。故这两个端点**必然**留下痕迹。

纪律
----
* **只发 `GET` / `PUT` / `DELETE`，且只碰设计配置端点**；**不**碰节点 / 单元 / 材料 / 截面。
* 写入体**照手册示例**（`registry/live/write_templates.json`），**不**臆造。
* **默认预演**；`--probe` 才真发。`--check` 离线断言证据自洽。

用法（仓库根目录执行，需 `MIDAS_*` 环境或 `~/.structai/midas-test.env` 的 `[gen]` 段）
----------------------------------------------------------------------------------------
    python registry/tools/probe_design_config.py            # 预演（不发请求）
    python registry/tools/probe_design_config.py --probe    # 真机
    python registry/tools/probe_design_config.py --check    # 离线断言
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

EVIDENCE_RELATIVE = "live/design_config_probe.json"
TEMPLATES_RELATIVE = "live/write_templates.json"
INSTANCE_ALIAS = "gen-local"
INSTANCE_PRODUCT = "GEN NX"
PROBED_AT = "2026-10-13"
CRITERION_VERSION = 1

# (key, uri, read_root, 手册示例模板键)
TARGETS: tuple[tuple[str, str, str, str], ...] = (
    ("DESIGN.RC.DRC", "DESIGN/RC/DRC", "DCON", "DESIGN.RC.DRC"),
    (
        "DESIGN.RC.KDS-41-20-2022.DCO",
        "DESIGN/RC/KDS-41-20-2022/DCO",
        "DCORC",
        "DESIGN.RC.KDS-41-20-2022.DCO",
    ),
    ("DESIGN.SRC.AIK-SRC2K.DSRC", "DESIGN/SRC/AIK-SRC2K/DSRC", "DSRC", "DESIGN.SRC.AIK-SRC2K.DSRC"),
    ("DESIGN.SRC.AIK-SRC2K.DCO", "DESIGN/SRC/AIK-SRC2K/DCO", "SRCDCO", "DESIGN.SRC.AIK-SRC2K.DCO"),
)

CANONICAL_CLEANUP: dict[str, str | None] = {
    # ⚠️ **P164-c 修正（实测驱动）**：`DESIGN/<族>/…` 的 `DELETE` **不是删除** ——
    # 它把该设计模块的设置**写回产品默认值**（STEEL → `GB50017-17`、RC → `GB/T50010-10`）。
    # **`/db/*` 家族的 `DELETE` 才是真删除**（⇒ `{}`）。两者作用于**同一份数据**
    # （PUT/GET 互通，实测）。故清理由**规范路由**执行。
    "DESIGN.RC.DRC": "/DB/DCON",
    # ⚠️ SRC **没有** 规范路由（手册索引里只有 `/db/DSTL` 与 `/db/DCON`，无 `/db/DSRC`）
    # ⇒ 它的设计规范**无法**被删除，只能被"重置为默认"；而其唯一合法值 `AIK-SRC2K`
    # **就是**默认值 ⇒ 重置与 no-op **不可区分**。
    "DESIGN.SRC.AIK-SRC2K.DSRC": None,
    "DESIGN.RC.KDS-41-20-2022.DCO": "DESIGN/RC/KDS-41-20-2022/DCO",
    "DESIGN.SRC.AIK-SRC2K.DCO": "DESIGN/SRC/AIK-SRC2K/DCO",
}
"""清理时实际 `DELETE` 的路由（`None` = 没有可用的规范路由，**无法**删除）。"""

SENTINEL_PATHS: tuple[str, ...] = (
    "DB/NODE",
    "DB/ELEM",
    "DB/MATL",
    "DB/SECT",
    "DB/STLD",
    "DB/CNLD",
    "DB/CONS",
    "DB/LCOM-STEEL",
    "DB/LCOM-CONC",
    "DB/GRUP",
    *(uri for _k, uri, _r, _t in TARGETS),
)
"""跑前 / 跑后只读哨兵。⚠️ `DB/GRUP` 与两个设计代码单例**已知非空**（见模块文档）。"""


IDENTITY_FIELDS: tuple[str, ...] = ("DGNCODE", "DESIGN_CD")
"""判「配置写进去了」的**规范代码字段** —— 按**逐值相等**判。"""

PRESENCE_FIELDS: tuple[str, ...] = ("SEISMIC",)
"""必须**存在**（不要求逐值相等）的字段。

⚠️ 实测：`SEISMIC` 是嵌套对象，其**子字段**可能按分支被静默丢弃
（`SHEAR_DES.A2` 在 `MTHD="Ve1"` 下即如此）—— 拿整个对象比相等会把这个**已记录**的
现象误判成「配置没写进去」。故 `SEISMIC` **只判存在**，丢弃的子字段进 `dropped_fields`。
"""


def _flatten(node: object, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_flatten(value, f"{prefix}.{key}" if prefix else str(key)))
    else:
        out[prefix] = node
    return out


def _dropped(sent: dict, readback: dict) -> dict[str, object]:
    """送出去但读回里**没有**的字段（**如实记录**；按分支被忽略的可选字段属此类）。"""
    flat_sent, flat_got = _flatten(sent), _flatten(readback)
    return {k: v for k, v in flat_sent.items() if k not in flat_got}


def _load_credentials(instance: str) -> tuple[str, str]:
    base = os.environ.get("MIDAS_BASE_URL", "").rstrip("/")
    key = os.environ.get("MIDAS_MAPI_KEY", "")
    if base and key:
        return base, key
    path = pathlib.Path(os.environ.get("USERPROFILE", "")) / ".structai" / "midas-test.env"
    section, values = "", {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip().lower()
            continue
        if section == instance and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip()
    return values["MIDAS_BASE_URL"].rstrip("/"), values["MIDAS_MAPI_KEY"]


def _read_block(client, path: str, root: str) -> dict:
    payload = client.get("/" + path.lstrip("/")).json()
    block = payload.get(root) if isinstance(payload, dict) else None
    return block if isinstance(block, dict) else {}


def _sentinel(client) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for path in SENTINEL_PATHS:
        response = client.get("/" + path)
        try:
            payload = response.json()
            top = list(payload) if isinstance(payload, dict) else []
            block = payload.get(top[0]) if top else None
            if isinstance(block, dict) and "ITEMS" in block:
                count = len(block["ITEMS"])
            elif isinstance(block, dict):
                count = len([k for k in block if str(k).isdigit()])
            else:
                count = len(block) if isinstance(block, list) else 0
        except ValueError:
            top, count = ["<非 JSON>"], 0
        out[path] = {"status": int(response.status_code), "top": top, "count": count}
    return out


def _route_semantics(client, *, read_block) -> dict:
    """**决定性对比**：别名路由与规范路由作用于同一份数据，但 `DELETE` 语义不同。

    步骤（每步都**双读**：别名 + 规范）：
        ① 读基线 → ② `PUT` **别名** → 双读 → ③ `DELETE` **别名** → 双读
        → ④ `DELETE` **规范** → 双读
    """
    alias, canonical, root, seed = "/DESIGN/RC/DRC", "/DB/DCON", "DCON", "KDS 41 20 : 2022"

    def both() -> dict:
        return {"alias": read_block(client, alias, root), "canonical": read_block(client, canonical, root)}

    out: dict = {
        "alias_uri": alias,
        "canonical_uri": canonical,
        "seed": seed,
        "steps": [],
    }
    out["steps"].append({"step": "baseline", "state": both()})
    client.put("/" + alias.lstrip("/"), json={"Assign": {"1": {"DGNCODE": seed}}})
    out["steps"].append({"step": "put_alias", "state": both()})
    response = client.delete("/" + alias.lstrip("/"))
    out["alias_delete_response"] = response.text[:200]
    out["steps"].append({"step": "delete_alias", "state": both()})
    response = client.delete("/" + canonical.lstrip("/"))
    out["canonical_delete_response"] = response.text[:200]
    out["steps"].append({"step": "delete_canonical", "state": both()})
    after_alias_delete = out["steps"][2]["state"]
    final = out["steps"][3]["state"]
    out["verdict"] = {
        "alias_delete_clears": not after_alias_delete["canonical"],
        "alias_delete_writes_default": bool(after_alias_delete["canonical"]),
        "callback_alias_delete_value": (
            (after_alias_delete["canonical"].get("1") or {}).get("DGNCODE")
            if after_alias_delete["canonical"]
            else None
        ),
        "canonical_delete_clears": not final["canonical"],
        "routes_share_storage": after_alias_delete["alias"] == after_alias_delete["canonical"],
    }
    return out


def probe(repo: pathlib.Path) -> int:
    import httpx

    base, key = _load_credentials("gen")
    templates = json.loads((repo / "registry" / TEMPLATES_RELATIVE).read_text(encoding="utf-8"))[
        "templates"
    ]
    document: dict = {
        "criterion_version": CRITERION_VERSION,
        "note": [
            "P164-c：`DESIGN.*` 配置端点的真机写入 + **读回验效果**（铁律 ⓪）+ 清理再读。",
            "判据 = **读回里有那个值**，**不是** `200`。",
            "⚠️ **DELETE 语义分两族（本批实测，已更正初版结论）**：",
            "   · `/DESIGN/<族>/<模块>` 的 DELETE = **把该模块的设置写回产品默认值**"
            "（STEEL → `GB50017-17`、RC → `GB/T50010-10`）—— **不是**删除；其响应体**回显删除前的状态**。",
            "   · `/db/*` 家族的 DELETE = **真删除**（⇒ `{}`）。两者作用于**同一份数据**"
            "（给别名 PUT，规范路由的 GET 立刻可见，反之亦然）。",
            "   · 故清理必须走**规范路由**；`/DESIGN/SRC/AIK-SRC2K/DSRC` **没有**规范路由 ⇒ 无法删除，"
            "而其唯一合法值 `AIK-SRC2K` 即产品默认值 ⇒ 重置与 no-op **不可区分**"
            "（这才是「看起来像 no-op」的真正原因，**不是**「单例不可清」）。",
            "⚠️ `DB/GRUP` 的 26 条是 **app 自建**的 `TEMP_DATA` 组（2026-10-11 的探针记录为空）—— "
            "哨兵口径是「跑前 == 跑后」，**不是**「必须全空」。",
            "生成器 = `registry/tools/probe_design_config.py --probe`（只碰设计配置端点）。",
        ],
        "instance": {"alias": INSTANCE_ALIAS, "product": INSTANCE_PRODUCT, "base_url": base,
                     "probed_at": PROBED_AT},
        "sentinel_paths": list(SENTINEL_PATHS),
        "aborted": "",
        "steps": [],
        "cleanup": [],
    }
    with httpx.Client(base_url=base, headers={"MAPI-Key": key}, timeout=25.0) as client:
        before = _sentinel(client)
        document["sentinel_before"] = before
        for target, uri, root, template_key in TARGETS:
            body = (templates.get(template_key) or {}).get("body") or {}
            wire = {"Assign": {"1": dict(body)}}
            response = client.put("/" + uri, json=wire)
            block = _read_block(client, uri, root)
            entry = block.get("1") if isinstance(block, dict) else None
            # ⚠️ **判据分两层**（否则会把「按分支被忽略的可选字段」误判成失败）：
            #   ① `effect_ok` = **标识字段**确实落库（`DGNCODE` / `DESIGN_CD` / `SEISMIC`）
            #      —— 这才是「配置写进去了」的**效果**（铁律 ⓪）。
            #   ② `dropped_fields` = 送了但读回里**没有**的字段 ⇒ **如实记录**，不判失败。
            #      （实测：`SEISMIC.SHEAR_DES.A2` 在 `MTHD="Ve1"` 下被静默丢弃 —— 疑为按分支忽略。）
            identity = {k: v for k, v in body.items() if k in IDENTITY_FIELDS}
            presence = [k for k in PRESENCE_FIELDS if k in body]
            found = {k: entry.get(k) for k in identity} if isinstance(entry, dict) else {}
            present = [k for k in presence if isinstance(entry, dict) and k in entry]
            dropped = _dropped(body, entry if isinstance(entry, dict) else {})
            document["steps"].append(
                {
                    "key": target,
                    "uri": uri,
                    "read_root": root,
                    "request": wire,
                    "status_code": int(response.status_code),
                    "readback": block,
                    "identity": identity,
                    "presence": presence,
                    "found": found,
                    "present": present,
                    "effect_ok": bool(entry)
                    and all(found.get(k) == v for k, v in identity.items())
                    and present == presence,
                    "dropped_fields": dropped,
                }
            )
        for target, uri, root, _template_key in TARGETS:
            before_block = _read_block(client, uri, root)
            cleanup_uri = CANONICAL_CLEANUP.get(target)
            if cleanup_uri is None:
                document["cleanup"].append(
                    {
                        "key": target,
                        "uri": uri,
                        "delete_uri": None,
                        "status_code": None,
                        "before": before_block,
                        "after": before_block,
                        "cleared": False,
                        "reason": "no_canonical_route",
                        "note": (
                            "`/DESIGN/<族>/…` 的 DELETE 是「写回产品默认值」而非删除；"
                            "本端点没有 `/db/*` 规范路由 ⇒ **无法**删除。"
                            "其唯一合法值即产品默认值 ⇒ 重置与 no-op 不可区分。"
                        ),
                    }
                )
                continue
            response = client.delete("/" + cleanup_uri.lstrip("/"))
            after_block = _read_block(client, uri, root)
            document["cleanup"].append(
                {
                    "key": target,
                    "uri": uri,
                    "delete_uri": cleanup_uri,
                    "status_code": int(response.status_code),
                    "before": before_block,
                    "after": after_block,
                    "cleared": not after_block,
                    "reason": "" if not after_block else "alias_delete_is_reset",
                }
            )
        document["sentinel_after"] = _sentinel(client)

        # ---- 路由语义对比：别名 DELETE vs 规范 DELETE（作用于**同一份数据**）----
        document["route_semantics"] = _route_semantics(client, read_block=_read_block)

    document["counts"] = {
        "steps": len(document["steps"]),
        "effect_ok": sum(1 for s in document["steps"] if s["effect_ok"]),
        "cleared": sum(1 for c in document["cleanup"] if c["cleared"]),
        "not_cleared": sum(1 for c in document["cleanup"] if not c["cleared"]),
    }
    path = repo / "registry" / EVIDENCE_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"写入 {path.relative_to(repo)}")
    print(f"  配置写入效果确认: {document['counts']['effect_ok']}/{document['counts']['steps']}")
    print(f"  清理：清空 {document['counts']['cleared']} · 未清空 {document['counts']['not_cleared']}")
    changed = [k for k in SENTINEL_PATHS if before[k] != document["sentinel_after"][k]]
    print(f"  哨兵变化的项: {changed or '（无）'}")
    return 0


def check(repo: pathlib.Path) -> int:
    path = repo / "registry" / EVIDENCE_RELATIVE
    if not path.is_file():
        print(f"❌ 缺证据文件 registry/{EVIDENCE_RELATIVE}")
        return 1
    document = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if document.get("aborted"):
        errors.append(f"探针被中止：{document['aborted']}")
    counts = document.get("counts") or {}
    if counts.get("steps") != len(TARGETS):
        errors.append(f"steps = {counts.get('steps')}（应为 {len(TARGETS)}）")
    if counts.get("effect_ok") != len(TARGETS):
        errors.append(f"效果确认 {counts.get('effect_ok')}/{len(TARGETS)} —— 有配置步没验到效果")
    # 模型哨兵必须全空（设计配置端点**不**在此列）
    for path_name in SENTINEL_PATHS:
        if path_name.startswith("DESIGN/"):
            continue
        for moment in ("sentinel_before", "sentinel_after"):
            count = ((document.get(moment) or {}).get(path_name) or {}).get("count")
            if path_name == "DB/GRUP":
                continue  # app 自建，已知非空
            if count:
                errors.append(f"{moment}.{path_name} = {count}（模型哨兵应全空）")
    if errors:
        print("❌ 证据不自洽：")
        for error in errors:
            print("   -", error)
        return 1
    print(
        f"✅ 证据自洽：配置写入效果 {counts['effect_ok']}/{counts['steps']} · "
        f"清空 {counts['cleared']} · 未清空 {counts['not_cleared']}（已披露）· 模型哨兵全空"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--probe", action="store_true", help="真机实测（默认只预演）")
    parser.add_argument("--check", action="store_true", help="离线：断言证据自洽")
    args = parser.parse_args()
    repo = pathlib.Path(args.repo).resolve()

    if args.check:
        return check(repo)
    if not args.probe:
        print("预演：将按手册示例写以下端点（**未**发请求）：")
        for target, uri, root, template_key in TARGETS:
            print(f"  PUT /{uri:34s} read_root={root:8s} 模板={template_key}")
        print("  随后逐条 DELETE + 再读确认；哨兵跑前 / 跑后对比。")
        print("\n加 --probe 才真发。")
        return 0
    return probe(repo)


if __name__ == "__main__":
    raise SystemExit(main())
