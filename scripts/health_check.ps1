<#
.SYNOPSIS
星露谷 AI NPC 项目的「只读体检」入口：把若干审计工具串成一条命令。

.DESCRIPTION
与 verify_project.ps1 的分工：

    verify_project.ps1   跑**测试与静态检查**（会编译、会跑 dotnet test 与 pytest）
    health_check.ps1     跑**只读审计**（不修改任何文件、不发云端请求）

两者互补：改完一轮后各跑一次即可。本脚本不做任何写操作。

.PARAMETER SkipUncovered
跳过「从未被执行的函数」一节（需要先有 .coverage）。

.EXAMPLE
pwsh -NoProfile -ExecutionPolicy Bypass -File scripts\health_check.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipUncovered
)

$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$safe = "safe.directory=$root"

# Python 解释器探测。本机实测：Python 3.10 装在用户目录下，**没有注册到 py launcher**，
# 所以 `py -3.10` 会报 "No Installed Pythons Found!"——必须优先探测绝对路径，
# 而且每个候选都要真正跑一次才算数。
$pythonExe = $null
$pythonArgs = @()
$candidates = @(
    @{ Exe = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python310\python.exe'); Args = @() },
    @{ Exe = 'py'; Args = @('-3.10') },
    @{ Exe = 'python'; Args = @() }
)
foreach ($candidate in $candidates) {
    $isCommand = $candidate.Exe -in @('py', 'python')
    if ($isCommand) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
    } elseif (-not (Test-Path $candidate.Exe)) {
        continue
    }
    & $candidate.Exe @($candidate.Args) -c 'import sys' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = $candidate.Exe
        $pythonArgs = $candidate.Args
        break
    }
}

Push-Location $root
try {
    # Python 子进程默认按控制台代码页输出，中文会乱码；显式要求 UTF-8。
    # PYTHONPATH 让脚本在需要时也能 import 到项目模块（审计脚本本身只读文件，不依赖它）。
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHONPATH = 'bridge/src;scripts'

    if (-not $pythonExe) {
        Write-Host '找不到 Python 3.10，只有 git 相关检查会执行。' -ForegroundColor Yellow
    }

    Write-Host '=== 1/5 工作树规模 ===' -ForegroundColor Cyan
    $status = @(git -c $safe status --short)
    $modified = @($status | Where-Object { $_ -match '^ ?M' }).Count
    $untracked = @($status | Where-Object { $_ -match '^\?\?' }).Count
    Write-Host "  共 $($status.Count) 项 = 已修改 $modified + 未跟踪 $untracked"
    Write-Host '  注意：HEAD 停在较早的提交，所以这些是长期累积，不等于最近一轮的改动量。'

    Write-Host '=== 2/5 空白错误 ===' -ForegroundColor Cyan
    # git 在 Windows 上会对每个文件提示 "LF will be replaced by CRLF"——那只是换行符提示，
    # 不是空白错误；这里只保留 diff --check 的真正输出。
    git -c $safe diff --check 2>$null
    Write-Host "  git diff --check 退出码 $LASTEXITCODE（已忽略换行符提示）"

    if ($pythonExe) {
        Write-Host '=== 3/5 资料索引体检 ===' -ForegroundColor Cyan
        & $pythonExe @pythonArgs -B scripts\audit_profile_index.py
        Write-Host ''

        Write-Host '=== 4/5 Bridge 公开名字与脚本安全门 ===' -ForegroundColor Cyan
        & $pythonExe @pythonArgs -B scripts\audit_bridge_health.py

        if (-not $SkipUncovered) {
            Write-Host ''
            Write-Host '=== 5/5 从未被执行的函数 ===' -ForegroundColor Cyan
            if (Test-Path '.coverage') {
                & $pythonExe @pythonArgs -B scripts\find_uncovered_functions.py
            } else {
                Write-Host '  没有 .coverage，跳过。生成方式：先带覆盖率跑一轮 pytest。'
            }
        }
    }

    Write-Host ''
    Write-Host '体检完成（全程只读，未修改任何文件）。' -ForegroundColor Green
}
finally {
    Pop-Location
}
