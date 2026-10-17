"""端点目录：`registry/manifest.json` 的**只读**视图（P181 管理面数据源）。

为什么在 Application 层
------------------------
UI 的「工具与接口」页要展示端点 / Schema / 能力矩阵 / 请求示例。这些是**数据**，
不是传输格式、也不是某家软件的专属实现 —— 接口层只做转发（`docs/07` §14.1）。

口径
----
1. **只读**：目录是交付物，本层**不**写回；
2. 路径来自构造参数（`registry_root`），**不**硬编码；
3. 索引缺失 ⇒ `available=False`，**不**伪造端点；
4. 本模块**不**出现任何厂商名（`docs/07` §14.2）。
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

__all__ = ["EndpointCatalog", "MANIFEST_FILENAME", "load_catalog"]

MANIFEST_FILENAME: Final[str] = "manifest.json"
"""目录索引文件名（`registry/manifest.json`，由 `sync_manifest.py` 派生）。"""


@dataclass(frozen=True, slots=True)
class EndpointCatalog:
    """`registry/` 的只读索引（**懒加载** Schema 原文）。"""

    root: pathlib.Path
    available: bool
    counts: Mapping[str, Any]
    endpoints: tuple[Mapping[str, Any], ...]

    def summary(self) -> dict[str, Any]:
        """目录摘要（工具页顶部 / 首页卡片）。"""
        namespaces: dict[str, int] = {}
        for item in self.endpoints:
            name = str(item.get("namespace") or "")
            namespaces[name] = namespaces.get(name, 0) + 1
        return {
            "available": self.available,
            "root": str(self.root),
            "counts": dict(self.counts),
            "namespaces": dict(sorted(namespaces.items())),
        }

    def list_endpoints(
        self,
        *,
        namespace: str = "",
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """按命名空间 / 关键词过滤（**不分页以外的隐式截断**）。"""
        prefix = namespace.strip().upper()
        needle = query.strip().lower()
        rows = [
            item
            for item in self.endpoints
            if (not prefix or str(item.get("namespace") or "").upper() == prefix)
            and (
                not needle
                or needle in str(item.get("key") or "").lower()
                or needle in str(item.get("title") or "").lower()
                or needle in str(item.get("title_zh") or "").lower()
                or needle in str(item.get("uri") or "").lower()
            )
        ]
        page = rows[offset : offset + limit]
        return {
            "total": len(rows),
            "limit": limit,
            "offset": offset,
            "items": [self._row(item) for item in page],
        }

    def endpoint(self, key: str) -> dict[str, Any] | None:
        """单个端点（含请求 Schema 原文；取不到 ⇒ `None`，**不**猜）。"""
        target = str(key)
        for item in self.endpoints:
            if str(item.get("key")) == target:
                payload = self._row(item)
                payload["schema"] = self._schema(item)
                payload["definition"] = item.get("definition")
                return payload
        return None

    def operations(self, operation_names: tuple[str, ...]) -> dict[str, Any]:
        """Operation 清单（名字来自运行时注册表；本层只做分组）。"""
        return {
            "count": len(operation_names),
            "items": [{"name": name} for name in operation_names],
        }

    @staticmethod
    def _row(item: Mapping[str, Any]) -> dict[str, Any]:
        """列表 / 详情共用的字段（**不含** Schema 原文）。"""
        return {
            "key": item.get("key"),
            "namespace": item.get("namespace"),
            "uri": item.get("uri"),
            "methods": item.get("methods"),
            "products": item.get("products") or [],
            "title": item.get("title"),
            "title_zh": item.get("title_zh"),
            "table_type": item.get("table_type"),
            "execution_mode": item.get("execution_mode"),
            "availability": item.get("availability"),
            "verified_on": item.get("verified_on") or [],
            "spec_rows": item.get("spec_rows"),
            "examples": item.get("examples"),
            "schema_source": item.get("schema_source"),
        }

    def _schema(self, item: Mapping[str, Any]) -> Any:
        """请求 Schema 原文（相对 `registry/` 的路径；缺失 ⇒ `None`）。"""
        relative = item.get("schema")
        if not relative:
            return None
        path = self.root / str(relative)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


def load_catalog(root: str | pathlib.Path) -> EndpointCatalog:
    """装载目录（**只读**；索引缺失 ⇒ `available=False`，不抛）。"""
    base = pathlib.Path(root)
    path = base / MANIFEST_FILENAME
    if not path.is_file():
        return EndpointCatalog(root=base, available=False, counts={}, endpoints=())
    payload = json.loads(path.read_text(encoding="utf-8"))
    endpoints = tuple(item for item in payload.get("endpoints") or [] if isinstance(item, Mapping))
    counts = payload.get("counts") or {}
    return EndpointCatalog(
        root=base,
        available=True,
        counts=counts if isinstance(counts, Mapping) else {},
        endpoints=endpoints,
    )
