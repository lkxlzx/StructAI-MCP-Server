"""Application · Security（`docs/07` §3.3；`docs/02` §6–§9）。

本包是安全能力的 Application 层落点：

| 文件 | 内容 | 批次 |
| --- | --- | --- |
| `password.py` | `PasswordService`：Argon2id 口令哈希（`docs/02` §7） | **P07 ✅** |
| `authentication.py` | `AuthenticationService`（`docs/02` §25） | P10 |
| `session.py` | 会话 / Token（`docs/02` §26） | P11 |
| `rbac.py` · `permission.py` · `context.py` | RBAC / Effective Permission | P12–P13 |

安全红线（`docs/07` §14.3）：本包**绝不**记录 secret（password / API key /
token / private key）；口令只以 `password_hash` 形式离开本包。
"""

from __future__ import annotations

from app.application.security.password import PasswordService

__all__ = ["PasswordService"]
