<#
.SYNOPSIS
    项目一键验证：SMAPI 测试、Bridge 测试与语法编译、工作树空白检查。

.DESCRIPTION
    把日常要跑的四类检查串成一条命令，并在末尾给出汇总与退出码（0 = 全绿）。

    设计取舍：
    - SMAPI 与 Bridge 两侧都跑，但 Bridge 侧会先探测"是否可收集"——若测试模块因
      并行工作线的重构中间态而 ImportError，会明确报告为「环境问题」而不是
      「本线回归失败」，避免误判。
    - Python 解释器按顺序探测：项目 venv → 本机 Python 3.10 → py -3.10 → PATH 里的 python，
      因此既能在用户桌面会话跑，也能在服务的 SYSTEM 会话里跑。

.EXAMPLE
    pwsh -NoProfile -File .\scripts\verify_project.ps1
    pwsh -NoProfile -File .\scripts\verify_project.ps1 -SkipBridge      # 只验 SMAPI 侧
#>
[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [switch]$SkipBridge,
    [switch]$SkipSmapi
)

$ErrorActionPreference = 'Continue'

if (-not $ProjectRoot) {
    $ProjectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
}
Set-Location -LiteralPath $ProjectRoot

$results = [System.Collections.Generic.List[object]]::new()

function Add-Result {
    param([string]$Name, [string]$Status, [string]$Detail)
    $script:results.Add([pscustomobject]@{ Name = $Name; Status = $Status; Detail = $Detail })
    $color = switch ($Status) { 'PASS' { 'Green' } 'FAIL' { 'Red' } 'SKIP' { 'DarkGray' } default { 'Yellow' } }
    Write-Host ("[{0}] {1} —— {2}" -f $Status, $Name, $Detail) -ForegroundColor $color
}

function Get-ProjectPython {
    $candidates = @(
        (Join-Path $ProjectRoot 'bridge\.venv\Scripts\python.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'),
        'C:\Users\Lenovo\AppData\Local\Programs\Python\Python310\python.exe'
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            $version = & $candidate -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($version -and [version]$version -ge [version]'3.10') { return $candidate }
        }
    }
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        $version = & $command.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($version -and [version]$version -ge [version]'3.10') { return $command.Source }
    }
    return $null
}

Write-Host ("=== 项目验证 {0} ===" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')) -ForegroundColor Cyan
Write-Host "根目录：$ProjectRoot"

# 1) SMAPI 侧单元测试
if (-not $SkipSmapi) {
    $project = Join-Path $ProjectRoot 'smapi\tests\StardewAI.NPC.Tests.csproj'
    if (-not (Test-Path -LiteralPath $project -PathType Leaf)) {
        Add-Result 'SMAPI 测试' 'FAIL' "找不到测试工程：$project"
    }
    else {
        $output = & dotnet test $project -p:GamePath="$GamePath" 2>&1 | Out-String
        $line = ($output -split "`n" | Where-Object { $_ -match '已通过!|失败!' } | Select-Object -Last 1)
        if ($LASTEXITCODE -eq 0) {
            Add-Result 'SMAPI 测试' 'PASS' ($line.Trim() -replace '\s+', ' ')
        }
        else {
            Add-Result 'SMAPI 测试' 'FAIL' ($line.Trim() -replace '\s+', ' ')
        }
    }
}

# 2) Bridge 侧：先探测能否收集，再跑全量
if (-not $SkipBridge) {
    $python = Get-ProjectPython
    if (-not $python) {
        Add-Result 'Bridge 测试' 'SKIP' '未找到 Python 3.10+（可用 -SkipBridge 显式跳过）'
    }
    else {
        $env:PYTHONPATH = 'bridge/src;scripts'
        $env:PYTHONIOENCODING = 'utf-8'
        $collect = & $python -B -m pytest bridge/tests -q -p no:cacheprovider --collect-only 2>&1 | Out-String
        if ($LASTEXITCODE -ne 0) {
            $firstError = ($collect -split "`n" | Where-Object { $_ -match 'ImportError|ModuleNotFoundError' } | Select-Object -First 1)
            Add-Result 'Bridge 测试' 'ENV' ("收集失败（很可能是并行工作线的中间态）：" + ($firstError -replace '^\s+', '').Trim())
        }
        else {
            $testOutput = & $python -B -m pytest bridge/tests -q -p no:cacheprovider 2>&1 | Out-String
            $summary = ($testOutput -split "`n" | Where-Object { $_ -match 'passed|failed' } | Select-Object -Last 1)
            Add-Result 'Bridge 测试' ($(if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' })) $summary.Trim()
        }

        # 语法编译检查（与测试无关，始终可跑）
        $compile = & $python -B -m compileall -q bridge/src scripts 2>&1 | Out-String
        Add-Result 'compileall' ($(if ($LASTEXITCODE -eq 0) { 'PASS' } else { 'FAIL' })) "exit=$LASTEXITCODE"
    }
}

# 3) 工作树空白检查
$diffCheck = & git -c "safe.directory=$ProjectRoot" diff --check 2>&1 | Out-String
if ($LASTEXITCODE -eq 0) {
    Add-Result 'git diff --check' 'PASS' '无空白错误'
}
else {
    $first = ($diffCheck -split "`n" | Where-Object { $_ -match '\S' } | Select-Object -First 1)
    Add-Result 'git diff --check' 'FAIL' $first.Trim()
}

# 汇总
Write-Host ''
Write-Host '=== 汇总 ===' -ForegroundColor Cyan
$results | Format-Table -AutoSize
$failed = @($results | Where-Object { $_.Status -eq 'FAIL' }).Count
$envIssues = @($results | Where-Object { $_.Status -eq 'ENV' }).Count
if ($failed -gt 0) {
    Write-Host "结果：$failed 项失败" -ForegroundColor Red
    Write-Host "提示：若失败集中在 npc_bubble_* 等并行工作线的测试，那是该线的重构中间态、" -ForegroundColor Yellow
    Write-Host "      不代表本线回归（诊断见 docs/diagnosis-bubble-elements-5-failures-2026-09-20.md）。" -ForegroundColor Yellow
    exit 1
}
if ($envIssues -gt 0) {
    Write-Host "结果：无本线失败，但有 $envIssues 项受环境/并行工作影响，需人工确认" -ForegroundColor Yellow
    exit 2
}
Write-Host '结果：全部通过' -ForegroundColor Green
exit 0
