$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $PSScriptRoot
$cmdPath = Join-Path $PSScriptRoot 'start_ai_npc_test.cmd'
$launcherPath = Join-Path $PSScriptRoot 'start_ai_npc_test.ps1'
$bridgeLauncherPath = Join-Path $PSScriptRoot 'start_bridge.ps1'
$passed = 0
$failed = 0

function Assert-True {
    param(
        [Parameter(Mandatory)] [bool]$Condition,
        [Parameter(Mandatory)] [string]$Message
    )

    if ($Condition) {
        $script:passed++
        Write-Output "PASS: $Message"
    } else {
        $script:failed++
        Write-Output "FAIL: $Message"
    }
}

Assert-True (Test-Path -LiteralPath $cmdPath -PathType Leaf) '双击入口文件存在'
Assert-True (Test-Path -LiteralPath $launcherPath -PathType Leaf) 'PowerShell 编排脚本存在'
Assert-True (Test-Path -LiteralPath $bridgeLauncherPath -PathType Leaf) 'Bridge 独立启动脚本存在'

if ((Test-Path -LiteralPath $cmdPath -PathType Leaf) -and
    (Test-Path -LiteralPath $launcherPath -PathType Leaf) -and
    (Test-Path -LiteralPath $bridgeLauncherPath -PathType Leaf)) {
    $cmdText = Get-Content -LiteralPath $cmdPath -Raw -Encoding utf8
    $launcherText = Get-Content -LiteralPath $launcherPath -Raw -Encoding utf8
    $bridgeLauncherText = Get-Content -LiteralPath $bridgeLauncherPath -Raw -Encoding utf8
    $bridgeScriptBytes = [IO.File]::ReadAllBytes($bridgeLauncherPath)

    Assert-True ($cmdText -notmatch '[^\x00-\x7F]') '批处理入口只包含 ASCII 字符，避免 cmd.exe 编码乱码'
    Assert-True ($cmdText -match "`r`n") '批处理入口使用 Windows CRLF 换行'
    Assert-True ($cmdText -notmatch '(?im)^\s*echo[^\r\n]*\([^\r\n]*\)') '批处理提示不含括号，避免 cmd.exe 分组解析冲突'
    Assert-True ($cmdText -match '(?i)pwsh') '双击入口调用 PowerShell 7'
    Assert-True ($cmdText -notmatch '(?i)\\powershell\.exe\s+-NoProfile') '双击入口不直接调用 Windows PowerShell 5.1'
    Assert-True ($launcherText -match '127\.0\.0\.1:5678/health') '编排脚本先检查 Bridge 健康状态'
    Assert-True ($launcherText -match 'Start-Process') '编排脚本能后台启动 Bridge'
    $startBridgeFunction = [regex]::Match(
        $launcherText,
        '(?s)function Start-ManagedBridge\s*\{.*?(?=function Stop-ManagedBridge)').Value
    Assert-True (
        $startBridgeFunction -notmatch 'Write-Output'
    ) 'Bridge 启动函数只返回 Process，不把状态文本混入返回值'
    Assert-True ($launcherText -match 'start_fast_test\.ps1') '编排脚本调用快速 profile'
    Assert-True ($launcherText -match 'fastArguments\s*\+=\s*''-IncludeRasmodia''') '默认快速 profile 包含 Rasmodia 资源'
    Assert-True ($launcherText -match '(?s)if \(\$Launch\).*?Test-BridgeHealth') '启动游戏前检查 Bridge 健康状态'
    Assert-True ($launcherText -match '\[switch\]\$Launch') '编排脚本提供显式 Launch 开关'
    Assert-True ($launcherText -match '(?s)if \(\$Launch\).*?\$fastArguments \+= ''-Launch''') '只有显式 Launch 才传递启动参数'
    Assert-True ($launcherText -match '(?s)if \(\$Launch\).*?\$fastArguments \+= ''-Launch''.*?else\s*\{\s*\$fastArguments \+= ''-NoLaunch''') '默认模式传递 NoLaunch 参数'
    Assert-True ($launcherText -match 'finally') '编排脚本包含退出清理路径'
    Assert-True ($launcherText -match 'Stop-Process') '编排脚本只清理自己启动的 Bridge'
    Assert-True ($launcherText -match 'ExecutionPolicy.*Bypass') '编排脚本对临时 PowerShell 进程使用 Bypass'
    Assert-True ($launcherText -match 'dotnet.*build') '编排脚本启动前自动构建当前 Mod'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_LOCAL_URL') 'Bridge 启动脚本配置本机 Provider 地址'
    Assert-True ($bridgeLauncherText -match '127\.0\.0\.1:11435/api/chat') 'Bridge 默认使用隔离 Ollama 端口'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_LOCAL_MODEL') 'Bridge 启动脚本配置本机模型'
    Assert-True ($bridgeLauncherText -match 'qwen3\.5:9b') 'Bridge 默认使用已验证的 9B 模型'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_LOCAL_API_MODE') 'Bridge 启动脚本选择 Ollama 原生接口'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_LOCAL_TIMEOUT') 'Bridge 启动脚本配置本机模型超时'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_LOCAL_TIMEOUT\s*=\s*["'']45["'']') 'Bridge 本机模型默认允许完整角色上下文生成'
    Assert-True ($bridgeLauncherText -match 'BRIDGE_PROFILE_INDEX') 'Bridge 启动脚本配置资料索引路径'
    Assert-True ($bridgeLauncherText -match 'vanilla-sve-rasmodia-profile-index-zh-CN\.next-event-dialogue\.json') 'Bridge 默认使用事件对白中文联合索引'
    Assert-True ($bridgeLauncherText -match 'codex-runtimes.*python\.exe') 'Bridge 启动脚本支持工作区 Python 运行时'
    Assert-True ($bridgeLauncherText -match 'function Test-BridgePython') 'Bridge 启动脚本验证 Python 运行依赖'
    Assert-True ($bridgeLauncherText -match 'import fastapi.*import httpx.*import pydantic.*import uvicorn') 'Bridge 启动脚本探测完整运行依赖'
    Assert-True ($bridgeLauncherText -match 'Test-BridgePython\s+\$candidate') 'Bridge 只选择依赖可用的 Python'
    Assert-True (
        $bridgeScriptBytes.Length -ge 3 -and
        $bridgeScriptBytes[0] -eq 0xEF -and
        $bridgeScriptBytes[1] -eq 0xBB -and
        $bridgeScriptBytes[2] -eq 0xBF
    ) 'Bridge 启动脚本带 UTF-8 BOM，可被 Windows PowerShell 正确解析'
    Assert-True ($launcherText -match 'function Test-BridgePython') '快速测试编排脚本验证 Python 运行依赖'
    Assert-True ($launcherText -match 'Test-BridgePython\s+\$candidate') '快速测试编排脚本只选择依赖可用的 Python'
    Assert-True ($launcherText -match '127\.0\.0\.1:11435/api/chat') '快速测试启动器沿用真实本机 Provider'
    Assert-True ($launcherText -match 'BRIDGE_LOCAL_TIMEOUT') '快速测试启动器沿用本机模型超时'
    Assert-True ($launcherText -match 'BRIDGE_PROFILE_INDEX') '快速测试启动器沿用资料索引路径'
    Assert-True ($launcherText -match 'vanilla-sve-rasmodia-profile-index-zh-CN\.next-event-dialogue\.json') '快速测试启动器默认使用事件对白中文联合索引'

    try {
        [scriptblock]::Create($launcherText) | Out-Null
        Assert-True $true 'PowerShell 7 可解析 UTF-8 编排脚本'
    } catch {
        Assert-True $false "PowerShell 7 解析编排脚本：$($_.Exception.Message)"
    }

}

Write-Output "结果：通过 $passed，失败 $failed"
if ($failed -gt 0) {
    exit 1
}
exit 0
