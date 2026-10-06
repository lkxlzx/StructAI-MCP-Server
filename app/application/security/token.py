"""Application · Security · TokenService（`docs/02` §12 / §13；`docs/07` §8.3）。

权威来源
--------
- `docs/02` §12（`sec` §12）—— 文件 `app/application/security/token.py`；
  原则「客户端持有 token，数据库只保存 token hash」；实现
  `generate() -> secrets.token_urlsafe(48)`、`hash(token) -> sha256 hexdigest`，
  逐字照抄（含 `token_urlsafe(48)` 的位数）。
- `docs/02` §13（`sec` §13）—— 为什么只存 hash：`Raw Token → Client`，
  `Hash(Token) → DB`，验证时 `Client Token → Hash → DB lookup`。
- `docs/02` §10（`sec` §10）—— `sessions.token_hash` 是 `String(128)`：sha256 的
  hexdigest 恰好 64 字符，落在该长度内。
- `docs/02` §58（`sec` §58）—— 日志**禁止**记录 `raw_token`；只允许记录
  「token fingerprint」，即 `sha256(value)[:12]`（§58 给出的原文实现）。
- `docs/07` §8.3 —— Token 存储：只存 hash，绝不存明文。

为什么 token 用 sha256 而不是 Argon2id
--------------------------------------
`docs/02` §7 / §8 要求**口令**用 Argon2id（慢哈希、抗离线爆破）；`docs/02` §12 要求
**token** 用 sha256。两者不矛盾：token 由 `secrets.token_urlsafe(48)` 生成
（48 字节 CSPRNG 熵，约 384 bit），不存在「可猜测的弱口令」问题，而认证路径需要
O(1) 的反查；对 token 用 Argon2id 只会让每次请求都付出一次慢哈希的代价。
本模块据此严格照抄规范：口令 → `password.PasswordService`（Argon2id），
token → 本模块（sha256）。**不得**互换。

分层红线（`docs/07` §14.1 / §14.2）
----------------------------------
本模块只依赖标准库（`hashlib` / `secrets`）：不引用 ORM / Web 框架 / MCP SDK，
不依赖 `app.infrastructure`，也不出现任何厂商专属内容。
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Final

__all__ = ["FINGERPRINT_LENGTH", "TOKEN_BYTES", "TokenService", "fingerprint"]

TOKEN_BYTES: Final[int] = 48
"""`secrets.token_urlsafe` 的字节数（`docs/02` §12 原文：`token_urlsafe(48)`）。"""

FINGERPRINT_LENGTH: Final[int] = 12
"""日志可记录的 token 指纹长度（`docs/02` §58 原文：`hexdigest()[:12]`）。"""


def fingerprint(value: str) -> str:
    """计算可安全写入日志的短指纹（`docs/02` §58）。

    Args:
        value: 任意待指纹化的字符串（典型用法：明文 token / 会话标识）。

    Returns:
        `sha256(value)` 的前 `FINGERPRINT_LENGTH` 个十六进制字符。

    ⚠️ 指纹**不可**用于认证（只有 12 个十六进制字符，不可作为凭据），它只用于
    「同一次操作能否在日志里对上号」；`docs/02` §58 明确禁止记录 `raw_token`。
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:FINGERPRINT_LENGTH]


class TokenService:
    """会话 Token 的生成与哈希（`docs/02` §12）。

    只做两件事：生成高熵 token、对 token 求哈希。**不**持有任何状态，
    也**不**持久化任何东西 —— 落库由 `SessionService` + `SessionStore` 负责
    （`docs/02` §19），且只落哈希（`docs/02` §13）。
    """

    def generate(self) -> str:
        """生成新的明文 token（`docs/02` §12）。

        Returns:
            URL-safe 的高熵随机串。它只在「返回给客户端的那一次」出现，
            绝不落库 / 落日志 / 落审计（`docs/07` §14.3）。
        """
        return secrets.token_urlsafe(TOKEN_BYTES)

    def hash(self, token: str) -> str:
        """计算 token 的库内表示（`docs/02` §12 / §13）。

        Args:
            token: 明文 token（或调用方传来的待校验 token）。

        Returns:
            `sha256(token)` 的十六进制摘要；这是**唯一**允许写进
            `sessions.token_hash` 的形状（`docs/07` §8.3）。

        ⚠️ 返回值是 secret 的派生值，同样不得进日志（`docs/02` §58 只允许
        `fingerprint`）。
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def fingerprint(self, token: str) -> str:
        """本服务实例视角下的日志指纹（`docs/02` §58）。

        Args:
            token: 明文 token。

        Returns:
            与模块级 `fingerprint()` 相同的短指纹，便于调用方统一从本服务取。
        """
        return fingerprint(token)
