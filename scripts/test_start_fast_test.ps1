$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'start_fast_test.ps1'
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$root = Join-Path ([IO.Path]::GetTempPath()) ('stardew-ai-fast-test-' + [guid]::NewGuid().ToString('N'))
$projectRoot = Join-Path $root 'project'
$gamePath = Join-Path $root 'game'
$sourceModsPath = Join-Path $root 'source-mods'
$fastModsPath = Join-Path $root 'fast-mods'
$buildPath = Join-Path $projectRoot 'smapi\bin\Debug\net6.0'
$gmcmSourcePath = Join-Path $sourceModsPath 'GenericModConfigMenu'
$rasmodiaSourcePath = Join-Path $sourceModsPath '[CP] Romanceable Rasmodia'

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

function Invoke-Launcher {
    param(
        [switch]$IncludeRasmodia,
        [string]$TargetPath = $fastModsPath,
        [string]$BuildPath = $buildPath
    )

    $arguments = @(
        '-NoProfile',
        '-File', $scriptPath,
        '-ProjectRoot', $projectRoot,
        '-GamePath', $gamePath,
        '-FastModsPath', $TargetPath,
        '-SourceModsPath', $sourceModsPath,
        '-GmcmSourcePath', $gmcmSourcePath,
        '-RasmodiaSourcePath', $rasmodiaSourcePath,
        '-NoLaunch'
    )
    if ($IncludeRasmodia) {
        $arguments += '-IncludeRasmodia'
    }

    $output = & $pwsh @arguments 2>&1 | Out-String
    [pscustomobject]@{
        ExitCode = $LASTEXITCODE
        Output = $output
    }
}

try {
    New-Item -ItemType Directory -Path $buildPath, $gamePath, $gmcmSourcePath, $rasmodiaSourcePath -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $gmcmSourcePath 'assets'), (Join-Path $rasmodiaSourcePath 'assets') -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $buildPath 'StardewAI.NPC.dll') -Value 'test dll' -NoNewline
    Set-Content -LiteralPath (Join-Path $projectRoot 'smapi\manifest.json') -Value '{"Name":"StardewAI.NPC"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $gamePath 'StardewModdingAPI.exe') -Value 'fake smapi' -NoNewline
    Set-Content -LiteralPath (Join-Path $gmcmSourcePath 'manifest.json') -Value '{"Name":"Generic Mod Config Menu"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $rasmodiaSourcePath 'content.json') -Value '{"Name":"Romanceable Rasmodia"}' -NoNewline

    $basic = Invoke-Launcher
    Assert-True ($basic.ExitCode -eq 0) '基础模式成功完成同步'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'StardewAI.NPC\StardewAI.NPC.dll')) '基础模式复制 StardewAI.NPC'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'StardewAI.NPC\manifest.json')) '基础模式复制 Mod manifest'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'GenericModConfigMenu\manifest.json')) '基础模式复制 GMCM'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $fastModsPath '[CP] Romanceable Rasmodia\content.json'))) '基础模式不复制 Rasmodia'

    Remove-Item -LiteralPath $fastModsPath -Recurse -Force -ErrorAction SilentlyContinue
    $rasmodia = Invoke-Launcher -IncludeRasmodia
    Assert-True ($rasmodia.ExitCode -eq 0) 'Rasmodia 模式成功完成同步'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath '[CP] Romanceable Rasmodia\content.json')) 'Rasmodia 模式复制内容包'

    $unsafe = Invoke-Launcher -TargetPath $sourceModsPath
    Assert-True ($unsafe.ExitCode -ne 0) '目标等于正式 Mod 源目录时拒绝执行'

    $gameRoot = Invoke-Launcher -TargetPath $gamePath
    Assert-True ($gameRoot.ExitCode -ne 0) '目标等于游戏目录时拒绝执行'

    Remove-Item -LiteralPath (Join-Path $buildPath 'StardewAI.NPC.dll') -Force
    $missingDll = Invoke-Launcher
    Assert-True ($missingDll.ExitCode -ne 0) '缺少构建 DLL 时拒绝启动'
} finally {
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "结果：通过 $passed，失败 $failed"
if ($failed -gt 0) {
    exit 1
}
exit 0
