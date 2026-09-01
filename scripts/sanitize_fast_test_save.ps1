[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SavePath,

    [string]$MissingModPrefix = 'FlashShifter.StardewValleyExpandedCP_',

    [string]$LocationName,

    [switch]$Apply,

    [Parameter(DontShow = $true)]
    [switch]$TestSimulateSaveChangeBeforeBackup
)

$ErrorActionPreference = 'Stop'

function Get-MatchingTerrainFeatures {
    param(
        [Parameter(Mandatory = $true)]
        [System.Xml.XmlDocument]$Document,

        [Parameter(Mandatory = $true)]
        [string]$Prefix,

        [AllowNull()]
        [string]$Location
    )

    $matches = [System.Collections.Generic.List[System.Xml.XmlNode]]::new()
    foreach ($item in $Document.SelectNodes('//terrainFeatures/item')) {
        $idNodes = @(
            $item.SelectNodes('./value/TerrainFeature/treeType | ./value/TerrainFeature/treeId')
        )
        $hasMatchingId = @(
            $idNodes | Where-Object {
                $_.InnerText.StartsWith($Prefix, [System.StringComparison]::Ordinal)
            }
        ).Count -gt 0

        $locationNode = $item.SelectSingleNode('ancestor::GameLocation[1]/name')
        $isRequestedLocation = [string]::IsNullOrWhiteSpace($Location) -or (
            $null -ne $locationNode -and
            [string]::Equals($locationNode.InnerText, $Location, [System.StringComparison]::OrdinalIgnoreCase))

        if (
            $isRequestedLocation -and
            $hasMatchingId) {
            $matches.Add($item)
        }
    }

    return $matches.ToArray()
}

$saveItem = Get-Item -LiteralPath $SavePath -ErrorAction Stop
if ($saveItem.PSIsContainer) {
    throw "SavePath must name the main save XML file, not a directory: $SavePath"
}

if ([string]::IsNullOrWhiteSpace($MissingModPrefix)) {
    throw 'MissingModPrefix cannot be empty.'
}

if ($Apply -and [string]::IsNullOrWhiteSpace($LocationName)) {
    throw 'Applying save changes requires an explicit -LocationName scope.'
}

$resolvedSavePath = [System.IO.Path]::GetFullPath($saveItem.FullName)
$document = [System.Xml.XmlDocument]::new()
$document.PreserveWhitespace = $true
$document.Load($resolvedSavePath)

$matches = @(Get-MatchingTerrainFeatures -Document $document -Prefix $MissingModPrefix -Location $LocationName)
$locationScope = if ([string]::IsNullOrWhiteSpace($LocationName)) { '<all-preview>' } else { $LocationName }
Write-Host "FastTest save scan: matches=$($matches.Count) prefix=$MissingModPrefix location=$locationScope"

foreach ($group in ($matches | Group-Object {
    $locationNode = $_.SelectSingleNode('ancestor::GameLocation[1]/name')
    if ($null -eq $locationNode) { '<unknown>' } else { $locationNode.InnerText }
} | Sort-Object Name)) {
    Write-Host "  location=$($group.Name) matches=$($group.Count)"
}

$detailLimit = 20
foreach ($match in @($matches | Select-Object -First $detailLimit)) {
    $location = $match.SelectSingleNode('ancestor::GameLocation[1]/name').InnerText
    $x = $match.SelectSingleNode('./key/Vector2/X').InnerText
    $y = $match.SelectSingleNode('./key/Vector2/Y').InnerText
    $matchingIds = @(
        $match.SelectNodes('./value/TerrainFeature/treeType | ./value/TerrainFeature/treeId') |
            ForEach-Object { $_.InnerText } |
            Where-Object { $_.StartsWith($MissingModPrefix, [System.StringComparison]::Ordinal) }
    )
    Write-Host "    location=$location tile=($x,$y) id=$($matchingIds -join ',')"
}
if ($matches.Count -gt $detailLimit) {
    Write-Host "    ... omitted=$($matches.Count - $detailLimit)"
}

if ($matches.Count -eq 0) {
    Write-Host 'Save is already clean; no file was changed.'
    return
}

if (-not $Apply) {
    Write-Host 'Preview only; pass -Apply to create a verified backup and remove these entries.'
    return
}

$timestamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$backupPath = "$resolvedSavePath.before-fasttest-sanitize-$timestamp.bak"
if ($TestSimulateSaveChangeBeforeBackup) {
    [System.IO.File]::AppendAllText(
        $resolvedSavePath,
        '<!--pre-backup-concurrent-save-change-->',
        [System.Text.UTF8Encoding]::new($false))
}
Copy-Item -LiteralPath $resolvedSavePath -Destination $backupPath

