<#
.SYNOPSIS
    同步并启动 StardewAI.NPC 的独立快速测试 Mod 集合。

.DESCRIPTION
    默认只同步 StardewAI.NPC 和 Generic Mod Config Menu，使用 SMAPI 的
    --mods-path 启动独立目录。正式 Mods、Stardrop profile 和存档不会被修改。
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$FastModsPath,
    [string]$SourceModsPath,
    [string]$GmcmSourcePath,
    [string]$RasmodiaSourcePath,
    [string]$ProjectRoot,
    [switch]$IncludeRasmodia,
    [switch]$NoLaunch
)

$ErrorActionPreference = 'Stop'

function Get-NormalizedPath {
    param([Parameter(Mandatory)] [string]$Path)

    $fullPath = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetPathRoot($fullPath)
    if ($fullPath -ne $root) {
        return $fullPath.TrimEnd('\')
    }
    return $fullPath
}

function Test-SamePath {
    param(
        [Parameter(Mandatory)] [string]$Left,
        [Parameter(Mandatory)] [string]$Right
    )

    return [string]::Equals((Get-NormalizedPath $Left), (Get-NormalizedPath $Right), [StringComparison]::OrdinalIgnoreCase)
}

function Test-PathInside {
    param(
        [Parameter(Mandatory)] [string]$Candidate,
        [Parameter(Mandatory)] [string]$Root
    )

    $candidatePath = Get-NormalizedPath $Candidate
    $rootPath = Get-NormalizedPath $Root
    return $candidatePath.StartsWith($rootPath + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Require-Directory {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name 不存在或不是目录：$Path"
    }
    return (Get-NormalizedPath ((Get-Item -LiteralPath $Path).FullName))
}

function Require-File {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name 不存在：$Path"
    }
    return (Get-NormalizedPath ((Get-Item -LiteralPath $Path).FullName))
}

function Resolve-SourceModsPath {
    param(
        [Parameter(Mandatory)] [string]$GameRoot,
        [string]$ExplicitPath
    )

    if ($ExplicitPath) {
        return Require-Directory -Path $ExplicitPath -Name 'SourceModsPath'
    }

    $candidates = @(
        (Join-Path $GameRoot 'Mods'),
        (Join-Path $env:APPDATA 'Stardrop\Data\SELECT~1')
    )

    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate -PathType Container) -and
            (Test-Path -LiteralPath (Join-Path $candidate 'GenericModConfigMenu') -PathType Container)) {
            return Require-Directory -Path $candidate -Name 'SourceModsPath'
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            return Require-Directory -Path $candidate -Name 'SourceModsPath'
        }
    }

    throw "没有找到可用的 Mod 源目录，请使用 -SourceModsPath 指定。"
}

function Assert-SafeTarget {
    param(
        [Parameter(Mandatory)] [string]$Target,
        [Parameter(Mandatory)] [string[]]$ProtectedRoots
    )

    foreach ($protectedRoot in $ProtectedRoots) {
        if ((Test-SamePath -Left $Target -Right $protectedRoot) -or
            (Test-PathInside -Candidate $Target -Root $protectedRoot) -or
            (Test-PathInside -Candidate $protectedRoot -Root $Target)) {
            throw "快速测试目录不能与受保护目录相同或互相包含：$Target / $protectedRoot"
        }
    }
}

function Remove-ManagedDirectory {
    param(
        [Parameter(Mandatory)] [string]$FastRoot,
        [Parameter(Mandatory)] [string]$Name
    )

    $managedPath = Join-Path $FastRoot $Name
    if (-not (Test-Path -LiteralPath $managedPath)) {
        return
    }

    if (-not (Test-PathInside -Candidate $managedPath -Root $FastRoot)) {
        throw "拒绝清理快速目录之外的路径：$managedPath"
    }
    Remove-Item -LiteralPath $managedPath -Recurse -Force
}

if (-not $ProjectRoot) {
    $ProjectRoot = Get-NormalizedPath (Join-Path $PSScriptRoot '..')
} else {
    $ProjectRoot = Get-NormalizedPath $ProjectRoot
}
if (-not $FastModsPath) {
    $FastModsPath = Join-Path $GamePath 'Mods-AI-FastTest'
}

