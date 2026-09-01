$ErrorActionPreference = "Stop"

# 默认连接项目已验证的隔离 Ollama；调用方显式设置环境变量时保留其覆盖值。
if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_URL)) {
    $env:BRIDGE_LOCAL_URL = "http://127.0.0.1:11435/api/chat"
}
if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_MODEL)) {
    $env:BRIDGE_LOCAL_MODEL = "qwen3.5:9b"
}
if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_API_MODE)) {
    $env:BRIDGE_LOCAL_API_MODE = "ollama"
}
if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_TIMEOUT)) {
    $env:BRIDGE_LOCAL_TIMEOUT = "45"
}
if ([string]::IsNullOrWhiteSpace($env:BRIDGE_DIALOGUE_SESSION_PATH)) {
    $env:BRIDGE_DIALOGUE_SESSION_PATH = Join-Path $env:TEMP 'StardewAI.NPC\dialogue-lab-session.json'
}

$projectRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($env:BRIDGE_PROFILE_INDEX)) {
    $preferredProfileIndex = Join-Path $projectRoot 'data\generated\vanilla-sve-rasmodia-profile-index-zh-CN.json'
    if (Test-Path -LiteralPath $preferredProfileIndex -PathType Leaf) {
        $env:BRIDGE_PROFILE_INDEX = $preferredProfileIndex
    }
}

function Get-BridgePythonPath {
    $candidates = @(
        (Join-Path $projectRoot 'bridge\.venv\Scripts\python.exe')
    )

    $localPythonRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $localPythonRoot -PathType Container) {
        $candidates += @(
            Get-ChildItem -Path (Join-Path $localPythonRoot 'Python*\python.exe') -File -ErrorAction SilentlyContinue |
                Sort-Object FullName -Descending |
                Select-Object -ExpandProperty FullName
        )
    }

    $candidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf) -and (Test-BridgePython $candidate)) {
            return $candidate
        }
    }

    throw "未找到可运行 Bridge 的 Python。需要 Python 3.10+ 及 fastapi/httpx/pydantic/uvicorn；请先创建 bridge\\.venv 并安装依赖。"
}

function Test-BridgePython {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonPath
    )

    try {
        & $PythonPath -c "import sys; import fastapi; import httpx; import pydantic; import uvicorn; sys.exit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$python = Get-BridgePythonPath
$sourceRoot = Join-Path $projectRoot "bridge\src"

& $python -m uvicorn stardew_ai_bridge.app:app `
    --app-dir $sourceRoot `
    --host 127.0.0.1 `
    --port 5678
