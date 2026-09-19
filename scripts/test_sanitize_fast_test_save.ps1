$ErrorActionPreference = 'Stop'

$sanitizerPath = Join-Path $PSScriptRoot 'sanitize_fast_test_save.ps1'
$script:passed = 0
$script:failed = 0

function Invoke-TestCase {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [scriptblock]$Body
    )

    try {
        & $Body
        $script:passed++
        Write-Host "PASS: $Name"
    }
    catch {
        $script:failed++
        Write-Host "FAIL: $Name"
        Write-Host "  $($_.Exception.Message)"
    }
}

function Assert-True {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$Condition,

        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function New-SaveFixture {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $xml = @'
<?xml version="1.0" encoding="utf-8"?>
<SaveGame xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <locations>
    <GameLocation>
      <name>BusStop</name>
      <terrainFeatures>
        <item><key><Vector2><X>29</X><Y>17</Y></Vector2></key><value><TerrainFeature xsi:type="Tree"><treeType>FlashShifter.StardewValleyExpandedCP_Birch_Tree</treeType></TerrainFeature></value></item>
        <item><key><Vector2><X>30</X><Y>17</Y></Vector2></key><value><TerrainFeature xsi:type="FruitTree"><treeId>FlashShifter.StardewValleyExpandedCP_Pear_Tree</treeId></TerrainFeature></value></item>
        <item><key><Vector2><X>31</X><Y>17</Y></Vector2></key><value><TerrainFeature xsi:type="Tree"><treeType>2</treeType></TerrainFeature></value></item>
        <item><key><Vector2><X>32</X><Y>17</Y></Vector2></key><value><TerrainFeature xsi:type="Tree"><treeType>Other.Mod.Tree</treeType></TerrainFeature></value></item>
        <item><key><Vector2><X>33</X><Y>17</Y></Vector2></key><value><TerrainFeature xsi:type="Tree"><treeType>2</treeType><treeId>FlashShifter.StardewValleyExpandedCP_Hybrid_Tree</treeId></TerrainFeature></value></item>
      </terrainFeatures>
    </GameLocation>
    <GameLocation>
      <name>Forest</name>
      <terrainFeatures>
        <item><key><Vector2><X>40</X><Y>20</Y></Vector2></key><value><TerrainFeature xsi:type="Tree"><treeType>FlashShifter.StardewValleyExpandedCP_Maple_Tree</treeType></TerrainFeature></value></item>
      </terrainFeatures>
    </GameLocation>
  </locations>
</SaveGame>
'@

    [System.IO.File]::WriteAllText(
        $Path,
        $xml,
        [System.Text.UTF8Encoding]::new($false))
}

Invoke-TestCase 'sanitizer script exists' {
    Assert-True (Test-Path -LiteralPath $sanitizerPath -PathType Leaf) `
        "Missing sanitizer script: $sanitizerPath"
}

if ($script:failed -gt 0) {
    Write-Host "RESULT: passed=$($script:passed) failed=$($script:failed)"
    exit 1
}

$tempRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$tempDirectory = Join-Path $tempRoot ("stardew-ai-fasttest-sanitize-" + [guid]::NewGuid().ToString('N'))
[System.IO.Directory]::CreateDirectory($tempDirectory) | Out-Null

try {
    $prefix = 'FlashShifter.StardewValleyExpandedCP_'
    $dryRunPath = Join-Path $tempDirectory 'DryRunSave'
    $applyPath = Join-Path $tempDirectory 'ApplySave'
    New-SaveFixture -Path $dryRunPath
    New-SaveFixture -Path $applyPath

    Invoke-TestCase 'preview reports without changing the save' {
        $beforeHash = (Get-FileHash -LiteralPath $dryRunPath -Algorithm SHA256).Hash

        & $sanitizerPath -SavePath $dryRunPath -MissingModPrefix $prefix | Out-Null

        $afterHash = (Get-FileHash -LiteralPath $dryRunPath -Algorithm SHA256).Hash
        Assert-True ($beforeHash -eq $afterHash) 'Preview changed the save file.'
        $backups = @(Get-ChildItem -LiteralPath $tempDirectory -Filter 'DryRunSave.before-fasttest-sanitize-*.bak')
        Assert-True ($backups.Count -eq 0) 'Preview unexpectedly created a backup.'
    }

    Invoke-TestCase 'apply requires an explicit location scope' {
        $beforeHash = (Get-FileHash -LiteralPath $dryRunPath -Algorithm SHA256).Hash
        $threw = $false
        try {
            & $sanitizerPath -SavePath $dryRunPath -MissingModPrefix $prefix -Apply | Out-Null
        }
        catch {
            $threw = $true
        }

        $afterHash = (Get-FileHash -LiteralPath $dryRunPath -Algorithm SHA256).Hash
        Assert-True $threw 'Unscoped apply was accepted.'
        Assert-True ($beforeHash -eq $afterHash) 'Rejected unscoped apply changed the save.'
        $backups = @(Get-ChildItem -LiteralPath $tempDirectory -Filter 'DryRunSave.before-fasttest-sanitize-*.bak')
        Assert-True ($backups.Count -eq 0) 'Rejected unscoped apply created a backup.'
    }

    Invoke-TestCase 'apply removes only matching missing-mod terrain features and creates a verified backup' {
        $originalHash = (Get-FileHash -LiteralPath $applyPath -Algorithm SHA256).Hash

        & $sanitizerPath -SavePath $applyPath -MissingModPrefix $prefix -LocationName 'BusStop' -Apply | Out-Null

        $backups = @(Get-ChildItem -LiteralPath $tempDirectory -Filter 'ApplySave.before-fasttest-sanitize-*.bak')
        Assert-True ($backups.Count -eq 1) "Expected one backup, found $($backups.Count)."
        $backupHash = (Get-FileHash -LiteralPath $backups[0].FullName -Algorithm SHA256).Hash
        Assert-True ($backupHash -eq $originalHash) 'Backup hash does not match the original save.'

        $document = [System.Xml.XmlDocument]::new()
        $document.Load($applyPath)
        $ids = @(
            $document.SelectNodes('//terrainFeatures/item/value/TerrainFeature/treeType | //terrainFeatures/item/value/TerrainFeature/treeId') |
                ForEach-Object { $_.InnerText }
        )

        Assert-True ($ids.Count -eq 3) "Expected three preserved terrain features, found $($ids.Count)."
        Assert-True ($ids -contains '2') 'Vanilla tree was removed.'
        Assert-True ($ids -contains 'Other.Mod.Tree') 'A different mod tree was removed.'
        $busStopMatches = @(
            $document.SelectNodes('//GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeType | //GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeId') |
                ForEach-Object { $_.InnerText } |
                Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) }
        )
        $forestMatches = @(
            $document.SelectNodes('//GameLocation[name="Forest"]/terrainFeatures/item/value/TerrainFeature/treeType | //GameLocation[name="Forest"]/terrainFeatures/item/value/TerrainFeature/treeId') |
                ForEach-Object { $_.InnerText } |
                Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) }
        )
        Assert-True ($busStopMatches.Count -eq 0) 'A matching BusStop terrain feature remains.'
        Assert-True ($forestMatches.Count -eq 1) 'A matching terrain feature outside the requested location was removed.'
    }

    Invoke-TestCase 'second apply is idempotent and does not create another backup' {
        $beforeHash = (Get-FileHash -LiteralPath $applyPath -Algorithm SHA256).Hash

        & $sanitizerPath -SavePath $applyPath -MissingModPrefix $prefix -LocationName 'BusStop' -Apply | Out-Null

        $afterHash = (Get-FileHash -LiteralPath $applyPath -Algorithm SHA256).Hash
        $backups = @(Get-ChildItem -LiteralPath $tempDirectory -Filter 'ApplySave.before-fasttest-sanitize-*.bak')
        Assert-True ($beforeHash -eq $afterHash) 'Idempotent apply changed an already-clean save.'
        Assert-True ($backups.Count -eq 1) 'Idempotent apply created an unnecessary backup.'
    }

    Invoke-TestCase 'concurrent save change aborts before replacement and preserves the newer file' {
        $concurrentPath = Join-Path $tempDirectory 'ConcurrentSave'
        New-SaveFixture -Path $concurrentPath

        $global:StardewAiSanitizerHashCallCount = 0
        $global:StardewAiSanitizerMutationPath = $concurrentPath
        function global:Get-FileHash {
            param(
                [Parameter(Mandatory = $true)]
                [string]$LiteralPath,

                [string]$Algorithm = 'SHA256'
            )

            $result = Microsoft.PowerShell.Utility\Get-FileHash -LiteralPath $LiteralPath -Algorithm $Algorithm
            $global:StardewAiSanitizerHashCallCount++
            if ($global:StardewAiSanitizerHashCallCount -eq 2) {
                [System.IO.File]::AppendAllText(
                    $global:StardewAiSanitizerMutationPath,
                    '<!--concurrent-save-change-->',
                    [System.Text.UTF8Encoding]::new($false))
            }

            return $result
        }

        $threw = $false
        try {
            & $sanitizerPath -SavePath $concurrentPath -MissingModPrefix $prefix -LocationName 'BusStop' -Apply | Out-Null
        }
        catch {
            $threw = $true
        }
        finally {
            Remove-Item -Path 'Function:\Get-FileHash' -Force -ErrorAction SilentlyContinue
            Remove-Variable -Name StardewAiSanitizerHashCallCount -Scope Global -ErrorAction SilentlyContinue
            Remove-Variable -Name StardewAiSanitizerMutationPath -Scope Global -ErrorAction SilentlyContinue
        }

        $currentText = [System.IO.File]::ReadAllText($concurrentPath)
        Assert-True $threw 'Concurrent save mutation was not rejected.'
        Assert-True ($currentText.Contains('<!--concurrent-save-change-->')) `
            'The newer concurrent save content was overwritten.'

        $document = [System.Xml.XmlDocument]::new()
        $document.Load($concurrentPath)
        $busStopMatchingIds = @(
            $document.SelectNodes('//GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeType | //GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeId') |
                ForEach-Object { $_.InnerText } |
                Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) }
        )
        Assert-True ($busStopMatchingIds.Count -eq 3) `
            'The concurrent save was partially sanitized before the operation aborted.'
    }

    Invoke-TestCase 'save change before backup is included in the verified snapshot' {
        $preBackupPath = Join-Path $tempDirectory 'PreBackupConcurrentSave'
        New-SaveFixture -Path $preBackupPath

        & $sanitizerPath `
            -SavePath $preBackupPath `
            -MissingModPrefix $prefix `
            -LocationName 'BusStop' `
            -Apply `
            -TestSimulateSaveChangeBeforeBackup |
            Out-Null

        $currentText = [System.IO.File]::ReadAllText($preBackupPath)
        Assert-True ($currentText.Contains('<!--pre-backup-concurrent-save-change-->')) `
            'A save change made before the backup snapshot was lost.'

        $document = [System.Xml.XmlDocument]::new()
        $document.Load($preBackupPath)
        $busStopMatchingIds = @(
            $document.SelectNodes('//GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeType | //GameLocation[name="BusStop"]/terrainFeatures/item/value/TerrainFeature/treeId') |
                ForEach-Object { $_.InnerText } |
                Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) }
        )
        Assert-True ($busStopMatchingIds.Count -eq 0) `
            'The verified pre-backup snapshot was not sanitized.'

        $backups = @(Get-ChildItem -LiteralPath $tempDirectory -Filter 'PreBackupConcurrentSave.before-fasttest-sanitize-*.bak')
        Assert-True ($backups.Count -eq 1) "Expected one pre-backup snapshot, found $($backups.Count)."
        $backupText = [System.IO.File]::ReadAllText($backups[0].FullName)
        Assert-True ($backupText.Contains('<!--pre-backup-concurrent-save-change-->')) `
            'The verified backup did not capture the concurrent save change.'
    }
}
finally {
    $resolvedTempDirectory = [System.IO.Path]::GetFullPath($tempDirectory)
    if ($resolvedTempDirectory.StartsWith($tempRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedTempDirectory -Recurse -Force
    }
}

Write-Host "RESULT: passed=$($script:passed) failed=$($script:failed)"
if ($script:failed -gt 0) {
    exit 1
}
