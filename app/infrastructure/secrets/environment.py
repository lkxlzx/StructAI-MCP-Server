"""Environment credential provider（`docs/07` §8.5 / §14.3；`docs/02` §21 / §26）。

凭据**只**由运行环境注入，进程内从 `os.environ` 读取，**不**持有任何值存储，
**不**把凭据写回任何持久层。

引用名口径：`reference` 是**逻辑引用名**（如 `adapter.primary`）。读取时规范化为
环境变量名 `<ENVIRONMENT_REFERENCE_PREFIX><REF 大写，非字母数字→下划线>`，即
`adapter.primary` → `STRUCTAI_SECRET_ADAPTER_PRIMARY`。
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Final

from app.domain.errors import InternalError
from app.infrastructure.secrets.base import looks_sensitive

ENVIRONMENT_REFERENCE_PREFIX: Final[str] = "STRUCTAI_SECRET_"
"""引用名 → 环境变量名前缀（`docs/07` §8.5）。"""

_NON_ALNUM: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9]+")


class EnvironmentCredentialProvider:
    """从运行环境按 `<PREFIX><REF>` 读取凭据值（`docs/02` §26）。

    Args:
        environ: 环境映射；`None` → 进程 `os.environ`（**不**复制，便于测试注入）。
    """

    prefix: Final[str] = ENVIRONMENT_REFERENCE_PREFIX

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    @classmethod
    def variable_name_for(cls, reference: str) -> str:
        """逻辑引用名 → 环境变量名（大写、非字母数字→下划线、加前缀）。"""
        normalized = _NON_ALNUM.sub("_", str(reference).strip()).strip("_").upper()
        return f"{ENVIRONMENT_REFERENCE_PREFIX}{normalized}"

    @staticmethod
    def _reference_key(reference: str) -> str:
        """逻辑引用名 → 规范化的**裸**引用键（小写、非字母数字→下划线）。"""
        return _NON_ALNUM.sub("_", str(reference).strip()).strip("_").lower()

    def references(self) -> tuple[str, ...]:
        """已配置的引用名（规范化裸名，升序、去重；**不**含值）。"""
        names = set()
        for key in self._environ:
            if key.startswith(ENVIRONMENT_REFERENCE_PREFIX):
                names.add(key[len(ENVIRONMENT_REFERENCE_PREFIX):].lower())
        return tuple(sorted(names))

    async def get_secret(self, reference: str) -> str:
        """按引用名读取凭据值（缺失 / 空白 → `STRUCTAI-7000`，**不**回落空串）。

        Raises:
            InternalError: `STRUCTAI-7000`，`details = {"stage": "credentials",
                "reason": "secret_not_configured"}`；引用名**不**敏感时附带
                `"reference": <name>`，敏感时**不**回显引用名。
        """
        name = self.variable_name_for(reference)
        value = self._environ.get(name)
        if value is None or not value.strip():
            details: dict[str, object] = {
                "stage": "credentials",
                "reason": "secret_not_configured",
            }
            if not looks_sensitive(reference):
                details["reference"] = str(reference)
            raise InternalError(
                "credential is not configured in the runtime environment",
                details=details,
            )
        return value

    async def set_secret(self, reference: str, value: str) -> None:
        """**显式拒绝**：凭据只由运行环境注入（`docs/07` §8.5 / §14.3）。"""
        raise RuntimeError(
            "credentials are injected by the runtime environment only; "
            "the process must never write them back (docs/07 §8.5 / §14.3)"
        )

    async def delete_secret(self, reference: str) -> None:
        """**显式拒绝**：凭据只由运行环境注入（`docs/07` §8.5 / §14.3）。"""
        raise RuntimeError(
            "credentials are injected by the runtime environment only; "
            "the process must never delete them (docs/07 §8.5 / §14.3)"
        )

    def __repr__(self) -> str:
        """诊断表示：只含前缀与已配置数量，**绝不**含任何值。"""
        count = sum(1 for k in self._environ if k.startswith(ENVIRONMENT_REFERENCE_PREFIX))
        return f"EnvironmentCredentialProvider(prefix={self.prefix!r}, configured={count})"
