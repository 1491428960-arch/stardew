<#
.SYNOPSIS
    只读执行 AI NPC 的 SMAPI 回归前检查，并在用户明确要求时启动 SMAPI。

.DESCRIPTION
    默认只检查路径、Bridge 健康状态和 profile/Mods 是否存在，然后输出存档元数据快照。
    本脚本不读存档内容，不删除、覆盖、复制、移动任何文件，不写注册表，也不修改源 Mods 仓库。
    只有传入 -LaunchSmapi 才会调用 SMAPI；只有传入 -InspectLog 才会读取日志。
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$SmapiExecutable = 'D:\sbeam\steamapps\common\Stardew Valley\StardewModdingAPI.exe',
    [string]$StardropProfile = 'C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\Profiles\AI-SVE-测试.json',
    [string]$SelectedModsPath = 'C:\Users\Lenovo\AppData\Roaming\Stardrop\Data\Selected Mods',
    [string]$SourceModsPath = 'D:\sbeam\steamapps\common\Stardew Valley\Mods',
    [string]$SaveRoot = 'D:\sbeam\userdata\1422226217\413150\ac\WinAppDataRoaming\StardewValley\Saves',
    [string]$SmapiLogPath = 'D:\sbeam\steamapps\common\Stardew Valley\smapi-internal\SMAPI-latest.txt',
    [uri]$BridgeUrl = 'http://127.0.0.1:5678',
    [switch]$LaunchSmapi,
    [switch]$InspectLog
)

$ErrorActionPreference = 'Stop'
$scriptExitCode = 0

function Write-Check {
    param(
        [Parameter(Mandatory)] [string]$Name,
        [Parameter(Mandatory)] [ValidateSet('PASS', 'WARN', 'INFO', 'FAIL')] [string]$Status,
        [Parameter(Mandatory)] [string]$Detail
    )

    [pscustomobject]@{
        Check = $Name
        Status = $Status
        Detail = $Detail
    } | Format-Table -AutoSize | Out-Host
}

