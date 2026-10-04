# MIDAS Open API 示例与冒烟测试

本目录由 **Endpoint Registry**（`../registry`）与 **Dennis5882/MIDAS-API** 仓库的 Python 示例自动生成，用于联调、验收与回归。

## 文件

| 文件 | 说明 |
| --- | --- |
| `midas_client.py` | 参考客户端：Registry 驱动的 REST 调用、方法集校验、请求体自动包装、重试策略、`info/db/{CODE}` 自省、WebSocket 骨架 |
| `cases.json` | 从官方示例抽取的请求用例（方法 / URI / 载荷 / 对应 Registry key） |
| `smoke_test.py` | 按 Registry 逐端点冒烟测试（默认 dry-run，`--live` 真实调用） |
| `smoke_report.json` | 冒烟测试报告（运行后生成） |

## 快速开始

```bash
# 1) 只校验 Registry，不连 MIDAS
python smoke_test.py

# 2) 真实只读冒烟（只调用 GET 端点，不改模型）
python smoke_test.py --live \
  --base-url https://moa-engineers.midasit.com:443/gen \
  --mapi-key <你的 MAPI-Key> \
  --product GEN_NX
```

## 客户端用法

```python
from midas_client import MidasClient, MidasError

c = MidasClient(base_url="https://moa-engineers.midasit.com:443/gen", mapi_key="<KEY>")

c.get("DB.NODE")                      # 按 Registry key 读取，自动校验方法集
c.call("DB.NODE", "POST", payload={   # 自动包一层 Assign
    "1": {"X": 0, "Y": 0, "Z": 0}})
c.call("POST.TABLE.BEAMFORCE", "POST", payload={
    "Argument": {"TABLE_TYPE": "BEAMFORCE", "TABLE_NAME": "BF"}})
c.introspect("NODE")                  # {base url} + info/db/NODE

try:
    c.call("DOC.ANAL", "POST")        # ANAL 不自动重试
except MidasError as e:
    print(e.code, e.details)          # 结构化错误（对齐主开发文档 §104）
```

客户端行为由 Registry 决定：

| 行为 | 依据 |
| --- | --- |
| 方法是否允许 | `methods`；不允许时抛 `METHOD_NOT_ALLOWED`，**不发出请求** |
| 产品是否支持 | `products` / `product_overrides`；不支持时抛 `PRODUCT_CAPABILITY_UNSUPPORTED` |
| 请求体包装 | `wrapper.write`（`Assign` / `Argument`） |
| 是否自动重试 | `risk.retry.<METHOD>`（`true` 才重试；`conditional` 不自动重试） |
| 超时 | `execution.timeout_ms` |

## 用例分布

- 用例总数：**505**（其中 **317** 个含请求载荷）
- 已映射到 Registry key：**396**

| 命名空间 | 用例数 |
| --- | --- |
| DB | 271 |
| POST | 101 |
| DESIGN | 61 |
| OPE | 34 |
| DOC | 23 |
| VIEW | 15 |

| 方法 | 用例数 |
| --- | --- |
| POST | 324 |
| GET | 71 |
| DELETE | 64 |
| PUT | 46 |

## 注意

1. **`--live` 默认只调用 GET 端点**，不会修改模型；如需调用写操作请显式加 `--all-methods`（危险，会改模型）。
2. `DOC.ANAL`、`DESIGN.*` 等长任务在 Registry 中标为 `execution.mode: LONG`，真实调用前请先确认 MIDAS 侧状态。
3. 载荷来自官方示例，**部分含占位值**（单元号、文件路径等），真实运行前需替换。
4. `cases.json` 中 `registry_key` 为空表示该 URI 在 Registry 中不唯一（如 `post/TABLE` 对应 199 个结果表），需结合 `TABLE_TYPE` 使用。
5. `midas_client.py` 仅依赖标准库（WebSocket 需额外 `pip install websocket-client`）。
