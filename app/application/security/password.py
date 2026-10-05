"""Password Service —— Argon2id 口令哈希（`docs/02` §7；`docs/07` §8.3）。

权威来源
--------
- `docs/02` §7（`blue` §7）—— 文件路径 `app/application/security/password.py`；
  「第一实现必须使用 **Argon2id**」，依赖 `argon2-cffi>=23.1,<26`；
  `PasswordService` 只暴露 `hash` / `verify` / `needs_rehash`，本文件逐项照抄。
- `docs/02` §7 的调用点（§9 AuthenticationService / §55 Password Test）——
  `verify` 的**参数顺序是 `(password_hash, password)`**，照抄规范，不擅自调换。
- `docs/02` §8（Password 安全要求）—— 禁止 `MD5` / `SHA1` / `SHA256(password)` /
  明文 / 可逆加密；数据库只能保存 `password_hash`；日志禁止 `password` /
  `password_hash`（`docs/07` §14.3：绝不记录 secret）。
- `docs/07` §8.3 —— 密码哈希 = Argon2id。
- `docs/07` §12 P07 —— P07 Seed 用本服务把 `STRUCTAI_BOOTSTRAP_ADMIN_PASSWORD`
  转成 `password_hash` 后入库（`docs/02` §44）。

本文件在规范之上的补充（只提供实现手段，不改变接口口径）
------------------------------------------------------
- `argon2.exceptions.*` 全部继承 `Exception`；规范要求 `verify` / `needs_rehash`
  在**任何**异常下一律返回 `False`（不向上抛、不泄露哈希格式细节），故此处
  按规范捕获 `Exception` 并附 `noqa` 说明。
- `PasswordHasher` 可由调用方注入（便于测试 / 参数轮换）；默认即 `PasswordHasher()`
  的规范默认参数。

🔴 安全（`docs/07` §14.3）：本模块**不产生任何日志**，也不把口令写回调用方之外的
任何地方；`hash()` 的返回值是唯一的出口。
"""

from __future__ import annotations

from argon2 import PasswordHasher

__all__ = ["PasswordService"]


class PasswordService:
    """口令哈希服务（`docs/02` §7）。

    只做三件事：生成哈希、校验哈希、判断是否需要重新哈希。
    口令本身（明文）**绝不**离开调用栈，也绝不落库 / 落日志（`docs/07` §14.3）。
    """

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        """创建服务实例。

        Args:
            hasher: 可选的 `argon2.PasswordHasher`（默认使用规范默认参数的实例）。
        """
        self._hasher = hasher if hasher is not None else PasswordHasher()

    def hash(self, password: str) -> str:
        """把明文口令转为 Argon2id 哈希（`docs/02` §7）。

        Args:
            password: 明文口令（**只在此处使用，不缓存、不记录**）。

        Returns:
            `$argon2id$...` 形式的自描述哈希串；数据库只保存本返回值
            （`docs/02` §8：只能保存 `password_hash`）。
        """
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        """校验口令与哈希是否匹配（`docs/02` §7；参数顺序照抄规范）。

        Args:
            password_hash: 库中保存的哈希（`docs/02` §8）。
            password: 待校验的明文口令。

        Returns:
            `True` 表示匹配；任何异常（格式非法、不匹配等）一律返回 `False`，
            **不向上抛**（`docs/02` §7；避免泄露哈希格式与失败原因）。
        """
        try:
            return bool(self._hasher.verify(password_hash, password))
        except Exception:  # noqa: BLE001 - 规范要求：任何异常都视为校验失败
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        """判断哈希是否需要用当前参数重新生成（`docs/02` §7）。

        Args:
            password_hash: 库中保存的哈希。

        Returns:
            需要重哈希为 `True`；哈希非法或校验异常时返回 `False`
            （`docs/02` §7：与 `verify` 同样不向上抛）。
        """
        try:
            return bool(self._hasher.check_needs_rehash(password_hash))
        except Exception:  # noqa: BLE001 - 规范要求：任何异常都视为「无需重哈希」
            return False
