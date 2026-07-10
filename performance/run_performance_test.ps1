<#!
.SYNOPSIS
生成隔离性能数据并依次运行核心读接口与订单创建压测。

.DESCRIPTION
脚本会将中文汇总报告与 Locust 原始中间文件分别保存到独立目录。
仅可在本地开发或专用测试环境运行，禁止连接生产数据库。
#>
param(
    [ValidateSet("small", "medium", "large")]
    [string]$Profile = "medium",
    [ValidateRange(10, 100)]
    [int]$ReadUsers = 20,
    [ValidateRange(0.1, 50)]
    [double]$SpawnRate = 5,
    [ValidatePattern("^\d+[smh]$")]
    [string]$ReadDuration = "5m",
    [ValidatePattern("^$|^\d+[smh]$")]
    [string]$WriteDuration = "",
    [string]$Password = "PerfPass123!"
)

$ErrorActionPreference = "Stop"

# 以脚本位置反推出项目根目录，允许从任意 PowerShell 当前目录执行。
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Locust = Join-Path $ProjectRoot ".venv\Scripts\locust.exe"
$Timestamp = Get-Date -Format "yyMMddHHmm"
# 前缀需预留分类名称后缀，避免超过 Category.name 的数据库长度限制。
$Prefix = "p$Timestamp"
$RunName = "性能测试_$Timestamp"
# 最终结果只放置面向阅读的中文报告，原始文件单独隔离保存。
$ResultDirectory = Join-Path $PSScriptRoot "测试结果\$RunName"
$IntermediateDirectory = Join-Path $PSScriptRoot "中间文件\$RunName"
$ConfigFile = Join-Path $IntermediateDirectory "测试配置.json"

# 大档数据默认执行更长的写入测试；其他档位保留快速验证时长。
if (-not $WriteDuration) {
    $WriteDuration = if ($Profile -eq "large") { "5m" } else { "1m" }
}

function Assert-CommandFile {
    param([string]$Path, [string]$Description)

    # 在执行前给出清晰错误，避免后续命令显示难以理解的系统异常。
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "未找到$Description：$Path。请先创建虚拟环境并安装项目依赖。"
    }
}

function Invoke-LocustRun {
    param(
        [string]$ResultPrefix,
        [string]$HtmlFile,
        [int]$Users,
        [double]$Rate,
        [string]$Duration,
        [string[]]$UserClasses
    )

    # 使用调用运算符保留参数边界，避免结果目录含空格时路径解析错误。
    & $Locust "-f" (Join-Path $PSScriptRoot "locustfile.py") `
        "--headless" "-u" $Users "-r" $Rate "-t" $Duration `
        "--csv" $ResultPrefix "--html" $HtmlFile @UserClasses
    if ($LASTEXITCODE -ne 0) {
        throw "Locust 执行失败，退出码：$LASTEXITCODE"
    }
}

function Convert-LocustStatsToMarkdown {
    param([string]$StatsFile)

    # 只记录实际接口行，排除 Locust 自动生成的 Aggregated 汇总行。
    $Rows = Import-Csv -LiteralPath $StatsFile | Where-Object { $_.Name -ne "Aggregated" }
    if (-not $Rows) {
        return "| 无接口数据 | - | - | - | - | - |`n"
    }

    $Culture = [System.Globalization.CultureInfo]::InvariantCulture
    $Lines = foreach ($Row in $Rows) {
        # 统一保留两位小数，使报告便于人工阅读和横向比较。
        $Average = ([double]$Row.'Average Response Time').ToString("0.00", $Culture)
        $P95 = ([double]$Row.'95%').ToString("0.00", $Culture)
        $P99 = ([double]$Row.'99%').ToString("0.00", $Culture)
        $Rps = ([double]$Row.'Requests/s').ToString("0.00", $Culture)
        "| $($Row.Name) | $($Row.'Request Count') | $($Row.'Failure Count') | $Average | $P95 | $P99 | $Rps |"
    }
    return ($Lines -join "`n")
}

Assert-CommandFile -Path $Python -Description "Python 虚拟环境"
Assert-CommandFile -Path $Locust -Description "Locust 可执行文件"
New-Item -ItemType Directory -Force -Path $ResultDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $IntermediateDirectory | Out-Null

