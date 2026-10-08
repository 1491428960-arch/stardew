<#[
.SYNOPSIS
    星露谷 AI NPC —— 正式游玩启动器（一键，含前置检查）。

.DESCRIPTION
    把「启动游戏」这件事固化，消除历史反复出现的三类岔子：

      ① mod 打错地方   —— 曾把 DLL 部署到 Mods-AI-FastTest 那类隔离目录，
                          正式存档读的是 Mods\StardewAI.NPC，等于没打上。
                          ⚠ 本脚本**绝不传 --mods-path**，只用正经 Mods。
      ② 起在 Session 0 —— DSH 是 LocalSystem，起在 Session 0 用户看不见。
                          本脚本统一投递到 Session 1。
      ③ 缺工作目录     —— SMAPI 必须在游戏根目录下运行，否则找不到游戏本体。

    事实来源：桌面快捷方式「星露谷 AI测试.lnk」的真实内容
        TargetPath       = <GamePath>\StardewModdingAPI.exe
        Arguments        = （无）
        WorkingDirectory = <GamePath>

    与 scripts/start_fast_test.ps1 的区别：那个走 -FastModsPath 隔离 profile，
    用于自动化回归；**日常游玩用本脚本**。

.PARAMETER WaitForLog
    启动后等到 SMAPI 日志出现「Loaded N mods」再返回，并摘要 StardewAI.NPC 的加载情况。

.PARAMETER SkipPreflight
    跳过 Bridge / DLL 哈希检查（仅在你明确知道它们没问题时用）。

.EXAMPLE
    pwsh -NoProfile -File scripts\launch-game.ps1 -WaitForLog
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$BridgeUrl = 'http://127.0.0.1:5678',
    [string]$DeployedModDir = 'Mods\StardewAI.NPC',
    [switch]$SkipPreflight,
    [switch]$WaitForLog
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$smapiExe = Join-Path $GamePath 'StardewModdingAPI.exe'
$smapiLog = Join-Path $env:APPDATA 'StardewValley\ErrorLogs\SMAPI-latest.txt'
$invokeHelper = 'E:\workspace\hub\scripts\invoke-in-session.ps1'

function Write-Step([string]$text) { Write-Host "`n=== $text ===" -ForegroundColor Cyan }
function Write-Ok([string]$text)   { Write-Host "  [OK]   $text" -ForegroundColor Green }
function Write-Warn2([string]$text){ Write-Host "  [WARN] $text" -ForegroundColor Yellow }
function Write-Bad([string]$text)  { Write-Host "  [BAD]  $text" -ForegroundColor Red }

Write-Host '星露谷 AI NPC 启动器' -ForegroundColor White
Write-Host "项目根：$projectRoot"

# ---------- 前置检查 ----------
$blockers = @()
if (-not $SkipPreflight) {
    Write-Step '前置检查'

    # 1. Session 1 存在（用户已登录桌面）
    $explorer = Get-Process explorer -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($explorer -and $explorer.SessionId -eq 1) {
        Write-Ok "Session 1 存在（explorer PID=$($explorer.Id)）"
    } else {
        Write-Bad 'Session 1 不存在 —— 请先登录桌面，否则游戏起了你也看不见'
        $blockers += 'session1'
    }

    # 2. SMAPI 启动器
    if (Test-Path -LiteralPath $smapiExe -PathType Leaf) {
        Write-Ok "SMAPI 启动器：$smapiExe"
    } else {
        Write-Bad "找不到 SMAPI 启动器：$smapiExe"
        $blockers += 'smapi'
    }

    # 3. Bridge 可达（游戏内对话全靠它）
    try {
        $health = Invoke-RestMethod -Uri "$BridgeUrl/health" -TimeoutSec 5
        Write-Ok "Bridge 可达：$BridgeUrl  provider=$($health.provider)"
        if ($health.provider -ne 'cloud') {
            Write-Warn2 "provider=$($health.provider)，不是 cloud —— 确认这是你要的吗？"
        }
    } catch {
        Write-Bad "Bridge 不可达：$BridgeUrl —— 先跑 scripts\start_bridge.ps1"
        $blockers += 'bridge'
    }

    # 4. 部署的 DLL 是否等于刚编译出来的产物
    $deployedDll = Join-Path $GamePath (Join-Path $DeployedModDir 'StardewAI.NPC.dll')
    $builtDll    = Join-Path $projectRoot 'smapi\bin\Debug\net6.0\StardewAI.NPC.dll'
    if ((Test-Path -LiteralPath $deployedDll -PathType Leaf) -and
        (Test-Path -LiteralPath $builtDll -PathType Leaf)) {
        $hDep = (Get-FileHash $deployedDll -Algorithm SHA256).Hash
        $hBlt = (Get-FileHash $builtDll -Algorithm SHA256).Hash
        if ($hDep -eq $hBlt) {
            Write-Ok "DLL 已是当前产物：$($hDep.Substring(0,16))…"
        } else {
            Write-Bad 'DLL 与刚编译的产物不一致 —— 部署的是旧版，改动不生效！'
            Write-Host "         部署=$($hDep.Substring(0,16))…  产物=$($hBlt.Substring(0,16))…"
            Write-Host "         修：Copy-Item '$builtDll' '$deployedDll' -Force"
            $blockers += 'dll'
        }
    } else {
        Write-Warn2 "DLL 校验跳过（部署或产物缺失）"
    }

    # 5. 提醒隔离目录的存在（历史踩坑点）
    $fastTestDir = Join-Path $GamePath 'Mods-AI-FastTest'
    if (Test-Path -LiteralPath $fastTestDir -PathType Container) {
        Write-Warn2 "存在 $fastTestDir（自动化测试用的隔离目录）。本脚本**不会**用它。"
    }
}

