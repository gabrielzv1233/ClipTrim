param(
    [Parameter(Mandatory = $true)]
    [string]$DistributionDirectory,

    [Parameter(Mandatory = $true)]
    [string]$PythonExecutable,

    [Parameter(Mandatory = $true)]
    [string]$PythonVersion,

    [Parameter(Mandatory = $true)]
    [string]$NuitkaVersion,

    [Parameter(Mandatory = $true)]
    [string]$FfmpegRoot,

    [Parameter(Mandatory = $true)]
    [string]$ZigRoot
)

$ErrorActionPreference = "Stop"
$repositoryRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$distributionRoot = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot $DistributionDirectory))
$sourceLicenses = Join-Path $repositoryRoot "licenses"
$packagedLicenses = Join-Path $distributionRoot "licenses"

function Copy-LegalFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Source,

        [Parameter(Mandatory = $true)]
        [string]$DestinationName
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required legal file was not found: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination (Join-Path $packagedLicenses $DestinationName) -Force
}

if (-not (Test-Path -LiteralPath $sourceLicenses -PathType Container)) {
    throw "Committed licenses directory was not found: $sourceLicenses"
}

New-Item -ItemType Directory -Path $packagedLicenses -Force | Out-Null
Copy-Item -Path (Join-Path $sourceLicenses "*") -Destination $packagedLicenses -Recurse -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "LICENSE") -Destination $distributionRoot -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot "THIRD_PARTY_NOTICES.md") -Destination $distributionRoot -Force

$pythonLicense = & $PythonExecutable -c "import sys; from pathlib import Path; print(Path(sys.base_prefix) / 'LICENSE.txt')"
if ($LASTEXITCODE -ne 0 -or -not $pythonLicense) {
    throw "Could not locate the CPython license file."
}
Copy-LegalFile $pythonLicense "CPython-$PythonVersion-LICENSE.txt"

$nuitkaLicenseDirectory = & $PythonExecutable -c "import importlib.metadata as m; from pathlib import Path; d=m.distribution('Nuitka'); print(next(Path(d.locate_file(p)).parent for p in d.files if p.name == 'LICENSE-RUNTIME.txt'))"
if ($LASTEXITCODE -ne 0 -or -not $nuitkaLicenseDirectory) {
    throw "Could not locate Nuitka's legal files."
}
Copy-LegalFile (Join-Path $nuitkaLicenseDirectory "LICENSE.txt") "Nuitka-$NuitkaVersion-LICENSE.txt"
Copy-LegalFile (Join-Path $nuitkaLicenseDirectory "LICENSE-RUNTIME.txt") "Nuitka-$NuitkaVersion-LICENSE-RUNTIME.txt"
Copy-LegalFile (Join-Path $nuitkaLicenseDirectory "NOTICE.txt") "Nuitka-$NuitkaVersion-NOTICE.txt"

Copy-LegalFile (Join-Path $FfmpegRoot "LICENSE") "FFmpeg-9.0-LICENSE.txt"
Copy-LegalFile (Join-Path $FfmpegRoot "README.txt") "FFmpeg-9.0-README.txt"
Copy-LegalFile (Join-Path $ZigRoot "lib\libc\mingw\COPYING") "mingw-w64-COPYING.txt"

# Every committed file is expected to survive the bulk copy. Only files sourced
# from the selected build environment need an explicit list here.
$committedFiles = Get-ChildItem -LiteralPath $sourceLicenses -File -Recurse
foreach ($file in $committedFiles) {
    $relativePath = $file.FullName.Substring($sourceLicenses.Length).TrimStart('\', '/')
    if (-not (Test-Path -LiteralPath (Join-Path $packagedLicenses $relativePath) -PathType Leaf)) {
        throw "Committed legal file was not packaged: $relativePath"
    }
}

$generatedFiles = @(
    "CPython-$PythonVersion-LICENSE.txt",
    "Nuitka-$NuitkaVersion-LICENSE.txt",
    "Nuitka-$NuitkaVersion-LICENSE-RUNTIME.txt",
    "Nuitka-$NuitkaVersion-NOTICE.txt",
    "FFmpeg-9.0-LICENSE.txt",
    "FFmpeg-9.0-README.txt",
    "mingw-w64-COPYING.txt"
)
foreach ($name in $generatedFiles) {
    if (-not (Test-Path -LiteralPath (Join-Path $packagedLicenses $name) -PathType Leaf)) {
        throw "Generated legal file was not packaged: $name"
    }
}

Write-Host "Packaged $($committedFiles.Count + $generatedFiles.Count) legal files in $packagedLicenses"