function Get-SaveSnapshot {
    param([Parameter(Mandatory)] [string]$Root)

    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        return @()
    }

    $resolvedRoot = (Get-Item -LiteralPath $Root).FullName.TrimEnd('\')
    return @(
        Get-ChildItem -LiteralPath $resolvedRoot -File -Recurse -ErrorAction Stop |
            ForEach-Object {
                [pscustomobject]@{
                    RelativePath = $_.FullName.Substring($resolvedRoot.Length).TrimStart('\')
                    LengthBytes = $_.Length
                    LastWriteTimeUtc = $_.LastWriteTimeUtc.ToString('o')
                }
            }
    )
}

function Show-Snapshot {
    param(
        [Parameter(Mandatory)] [string]$Label,
        [Parameter(Mandatory)] [object[]]$Snapshot
    )

    Write-Output "[$Label] 存档元数据（只读；文件内容未读取）"
    if ($Snapshot.Count -eq 0) {
        Write-Output '  <未发现存档文件或目录不存在>'
        return
    }
    $Snapshot | Sort-Object RelativePath | Format-Table -AutoSize | Out-Host
}

function Compare-Snapshot {
    param(
        [Parameter(Mandatory)] [object[]]$Before,
        [Parameter(Mandatory)] [object[]]$After
    )

    $beforeByPath = @{}
    foreach ($item in $Before) { $beforeByPath[$item.RelativePath] = $item }
    $afterByPath = @{}
    foreach ($item in $After) { $afterByPath[$item.RelativePath] = $item }
    $paths = @($beforeByPath.Keys + $afterByPath.Keys | Sort-Object -Unique)
    $changes = @(
        foreach ($path in $paths) {
            $old = $beforeByPath[$path]
            $new = $afterByPath[$path]
            if ($null -eq $old -or $null -eq $new -or
                $old.LengthBytes -ne $new.LengthBytes -or
                $old.LastWriteTimeUtc -ne $new.LastWriteTimeUtc) {
                [pscustomobject]@{
                    RelativePath = $path
                    Before = if ($null -eq $old) { '<不存在>' } else { "$($old.LengthBytes) bytes / $($old.LastWriteTimeUtc)" }
                    After = if ($null -eq $new) { '<不存在>' } else { "$($new.LengthBytes) bytes / $($new.LastWriteTimeUtc)" }
                }
            }
        }
    )

    if ($changes.Count -eq 0) {
        Write-Output '[SaveDelta] 未观察到大小或时间戳变化。'
    } else {
        Write-Output '[SaveDelta] 观察到以下元数据变化；脚本未执行任何存档写操作：'
        $changes | Format-Table -AutoSize | Out-Host
    }
}

function Test-Bridge {
    $healthUri = [uri]::new($BridgeUrl, '/health')
    $dialogueUri = [uri]::new($BridgeUrl, '/api/dialogue/test')

    try {
        $health = Invoke-RestMethod -Method Get -Uri $healthUri -TimeoutSec 2
        Write-Check -Name 'Bridge health' -Status 'PASS' -Detail "status=$($health.status); provider=$($health.provider)"
    } catch {
        Write-Check -Name 'Bridge closed' -Status 'WARN' -Detail "无法访问 $healthUri；按关闭场景记录，未启动 Bridge。"
        return
    }

    $payload = @{
        npcId = 'Rasmodia'
        displayName = 'Rasmodia'
        sourceMods = @('Stardew Valley Expanded', 'Romanceable Rasmodius')
        date = '春 1 日'
        weather = '晴天'
        location = '法师塔'
        friendship = 128
        relationship = '未婚'
        message = 'AI NPC 回归：请返回一句简短问候。'
    } | ConvertTo-Json -Depth 5

    try {
        $response = Invoke-RestMethod -Method Post -Uri $dialogueUri -ContentType 'application/json' -Body $payload -TimeoutSec 15
        $warnings = @($response.warnings | ForEach-Object { [string]$_ })
        $localFailed = $warnings -contains 'local provider failed'
        $cloudFailed = $warnings -contains 'cloud provider failed'
        if ($response.provider -eq 'fallback' -and $localFailed -and $cloudFailed) {
            Write-Check -Name 'Provider dual failure' -Status 'PASS' -Detail '记录到 local provider failed、cloud provider failed 和 fallback。'
        } elseif ($response.provider -eq 'fallback') {
            Write-Check -Name 'Provider dual failure' -Status 'WARN' -Detail "当前响应为 fallback，但双失败证据不完整：$($warnings -join ', ')"
        } else {
            Write-Check -Name 'Provider dual failure' -Status 'INFO' -Detail "当前响应 provider=$($response.provider)；需在两个上游均不可用时复跑。"
        }
    } catch {
        Write-Check -Name 'Provider request' -Status 'WARN' -Detail "Bridge 可达但对话请求失败：$($_.Exception.Message)"
    }
}

Write-Output '=== Stardew AI NPC SMAPI 回归（默认只读） ==='
Write-Output "GamePath: $GamePath"
Write-Output "StardropProfile: $StardropProfile"
Write-Output "SelectedModsPath: $SelectedModsPath"
Write-Output "SaveRoot: $SaveRoot"

foreach ($pathCheck in @(
    [pscustomobject]@{ Name = 'GamePath'; Path = $GamePath; Type = 'Container' },
    [pscustomobject]@{ Name = 'SMAPI entry'; Path = $SmapiExecutable; Type = 'Leaf' },
    [pscustomobject]@{ Name = 'AI-SVE-测试 profile'; Path = $StardropProfile; Type = 'Leaf' },
    [pscustomobject]@{ Name = 'Selected Mods (read-only)'; Path = $SelectedModsPath; Type = 'Container' },
    [pscustomobject]@{ Name = 'Source Mods (read-only)'; Path = $SourceModsPath; Type = 'Container' },
    [pscustomobject]@{ Name = 'SaveRoot'; Path = $SaveRoot; Type = 'Container' }
)) {
    if (Test-Path -LiteralPath $pathCheck.Path -PathType $pathCheck.Type) {
        Write-Check -Name $pathCheck.Name -Status 'PASS' -Detail "只读发现：$($pathCheck.Path)"
    } else {
        Write-Check -Name $pathCheck.Name -Status 'WARN' -Detail "未发现：$($pathCheck.Path)；请用参数覆盖，不会创建或修改它。"
        $scriptExitCode = 2
    }
}

$beforeSnapshot = @(Get-SaveSnapshot -Root $SaveRoot)
Show-Snapshot -Label 'Before' -Snapshot $beforeSnapshot
Test-Bridge

if ($InspectLog -and -not $LaunchSmapi) {
    Write-Check -Name 'Log inspection' -Status 'WARN' -Detail 'InspectLog 需要与 LaunchSmapi 一起使用，以避免把旧日志误当成本次证据。'
    $scriptExitCode = 2
}

$smapiProcess = $null
if ($LaunchSmapi) {
    if (-not (Test-Path -LiteralPath $SmapiExecutable -PathType Leaf)) {
        throw "SMAPI 启动入口不存在：$SmapiExecutable"
    }
    if (-not (Test-Path -LiteralPath $StardropProfile -PathType Leaf)) {
        throw "未找到 AI-SVE-测试 profile 文件；为避免启动错误 profile，已拒绝启动：$StardropProfile"
    }
    if (-not (Test-Path -LiteralPath $SelectedModsPath -PathType Container)) {
        throw "未找到 Stardrop Selected Mods 目录；为避免启动错误 Mods 集合，已拒绝启动：$SelectedModsPath"
    }

    Write-Output '正在调用 SMAPI 启动入口；请用户在游戏内完成 R5/R6 后退出游戏。'
    $smapiProcess = Start-Process -FilePath $SmapiExecutable -WorkingDirectory $GamePath -PassThru
    Wait-Process -Id $smapiProcess.Id
    $smapiProcess.Refresh()
    Write-Check -Name 'SMAPI process' -Status 'INFO' -Detail "已退出，ExitCode=$($smapiProcess.ExitCode)"

    $afterSnapshot = @(Get-SaveSnapshot -Root $SaveRoot)
    Show-Snapshot -Label 'After' -Snapshot $afterSnapshot
    Compare-Snapshot -Before $beforeSnapshot -After $afterSnapshot

    if ($InspectLog) {
        if (-not (Test-Path -LiteralPath $SmapiLogPath -PathType Leaf)) {
            Write-Check -Name 'SMAPI log' -Status 'WARN' -Detail "未发现日志：$SmapiLogPath；请用 -SmapiLogPath 覆盖实际路径。"
            $scriptExitCode = 2
        } else {
            Write-Output "[SMAPI log] 只读检查：$SmapiLogPath"
            $matches = @(Get-Content -LiteralPath $SmapiLogPath -Tail 200 | Select-String -Pattern 'Stardew AI NPC|Rasmodia|Bridge|provider|error|exception' -CaseSensitive:$false)
            if ($matches.Count -eq 0) {
                Write-Check -Name 'SMAPI log evidence' -Status 'WARN' -Detail '日志尾部未发现目标关键词；需要用户确认实际日志文件。'
            } else {
                $matches | ForEach-Object { Write-Output "  $($_.Line)" }
                Write-Check -Name 'SMAPI log evidence' -Status 'PASS' -Detail "发现 $($matches.Count) 条目标日志行。"
            }
        }
    }
} else {
    Write-Output '[After] 未传入 -LaunchSmapi，跳过启动和运行后存档快照。'
}

exit $scriptExitCode
