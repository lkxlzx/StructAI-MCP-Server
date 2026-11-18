<#
.SYNOPSIS
    一键启动 StructAI MCP Server（加载 MIDAS 测试凭据后运行）。

.DESCRIPTION
    1) 调用 scripts/load-midas-env.ps1 把 MIDAS 凭据注入当前进程环境
       （凭据来自仓库外的 %USERPROFILE%\.structai\midas-test.env）。
    2) 可选先把 MIDAS 软件实例登记进数据库（vendor=MIDAS / product=GEN NX），
       实例的 endpoint 指向测试地址、并绑定到默认项目（租户边界链路）。
    3) 以指定传输启动 MCP 服务。

  真实 MIDAS 实例怎么用（对齐上游 P185「按需连接」设计）
  -----------------------------------------------------
  Core 启动时**只**注册 Mock Adapter；真实厂商 Adapter 在「连接某个实例」时
  经 app/infrastructure/adapters/plugins.py 按需发现并注册（docs/07 §14.2：
  Core 不写厂商名）。因此：
    · HTTP 传输（推荐）：启动后调 `POST /api/clients/{instanceId}/connect`，
      或在 Web UI 客户端页点「连接」；连上后 `/api/call` 用同一 9 Tool 链即可
      调真实 MIDAS。`seed_midas_instance.py` 会打印 instanceId。
    · stdio 传输：只服务**启动时已绑定的 Mock 实例**；真实 MIDAS 需同进程
      先 connect，stdio 场景下不易触发 —— 连接真实 MIDAS 请用 http。

  为什么 MIDAS 凭据必须走进程环境而非 .env（docs/07 §8.5 / §14.3）：
    pydantic-settings 的 .env 只填 Settings 字段、**不**写入 os.environ；
    而 MidasEnvironmentCredential 读 os.environ 的 MIDAS_MAPI_KEY。
    故凭据只能经环境注入（本脚本的加载器完成）。

.PARAMETER Instance
    凭据实例：gen | civil | cdn。默认 gen（本机 MIDAS GEN NX 测试实例）。

.PARAMETER Transport
    http | stdio | none（none = 只做启动自检）。默认 http（连接真实 MIDAS 用 http）。

.PARAMETER Seed
    先登记 MIDAS 软件实例（幂等）。首次运行或换库时使用。

.EXAMPLE
    .\scripts\run-midas.ps1 -Seed                 # 登记实例并启动 http（默认）
    .\scripts\run-midas.ps1 -Seed -Transport none # 只做启动自检
#>
[CmdletBinding()]
param(
    [ValidateSet('gen', 'civil', 'cdn')]
    [string]$Instance = 'gen',

    [ValidateSet('stdio', 'http', 'none')]
    [string]$Transport = 'http',

    [switch]$Seed
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

# 1) 加载 MIDAS 凭据到当前进程环境
. (Join-Path $PSScriptRoot 'load-midas-env.ps1') -Instance $Instance

# 2) 可选：登记 MIDAS 软件实例（幂等；仅当库已建表/已 seed）
if ($Seed) {
    Write-Host '>> seeding MIDAS software instance (vendor=MIDAS / product=GEN NX) ...'
    python (Join-Path $PSScriptRoot 'seed_midas_instance.py')
}

# 3) 启动 MCP 服务
Write-Host (">> starting StructAI MCP Server (transport=$Transport, instance=$Instance) ...")
if ($Transport -eq 'none') {
    python -m app.main
} else {
    python -m app.main --transport $Transport
}