if ($blockers.Count -gt 0) {
    Write-Host "`n✘ 前置检查未通过：$($blockers -join ', ')" -ForegroundColor Red
    Write-Host '  修好再启动；确实要强行启动，加 -SkipPreflight' -ForegroundColor Red
    exit 1
}

# ---------- 已在运行则不重复启动 ----------
Write-Step '运行状态'
$running = Get-Process -Name 'StardewModdingAPI', 'Stardew Valley' -ErrorAction SilentlyContinue
if ($running) {
    Write-Warn2 "游戏已在运行：PID = $($running.Id -join ', ')（Session $($running[0].SessionId)）—— 不重复启动"
    exit 0
}
Write-Ok '游戏未运行，可以启动'

# ---------- 启动 ----------
Write-Step '启动游戏'

# ⚠ 2026-10-07 事故（「每次拉起都要出点岔子」的真因）：
#    本脚本原先**无条件**再调一次 invoke-in-session.ps1。可它自己往往就是被
#    Session 0 投递进 Session 1 的；那第二次投递会以**用户身份**去注册
#    `\DSH\DSH-Invoke-In-Session` 计划任务 ⇒ `Unregister-ScheduledTask: 拒绝访问`
#    ⇒ 投递链条当场断掉，内层 .ps1 从未执行，脚本空等 60 秒后报
#    「60 秒内未见游戏进程」。
#    现场证据：投递结果的 stdout 里**只有**那条拒绝访问，
#    **没有内层本该打印的 `PID=…`**。
#    现在先看自己在哪个 Session：已在 1 就直接启动，不再套一层。
$mySession = (Get-Process -Id $PID).SessionId
if ($mySession -eq 1) {
    Write-Ok '当前已在 Session 1，直接启动（不重复投递）'
    Start-Process -FilePath $smapiExe -WorkingDirectory $GamePath
} else {
    if (-not (Test-Path -LiteralPath $invokeHelper -PathType Leaf)) {
        Write-Bad "找不到投递脚本：$invokeHelper"
        exit 1
    }

    # ⚠ invoke-in-session.ps1 的 -Command 由 cmd.exe 执行：
    #    不能用内联 Start-Process（退出码 9009），必须落到一个无空格的 .ps1 再跑。
    #
    # ⚠ 2026-10-09 事故：本脚本常被从 Session 0 调用，而那里的 `$env:TEMP` 是
    #    `C:\WINDOWS\TEMP` —— Session 1 的 pwsh **读不到**它写下的那个文件，
    #    内层启动器报「无法识别为脚本文件」（退出码 64），投递白跑一趟；
    #    而报错文本指向「内层没有回显 PID」，很容易被误判成权限或二次投递问题。
    #    落到游戏目录：Session 1 必然可读，而且本就有写权限。
    $launcher = Join-Path $GamePath 'stardew-launch-inner.ps1'
    @"
`$ErrorActionPreference = 'Stop'
`$exe = '$smapiExe'
if (-not (Test-Path -LiteralPath `$exe -PathType Leaf)) { throw "找不到 `$exe" }
`$p = Start-Process -FilePath `$exe -WorkingDirectory '$GamePath' -PassThru
"PID=`$(`$p.Id)"
"@ | Set-Content -LiteralPath $launcher -Encoding UTF8

    # ⚠ 2026-10-09 事故（同一处第二次踩）：`$GamePath` 含空格，而这里的 -Command
    #    字符串原先**没给内层脚本路径加引号** ⇒ cmd.exe 把
    #    `D:\sbeam\steamapps\common\Stardew Valley\stardew-launch-inner.ps1`
    #    拆成 `D:\sbeam\steamapps\common\Stardew` + `Valley\...`，报
    #    「无法识别为脚本文件」。坑在于报错文本仍会说「内层没有回显 PID」，
    #    于是极容易被再次误判成上面那个 $env:TEMP 老问题（本次即如此）。
    #    cmd.exe 只认双引号，单引号在此无效。
    $out = & pwsh -File $invokeHelper -Command "pwsh -NoProfile -File `"$launcher`"" `
                  -WorkDir $GamePath -TimeoutSeconds 90 2>&1 | Out-String
    Write-Host $out

    # ⚠ 投递「完成：是」**不等于**内层跑起来了：计划任务可以注册并触发，
    #    而内层 pwsh 因路径 / 权限静默失败，invoke-in-session.ps1 照样报完成。
    #    唯一可信的证据是内层自己的回显 `PID=<数字>`。没有它就别白等 60 秒。
    if ($out -notmatch 'PID\s*=\s*\d+') {
        Write-Bad '投递完成，但内层没有回显 PID —— 启动命令并未真正执行'
        Write-Warn2 "内层脚本：$launcher（可手动检查）"
        Write-Warn2 '提示：若从 Session 0 调用，确认 invoke-in-session.ps1 未被二次投递'
        exit 1
    }

    Remove-Item -LiteralPath $launcher -Force -ErrorAction SilentlyContinue
}

# ---------- 等进程 ----------
Write-Step '等待进程'
$found = $null
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    $found = Get-Process -Name 'StardewModdingAPI', 'Stardew Valley' -ErrorAction SilentlyContinue
    if ($found) { break }
}
if (-not $found) {
    Write-Bad '60 秒内未见游戏进程'
    exit 1
}
$found | Select-Object Name, Id, SessionId,
    @{n='内存MB';e={[int]($_.WorkingSet64/1MB)}} | Format-Table -AutoSize | Out-String -Width 120 | Write-Host
if ($found[0].SessionId -ne 1) {
    Write-Bad "进程在 Session $($found[0].SessionId)，不是 1 —— 你看不见它"
    exit 1
}
Write-Ok "已启动，SessionId=1（你能看见）"

# ---------- 可选：等日志 ----------
if ($WaitForLog) {
    Write-Step '等待 SMAPI 加载 mod'
    $loaded = $false
    for ($i = 1; $i -le 40; $i++) {
        Start-Sleep -Seconds 3
        if (Test-Path -LiteralPath $smapiLog) {
            $content = Get-Content -LiteralPath $smapiLog -Raw -ErrorAction SilentlyContinue
            if ($content -match 'Loaded \d+ mods') { $loaded = $true; break }
        }
    }
    if (-not $loaded) {
        Write-Warn2 '未等到「Loaded N mods」，可稍后自己看日志'
    } else {
        Get-Content -LiteralPath $smapiLog | Select-String 'Loaded \d+ mods' |
            Select-Object -Last 1 | ForEach-Object { Write-Ok $_.Line.Trim() }

        $aiLines = Get-Content -LiteralPath $smapiLog | Select-String 'StardewAI\.NPC' |
                   Select-Object -Last 2
        if ($aiLines) {
            $aiLines | ForEach-Object { Write-Host "         $($_.Line.Trim())" }
            Write-Ok 'StardewAI.NPC 已被 SMAPI 加载'
        } else {
            Write-Bad '日志里看不到 StardewAI.NPC —— mod 可能没加载上'
        }
    }
}

Write-Host "`n✔ 启动完成" -ForegroundColor Green
Write-Host "  日志：$smapiLog"
