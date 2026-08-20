param(
    [string]$OutputDirectory = "licenses"
)

$ErrorActionPreference = "Stop"
$buildTag = "20260807"
$baseUri = "https://raw.githubusercontent.com/astral-sh/python-build-standalone/$buildTag"
$files = [ordered]@{
    "LICENSE.libffi.txt" = "libffi-LICENSE.txt"
    "LICENSE.liblzma.txt" = "liblzma-LICENSE.txt"
    "LICENSE.mpdecimal.txt" = "libmpdec-LICENSE.txt"
    "LICENSE.openssl-3.txt" = "OpenSSL-3-LICENSE.txt"
}
$expectedHashes = @{
    "libffi-LICENSE.txt" = "DEAF3A42EFFB551A5B140FA9AFEFED183A27F1341C6D1BF430D106A5E6931FC0"
    "liblzma-LICENSE.txt" = "9A4062DE0A2C388A98CF35A35D348B62FA97C838A71C3C28EE1A2D7D0A565B02"
    "libmpdec-LICENSE.txt" = "669512AF7219F58BE03A398766D7C9DA11A3B3DF9D3F05CB74C5CECA25C8DA3B"
    "OpenSSL-3-LICENSE.txt" = "7D5450CB2D142651B8AFA315B5F238EFC805DAD827D91BA367D8516BC9D49E7A"
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
[System.IO.Directory]::CreateDirectory($resolvedOutput) | Out-Null
foreach ($entry in $files.GetEnumerator()) {
    $uri = "$baseUri/$($entry.Key)"
    $destination = Join-Path $resolvedOutput $entry.Value
    Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $destination
    if ((Get-Item -LiteralPath $destination).Length -lt 500) {
        throw "Downloaded license file is unexpectedly short: $uri"
    }
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $destination).Hash
    if ($hash -ne $expectedHashes[$entry.Value]) {
        throw "Downloaded license hash changed for $uri`: $hash"
    }
    Write-Host "Downloaded $uri -> $destination"
}

$unicodeUri = "https://www.unicode.org/license.txt"
$unicodeDestination = Join-Path $resolvedOutput "Unicode-3.0-LICENSE.txt"
Invoke-WebRequest -UseBasicParsing -Uri $unicodeUri -OutFile $unicodeDestination
if ((Get-Item -LiteralPath $unicodeDestination).Length -lt 500) {
    throw "Downloaded Unicode license file is unexpectedly short: $unicodeUri"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $unicodeDestination).Hash -ne "E7A93B009565CFCE55919A381437AC4DB883E9DA2126FA28B91D12732BC53D96") {
    throw "Downloaded Unicode license hash changed."
}
Write-Host "Downloaded $unicodeUri -> $unicodeDestination"

# The standalone runtime and PySide wheels carry the Microsoft VC runtime.
$microsoftUri = "https://visualstudio.microsoft.com/wp-content/uploads/2021/09/Visual-C-Runtime-2015-2022-License-1.docx"
$microsoftDestination = Join-Path $resolvedOutput "Microsoft-Visual-C-Runtime-2015-2022-License.docx"
Invoke-WebRequest -UseBasicParsing -Uri $microsoftUri -OutFile $microsoftDestination
if ((Get-Item -LiteralPath $microsoftDestination).Length -lt 5000) {
    throw "Downloaded Microsoft license file is unexpectedly short: $microsoftUri"
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $microsoftDestination).Hash -ne "F1E3D56CEB2AD68AAE0711B910375009E651AC5530FA0760F0DEA6E81E54FAE1") {
    throw "Downloaded Microsoft runtime license hash changed."
}
Write-Host "Downloaded $microsoftUri -> $microsoftDestination"
