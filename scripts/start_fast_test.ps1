<#
.SYNOPSIS
    同步并启动 StardewAI.NPC 的独立快速测试 Mod 集合。

.DESCRIPTION
    默认只同步 StardewAI.NPC 和 Generic Mod Config Menu，不启动游戏。显式传入
    -Launch 后才会使用 SMAPI 的 --mods-path 启动独立目录；存档隔离由用户选择独立测试存档。
#>
[CmdletBinding()]
param(
    [string]$GamePath = 'D:\sbeam\steamapps\common\Stardew Valley',
    [string]$FastModsPath,
    [string]$SourceModsPath,
    [string]$GmcmSourcePath,
    [string]$RasmodiaSourcePath,
    [string]$ProjectRoot,
    [string]$SmapiExecutable,
    [switch]$IncludeRasmodia,
    [switch]$Launch,
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

function Test-AllowlistedWorktreeContainer {
    param([Parameter(Mandatory)] [object]$Item)

    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -or
        $Item.LinkType -ne 'Junction' -or
        [string]::IsNullOrWhiteSpace([string]$Item.Target)) {
        return $false
    }

    $aliasName = [string]$Item.Name
    $suffix = '.worktrees'
    if (-not $aliasName.EndsWith($suffix, [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }

    $targetItem = Get-Item -LiteralPath ([string]$Item.Target) -Force -ErrorAction SilentlyContinue
    if (-not $targetItem -or
        ($targetItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        -not [string]::Equals([string]$targetItem.Name, '.worktrees', [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }

    $targetRepository = Split-Path -Path (Get-NormalizedPath $targetItem.FullName) -Parent
    if (-not $targetRepository) {
        return $false
    }
    $targetRepositoryItem = Get-Item -LiteralPath $targetRepository -Force -ErrorAction SilentlyContinue
    if (-not $targetRepositoryItem -or
        ($targetRepositoryItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        -not [string]::Equals($aliasName, ([string]$targetRepositoryItem.Name + $suffix), [StringComparison]::OrdinalIgnoreCase)) {
        return $false
    }

    $aliasParent = Split-Path -Path $Item.FullName -Parent
    $repositoryParent = Split-Path -Path $targetRepositoryItem.FullName -Parent
    return $aliasParent -and $repositoryParent -and (Test-SamePath -Left $aliasParent -Right $repositoryParent)
}

function Assert-NoReparsePoints {
    param([Parameter(Mandatory)] [string]$Path)

    $current = Get-NormalizedPath $Path
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            $item = Get-Item -LiteralPath $current -Force
            if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -and
                -not (Test-AllowlistedWorktreeContainer -Item $item)) {
                throw "拒绝使用包含 Junction 或符号链接的路径：$current"
            }
            $parent = Split-Path -Path $item.FullName -Parent
        } else {
            $parent = Split-Path -Path $current -Parent
        }

        if (-not $parent -or (Test-SamePath -Left $parent -Right $current)) {
            break
        }
        $current = Get-NormalizedPath $parent
    }
}

function Require-Directory {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name 不存在或不是目录：$Path"
    }
    $resolvedPath = Get-NormalizedPath ((Get-Item -LiteralPath $Path -Force).FullName)
    Assert-NoReparsePoints -Path $resolvedPath
    return $resolvedPath
}

function Require-NamedDirectory {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$ExpectedName,
        [Parameter(Mandatory)] [string]$Name,
        [switch]$AllowLeafReparsePoint
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
        throw "$Name 不存在或不是目录：$Path"
    }
    $resolvedPath = Get-NormalizedPath ((Get-Item -LiteralPath $Path -Force).FullName)
    if (-not $AllowLeafReparsePoint) {
        Assert-NoReparsePoints -Path $resolvedPath
    } else {
        $parent = Split-Path -Path $resolvedPath -Parent
        if ($parent) {
            Assert-NoReparsePoints -Path $parent
        }
    }
    $actualName = (Get-Item -LiteralPath $resolvedPath -Force).Name
    if (-not [string]::Equals($actualName, $ExpectedName, [StringComparison]::Ordinal)) {
        throw "$Name 必须是目录 $ExpectedName，实际为：$actualName"
    }
    return $resolvedPath
}

function Assert-StardropSourceLink {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$TrustedRoot
    )

    $item = Get-Item -LiteralPath $Path -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) {
        return
    }
    if ($item.LinkType -ne 'Junction' -or -not $item.Target) {
        throw "源目录只能是普通目录，或指向 Stardrop 安装缓存的 Junction：$Path"
    }
    $targetItem = Get-Item -LiteralPath ([string]$item.Target) -Force -ErrorAction Stop
    $targetPath = Get-NormalizedPath $targetItem.FullName
    $trustedPath = Require-Directory -Path $TrustedRoot -Name 'Stardrop 安装缓存目录'
    if (-not (Test-PathInside -Candidate $targetPath -Root $trustedPath)) {
        throw "源目录 Junction 目标不在 Stardrop 安装缓存内：$targetPath"
    }
}

