<#
.SYNOPSIS
  文档数字一致性检查：把"当前值只维护一处"这条约定变成可执行的断言。

.DESCRIPTION
  2026-09-20 通宵会话的收尾产物。

  今晚最反复出现的问题是**同一份数字在多处漂移**：同一天里 Bridge 测试数从
  2551 → 2634 → 2658 → 2671 → 2682 → 2687 → 2723，每补一批测试就要手动同步 5 个文件。
  第 123 项把它写进了 docs/README.md 的写作约定（“**具体的当前值只维护在
  `.dsh/memory/current-state.md` 一处**”），本脚本把那条约定变成**可执行的检查**。

  检查三件事：
    1. 能从 `.dsh/memory/current-state.md` 解析出当前基线（Bridge 测试数、覆盖率、缺失行数）；
    2. 这些数字在“权威位置”集合里都出现（即：真的同步过）；
    3. “不应含数字”的文档里确实不含测试数字（即：没有又多出副本）。

  只读；不修改任何文件。退出码 0 = 一致，1 = 有漂移。

.EXAMPLE
  pwsh -NoProfile -File scripts/check_doc_consistency.ps1
#>
[CmdletBinding()]
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$failures = [System.Collections.Generic.List[string]]::new()

function Read-Text([string]$relative) {
    $path = Join-Path $Root $relative
    if (-not (Test-Path $path)) { return $null }
    return [IO.File]::ReadAllText($path, [Text.UTF8Encoding]::new($false))
}

# --- 1. 从权威源解析基线 ------------------------------------------------------

$state = Read-Text '.dsh/memory/current-state.md'
if ($null -eq $state) {
    Write-Host '[FAIL] 找不到 .dsh/memory/current-state.md（约定的权威源）'
    exit 1
}

$bridge = [regex]::Match($state, 'Bridge \*\*(\d+) passed')
$coverage = [regex]::Match($state, 'TOTAL (\d+)%')
$missing = [regex]::Match($state, '缺失 (\d+) 行')
$smapi = [regex]::Match($state, 'SMAPI \*\*(\d+) passed')

foreach ($pair in @(
        @{ Name = 'Bridge 测试数'; M = $bridge },
        @{ Name = '覆盖率'; M = $coverage },
        @{ Name = '缺失行数'; M = $missing },
        @{ Name = 'SMAPI 测试数'; M = $smapi })) {
    if (-not $pair.M.Success) {
        $failures.Add("权威源里解析不出「$($pair.Name)」——它的写法可能变了，请同步更新本脚本的正则")
    }
}
if ($failures.Count -gt 0) {
    Write-Host '[FAIL] 无法从权威源解析基线：'
    $failures | ForEach-Object { Write-Host "        $_" }
    exit 1
}

$bridgeN = $bridge.Groups[1].Value
$coverageN = $coverage.Groups[1].Value
$missingN = $missing.Groups[1].Value
$smapiN = $smapi.Groups[1].Value
Write-Host "权威源基线：SMAPI $smapiN / Bridge $bridgeN passed / 覆盖率 $coverageN% / 缺失 $missingN 行"

# --- 1b. 权威源自身是否过时 ---------------------------------------------------
# 这一条是 2026-09-20 05:00 补的。脚本原先只检查“各处是否与权威源一致”，
# 却不检查“权威源自己是不是旧的”——那次补完 28 条测试后（2723 → 2751），
# 脚本仍然报“一致”，因为权威源还停在 2723。盲区就在这里。
$takenMatch = [regex]::Match($state, '\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) 实测\*\*')
if (-not $takenMatch.Success) {
    Write-Host '[WARN] 权威源里找不到取数时刻（形如 `（**2026-09-20 05:00 实测**）`）——无法判断它是否过时'
}
else {
    $taken = [datetime]::ParseExact($takenMatch.Groups[1].Value, 'yyyy-MM-dd HH:mm', $null)
    $ageMinutes = [int]((Get-Date) - $taken).TotalMinutes
    Write-Host "权威源取数时刻：$($takenMatch.Groups[1].Value)（$ageMinutes 分钟前）"
    if ($ageMinutes -gt 45) {
        Write-Host "[WARN] 权威源可能已过时（$ageMinutes 分钟未更新）——如果你刚补过测试或改过生产代码，请先把新数字同步进 current-state.md，否则下面的“一致”只是自洽而已"
    }
}

