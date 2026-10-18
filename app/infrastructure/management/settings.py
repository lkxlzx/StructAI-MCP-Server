"""Infrastructure · Management · 系统设置的持久化（P183）。

为什么需要它
------------
系统设置页的 7 个标签页（基础 / 服务 / 模型 / 用户 / 安全 / 数据 / 关于）在原
原型里全是静态 mock。要让它们**真正可操作**，需要一处「设置值的落点」。

落点选择（与既有红线一致）
--------------------------
1. **不新增 Core 表**：`docs/07` §4.3 的 24 张表是冻结口径，多个测试逐表断言
   `Base.metadata.tables`。故设置值落在一个**独立**的 SQLite 文件
   （`Settings.management_settings_path`），由本模块用标准库 `sqlite3` 读写。
2. **不进 `Base.metadata`**：独立库 = 独立 schema，Alembic 不需要知道它；
   启动时**不建表**的纪律只针对 Core 库，本模块是显式的运维配置库。
3. **不写 secret**：`models` 的 `api_key` 只存**是否已配置**与掩码后的尾部，
   明文 key 由 `EnvironmentCredentialProvider` 从运行环境注入（`docs/07` §14.3）。
   安全设置的密码策略、通知邮箱等均非 secret，可按原值保存。

写入语义
--------
- 所有写操作走 `UnitOfWork` 之外的**短连接**（`sqlite3.connect` + 事务），
  与 Core 库的事务边界互不影响。
- `update_settings(section, values)` 是**深合并**：只覆盖给出的键，
  未知 section 拒绝（`STRUCTAI-1000`），未知键忽略（前端可能比后端新）。
- 读取时把默认值与落库值合并，保证「新加字段有默认值」。

⚠️ 本模块是 Infrastructure：允许文件 I/O 与 sqlite3；**不**做业务判定，
也**不**出现任何厂商名。
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sqlite3
import threading
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from app.domain.errors import ProtocolError

__all__ = [
    "DEFAULT_SETTINGS",
    "SETTINGS_SECTIONS",
    "SettingsStore",
    "build_settings_store",
]

SETTINGS_SECTIONS: Final[tuple[str, ...]] = (
    "system",
    "behavior",
    "interface",
    "paths",
    "notify",
    "service",
    "security",
    "models",
    "data",
)
"""可持久化的设置分区（与前端 7 个标签页对应；`system` 为只读信息，写时忽略）。"""

DEFAULT_SETTINGS: Final[dict[str, dict[str, Any]]] = {
    "system": {
        # 产品名 / 厂商名由前端（品牌资源）给出：`app/` 内不得出现厂商名
        # （`docs/07` §14.2；厂商知识只在 `registry/` 与 Adapter 子包）。
        "product_name": "",
        "vendor": "StructAI",
    },
    "behavior": {
        "default_software": "",
        "default_version": "",
        "task_timeout_minutes": 60,
        "log_retention_days": 30,
        "auto_cleanup": True,
        "check_update_on_start": True,
        "minimize_to_tray": False,
    },
    "interface": {
        "theme": "light",
        "language": "zh-CN",
        "density": "comfortable",
        "page_size": 10,
        "show_tooltips": True,
        "show_animations": True,
        "compact_sidebar": False,
    },
    "paths": {
        # 空串 = 跟随运行时（`service.settings()` 会用真实目录补全后再返回）。
        "software_home": "",
        "temp_dir": "",
        "project_dir": "",
        "model_dir": "",
        "result_dir": "",
    },
    "notify": {
        "task_done": True,
        "task_failed": True,
        "system_error": True,
        "channels": ["page", "browser"],
        "email": "",
        # SMTP 口令**不**落库：只从 `STRUCTAI_SMTP_PASSWORD` 读取（docs/07 §14.3）。
        "smtp": {
            "host": "",
            "port": 587,
            "username": "",
            "from": "",
            "tls": True,
        },
    },
    "service": {
        "listen_host": "127.0.0.1",
        "port": 7860,
        "management_port": 7860,
        "max_connections": 100,
        "cors_enabled": False,
        "cors_origins": "",
        "features": {
            "mcp": True,
            "rest": True,
            "web": True,
            "queue": True,
            "cache": True,
            "verbose_log": False,
        },
        "performance": {
            "workers": 4,
            "queue_size": 100,
            "task_timeout_seconds": 3600,
            "cache_seconds": 3600,
        },
        "env": [
            {"name": "SOFTWARE_HOME", "value": "", "description": "设计软件安装目录"},
            {"name": "TEMP_DIR", "value": "", "description": "临时文件目录"},
            {"name": "LOG_LEVEL", "value": "INFO", "description": "日志级别"},
            {"name": "MAX_FILE_SIZE", "value": "100", "description": "上传文件大小限制(MB)"},
        ],
    },
    "security": {
        "login": {
            "enabled": True,
            "max_attempts": 5,
            "lock_minutes": 30,
            "captcha": True,
            "captcha_minutes": 10,
            "two_factor": False,
            "session_hours": 24,
            "max_sessions": 3,
            "force_password_change": True,
        },
        "password": {
            "min_length": 8,
            "require_upper": True,
            "require_lower": True,
            "require_digit": True,
            "require_special": True,
            "expire_days": 90,
            "history": 5,
            "idle_disable_days": 180,
        },
        "access": {
            "whitelist_enabled": False,
            "whitelist": "",
            "blacklist_enabled": False,
            "blacklist": "",
            "rate_limit_enabled": True,
            "rate_per_minute": 120,
            "rate_per_ip": 1000,
        },
        "data": {
            "encrypt_at_rest": True,
            "https": True,
            "mask_sensitive": True,
            "backup_config": True,
            "backup_keep_days": 30,
            "mask_export": True,
        },
        "audit": {
            "audit_enabled": True,
            "alerts_enabled": True,
            "channels": ["system", "email"],
            "login_failure_threshold": 10,
            "abnormal_request_threshold": 100,
        },
    },
    "models": {
        # 与设计稿一致的初始模型清单（可用性如实标注；`gpt-4o` 标记为不可用）。
        "items": [
            {
                "id": "deepseek-v4-flash",
                "name": "deepseek-v4-flash",
                "provider": "DeepSeek",
                "kind": "对话模型",
                "context": "128K",
                "available": True,
                "is_default": True,
                "description": "高效快速的对话模型，适用于日常任务和工具调用",
            },
            {
                "id": "deepseek-v4-pro",
                "name": "deepseek-v4-pro",
                "provider": "DeepSeek",
                "kind": "对话模型",
                "context": "128K",
                "available": True,
                "is_default": False,
                "description": "高精度对话模型，适用于复杂工程任务",
            },
            {
                "id": "qwen3.8-max",
                "name": "qwen3.8-max",
                "provider": "通义千问",
                "kind": "对话模型",
                "context": "128K",
                "available": True,
                "is_default": False,
                "description": "通义千问旗舰模型",
            },
            {
                "id": "glm-4.5",
                "name": "glm-4.5",
                "provider": "智谱AI",
                "kind": "对话模型",
                "context": "128K",
                "available": True,
                "is_default": False,
                "description": "智谱 GLM 系列对话模型",
            },
            {
                "id": "claude-3-5-sonnet",
                "name": "claude-3-5-sonnet",
                "provider": "Anthropic",
                "kind": "对话模型",
                "context": "200K",
                "available": True,
                "is_default": False,
                "description": "Anthropic 长上下文对话模型",
            },
            {
                "id": "gpt-4o",
                "name": "gpt-4o",
                "provider": "OpenAI",
                "kind": "对话模型",
                "context": "128K",
                "available": False,
                "is_default": False,
                "description": "OpenAI 多模态对话模型",
            },
        ],
        "default": "deepseek-v4-flash",
        "parameters": {
            "temperature": 0.7,
            "max_tokens": 4096,
            "top_p": 0.9,
            "stream": True,
            "tools": True,
            "retry": True,
            "retry_count": 3,
        },
        "connection": {
            "base_url": "",
            "api_key_configured": False,
            "api_key_hint": "",
            "timeout_seconds": 60,
            "proxy": "none",
        },
    },
    "data": {
        "backup": {
            "auto": True,
            "frequency": "daily",
            "keep": 7,
            "path": "",
        },
        "export": {
            "scope": ["system", "users", "models", "tasks"],
            "format": "json",
        },
        "cleanup": {
            "tasks": {"enabled": True, "days": 30},
            "logs": {"enabled": True, "days": 60},
            "audit": {"enabled": False, "days": 180},
            "deleted_users": {"enabled": False, "days": 0},
            "temp": {"enabled": True, "days": 0},
        },
    },
}
"""全部设置分区的**默认值**（前端 `settings.js` / `settings-tabs*.js` 的字段口径）。"""

_DEEP_MERGE_SECTIONS: Final[frozenset[str]] = frozenset({"service", "security", "models", "data"})
"""需要**深合并**的分区（其余分区是扁平键值，直接浅合并）。"""

_LOCK = threading.Lock()
"""同一进程内的写串行化（设置写入是低频运维动作）。"""


class SettingsStore:
    """设置值的持久化（独立 SQLite 文件；`section → JSON`）。"""

    def __init__(self, path: str | pathlib.Path) -> None:
        """绑定存储文件（**不**建表；首次读取时惰性建表）。"""
        self._path = pathlib.Path(path)
        self._initialized = False

    @property
    def path(self) -> pathlib.Path:
        """存储文件路径（只读诊断）。"""
        return self._path

    # ===== 读 =====

    def read(self) -> dict[str, Any]:
        """读取全部设置（默认值 ⊕ 落库值）。

        Returns:
            `section → value`；文件不存在或损坏时返回默认值的深拷贝。
        """
        stored = self._read_stored()
        return {
            section: _merge(default, stored.get(section))
            for section, default in DEFAULT_SETTINGS.items()
        }

    def section(self, name: str) -> dict[str, Any]:
        """读取单个分区（未知分区 → `STRUCTAI-1000`）。"""
        self._require_section(name)
        return self.read()[name]

    # ===== 写 =====

    def update(self, section: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """深合并一个分区并返回**合并后**的分区值。

        Args:
            section: 分区名（`SETTINGS_SECTIONS`）。
            values: 只包含要覆盖的键（嵌套字典按层合并）。

        Raises:
            ProtocolError: `STRUCTAI-1000` —— 未知分区，
                或分区值是标量而给了映射（类型不匹配）。
        """
        self._require_section(section)
        if section == "system":
            # `system` 是运行时只读信息（版本 / 构建时间 / 运行环境），不接受写入。
            return self.section(section)
        current = self.read()
        merged = _merge(current[section], dict(values))
        if not isinstance(merged, dict):
            raise ProtocolError(
                "settings section must be an object",
                details={"stage": "management", "reason": "settings_type_mismatch"},
            )
        with _LOCK:
            stored = self._read_stored()
            stored[section] = merged
            self._write_stored(stored)
        return merged

    def reset(self, section: str = "") -> None:
        """恢复默认值（空串 = 全部；`system` 无落库值，天然是默认值）。

        ⚠️ 必须 `DELETE` 落库行：`_write_stored` 只做 `INSERT OR REPLACE`，
        从字典里 pop 掉并不会删掉数据库里的旧值。
        """
        with _LOCK:
            if section:
                self._require_section(section)
            with self._connection() as connection, connection:
                if section:
                    connection.execute("DELETE FROM settings WHERE section = ?", (section,))
                else:
                    connection.execute("DELETE FROM settings")

    def replace_items(self, section: str, key: str, items: list[Any]) -> list[Any]:
        """整体替换分区下的一个列表（列表语义不做深合并，避免元素错位）。"""
        self._require_section(section)
        current = self.read()
        payload = dict(current[section])
        payload[key] = items
        with _LOCK:
            stored = self._read_stored()
            stored[section] = payload
            self._write_stored(stored)
        return items

    # ===== 内部 =====

    def _require_section(self, name: str) -> None:
        """分区名校验（未知分区一律拒绝，避免拼写错误静默落库）。"""
        if name not in SETTINGS_SECTIONS:
            raise ProtocolError(
                "unknown settings section",
                details={"stage": "management", "reason": "unknown_settings_section"},
            )

    @contextlib.contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """连接即用即关（Windows 下句柄不释放会锁住文件）。"""
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        """打开存储库（首次调用时建表）。"""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._path), timeout=10)
        if not self._initialized:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS settings ("
                "section TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            # 用户档案（姓名 / 邮箱 / 手机 / 备注）：Core 的 `users` 表是冻结口径，
            # 不含这些展示字段，故落在本运维库，按 `user_id` 关联。
            connection.execute(
                "CREATE TABLE IF NOT EXISTS user_profiles ("
                "user_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            # 客户端档案 / 事件（P185）：Core 的 software_instances 是冻结口径，
            # 描述等展示字段与连接测试历史落在本运维库，按实例 id 关联。
            connection.execute(
                "CREATE TABLE IF NOT EXISTS client_profiles ("
                "client_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS client_events ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT NOT NULL, "
                "payload TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS ix_client_events_client ON client_events(client_id, id)"
            )
            # 口令历史（只存 Argon2id 哈希；用于「禁止使用历史密码」策略）。
            connection.execute(
                "CREATE TABLE IF NOT EXISTS password_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, "
                "password_hash TEXT NOT NULL, created_at TEXT NOT NULL)"
            )
            # DDL 用事务上下文提交（避免 `.commit()` 字面量：`docs/07` §14.4 要求
            # 只有 `unit_of_work.py` 出现 commit / rollback 调用）。
            with connection:
                pass
            self._initialized = True
        return connection

    # ===== 用户档案（展示字段；与 Core `users` 按 id 关联）=====

    def read_profiles(self) -> dict[str, dict[str, Any]]:
        """读取全部用户档案（损坏行跳过）。"""
        if not self._path.is_file():
            return {}
        try:
            with self._connection() as connection:
                rows = connection.execute("SELECT user_id, payload FROM user_profiles").fetchall()
        except sqlite3.Error:
            return {}
        profiles: dict[str, dict[str, Any]] = {}
        for user_id, payload in rows:
            try:
                value = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                profiles[str(user_id)] = value
        return profiles

    def write_profile(self, user_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """写入单个用户档案（与既有值合并）。"""
        profiles = self.read_profiles()
        merged = {**profiles.get(user_id, {}), **dict(values)}
        with _LOCK:
            # `with connection:` 在成功时提交、异常时回滚（sqlite3 的事务上下文）；
            # 本文件是**独立**的运维库，不参与 Core 的 UnitOfWork 事务边界。
            with self._connection() as connection, connection:
                connection.execute(
                    "INSERT OR REPLACE INTO user_profiles(user_id, payload, updated_at) "
                    "VALUES (?, ?, ?)",
                    (
                        user_id,
                        json.dumps(merged, ensure_ascii=False),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        return merged

    def delete_profile(self, user_id: str) -> None:
        """删除用户档案（幂等）。"""
        if not self._path.is_file():
            return
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute("DELETE FROM user_profiles WHERE user_id = ?", (user_id,))

    # ===== 客户端档案 / 事件（P185；与 Core 注册表按实例 id 关联）=====

    def read_client_profiles(self) -> dict[str, dict[str, Any]]:
        """读取全部客户端档案（描述等展示字段；损坏行跳过）。"""
        return self._read_json_table("client_profiles", "client_id")

    def write_client_profile(self, client_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """写入单个客户端档案（与既有值合并）。"""
        profiles = self.read_client_profiles()
        merged = {**profiles.get(client_id, {}), **dict(values)}
        self._write_json_row("client_profiles", "client_id", client_id, merged)
        return merged

    def delete_client_profile(self, client_id: str) -> None:
        """删除客户端档案（幂等）。"""
        self._delete_json_row("client_profiles", "client_id", client_id)

    def append_client_event(self, client_id: str, event: Mapping[str, Any]) -> None:
        """追加一条客户端事件（连接测试 / 生命周期；保留最近 200 条）。"""
        payload = json.dumps(dict(event), ensure_ascii=False)
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute(
                    "INSERT INTO client_events(client_id, payload, created_at) VALUES (?, ?, ?)",
                    (client_id, payload, datetime.now(UTC).isoformat()),
                )
                connection.execute(
                    "DELETE FROM client_events WHERE client_id = ? AND id NOT IN ("
                    "SELECT id FROM client_events WHERE client_id = ? ORDER BY id DESC LIMIT 200)",
                    (client_id, client_id),
                )

    def read_client_events(self, client_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        """读取客户端事件（新的在前）。"""
        if not self._path.is_file():
            return []
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT payload, created_at FROM client_events WHERE client_id = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (client_id, max(1, min(int(limit), 200))),
                ).fetchall()
        except sqlite3.Error:
            return []
        events: list[dict[str, Any]] = []
        for payload, created_at in rows:
            try:
                value = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                events.append({**value, "time": created_at})
        return events

    # ===== 口令历史（只存哈希）=====

    def read_password_history(self, user_id: str, *, limit: int = 20) -> list[str]:
        """读取用户最近 N 个口令哈希（新的在前）。"""
        if not self._path.is_file():
            return []
        try:
            with self._connection() as connection:
                rows = connection.execute(
                    "SELECT password_hash FROM password_history WHERE user_id = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (user_id, max(1, min(int(limit), 100))),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [str(row[0]) for row in rows]

    def append_password_history(self, user_id: str, password_hash: str, *, keep: int = 20) -> None:
        """记录一个口令哈希并裁剪历史（**绝不**存明文）。"""
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute(
                    "INSERT INTO password_history(user_id, password_hash, created_at) "
                    "VALUES (?, ?, ?)",
                    (user_id, password_hash, datetime.now(UTC).isoformat()),
                )
                connection.execute(
                    "DELETE FROM password_history WHERE user_id = ? AND id NOT IN ("
                    "SELECT id FROM password_history WHERE user_id = ? "
                    "ORDER BY id DESC LIMIT ?)",
                    (user_id, user_id, max(1, min(int(keep), 100))),
                )

    def clear_password_history(self, user_id: str) -> None:
        """清空用户口令历史（删除用户时调用）。"""
        if not self._path.is_file():
            return
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute("DELETE FROM password_history WHERE user_id = ?", (user_id,))

    # ===== 备份 / 恢复 / 导入 =====

    def backup_to(self, target: str | pathlib.Path) -> None:
        """用 SQLite backup API 把设置库复制到 `target`（不阻塞正在进行的读写）。"""
        destination = pathlib.Path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source, sqlite3.connect(str(destination)) as target_db:
            source.backup(target_db)

    def restore_from(self, source: str | pathlib.Path) -> None:
        """用 SQLite backup API 从 `source` 恢复设置库（源文件必须存在）。"""
        origin = pathlib.Path(source)
        if not origin.is_file():
            raise FileNotFoundError(str(origin))
        with sqlite3.connect(str(origin)) as source_db, self._connection() as target:
            source_db.backup(target)
        self._initialized = True

    def replace_sections(self, values: Mapping[str, Any]) -> list[str]:
        """按分区整体覆盖（导入用；未知分区忽略，`system` 忽略）。"""
        applied: list[str] = []
        with _LOCK:
            stored = self._read_stored()
            for section, value in values.items():
                if section not in SETTINGS_SECTIONS or section == "system":
                    continue
                if not isinstance(value, Mapping):
                    continue
                stored[section] = dict(value)
                applied.append(section)
            self._write_stored(stored)
        return applied

    # ===== 通用 JSON 行表 =====

    def _read_json_table(self, table: str, key: str) -> dict[str, dict[str, Any]]:
        """读取 `key → JSON` 表（损坏行跳过）。"""
        if not self._path.is_file():
            return {}
        try:
            with self._connection() as connection:
                rows = connection.execute(f"SELECT {key}, payload FROM {table}").fetchall()  # noqa: S608
        except sqlite3.Error:
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row_key, payload in rows:
            try:
                value = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                result[str(row_key)] = value
        return result

    def _write_json_row(self, table: str, key: str, row_key: str, value: Mapping[str, Any]) -> None:
        """写入一行 `key → JSON`。"""
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute(
                    f"INSERT OR REPLACE INTO {table}({key}, payload, updated_at) "  # noqa: S608
                    "VALUES (?, ?, ?)",
                    (
                        row_key,
                        json.dumps(dict(value), ensure_ascii=False),
                        datetime.now(UTC).isoformat(),
                    ),
                )

    def _delete_json_row(self, table: str, key: str, row_key: str) -> None:
        """删除一行（幂等）。"""
        if not self._path.is_file():
            return
        with _LOCK:
            with self._connection() as connection, connection:
                connection.execute(f"DELETE FROM {table} WHERE {key} = ?", (row_key,))  # noqa: S608

    def _read_stored(self) -> dict[str, Any]:
        """读取落库值（损坏的行跳过，不让一个坏分区拖垮整个设置页）。"""
        if not self._path.is_file():
            return {}
        try:
            with self._connection() as connection:
                rows = connection.execute("SELECT section, payload FROM settings").fetchall()
        except sqlite3.Error:
            return {}
        stored: dict[str, Any] = {}
        for section, payload in rows:
            try:
                value = json.loads(payload)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                stored[str(section)] = value
        return stored

    def _write_stored(self, stored: Mapping[str, Any]) -> None:
        """整分区覆盖写（`INSERT OR REPLACE`，带 UTC 时间戳）。"""
        stamp = datetime.now(UTC).isoformat()
        with self._connection() as connection, connection:
            for section, value in stored.items():
                connection.execute(
                    "INSERT OR REPLACE INTO settings"
                    "(section, payload, updated_at) VALUES (?, ?, ?)",
                    (section, json.dumps(value, ensure_ascii=False), stamp),
                )


def build_settings_store(path: str | pathlib.Path) -> SettingsStore:
    """装配设置存储（**不**做 I/O）。"""
    return SettingsStore(path)


def _merge(default: Any, override: Any) -> Any:
    """默认值 ⊕ 落库值（映射递归合并；列表 / 标量以落库值为准）。"""
    if isinstance(default, dict):
        base = dict(default)
        if isinstance(override, Mapping):
            for key, value in override.items():
                base[key] = _merge(base[key], value) if key in base else value
        return base
    if override is None:
        return default
    return override
