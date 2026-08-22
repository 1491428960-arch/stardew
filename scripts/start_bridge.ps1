$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot "bridge\.venv\Scripts\python.exe"
$sourceRoot = Join-Path $projectRoot "bridge\src"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到 Bridge Python：$python"
}

& $python -m uvicorn stardew_ai_bridge.app:app `
    --app-dir $sourceRoot `
    --host 127.0.0.1 `
    --port 5678
