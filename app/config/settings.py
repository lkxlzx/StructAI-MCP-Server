"""配置层 · Settings（pydantic-settings）。

权威来源：

- `docs/02` §5 / §5.1 —— Configuration Source（`source7`）与「配置」（`source9`）。
  两份规范的字段集互补，本文件取**并集**，默认值逐项照抄，不做改写。
- `.env.example` —— P01 已冻结全部变量名；本文件字段与之一一对应。
- `docs/07` §3.1 / §3.2 —— 配置方案冻结为 pydantic-settings。

约定（`docs/08` §4）：**环境变量名 = 字段名的大写形式**（pydantic-settings 默认行为，
大小写不敏感）。新增字段必须同步登记到 `.env.example`。

安全（`docs/07` §14.3）：本文件**绝不**出现任何 secret（password / API key / token /
private key）的默认值；凭据只能经运行环境注入，不得落库、落日志、落文件。
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]


class Settings(BaseSettings):
    """进程级配置：环境变量 / `.env` → 覆盖默认值。

    字段顺序与 `.env.example` 分组一致，便于逐项核对。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ===== 应用（source9 §5.1）=====
    app_name: str = "StructAI MCP Server"
    app_version: str = "2.0.0-alpha"
    environment: str = "development"
    debug: bool = True
    log_level: str = "INFO"

    # ===== 数据库（source9 §5.1 默认值 + source7 §5.1 `sql_echo`）=====
    # Core Alpha = SQLite(aiosqlite)；生产可切 PostgreSQL（postgresql+asyncpg://...）。
    database_url: str = "sqlite+aiosqlite:///./data/structai.db"
    sql_echo: bool = False
    # ===== 数据源目录（P08 Registry；`docs/02` §23 的 API Registry 数据源）=====
    # `registry/` 是外部软件 API 的**唯一权威数据源**（`registry/README.md`）；
    # 路径只能来自配置，不得在 `app/` 内硬编码任何厂商路径（`docs/07` §14.2）。
    registry_root: str = "./registry"

    # ===== MCP 传输（source7 §5.1；P40 STDIO / P41 Streamable HTTP 消费）=====
    mcp_transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 7860

    # ===== 任务 / 存储 / 超时（source7 §5.1）=====
    task_worker_count: int = 4
    artifact_root: str = "./data/artifacts"
    session_expire_seconds: int = 86400
    task_default_timeout_seconds: int = 3600
    lock_default_timeout_seconds: int = 300
    capability_cache_seconds: int = 300

    @property
    def data_dir(self) -> Path:
        """数据目录（source9 §5.1）。

        ⚠️ `source9` 规范中该属性的两个分支返回同一路径（占位写法）。此处**保持与
        规范一致**，不擅自收敛语义；待 P04 落地 SQLite 路径解析时再按需修正。
        """
        if self.database_url.startswith("sqlite"):
            return Path("./data")
        return Path("./data")


settings = Settings()
"""进程级单例（source9 §5.1）。

`docs/02` §34 的写法即为 `from app.config.settings import settings`。
"""
