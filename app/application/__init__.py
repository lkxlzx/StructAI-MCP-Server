"""Application 层（`docs/07` §3.3 冻结结构）。

依赖方向（`docs/07` §2.2）：`Interface → Application → Domain`；
`Infrastructure → Domain / Application`。本包**不得**引用 SQLAlchemy / FastAPI /
MCP SDK 之外的 Interface 层内容，也不得反向依赖 `app.interfaces`。

本批次（P07 Seed）只落地 `security/password.py` —— Seed 必须把管理员口令
转成 `password_hash` 入库（`docs/02` §43–§44 的 `password_service.hash(password)`），
其余子包（dto / execution / services / resource / task）由后续批次接入。

| 子包 | 内容 | 接入批次 |
| --- | --- | --- |
| `security/` | `password.py`（Argon2id 口令哈希） | **P07 ✅**（本批） |
| `security/` | `authentication.py` / `session.py` / `rbac.py` / … | P10–P13 |
| `dto/` · `execution/` · `services/` · `resource/` · `task/` | — | P14+ |
"""

from __future__ import annotations

__all__: list[str] = []