Push-Location $ProjectRoot
try {
    # 应用迁移，确保本次生成的数据与当前代码模型一致。
    & $Python "backend\manage.py" "migrate"
    if ($LASTEXITCODE -ne 0) {
        throw "数据库迁移失败，退出码：$LASTEXITCODE"
    }

    # 写出 JSON 配置，其中包含独立账号的短期 JWT 和本次商品、会话资源。
    & $Python "backend\manage.py" "seed_performance_data" `
        "--profile" $Profile "--prefix" $Prefix "--password" $Password `
        "--output-file" $ConfigFile
    if ($LASTEXITCODE -ne 0) {
        throw "性能数据生成失败，退出码：$LASTEXITCODE"
    }

    # Locust 在当前 PowerShell 进程中读取该变量，不需要人工复制任何测试账号。
    $env:PERF_BASE_URL = "http://127.0.0.1:8000"
    $env:PERF_CONFIG_FILE = $ConfigFile

    # 预热只用于填充匿名商品、分类和消息窗口缓存，不记录为正式结论。
    Invoke-LocustRun `
        -ResultPrefix (Join-Path $IntermediateDirectory "缓存预热") `
        -HtmlFile (Join-Path $IntermediateDirectory "缓存预热.html") `
        -Users $ReadUsers -Rate $SpawnRate -Duration "1m" `
        -UserClasses @("AnonymousBrowsingUser", "BuyerOrdersUser", "SellerOrdersUser", "MessagingUser")

    # 正式读接口测试覆盖商品、分类、卖家主页、订单与私信读取。
    Invoke-LocustRun `
        -ResultPrefix (Join-Path $IntermediateDirectory "核心读接口") `
        -HtmlFile (Join-Path $IntermediateDirectory "核心读接口.html") `
        -Users $ReadUsers -Rate $SpawnRate -Duration $ReadDuration `
        -UserClasses @("AnonymousBrowsingUser", "BuyerOrdersUser", "SellerOrdersUser", "MessagingUser")

    # 每个订单创建用户仅执行一次请求，且拥有独立账号和商品，因此不会触发每用户写入限流。
    $TestConfig = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
    $WriteAccountCount = [int]$TestConfig.order_creation_accounts.Count
    $WriteUsers = [Math]::Min($WriteAccountCount, 50)
    Invoke-LocustRun `
        -ResultPrefix (Join-Path $IntermediateDirectory "创建订单") `
        -HtmlFile (Join-Path $IntermediateDirectory "创建订单.html") `
        -Users $WriteUsers -Rate $SpawnRate -Duration $WriteDuration `
        -UserClasses @("OrderCreationUser")

    # 从 Locust 原始统计文件提取真实值，自动生成便于归档和阅读的汇总报告。
    $ReportFile = Join-Path $ResultDirectory "性能测试报告.md"
    $ReadStats = Convert-LocustStatsToMarkdown -StatsFile (Join-Path $IntermediateDirectory "核心读接口_stats.csv")
    $WriteStats = Convert-LocustStatsToMarkdown -StatsFile (Join-Path $IntermediateDirectory "创建订单_stats.csv")
    @"
# 核心接口性能测试报告

## 本次运行

- 测试时间：$(Get-Date -Format "yyyy-MM-dd HH:mm:ss K")
- 数据规模：$Profile
- 测试数据前缀：$Prefix
- 后端地址：$env:PERF_BASE_URL
- 读接口配置：$ReadUsers 用户，启动速率 $SpawnRate 用户/秒，持续 $ReadDuration
- 写接口配置：目标并发 $WriteUsers 用户，独立账号和商品池共 $WriteAccountCount 组；每次请求使用独立商品，持续 $WriteDuration
- 测试主机：$env:COMPUTERNAME
- PowerShell：$($PSVersionTable.PSVersion)

## 读接口结果

| 接口 | 请求数 | 失败数 | 平均响应时间(ms) | P95(ms) | P99(ms) | RPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
$ReadStats

## 创建订单结果

| 接口 | 请求数 | 失败数 | 平均响应时间(ms) | P95(ms) | P99(ms) | RPS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
$WriteStats

## 原始数据位置

原始 Locust HTML、CSV、缓存预热数据和测试配置均位于下列中间文件目录，不应提交到版本库：

`performance/中间文件/$RunName/`

- `核心读接口.html`：核心读接口完整 Locust 图表。
- `核心读接口_stats.csv`：核心读接口原始统计数据。
- `创建订单.html`：创建订单接口完整 Locust 图表。
- `创建订单_stats.csv`：创建订单接口原始统计数据。
- `测试配置.json`：本次数据集与账号配置，包含短期 JWT。

## 结果使用说明

本报告中的指标来自本次 Locust 实测。只有在失败数为 0、运行环境一致且完成对照实验时，才可以在项目说明或简历中引用性能数字。
"@ | Set-Content -LiteralPath $ReportFile -Encoding utf8

    Write-Host "性能测试完成。"
    Write-Host "测试结果目录：$ResultDirectory"
    Write-Host "中间文件目录：$IntermediateDirectory"
    Write-Host "汇总报告：$ReportFile"
}
finally {
    Pop-Location
}
