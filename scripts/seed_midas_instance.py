#!/usr/bin/env python
"""幂等登记 MIDAS 软件实例到 StructAI 数据库。

在既有 P07 seed（tenant/project/user 等）之后，补一条**真实 MIDAS** 四级软件注册
（vendor=MIDAS / product=GEN NX / version=<v> / instance），并把 instance.endpoint
设为运行环境 `MIDAS_BASE_URL`（由 `scripts/load-midas-env.ps1` 注入）。再绑定一个
model 到默认项目，使「实例 → 项目 → 租户」的租户边界链路成立，MCP Tool 才可通过
`software_instance_id` 使用该实例（`docs/02` §12 / §10）。

幂等：按 natural key 查重，已存在则更新 endpoint 并复用。
凭据**不**入库；这里只登记连接地址（非敏感）。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import uuid
from datetime import datetime, UTC

DB_PATH = os.environ.get("STRUCTAI_DB_PATH", "./data/structai.db")
VENDOR = "MIDAS"
SOFTWARE_NAME = "MIDAS GEN NX"
PRODUCT = "GEN NX"
VERSION = "2024"
INSTANCE_NAME = "MIDAS GEN NX @ localhost"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _gid() -> str:
    return str(uuid.uuid4())


def main() -> int:
    base_url = os.environ.get("MIDAS_BASE_URL", "").strip()
    if not base_url:
        print("MIDAS_BASE_URL is not set; run via scripts/load-midas-env.ps1 first", file=sys.stderr)
        return 2
    if not os.path.exists(DB_PATH):
        print(f"database not found: {DB_PATH} (run `python -m app.infrastructure.database.seed --create-tables` first)", file=sys.stderr)
        return 2

    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        now = _now()

        def one(sql: str, params: tuple) -> object | None:
            row = cur.execute(sql, params).fetchone()
            return row[0] if row else None

        sw_id = one("SELECT id FROM software WHERE vendor=? AND name=?", (VENDOR, SOFTWARE_NAME))
        if sw_id is None:
            sw_id = _gid()
            cur.execute(
                "INSERT INTO software(vendor,name,status,id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (VENDOR, SOFTWARE_NAME, "ENABLED", sw_id, now, now),
            )

        prod_id = one("SELECT id FROM software_products WHERE software_id=? AND product=?", (sw_id, PRODUCT))
        if prod_id is None:
            prod_id = _gid()
            cur.execute(
                "INSERT INTO software_products(software_id,product,id,created_at,updated_at) VALUES(?,?,?,?,?)",
                (sw_id, PRODUCT, prod_id, now, now),
            )

        ver_id = one("SELECT id FROM software_versions WHERE product_id=? AND version=?", (prod_id, VERSION))
        if ver_id is None:
            ver_id = _gid()
            cur.execute(
                "INSERT INTO software_versions(product_id,version,id,created_at,updated_at) VALUES(?,?,?,?,?)",
                (prod_id, VERSION, ver_id, now, now),
            )

        inst_id = one("SELECT id FROM software_instances WHERE version_id=? AND name=?", (ver_id, INSTANCE_NAME))
        if inst_id is None:
            inst_id = _gid()
            cur.execute(
                "INSERT INTO software_instances(version_id,name,endpoint,status,credential_reference,id,created_at,updated_at,version)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (ver_id, INSTANCE_NAME, base_url, "DISCONNECTED", None, inst_id, now, now, 1),
            )
        else:
            cur.execute("UPDATE software_instances SET endpoint=?, updated_at=? WHERE id=?", (base_url, now, inst_id))

        # 绑定 model 到默认项目（租户边界链路：model→project→tenant）。
        proj = cur.execute("SELECT id, tenant_id FROM projects WHERE name='default'").fetchone()
        if proj is not None:
            proj_id = proj[0]
            model_id = one("SELECT id FROM models WHERE project_id=? AND software_instance_id=?", (proj_id, inst_id))
            if model_id is None:
                model_id = _gid()
                cur.execute(
                    "INSERT INTO models(project_id,software_instance_id,name,id,created_at,updated_at,version)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (proj_id, inst_id, "MIDAS GEN NX Model", model_id, now, now, 1),
                )

        conn.commit()
        print(f"seed_midas_instance ok: instance={inst_id} endpoint={base_url}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