$backupHash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash
$currentHashAfterBackup = (Get-FileHash -LiteralPath $resolvedSavePath -Algorithm SHA256).Hash
if ($currentHashAfterBackup -ne $backupHash) {
    throw "Backup verification failed: current=$currentHashAfterBackup backup=$backupHash"
}
$originalHash = $backupHash

# The verified backup is the only snapshot whose bytes are tied to
# $originalHash. Reload it so an external save between the preview Load and
# Copy-Item can never leave us writing an older in-memory document.
$verifiedDocument = [System.Xml.XmlDocument]::new()
$verifiedDocument.PreserveWhitespace = $true
$verifiedDocument.Load($backupPath)
$verifiedMatches = @(
    Get-MatchingTerrainFeatures `
        -Document $verifiedDocument `
        -Prefix $MissingModPrefix `
        -Location $LocationName
)
$document = $verifiedDocument
$matches = $verifiedMatches
Write-Host "Verified backup snapshot: matches=$($matches.Count) location=$LocationName"
if ($matches.Count -eq 0) {
    Write-Host "The verified backup no longer contains matching entries; no replacement was performed. Backup retained at: $backupPath"
    return
}

foreach ($match in $matches) {
    [void]$match.ParentNode.RemoveChild($match)
}

$operationId = [guid]::NewGuid().ToString('N')
$temporaryPath = "$resolvedSavePath.fasttest-sanitize-$operationId.tmp"
$replacementBackupPath = "$resolvedSavePath.fasttest-replace-backup-$operationId.tmp"
$rejectedSanitizedPath = "$resolvedSavePath.fasttest-rejected-sanitized-$operationId.tmp"
$replacementBackupCanDelete = $false
$rejectedSanitizedCanDelete = $false
try {
    $settings = [System.Xml.XmlWriterSettings]::new()
    $settings.Encoding = [System.Text.UTF8Encoding]::new($false)
    $settings.Indent = $false
    $settings.NewLineHandling = [System.Xml.NewLineHandling]::None

    $writer = [System.Xml.XmlWriter]::Create($temporaryPath, $settings)
    try {
        $document.Save($writer)
    }
    finally {
        $writer.Dispose()
    }

    $validationDocument = [System.Xml.XmlDocument]::new()
    $validationDocument.Load($temporaryPath)
    $remainingMatches = @(
        Get-MatchingTerrainFeatures -Document $validationDocument -Prefix $MissingModPrefix -Location $LocationName
    )
    if ($remainingMatches.Count -ne 0) {
        throw "Sanitized save validation failed: $($remainingMatches.Count) matching entries remain."
    }

    $currentHash = (Get-FileHash -LiteralPath $resolvedSavePath -Algorithm SHA256).Hash
    if ($currentHash -ne $originalHash) {
        throw "Save changed after backup; refusing to overwrite newer data: expected=$originalHash actual=$currentHash"
    }

    [System.IO.File]::Replace($temporaryPath, $resolvedSavePath, $replacementBackupPath, $true)

    $replacementBackupHash = (Get-FileHash -LiteralPath $replacementBackupPath -Algorithm SHA256).Hash
    if ($replacementBackupHash -ne $originalHash) {
        try {
            [System.IO.File]::Replace(
                $replacementBackupPath,
                $resolvedSavePath,
                $rejectedSanitizedPath,
                $true)
        }
        catch {
            throw "Save changed during atomic replacement. Recovery copy preserved at '$replacementBackupPath'. $($_.Exception.Message)"
        }

        $restoredHash = (Get-FileHash -LiteralPath $resolvedSavePath -Algorithm SHA256).Hash
        if ($restoredHash -ne $replacementBackupHash) {
            throw "Concurrent save rollback verification failed: expected=$replacementBackupHash actual=$restoredHash"
        }

        $rejectedSanitizedCanDelete = $true
        throw "Save changed during atomic replacement; the newer file was restored and sanitization was aborted."
    }

    $replacementBackupCanDelete = $true
}
finally {
    if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
        Remove-Item -LiteralPath $temporaryPath -Force
    }

    if ($replacementBackupCanDelete -and (Test-Path -LiteralPath $replacementBackupPath -PathType Leaf)) {
        Remove-Item -LiteralPath $replacementBackupPath -Force
    }

    if ($rejectedSanitizedCanDelete -and (Test-Path -LiteralPath $rejectedSanitizedPath -PathType Leaf)) {
        Remove-Item -LiteralPath $rejectedSanitizedPath -Force
    }
}

$newHash = (Get-FileHash -LiteralPath $resolvedSavePath -Algorithm SHA256).Hash
Write-Host "Sanitized FastTest save: removed=$($matches.Count)"
Write-Host "Backup: $backupPath"
Write-Host "Original/backup SHA256: $originalHash"
Write-Host "Sanitized SHA256: $newHash"
