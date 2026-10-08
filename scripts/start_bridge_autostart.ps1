# 登录时自动启动 Bridge（由计划任务 \DSH\StardewBridge 调用）
#
# 为什么需要这一层包装，而不是让计划任务直接调 start_bridge.ps1：
#   1. 必须设 BRIDGE_APP_MODULE=bridge_debug_app:application —— 观测版才会把
#      每次对白抄进 dialogue-live.jsonl，那是排查「单场之内跑题」的唯一通道。
#      start_bridge.ps1 默认挂的是生产 app（stardew_ai_bridge.app:app），不落盘。
#   2. start_bridge.ps1 自己不重定向输出；计划任务里 stdout 会丢，
#      出错时只看到一个退出码，等于没有日志。
#   3. 需要「已在跑就不重复起」的保护：计划任务的 MultipleInstances=IgnoreNew
#      只管得住同一个任务，管不住手动起的或上一次登录遗留的实例。

$ErrorActionPreference = 'Continue'

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $env:LOCALAPPDATA 'StardewAI.NPC\logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null

$outLog = Join-Path $logDir 'bridge-out.log'
$errLog = Join-Path $logDir 'bridge-err.log'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'

function Write-BridgeLog {
    param([string]$Message)
    "[$stamp] $Message" | Add-Content -Path $outLog -Encoding UTF8
}

# --- 端口占用检查：Bridge 只能有一份 ---
$busy = Get-NetTCPConnection -LocalPort 5678 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    $owner = ($busy | Select-Object -First 1).OwningProcess
    Write-BridgeLog "5678 已被 PID $owner 占用，跳过启动（不重复起第二份）"
    exit 0
}

# --- 真机对白日志轮转：超过 50 MB 就归档，避免长期游玩把文件撑爆 ---
$chatLog = 'E:\workspace\.scratch\dialogue-live.jsonl'
if ((Test-Path -LiteralPath $chatLog) -and (Get-Item -LiteralPath $chatLog).Length -gt 50MB) {
    $archive = "E:\workspace\.scratch\dialogue-live.$(Get-Date -Format 'yyyyMMdd-HHmmss').jsonl.archive"
    Move-Item -LiteralPath $chatLog -Destination $archive -Force
    Write-BridgeLog "dialogue-live.jsonl 超过 50MB，已归档为 $(Split-Path -Leaf $archive)"
}

# --- 挂观测版 app ---
$env:BRIDGE_APP_MODULE = 'bridge_debug_app:application'
Write-BridgeLog "启动 Bridge（BRIDGE_APP_MODULE=$($env:BRIDGE_APP_MODULE)，日志目录=$logDir）"

# start_bridge.ps1 会在前台阻塞运行 uvicorn —— 这正是计划任务需要的长驻进程。
# stderr 单独落一份，方便区分 uvicorn 的启动错误与业务输出。
& (Join-Path $PSScriptRoot 'start_bridge.ps1') 1>> $outLog 2>> $errLog
$code = $LASTEXITCODE
Write-BridgeLog "Bridge 进程退出，退出码 $code"
exit $code
