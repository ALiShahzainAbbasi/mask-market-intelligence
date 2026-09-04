$ErrorActionPreference = "Stop"

$version = "8.28.0"
$archiveName = "gitleaks_${version}_windows_x64.zip"
$releaseBase = "https://github.com/gitleaks/gitleaks/releases/download/v${version}"
$scanRoot = Join-Path ([IO.Path]::GetTempPath()) ("mask-gitleaks-" + [Guid]::NewGuid().ToString("N"))
$archivePath = Join-Path $scanRoot $archiveName
$checksumsPath = Join-Path $scanRoot "checksums.txt"
$extractPath = Join-Path $scanRoot "gitleaks"

New-Item -ItemType Directory -Path $scanRoot | Out-Null

try {
    Invoke-WebRequest -Uri "$releaseBase/$archiveName" -OutFile $archivePath -MaximumRedirection 5
    Invoke-WebRequest -Uri "$releaseBase/gitleaks_${version}_checksums.txt" -OutFile $checksumsPath -MaximumRedirection 5

    $archivePattern = "^[0-9a-fA-F]{64}\s+\*?" + [Regex]::Escape($archiveName) + "\s*$"
    $checksumLine = Select-String -Path $checksumsPath -Pattern $archivePattern | Select-Object -First 1
    if ($null -eq $checksumLine) {
        throw "The release checksum manifest does not contain the expected Windows archive."
    }

    $expectedHash = ($checksumLine.Line -split "\s+")[0].ToLowerInvariant()
    $actualHash = (Get-FileHash -Path $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $expectedHash) {
        throw "The downloaded Gitleaks archive failed SHA-256 verification."
    }

    New-Item -ItemType Directory -Path $extractPath | Out-Null
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractPath
    $gitleaksPath = Join-Path $extractPath "gitleaks.exe"
    if (-not (Test-Path -LiteralPath $gitleaksPath -PathType Leaf)) {
        throw "The verified archive did not contain gitleaks.exe."
    }

    & $gitleaksPath detect --no-git --source . --redact --config .gitleaks.toml
    if ($LASTEXITCODE -ne 0) {
        throw "Gitleaks reported a source-secret finding or scan failure."
    }
}
finally {
    $resolvedScanRoot = [IO.Path]::GetFullPath($scanRoot)
    $resolvedTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd("\") + "\"
    $isTaskTemp = (Split-Path -Leaf $resolvedScanRoot).StartsWith("mask-gitleaks-")
    if ($isTaskTemp -and $resolvedScanRoot.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedScanRoot -Recurse -Force
    }
}
