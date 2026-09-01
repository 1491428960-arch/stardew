<#[
.SYNOPSIS
    一键启动 Bridge 和 Stardew AI NPC 快速测试 profile。

.DESCRIPTION
    默认复用现有 Bridge；没有运行时才在后台启动一个临时 Bridge，并在快速 profile
    退出后清理这个由本脚本创建的进程。默认包含 Rasmodia，但默认不启动游戏；
    只有显式传入 -Launch 才会启动游戏。
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$FastModsPath,
    [string]$SourceModsPath,
    [switch]$Launch,
    [switch]$NoLaunch,
    [switch]$WithoutRasmodia
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$fastTestScript = Join-Path $PSScriptRoot 'start_fast_test.ps1'
$bridgeHealthUri = 'http://127.0.0.1:5678/health'
$bridgeProcess = $null
$startedBridge = $false
$launcherExitCode = 0

function Set-LocalProviderDefaults {
    # 默认连接项目已验证的隔离 Ollama；调用方显式设置环境变量时保留其覆盖值。
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_URL)) {
        $env:BRIDGE_LOCAL_URL = 'http://127.0.0.1:11435/api/chat'
    }
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_MODEL)) {
        $env:BRIDGE_LOCAL_MODEL = 'qwen3.5:9b'
    }
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_API_MODE)) {
        $env:BRIDGE_LOCAL_API_MODE = 'ollama'
    }
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_LOCAL_TIMEOUT)) {
        $env:BRIDGE_LOCAL_TIMEOUT = '45'
    }
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_DIALOGUE_SESSION_PATH)) {
        $env:BRIDGE_DIALOGUE_SESSION_PATH = Join-Path $env:TEMP 'StardewAI.NPC\dialogue-lab-session.json'
    }
    if ([string]::IsNullOrWhiteSpace($env:BRIDGE_PROFILE_INDEX)) {
        $preferredProfileIndex = Join-Path $projectRoot 'data\generated\vanilla-sve-rasmodia-profile-index-zh-CN.json'
        if (Test-Path -LiteralPath $preferredProfileIndex -PathType Leaf) {
            $env:BRIDGE_PROFILE_INDEX = $preferredProfileIndex
        }
    }
}

function Get-PwshPath {
    $current = Join-Path $PSHOME 'pwsh.exe'
    if (Test-Path -LiteralPath $current -PathType Leaf) {
        return $current
    }

    $command = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw '未找到 PowerShell 7（pwsh.exe）。请安装 PowerShell 7 后重试。'
}

function Get-DotnetPath {
    $command = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = Join-Path ${env:ProgramFiles} 'dotnet\dotnet.exe'
    if (Test-Path -LiteralPath $fallback -PathType Leaf) {
        return $fallback
    }

    throw '未找到 dotnet.exe，无法在启动前构建 Stardew AI NPC。'
}

function Build-Mod {
    $dotnet = Get-DotnetPath
    $projectFile = Join-Path $projectRoot 'smapi\StardewAI.NPC.csproj'
    if (-not (Test-Path -LiteralPath $projectFile -PathType Leaf)) {
        throw "找不到 Mod 项目文件：$projectFile"
    }

    Write-Output '正在执行 dotnet build，确保游戏加载当前源码……'
    $buildArguments = @(
        'build',
        $projectFile,
        '--no-restore',
        '/p:OS=Windows_NT',
        ("/p:GamePath=$GamePath"),
        '/p:EnableModDeploy=false',
        '/p:EnableModZip=false',
        '/p:BundleExtraAssemblies=Game'
    )
    & $dotnet @buildArguments
    $buildExitCode = $LASTEXITCODE
    if ($buildExitCode -ne 0) {
        throw "dotnet build 失败（退出码=$buildExitCode）。"
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

    throw '未找到可运行 Bridge 的 Python。需要 Python 3.10+ 及 fastapi/httpx/pydantic/uvicorn；请先创建 bridge\.venv 并安装依赖。'
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

function Test-BridgeHealth {
    try {
        $health = Invoke-RestMethod -Uri $bridgeHealthUri -Method Get -TimeoutSec 2
        return $health.status -eq 'ok'
    } catch {
        return $false
    }
}

function Start-ManagedBridge {
    Set-LocalProviderDefaults
    $python = Get-BridgePythonPath
    $bridgeSource = Join-Path $projectRoot 'bridge\src'
    $arguments = @(
        '-m', 'uvicorn', 'stardew_ai_bridge.app:app',
        '--app-dir', $bridgeSource,
        '--host', '127.0.0.1',
        '--port', '5678'
    )

    Write-Host '未检测到 Bridge，正在后台启动……'
    $process = Start-Process -FilePath $python `
        -ArgumentList $arguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -PassThru

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-BridgeHealth) {
            Write-Host "Bridge 已就绪（PID=$($process.Id)）。"
            return $process
        }
        if ($process.HasExited) {
            throw "Bridge 进程提前退出（ExitCode=$($process.ExitCode)）。"
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $process.HasExited) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
    }
    throw 'Bridge 启动超时，请检查 Python/uvicorn 依赖。'
}

function Stop-ManagedBridge {
    if (-not $startedBridge -or $null -eq $bridgeProcess) {
        return
    }
    try {
        if (-not $bridgeProcess.HasExited) {
            Stop-Process -Id $bridgeProcess.Id -ErrorAction SilentlyContinue
            $bridgeProcess.WaitForExit(3000)
            Write-Output '已清理本次启动的 Bridge。'
        }
    } catch {
        Write-Warning "清理本次 Bridge 失败：$($_.Exception.Message)"
    }
}

try {
    if ($Launch -and $NoLaunch) {
        throw '-Launch 和 -NoLaunch 不能同时使用。'
    }

    if (-not (Test-Path -LiteralPath $fastTestScript -PathType Leaf)) {
        throw "找不到快速测试脚本：$fastTestScript"
    }

    Build-Mod

    if ($Launch) {
        if (Test-BridgeHealth) {
            Write-Output '检测到 Bridge 已在运行，直接复用。'
        } else {
            $bridgeProcess = Start-ManagedBridge
            $startedBridge = $true
        }
    }

    $pwsh = Get-PwshPath
    $fastArguments = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $fastTestScript,
        '-GamePath', $GamePath,
        '-ProjectRoot', $projectRoot
    )
    if ($FastModsPath) {
        $fastArguments += @('-FastModsPath', $FastModsPath)
    }
    if ($SourceModsPath) {
        $fastArguments += @('-SourceModsPath', $SourceModsPath)
    }
    if ($WithoutRasmodia) {
        # 不传 IncludeRasmodia 时沿用快速脚本的基础模式。
    } else {
        $fastArguments += '-IncludeRasmodia'
    }
    if ($Launch) {
        $fastArguments += '-Launch'
    } else {
        $fastArguments += '-NoLaunch'
    }

    Write-Output '正在启动快速测试 profile……'
    & $pwsh @fastArguments
    $launcherExitCode = $LASTEXITCODE
} catch {
    Write-Error $_.Exception.Message
    $launcherExitCode = 1
} finally {
    Stop-ManagedBridge
}

exit $launcherExitCode