function Require-File {
    param(
        [Parameter(Mandatory)] [string]$Path,
        [Parameter(Mandatory)] [string]$Name,
        [switch]$AllowReparsePoint
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name 不存在：$Path"
    }
    $resolvedPath = Get-NormalizedPath ((Get-Item -LiteralPath $Path -Force).FullName)
    if (-not $AllowReparsePoint) {
        Assert-NoReparsePoints -Path $resolvedPath
    }
    return $resolvedPath
}

function Require-ModManifest {
    param(
        [Parameter(Mandatory)] [string]$Directory,
        [Parameter(Mandatory)] [string]$ExpectedUniqueId,
        [Parameter(Mandatory)] [string]$Name
    )

    $manifestPath = Require-File -Path (Join-Path $Directory 'manifest.json') -Name "$Name manifest" -AllowReparsePoint
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding utf8 | ConvertFrom-Json -ErrorAction Stop
    } catch {
        throw "$Name manifest 不是有效 JSON：$manifestPath"
    }
    $actualUniqueId = [string]$manifest.UniqueID
    if (-not [string]::Equals($actualUniqueId, $ExpectedUniqueId, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Name manifest UniqueID 不匹配，期望 $ExpectedUniqueId，实际 $actualUniqueId"
    }
    return $manifestPath
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

    Assert-NoReparsePoints -Path $Target
    foreach ($protectedRoot in $ProtectedRoots) {
        if (Test-Path -LiteralPath $protectedRoot) {
            Assert-NoReparsePoints -Path $protectedRoot
        }
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
    if (-not (Test-Path -LiteralPath $managedPath -PathType Container)) {
        throw "快速目录中的受控名称不是目录，拒绝删除：$managedPath"
    }

    if (-not (Test-PathInside -Candidate $managedPath -Root $FastRoot)) {
        throw "拒绝清理快速目录之外的路径：$managedPath"
    }
    Assert-NoReparsePoints -Path $managedPath
    Remove-Item -LiteralPath $managedPath -Recurse -Force
}

if (-not $ProjectRoot) {
    $ProjectRoot = Get-NormalizedPath (Join-Path $PSScriptRoot '..')
} else {
    $ProjectRoot = Get-NormalizedPath $ProjectRoot
}
if ($Launch -and $NoLaunch) {
    throw '-Launch 和 -NoLaunch 不能同时使用。'
}
if (-not $FastModsPath) {
    $FastModsPath = Join-Path $GamePath 'Mods-AI-FastTest'
}

$GamePath = Require-Directory -Path $GamePath -Name 'GamePath'
$SourceModsPath = Resolve-SourceModsPath -GameRoot $GamePath -ExplicitPath $SourceModsPath
$FastModsPath = Get-NormalizedPath $FastModsPath
$ProjectRoot = Require-Directory -Path $ProjectRoot -Name 'ProjectRoot'
$officialModsPath = Get-NormalizedPath (Join-Path $GamePath 'Mods')
$smapiPath = if ($SmapiExecutable) {
    Require-File -Path $SmapiExecutable -Name 'SMAPI 启动入口'
} else {
    Require-File -Path (Join-Path $GamePath 'StardewModdingAPI.exe') -Name 'SMAPI 启动入口'
}
$buildPath = Require-Directory -Path (Join-Path $ProjectRoot 'smapi\bin\Debug\net6.0') -Name 'SMAPI 构建目录'
$dllSourcePath = Require-File -Path (Join-Path $buildPath 'StardewAI.NPC.dll') -Name 'StardewAI.NPC 构建 DLL'
$manifestSourcePath = Require-File -Path (Join-Path $ProjectRoot 'smapi\manifest.json') -Name 'StardewAI.NPC manifest'
$sourceRoot = Join-Path $ProjectRoot 'smapi'
if (Test-Path -LiteralPath $sourceRoot -PathType Container) {
    $sourceFiles = @(
        Get-ChildItem -LiteralPath $sourceRoot -Filter '*.cs' -File -Recurse |
            Where-Object { $_.FullName -notmatch '[\\/]((bin|obj|tests))[\\/]' }
    )
    if ($sourceFiles.Count -gt 0) {
        $latestSource = $sourceFiles |
            Sort-Object LastWriteTimeUtc -Descending |
            Select-Object -First 1
        $dllInfo = Get-Item -LiteralPath $dllSourcePath
        if ($latestSource.LastWriteTimeUtc -gt $dllInfo.LastWriteTimeUtc) {
            throw "源码文件晚于构建 DLL，拒绝同步旧产物：$($latestSource.FullName) / $dllSourcePath。请先重新构建。"
        }
    }
}

Assert-SafeTarget -Target $FastModsPath -ProtectedRoots @(
    $officialModsPath,
    $SourceModsPath,
    $ProjectRoot
)
if (Test-SamePath -Left $FastModsPath -Right $GamePath) {
    throw "快速测试目录不能直接使用游戏目录：$FastModsPath"
}

if ($GmcmSourcePath) {
    $GmcmSourcePath = Require-NamedDirectory -Path $GmcmSourcePath -ExpectedName 'GenericModConfigMenu' -Name 'GmcmSourcePath' -AllowLeafReparsePoint
} else {
    $GmcmSourcePath = Require-NamedDirectory -Path (Join-Path $SourceModsPath 'GenericModConfigMenu') -ExpectedName 'GenericModConfigMenu' -Name 'GenericModConfigMenu 源目录' -AllowLeafReparsePoint
}
Require-File -Path (Join-Path $GmcmSourcePath 'manifest.json') -Name 'GMCM manifest' -AllowReparsePoint | Out-Null
$stardropCachePath = Join-Path $officialModsPath 'Stardrop Installed Mods'
Assert-StardropSourceLink -Path $GmcmSourcePath -TrustedRoot $stardropCachePath

if ($IncludeRasmodia) {
    if ($RasmodiaSourcePath) {
        $RasmodiaSourcePath = Require-NamedDirectory -Path $RasmodiaSourcePath -ExpectedName '[CP] Romanceable Rasmodia' -Name 'RasmodiaSourcePath' -AllowLeafReparsePoint
    } else {
        $RasmodiaSourcePath = Require-NamedDirectory -Path (Join-Path $SourceModsPath '[CP] Romanceable Rasmodia') -ExpectedName '[CP] Romanceable Rasmodia' -Name 'Rasmodia 内容包源目录' -AllowLeafReparsePoint
    }
    Require-File -Path (Join-Path $RasmodiaSourcePath 'manifest.json') -Name 'Rasmodia manifest' -AllowReparsePoint | Out-Null
    Assert-StardropSourceLink -Path $RasmodiaSourcePath -TrustedRoot $stardropCachePath

    $contentPatcherSourcePath = Require-NamedDirectory -Path (Join-Path $SourceModsPath 'ContentPatcher') -ExpectedName 'ContentPatcher' -Name 'Content Patcher 源目录' -AllowLeafReparsePoint
    Require-ModManifest -Directory $contentPatcherSourcePath -ExpectedUniqueId 'Pathoschild.ContentPatcher' -Name 'Content Patcher' | Out-Null
    Assert-StardropSourceLink -Path $contentPatcherSourcePath -TrustedRoot $stardropCachePath

    $cmctSourcePath = Require-NamedDirectory -Path (Join-Path $SourceModsPath 'CrossModCompatibilityTokens') -ExpectedName 'CrossModCompatibilityTokens' -Name 'CMCT 源目录' -AllowLeafReparsePoint
    Require-ModManifest -Directory $cmctSourcePath -ExpectedUniqueId 'Spiderbuttons.CMCT' -Name 'CMCT' | Out-Null
    Assert-StardropSourceLink -Path $cmctSourcePath -TrustedRoot $stardropCachePath
}

[IO.Directory]::CreateDirectory($FastModsPath) | Out-Null
$managedNames = @(
    'StardewAI.NPC',
    'GenericModConfigMenu',
    '[CP] Romanceable Rasmodia',
    'ContentPatcher',
    'CrossModCompatibilityTokens'
)
foreach ($managedName in $managedNames) {
    Remove-ManagedDirectory -FastRoot $FastModsPath -Name $managedName
}

$npcTargetPath = Join-Path $FastModsPath 'StardewAI.NPC'
[IO.Directory]::CreateDirectory($npcTargetPath) | Out-Null
Get-ChildItem -LiteralPath $buildPath -File -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $npcTargetPath -Force
}
Copy-Item -LiteralPath $manifestSourcePath -Destination $npcTargetPath -Force
Copy-Item -LiteralPath $GmcmSourcePath -Destination $FastModsPath -Recurse -Force
if ($IncludeRasmodia) {
    Copy-Item -LiteralPath $RasmodiaSourcePath -Destination $FastModsPath -Recurse -Force
    Copy-Item -LiteralPath $contentPatcherSourcePath -Destination $FastModsPath -Recurse -Force
    Copy-Item -LiteralPath $cmctSourcePath -Destination $FastModsPath -Recurse -Force
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

if (-not $Launch -or $NoLaunch) {
    Write-Output 'Launch: 未启用，只完成同步和检查。需要启动游戏时请显式添加 -Launch。'
    exit 0
}

Write-Output "正在启动 SMAPI：$smapiPath --mods-path $FastModsPath"
$quotedFastModsPath = '"' + $FastModsPath + '"'
$argumentList = @('--mods-path', $quotedFastModsPath)
$originalWindir = $env:windir
$windirWasAdded = $false
if ([string]::IsNullOrWhiteSpace($env:windir)) {
    $windowsDirectory = $env:SystemRoot
    if ([string]::IsNullOrWhiteSpace($windowsDirectory)) {
        $windowsDirectory = [Environment]::GetEnvironmentVariable('windir', 'Machine')
    }
    if ([string]::IsNullOrWhiteSpace($windowsDirectory) -or -not [IO.Directory]::Exists($windowsDirectory)) {
        throw '当前进程缺少有效的 windir/SystemRoot，无法安全启动 SMAPI。'
    }
    $env:windir = $windowsDirectory
    $windirWasAdded = $true
    Write-Output "已为 SMAPI 子进程补回 windir：$windowsDirectory"
}
try {
    $process = Start-Process -FilePath $smapiPath -WorkingDirectory $GamePath -ArgumentList $argumentList -PassThru
    try {
        Write-Output "SMAPI 已启动，PID=$($process.Id)"
        $process.WaitForExit()
    } finally {
        $process.Dispose()
    }
} finally {
    if ($windirWasAdded) {
        if ($null -eq $originalWindir) {
            Remove-Item Env:windir -ErrorAction SilentlyContinue
        } else {
            $env:windir = $originalWindir
        }
    }
}
Write-Output 'SMAPI 已退出，启动器已释放进程句柄。'
exit 0