$GamePath = Require-Directory -Path $GamePath -Name 'GamePath'
$SourceModsPath = Resolve-SourceModsPath -GameRoot $GamePath -ExplicitPath $SourceModsPath
$FastModsPath = Get-NormalizedPath $FastModsPath
$ProjectRoot = Require-Directory -Path $ProjectRoot -Name 'ProjectRoot'
$officialModsPath = Get-NormalizedPath (Join-Path $GamePath 'Mods')
$smapiPath = Require-File -Path (Join-Path $GamePath 'StardewModdingAPI.exe') -Name 'SMAPI 启动入口'
$buildPath = Require-Directory -Path (Join-Path $ProjectRoot 'smapi\bin\Debug\net6.0') -Name 'SMAPI 构建目录'
$dllSourcePath = Require-File -Path (Join-Path $buildPath 'StardewAI.NPC.dll') -Name 'StardewAI.NPC 构建 DLL'
$manifestSourcePath = Require-File -Path (Join-Path $ProjectRoot 'smapi\manifest.json') -Name 'StardewAI.NPC manifest'

Assert-SafeTarget -Target $FastModsPath -ProtectedRoots @(
    $officialModsPath,
    $SourceModsPath,
    $ProjectRoot
)
if (Test-SamePath -Left $FastModsPath -Right $GamePath) {
    throw "快速测试目录不能直接使用游戏目录：$FastModsPath"
}

if ($GmcmSourcePath) {
    $GmcmSourcePath = Require-Directory -Path $GmcmSourcePath -Name 'GmcmSourcePath'
} else {
    $GmcmSourcePath = Require-Directory -Path (Join-Path $SourceModsPath 'GenericModConfigMenu') -Name 'GenericModConfigMenu 源目录'
}

if ($IncludeRasmodia) {
    if ($RasmodiaSourcePath) {
        $RasmodiaSourcePath = Require-Directory -Path $RasmodiaSourcePath -Name 'RasmodiaSourcePath'
    } else {
        $RasmodiaSourcePath = Require-Directory -Path (Join-Path $SourceModsPath '[CP] Romanceable Rasmodia') -Name 'Rasmodia 内容包源目录'
    }
}

New-Item -ItemType Directory -Path $FastModsPath -Force | Out-Null
$managedNames = @('StardewAI.NPC', 'GenericModConfigMenu', '[CP] Romanceable Rasmodia')
foreach ($managedName in $managedNames) {
    Remove-ManagedDirectory -FastRoot $FastModsPath -Name $managedName
}

$npcTargetPath = Join-Path $FastModsPath 'StardewAI.NPC'
New-Item -ItemType Directory -Path $npcTargetPath -Force | Out-Null
Get-ChildItem -LiteralPath $buildPath -File -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $npcTargetPath -Force
}
Copy-Item -LiteralPath $manifestSourcePath -Destination $npcTargetPath -Force
Copy-Item -LiteralPath $GmcmSourcePath -Destination $FastModsPath -Recurse -Force
if ($IncludeRasmodia) {
    Copy-Item -LiteralPath $RasmodiaSourcePath -Destination $FastModsPath -Recurse -Force
}

$dllTargetPath = Join-Path $npcTargetPath 'StardewAI.NPC.dll'
$hash = (Get-FileHash -LiteralPath $dllTargetPath -Algorithm SHA256).Hash
$modNames = @(Get-ChildItem -LiteralPath $FastModsPath -Directory -Force | Select-Object -ExpandProperty Name)

Write-Output '=== StardewAI.NPC 快速测试 profile ==='
Write-Output "GamePath: $GamePath"
Write-Output "FastModsPath: $FastModsPath"
Write-Output "SourceModsPath: $SourceModsPath"
Write-Output "StardewAI.NPC SHA256: $hash"
Write-Output ('Mods: ' + ($modNames -join ', '))

if ($NoLaunch) {
    Write-Output 'NoLaunch: 已启用，只完成同步和检查。'
    exit 0
}

Write-Output "正在启动 SMAPI：$smapiPath --mods-path $FastModsPath"
$process = Start-Process -FilePath $smapiPath -WorkingDirectory $GamePath -ArgumentList @('--mods-path', $FastModsPath) -PassThru
Write-Output "SMAPI 已启动，PID=$($process.Id)"
exit 0
