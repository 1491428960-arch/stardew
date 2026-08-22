$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'start_fast_test.ps1'
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$root = Join-Path ([IO.Path]::GetTempPath()) ('stardew-ai-fast-test-' + [guid]::NewGuid().ToString('N'))
$projectRoot = Join-Path $root 'project'
$gamePath = Join-Path $root 'game'
$sourceModsPath = Join-Path $root 'source-mods'
$officialModsPath = Join-Path $gamePath 'Mods'
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
        [switch]$NoLaunch,
        [string]$TargetPath = $fastModsPath
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
    if (-not $NoLaunch) {
        $arguments = $arguments | Where-Object { $_ -ne '-NoLaunch' }
    }
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
    foreach ($directory in @($buildPath, $gamePath, $officialModsPath, $gmcmSourcePath, $rasmodiaSourcePath, (Join-Path $gmcmSourcePath 'assets'), (Join-Path $rasmodiaSourcePath 'assets'), (Join-Path $sourceModsPath 'ExtraMod'))) {
        [IO.Directory]::CreateDirectory($directory) | Out-Null
    }
    Set-Content -LiteralPath (Join-Path $buildPath 'StardewAI.NPC.dll') -Value 'test dll' -NoNewline
    Set-Content -LiteralPath (Join-Path $projectRoot 'smapi\manifest.json') -Value '{"Name":"StardewAI.NPC"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $gamePath 'StardewModdingAPI.exe') -Value 'fake smapi' -NoNewline
    Set-Content -LiteralPath (Join-Path $gmcmSourcePath 'manifest.json') -Value '{"Name":"Generic Mod Config Menu"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $rasmodiaSourcePath 'manifest.json') -Value '{"Name":"Romanceable Rasmodia"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $rasmodiaSourcePath 'content.json') -Value '{"Name":"Romanceable Rasmodia"}' -NoNewline
    Set-Content -LiteralPath (Join-Path $sourceModsPath 'ExtraMod\manifest.json') -Value '{"Name":"Extra Mod"}' -NoNewline

    $basic = Invoke-Launcher
    Assert-True ($basic.ExitCode -eq 0) '基础模式成功完成同步'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'StardewAI.NPC\StardewAI.NPC.dll')) '基础模式复制 StardewAI.NPC'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'StardewAI.NPC\manifest.json')) '基础模式复制 Mod manifest'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath 'GenericModConfigMenu\manifest.json')) '基础模式复制 GMCM'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $fastModsPath '[CP] Romanceable Rasmodia\content.json'))) '基础模式不复制 Rasmodia'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $fastModsPath 'ExtraMod\manifest.json'))) '基础模式不复制额外 Mod'

    $explicitNoLaunch = Invoke-Launcher -NoLaunch
    Assert-True ($explicitNoLaunch.ExitCode -eq 0) '显式 NoLaunch 模式成功完成同步'

    $launchTargetPath = Join-Path $root 'fast mods with spaces'
    $launchMarkerPath = Join-Path $root 'launch marker.txt'
    $captureScriptPath = Join-Path $root 'capture-smapi.cmd'
    Set-Content -LiteralPath $captureScriptPath -Value @(
        '@echo off',
        ("> `"$launchMarkerPath`" echo %1"),
        (">> `"$launchMarkerPath`" echo %2")
    ) -Encoding ascii
    $launchArguments = @(
        '-NoProfile', '-File', $scriptPath,
        '-ProjectRoot', $projectRoot,
        '-GamePath', $gamePath,
        '-FastModsPath', $launchTargetPath,
        '-SourceModsPath', $sourceModsPath,
        '-GmcmSourcePath', $gmcmSourcePath,
        '-SmapiExecutable', $captureScriptPath,
        '-Launch'
    )
    $launchOutput = & $pwsh @launchArguments 2>&1 | Out-String
    $launchExitCode = $LASTEXITCODE
    for ($attempt = 0; $attempt -lt 20 -and -not (Test-Path -LiteralPath $launchMarkerPath); $attempt++) {
        Start-Sleep -Milliseconds 50
    }
    $capturedArguments = if (Test-Path -LiteralPath $launchMarkerPath) { @(Get-Content -LiteralPath $launchMarkerPath -Encoding UTF8) } else { @() }
    $capturedText = $capturedArguments -join ' '
    if ($launchExitCode -ne 0) {
        Write-Output "Launch 输出：$launchOutput"
    }
    Assert-True ($launchExitCode -eq 0) '显式 Launch 模式成功调用模拟 SMAPI'
    $capturedPath = if ($capturedArguments.Count -ge 2) { $capturedArguments[1].Trim('"') } else { '' }
    Assert-True ($capturedArguments.Count -eq 2 -and $capturedArguments[0] -eq '--mods-path' -and $capturedPath -eq $launchTargetPath) 'Launch 模式将带空格的 mods-path 作为单个参数传递'

    Remove-Item -LiteralPath $fastModsPath -Recurse -Force -ErrorAction SilentlyContinue
    $rasmodia = Invoke-Launcher -IncludeRasmodia
    Assert-True ($rasmodia.ExitCode -eq 0) 'Rasmodia 模式成功完成同步'
    Assert-True (Test-Path -LiteralPath (Join-Path $fastModsPath '[CP] Romanceable Rasmodia\content.json')) 'Rasmodia 模式复制内容包'

    $managedFilePath = Join-Path $fastModsPath 'GenericModConfigMenu'
    Remove-Item -LiteralPath $managedFilePath -Recurse -Force
    Set-Content -LiteralPath $managedFilePath -Value 'sentinel' -NoNewline
    $managedFile = Invoke-Launcher
    Assert-True ($managedFile.ExitCode -ne 0) '受控名称为普通文件时拒绝删除'
    Assert-True ((Get-Content -LiteralPath $managedFilePath -Raw) -eq 'sentinel') '拒绝删除时保留普通文件'

    $unsafe = Invoke-Launcher -TargetPath $sourceModsPath
    Assert-True ($unsafe.ExitCode -ne 0) '目标等于正式 Mod 源目录时拒绝执行'

    $official = Invoke-Launcher -TargetPath $officialModsPath
    Assert-True ($official.ExitCode -ne 0) '目标等于游戏正式 Mods 目录时拒绝执行'

    $gameRoot = Invoke-Launcher -TargetPath $gamePath
    Assert-True ($gameRoot.ExitCode -ne 0) '目标等于游戏目录时拒绝执行'

    $project = Invoke-Launcher -TargetPath $projectRoot
    Assert-True ($project.ExitCode -ne 0) '目标等于项目目录时拒绝执行'

    $invalidGmcm = & $pwsh -NoProfile -File $scriptPath `
        -ProjectRoot $projectRoot -GamePath $gamePath -FastModsPath $fastModsPath `
        -SourceModsPath $sourceModsPath -GmcmSourcePath $projectRoot -NoLaunch 2>&1 | Out-String
    Assert-True ($LASTEXITCODE -ne 0) 'GMCM 源目录名称不匹配时拒绝执行'

    $junctionPath = Join-Path $root 'junction-fast-mods'
    try {
        New-Item -ItemType Junction -Path $junctionPath -Target $fastModsPath -Force | Out-Null
        $junction = Invoke-Launcher -TargetPath $junctionPath
        Assert-True ($junction.ExitCode -ne 0) '目标为 Junction 时拒绝执行'
    } catch {
        Write-Output "SKIP: 当前环境无法创建 Junction，跳过 Junction 安全测试：$($_.Exception.Message)"
    }

    $untrustedTarget = Join-Path $root 'untrusted-source-target'
    $badSourceRoot = Join-Path $root 'bad-selected-mods'
    $badRasmodiaPath = Join-Path $badSourceRoot '[CP] Romanceable Rasmodia'
    [IO.Directory]::CreateDirectory($untrustedTarget) | Out-Null
    [IO.Directory]::CreateDirectory($badSourceRoot) | Out-Null
    Set-Content -LiteralPath (Join-Path $untrustedTarget 'manifest.json') -Value '{"Name":"Untrusted"}' -NoNewline
    try {
        New-Item -ItemType Junction -Path $badRasmodiaPath -Target $untrustedTarget -Force | Out-Null
        $badSourceArguments = @(
            '-NoProfile', '-File', $scriptPath,
            '-ProjectRoot', $projectRoot, '-GamePath', $gamePath,
            '-FastModsPath', $fastModsPath, '-SourceModsPath', $sourceModsPath,
            '-GmcmSourcePath', $gmcmSourcePath, '-RasmodiaSourcePath', $badRasmodiaPath,
            '-IncludeRasmodia', '-NoLaunch'
        )
        $badSourceOutput = & $pwsh @badSourceArguments 2>&1 | Out-String
        Assert-True ($LASTEXITCODE -ne 0) '不在 Stardrop 安装缓存内的源 Junction 被拒绝'
    } catch {
        Write-Output "SKIP: 当前环境无法创建源 Junction，跳过源链接白名单测试：$($_.Exception.Message)"
    }

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
