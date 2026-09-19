$ErrorActionPreference = 'Stop'

$scriptPath = Join-Path $PSScriptRoot 'start_visual_test.ps1'
$pwsh = (Get-Command pwsh -ErrorAction Stop).Source
$root = Join-Path ([IO.Path]::GetTempPath()) ('stardew-ai-visual-test-' + [guid]::NewGuid().ToString('N'))
$projectRoot = Join-Path $root 'project'
$scriptsRoot = Join-Path $projectRoot 'scripts'
$buildRoot = Join-Path $projectRoot 'smapi\bin\Debug\net6.0'
$gameRoot = Join-Path $root 'game'
$fastModsPath = Join-Path $root 'fast mods with spaces'
$outputPath = Join-Path $root 'visual output'
$fakeSyncPath = Join-Path $scriptsRoot 'fake_sync.ps1'
$fakeSmapiPath = Join-Path $gameRoot 'fake-smapi.cmd'
$dllPath = Join-Path $fastModsPath 'StardewAI.NPC\StardewAI.NPC.dll'

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

try {
    [IO.Directory]::CreateDirectory($scriptsRoot) | Out-Null
    [IO.Directory]::CreateDirectory($buildRoot) | Out-Null
    [IO.Directory]::CreateDirectory($gameRoot) | Out-Null

    Set-Content -LiteralPath (Join-Path $buildRoot 'StardewAI.NPC.dll') -Value 'visual test dll' -NoNewline
    $expectedDllHash = (Get-FileHash -LiteralPath (Join-Path $buildRoot 'StardewAI.NPC.dll') -Algorithm SHA256).Hash
    Set-Content -LiteralPath (Join-Path $projectRoot 'smapi\manifest.json') -Value '{}' -NoNewline
    Set-Content -LiteralPath $fakeSyncPath -Encoding utf8 -Value @'
param(
    [string]$FastModsPath,
    [string]$ProjectRoot,
    [string]$GamePath,
    [switch]$IncludeRasmodia,
    [switch]$NoLaunch,
    [string]$SourceModsPath,
    [string]$GmcmSourcePath,
    [string]$RasmodiaSourcePath)
$target = Join-Path $FastModsPath 'StardewAI.NPC'
[IO.Directory]::CreateDirectory($target) | Out-Null
Set-Content -LiteralPath (Join-Path $target 'StardewAI.NPC.dll') -Value 'visual test dll' -NoNewline
exit 0
'@

    Set-Content -LiteralPath $fakeSmapiPath -Encoding ascii -Value @'
@echo off
powershell.exe -NoProfile -Command "$out = $env:STARDEW_AI_NPC_VISUAL_OUTPUT; New-Item -ItemType Directory -Force -Path $out | Out-Null; $root = Split-Path $out -Parent; $dll = Get-ChildItem -LiteralPath $root -Filter 'StardewAI.NPC.dll' -File -Recurse | Select-Object -First 1; $hash = (Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash; $json = @{schemaVersion=1;scenarioId=$env:STARDEW_AI_NPC_VISUAL_SCENARIO;gameVersion='fake';smapiVersion='fake';modDllSha256=$hash;locale='zh-CN';backBufferWidth=2;backBufferHeight=2;uiViewportWidth=2;uiViewportHeight=2;uiScale=1;zoom=1;screenshotFile='chat-empty.png'} | ConvertTo-Json -Compress; Set-Content -LiteralPath (Join-Path $out 'chat-empty.png') -Value 'png' -NoNewline; Set-Content -LiteralPath (Join-Path $out 'chat-empty.json') -Value $json -NoNewline; Set-Content -LiteralPath (Join-Path $out 'visual-test.done') -Value 'chat-empty.json' -NoNewline"
'@
    $fakeSmapiText = Get-Content -LiteralPath $fakeSmapiPath -Raw -Encoding ascii
    $fakeSmapiText = $fakeSmapiText.Replace(
        '$hash = (Get-FileHash -LiteralPath $dll.FullName -Algorithm SHA256).Hash',
        "`$hash = '$expectedDllHash'")
    Set-Content -LiteralPath $fakeSmapiPath -Encoding ascii -Value $fakeSmapiText -NoNewline

    $visualScriptText = Get-Content -LiteralPath $scriptPath -Raw -Encoding utf8
    Assert-True ($visualScriptText -match '\[int\]\$BackBufferWidth') '视觉启动器提供宽度参数'
    Assert-True ($visualScriptText -match '\[int\]\$BackBufferHeight') '视觉启动器提供高度参数'
    Assert-True ($visualScriptText -match 'STARDEW_AI_NPC_VISUAL_BACKBUFFER_WIDTH') '视觉启动器传递宽度环境变量'
    Assert-True ($visualScriptText -match 'STARDEW_AI_NPC_VISUAL_BACKBUFFER_HEIGHT') '视觉启动器传递高度环境变量'
    Assert-True ($visualScriptText -match 'group-message') '视觉启动器接受群聊端到端动作'
    Assert-True ($visualScriptText -match 'group-send') '视觉启动器接受群聊真实发送动作'

    $common = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $scriptPath,
        '-ProjectRoot', $projectRoot,
        '-GamePath', $gameRoot,
        '-FastModsPath', $fastModsPath,
        '-OutputPath', $outputPath,
        '-ScenarioId', 'chat-empty',
        '-SaveName', 'test_447101921',
        '-TimeoutSeconds', '10',
        '-FastTestScriptPath', $fakeSyncPath,
        '-SmapiExecutable', $fakeSmapiPath,
        '-SkipBuild'
    )

    $oldTest = $env:STARDEW_AI_NPC_VISUAL_TEST
    try {
        $env:STARDEW_AI_NPC_VISUAL_TEST = 'leak-sentinel'
    $output = & $pwsh @common 2>&1 | Out-String
    $exitCode = $LASTEXITCODE
    Write-Output "首次启动器输出：$output"
    } finally {
        if ($null -eq $oldTest) { Remove-Item Env:STARDEW_AI_NPC_VISUAL_TEST -ErrorAction SilentlyContinue }
        else { $env:STARDEW_AI_NPC_VISUAL_TEST = $oldTest }
    }

    Assert-True ($exitCode -eq 0) '完成标记出现时启动器返回成功'
    Assert-True ($output -match 'VISUAL_TEST_DONE') '启动器输出完成标记'
    Assert-True ((Test-Path -LiteralPath (Join-Path $outputPath 'chat-empty.json')) -and (Test-Path -LiteralPath (Join-Path $outputPath 'chat-empty.png'))) '启动器验证截图与 manifest 同时存在'

    if (Test-Path -LiteralPath (Join-Path $outputPath 'chat-empty.json')) {
        $manifest = Get-Content -LiteralPath (Join-Path $outputPath 'chat-empty.json') -Raw | ConvertFrom-Json
        $expectedHash = (Get-FileHash -LiteralPath $dllPath -Algorithm SHA256).Hash
        Assert-True ($manifest.modDllSha256 -eq $expectedHash) 'manifest DLL 哈希与 FastTest profile 一致'
    } else {
        Write-Output "启动器输出：$output"
    }

    Remove-Item -LiteralPath $outputPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output '开始超时场景测试。'
    $timeoutArguments = $common | ForEach-Object { $_ }
    $timeoutArguments[$timeoutArguments.IndexOf('-SmapiExecutable') + 1] = $fakeSmapiPath
    $timeoutArguments[$timeoutArguments.IndexOf('-TimeoutSeconds') + 1] = '1'
    $timeoutOutput = & $pwsh @timeoutArguments 2>&1 | Out-String
    Assert-True ($LASTEXITCODE -ne 0 -and $timeoutOutput -match 'VISUAL_TEST_FAILED') '超时返回失败并输出失败标记'
} finally {
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "结果：通过 $passed，失败 $failed"
if ($failed -gt 0) { exit 1 }
exit 0