# --- 2. 权威位置必须都持有同一组数字 ------------------------------------------

$authoritative = @(
    '.dsh/memory/current-state.md',
    '.dsh/memory/commands.md',
    'docs/active-work.md',                     # 顶部「阅读约定」
    'docs/overnight-report-2026-09-20.md',     # 开头「最终验证」表
    'docs/next-steps-2026-09-20.md'            # A3 的“唯一的红灯”
)

Write-Host ''
Write-Host '权威位置：'
foreach ($file in $authoritative) {
    $text = Read-Text $file
    if ($null -eq $text) {
        $failures.Add("$file 不存在")
        Write-Host "  [FAIL] $file 不存在"
        continue
    }
    if ($text -match [regex]::Escape($bridgeN)) {
        Write-Host "  [ OK ] $file 含 Bridge $bridgeN"
    }
    else {
        $failures.Add("$file 没有当前 Bridge 测试数 $bridgeN（可能忘了同步）")
        Write-Host "  [FAIL] $file 缺少 Bridge $bridgeN"
    }
}

# --- 3. 不应含数字的文档里不能出现测试数字 ------------------------------------

$shouldHaveNoNumbers = @(
    'README.md',
    'AGENTS.md',
    'docs/README.md',
    '.dsh/memory/MEMORY.md'
)

Write-Host ''
Write-Host '不应含测试数字的文档：'
$numberPattern = '\d{4} passed|TOTAL \d+%|缺失 \d+ 行'
foreach ($file in $shouldHaveNoNumbers) {
    $text = Read-Text $file
    if ($null -eq $text) {
        Write-Host "  [ -- ] $file 不存在（跳过）"
        continue
    }
    $hit = [regex]::Match($text, $numberPattern)
    if ($hit.Success) {
        $failures.Add("$file 出现了测试数字「$($hit.Value)」——按约定当前值只维护在 current-state.md")
        Write-Host "  [FAIL] $file 含「$($hit.Value)」"
    }
    else {
        Write-Host "  [ OK ] $file 不含测试数字"
    }
}

# --- 4. 各权威位置的时间戳必须一致 -------------------------------------------
# 这一条是 2026-09-20 04:55 补的（第 147 项）。当时发现 `active-work.md` 顶部的时间戳
# 停在 03:44，而其他位置已是 04:53——历次批量替换的锚点每次都绕过了它，
# 而本脚本此前只查数字、不查时间戳，所以没发现。这是它的第二个盲区。
Write-Host ''
Write-Host '时间戳一致性：'
$stampSources = [ordered]@{
    'active-work 顶部'   = @('docs/active-work.md', '截至 (\d{4}-\d{2}-\d{2} \d{2}:\d{2})')
    'current-state 标题' = @('.dsh/memory/current-state.md', '截至 (\d{4}-\d{2}-\d{2} \d{2}:\d{2})')
    'current-state 基线' = @('.dsh/memory/current-state.md', '\*\*(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) 实测\*\*')
    'next-steps A3'      = @('docs/next-steps-2026-09-20.md', '(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) 实测')
}
$stamps = [ordered]@{}
foreach ($name in $stampSources.Keys) {
    $target = $stampSources[$name]
    $stampText = Read-Text $target[0]
    if ($null -eq $stampText) { continue }
    $match = [regex]::Match($stampText, $target[1])
    if ($match.Success) {
        $stamps[$name] = $match.Groups[1].Value
        Write-Host "  $name = $($match.Groups[1].Value)"
    }
    else {
        Write-Host "  [WARN] $name 里找不到时间戳"
    }
}
$distinctStamps = @($stamps.Values | Sort-Object -Unique)
if ($distinctStamps.Count -gt 1) {
    $detail = ($stamps.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join '，'
    $failures.Add("时间戳不一致：$detail（同时同步它们，别只改数字）")
    Write-Host "  [FAIL] 不一致：$detail"
}
elseif ($distinctStamps.Count -eq 1) {
    Write-Host "  [ OK ] 四处一致：$($distinctStamps[0])"
}

# --- 汇总 -------------------------------------------------------------------

Write-Host ''
if ($failures.Count -eq 0) {
    Write-Host '结论：一致 ✓（当前值只在权威位置，且各处相同）'
    exit 0
}

Write-Host "结论：发现 $($failures.Count) 处漂移"
$failures | ForEach-Object { Write-Host "  - $_" }
exit 1
