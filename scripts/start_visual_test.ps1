<#[
.SYNOPSIS
    启动 FastTest 的真实游戏引擎视觉测试，并验证截图、manifest 与 DLL 哈希。

.DESCRIPTION
    该脚本只在显式调用时启用视觉 harness。它不会修改存档，也不会清理正式游戏
    目录；只同步受控的 FastTest profile，并清理自己启动的 SMAPI 进程树。
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$FastModsPath,
    [string]$ProjectRoot,
    [string]$SaveName = 'test_447101921',
    [string]$OutputPath = 'artifacts\visual-tests\chat-empty',
    [string]$ScenarioId = 'chat-empty',
    [string]$ActionId = 'capture',
    [int]$TimeoutSeconds = 120,
    [int]$BackBufferWidth = 0,
    [int]$BackBufferHeight = 0,
    [string]$SourceModsPath,
    [string]$GmcmSourcePath,
    [string]$RasmodiaSourcePath,
    [string]$FastTestScriptPath,
    [string]$SmapiExecutable,
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedPath {
    param([Parameter(Mandatory)] [string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd('\')
}

function Test-SamePath {
    param([Parameter(Mandatory)] [string]$Left, [Parameter(Mandatory)] [string]$Right)
    return [string]::Equals(
        (Get-NormalizedPath $Left),
        (Get-NormalizedPath $Right),
        [StringComparison]::OrdinalIgnoreCase)
}

function Assert-FileName {
    param([Parameter(Mandatory)] [string]$Value, [Parameter(Mandatory)] [string]$Name)
    if ([string]::IsNullOrWhiteSpace($Value) -or
        $Value -in @('.', '..') -or
        $Value.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -ge 0 -or
        $Value.Contains('/') -or $Value.Contains('\')) {
        throw "$Name 不是安全的单层名称：$Value"
    }
}

function Get-PwshPath {
    $current = Join-Path $PSHOME 'pwsh.exe'
    if (Test-Path -LiteralPath $current -PathType Leaf) { return $current }
    $command = Get-Command pwsh.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    throw '未找到 PowerShell 7（pwsh.exe）。'
}

function Get-DotnetPath {
    $command = Get-Command dotnet.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $fallback = Join-Path ${env:ProgramFiles} 'dotnet\dotnet.exe'
    if (Test-Path -LiteralPath $fallback -PathType Leaf) { return $fallback }
    throw '未找到 dotnet.exe，无法构建 Mod。'
}

function Invoke-ModBuild {
    param([Parameter(Mandatory)] [string]$Root, [Parameter(Mandatory)] [string]$Game)
    $projectFile = Join-Path $Root 'smapi\StardewAI.NPC.csproj'
    if (-not (Test-Path -LiteralPath $projectFile -PathType Leaf)) {
        throw "找不到 Mod 项目文件：$projectFile"
    }
    $dotnet = Get-DotnetPath
    & $dotnet build $projectFile --no-restore '/p:OS=Windows_NT' ("/p:GamePath=$Game") '/p:EnableModDeploy=false' '/p:EnableModZip=false' '/p:BundleExtraAssemblies=Game'
    if ($LASTEXITCODE -ne 0) { throw "dotnet build 失败（退出码=$LASTEXITCODE）。" }
}

function Invoke-FastProfileSync {
    param([Parameter(Mandatory)] [string]$ScriptPath)
    $pwsh = Get-PwshPath
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath,
        '-ProjectRoot', $ProjectRoot, '-GamePath', $GamePath,
        '-FastModsPath', $FastModsPath, '-IncludeRasmodia', '-NoLaunch')
    foreach ($pair in @(
        @('-SourceModsPath', $SourceModsPath),
        @('-GmcmSourcePath', $GmcmSourcePath),
        @('-RasmodiaSourcePath', $RasmodiaSourcePath))) {
        if (-not [string]::IsNullOrWhiteSpace($pair[1])) { $arguments += $pair }
    }
    & $pwsh @arguments
    if ($LASTEXITCODE -ne 0) { throw "FastTest profile 同步失败（退出码=$LASTEXITCODE）。" }
}

function Get-DescendantProcessIds {
    param([Parameter(Mandatory)] [int]$ParentId)
    $children = @(Get-CimInstance -ClassName Win32_Process -Filter "ParentProcessId = $ParentId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        $child.ProcessId
        Get-DescendantProcessIds -ParentId ([int]$child.ProcessId)
    }
}

function Stop-ProcessTree {
    param([Parameter(Mandatory)] [int]$RootId)
    $ids = @($RootId) + @(Get-DescendantProcessIds -ParentId $RootId)
    foreach ($id in ($ids | Sort-Object -Descending -Unique)) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
}

if (-not $ProjectRoot) { $ProjectRoot = Get-NormalizedPath (Join-Path $PSScriptRoot '..') }
if (-not $FastModsPath) { $FastModsPath = Join-Path $GamePath 'Mods-AI-FastTest' }
if (-not $FastTestScriptPath) { $FastTestScriptPath = Join-Path $PSScriptRoot 'start_fast_test.ps1' }
if (-not $OutputPath) { throw 'OutputPath 不能为空。' }

Assert-FileName -Value $SaveName -Name 'SaveName'
Assert-FileName -Value $ScenarioId -Name 'ScenarioId'
if ($ActionId -notin @('capture', 'topic', 'group-hub', 'group-message', 'group-send', 'group-accept', 'group-free')) { throw 'ActionId 只支持 capture、topic、group-hub、group-message、group-send、group-accept 或 group-free。' }
if ($TimeoutSeconds -lt 1 -or $TimeoutSeconds -gt 3600) { throw 'TimeoutSeconds 必须在 1 到 3600 秒之间。' }
if (($BackBufferWidth -eq 0) -xor ($BackBufferHeight -eq 0)) {
    throw 'BackBufferWidth 和 BackBufferHeight 必须同时设置。'
}
if ($BackBufferWidth -ne 0 -and
    ($BackBufferWidth -lt 320 -or $BackBufferWidth -gt 7680 -or
     $BackBufferHeight -lt 320 -or $BackBufferHeight -gt 7680)) {
    throw 'BackBufferWidth 和 BackBufferHeight 必须在 320 到 7680 之间。'
}

$GamePath = Get-NormalizedPath $GamePath
$ProjectRoot = Get-NormalizedPath $ProjectRoot
$FastModsPath = Get-NormalizedPath $FastModsPath
$OutputPath = [IO.Path]::GetFullPath($OutputPath)
$FastTestScriptPath = Get-NormalizedPath $FastTestScriptPath
if ((Test-SamePath $FastModsPath $GamePath) -or
    (Test-SamePath $FastModsPath (Join-Path $GamePath 'Mods')) -or
    (Test-SamePath $FastModsPath $ProjectRoot)) {
    throw "FastModsPath 不能指向游戏目录、正式 Mods 或项目目录：$FastModsPath"
}
if (-not (Test-Path -LiteralPath $FastTestScriptPath -PathType Leaf)) { throw "找不到 FastTest 同步脚本：$FastTestScriptPath" }
if (-not (Test-Path -LiteralPath $GamePath -PathType Container)) { throw "GamePath 不存在：$GamePath" }

$outputDirectory = Split-Path -Parent $OutputPath
if ($outputDirectory) { [IO.Directory]::CreateDirectory($outputDirectory) | Out-Null }
if (Test-Path -LiteralPath $OutputPath -PathType Leaf) { throw "OutputPath 不能是文件：$OutputPath" }
[IO.Directory]::CreateDirectory($OutputPath) | Out-Null
$markerPaths = @(
    (Join-Path $OutputPath 'visual-test.done'),
    (Join-Path $OutputPath 'visual-test.failed'),
    (Join-Path $OutputPath "$ScenarioId.png"),
    (Join-Path $OutputPath "$ScenarioId.json"))
if ($markerPaths | Where-Object { Test-Path -LiteralPath $_ }) {
    throw "OutputPath 已存在本次场景产物，为避免误读旧截图请换一个目录：$OutputPath"
}

$process = $null
$windirWasAdded = $false
$originalWindir = $env:windir
$environmentNames = @(
    'OS',
    'STARDEW_AI_NPC_VISUAL_TEST',
    'STARDEW_AI_NPC_VISUAL_SAVE_NAME',
    'STARDEW_AI_NPC_VISUAL_OUTPUT',
    'STARDEW_AI_NPC_VISUAL_SCENARIO',
    'STARDEW_AI_NPC_VISUAL_ACTION',
    'STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH',
    'STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT')
$savedEnvironment = @{}
try {
    foreach ($name in $environmentNames) { $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    [Environment]::SetEnvironmentVariable('OS', 'Windows_NT', 'Process')
    if (-not $SkipBuild) { Invoke-ModBuild -Root $ProjectRoot -Game $GamePath }
    Invoke-FastProfileSync -ScriptPath $FastTestScriptPath

    $dllPath = Join-Path $FastModsPath 'StardewAI.NPC\StardewAI.NPC.dll'
    if (-not (Test-Path -LiteralPath $dllPath -PathType Leaf)) { throw "FastTest profile 缺少 DLL：$dllPath" }
    $profileHash = (Get-FileHash -LiteralPath $dllPath -Algorithm SHA256).Hash
    if (-not $SmapiExecutable) { $SmapiExecutable = Join-Path $GamePath 'StardewModdingAPI.exe' }
    if (-not (Test-Path -LiteralPath $SmapiExecutable -PathType Leaf)) { throw "找不到 SMAPI 启动入口：$SmapiExecutable" }

    [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_TEST', '1', 'Process')
    [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_SAVE_NAME', $SaveName, 'Process')
    [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_OUTPUT', (Get-NormalizedPath $OutputPath), 'Process')
    [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_SCENARIO', $ScenarioId, 'Process')
    [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_ACTION', $ActionId, 'Process')
    if ($BackBufferWidth -ne 0) {
        [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH', $BackBufferWidth.ToString(), 'Process')
        [Environment]::SetEnvironmentVariable('STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT', $BackBufferHeight.ToString(), 'Process')
    }
    if ([string]::IsNullOrWhiteSpace($env:windir)) {
        $windowsDirectory = $env:SystemRoot
        if ([string]::IsNullOrWhiteSpace($windowsDirectory) -or -not [IO.Directory]::Exists($windowsDirectory)) {
            throw '当前进程缺少有效的 windir/SystemRoot，无法安全启动 SMAPI。'
        }
        $env:windir = $windowsDirectory
        $windirWasAdded = $true
    }

    $quotedModsPath = '"' + $FastModsPath + '"'
    # 真实游戏需要创建可渲染的窗口；Hidden 会让部分 MonoGame/Steam 环境停在加载态。
    # 视觉测试仍会在完成标记后自动结束进程，不要求用户点击窗口。
    $process = Start-Process -FilePath $SmapiExecutable -WorkingDirectory $GamePath -ArgumentList @('--mods-path', $quotedModsPath) -PassThru -WindowStyle Normal
    Write-Output "SMAPI 已启动，PID=$($process.Id)，等待视觉测试完成……"

    $donePath = Join-Path $OutputPath 'visual-test.done'
    $failedPath = Join-Path $OutputPath 'visual-test.failed'
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $failedPath) {
            $reason = Get-Content -LiteralPath $failedPath -Raw -ErrorAction SilentlyContinue
            throw "视觉 harness 报告失败：$reason"
        }
        if (Test-Path -LiteralPath $donePath) { break }
        if ($process.HasExited) { throw "SMAPI 在视觉测试完成前退出（ExitCode=$($process.ExitCode)）。" }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $donePath)) { throw "视觉测试超时（${TimeoutSeconds}s）。" }

    $manifestPath = Join-Path $OutputPath "$ScenarioId.json"
    $screenshotPath = Join-Path $OutputPath "$ScenarioId.png"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf) -or -not (Test-Path -LiteralPath $screenshotPath -PathType Leaf)) {
        throw '完成标记存在，但 PNG 或 manifest 缺失。'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($manifest.modDllSha256 -ne $profileHash) {
        throw "manifest DLL 哈希不匹配：profile=$profileHash，manifest=$($manifest.modDllSha256)"
    }
    Write-Output 'VISUAL_TEST_DONE'
    Write-Output "Screenshot: $screenshotPath"
    Write-Output "Manifest: $manifestPath"
    Write-Output "DLL SHA256: $profileHash"
    exit 0
} catch {
    $failurePath = Join-Path $OutputPath 'visual-test.failed'
    try { Set-Content -LiteralPath $failurePath -Value $_.Exception.Message -Encoding utf8 } catch { }
    Write-Error "VISUAL_TEST_FAILED: $($_.Exception.Message)"
    exit 1
} finally {
    if ($null -ne $process) {
        try {
            if (-not $process.HasExited) { Stop-ProcessTree -RootId $process.Id }
        } catch { }
        $process.Dispose()
    }
    foreach ($name in $environmentNames) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
    if ($windirWasAdded) {
        if ($null -eq $originalWindir) { Remove-Item Env:windir -ErrorAction SilentlyContinue }
        else { $env:windir = $originalWindir }
    }
}
