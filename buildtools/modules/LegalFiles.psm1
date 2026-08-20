$ErrorActionPreference = "Stop"

function Copy-RequiredFile {
    param(
        [Parameter(Mandatory)] [string]$Source,
        [Parameter(Mandatory)] [string]$Destination
    )

    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Required legal file was not found: $Source"
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-ClipTrimLegalFiles {
    param(
        [Parameter(Mandatory)] [string]$RepositoryRoot,
        [Parameter(Mandatory)] [string]$DistributionDirectory,
        [Parameter(Mandatory)] [string]$PythonExecutable,
        [Parameter(Mandatory)] [hashtable]$Versions,
        [Parameter(Mandatory)] [psobject]$Ffmpeg,
        [Parameter(Mandatory)] [psobject]$Zig
    )

    $sourceLicenses = Join-Path $RepositoryRoot "licenses"
    $legalRoot = Join-Path $DistributionDirectory "legal"
    $packagedLicenses = Join-Path $legalRoot "licenses"
    New-Item -ItemType Directory -Path $packagedLicenses -Force | Out-Null
    Copy-Item -Path (Join-Path $sourceLicenses "*") -Destination $packagedLicenses -Recurse -Force
    Copy-RequiredFile (Join-Path $RepositoryRoot "LICENSE") (Join-Path $legalRoot "LICENSE")
    Copy-RequiredFile (Join-Path $RepositoryRoot "THIRD_PARTY_NOTICES.md") (Join-Path $legalRoot "THIRD_PARTY_NOTICES.md")

    $pythonLicense = & $PythonExecutable -c "import sys; from pathlib import Path; print(Path(sys.base_prefix) / 'LICENSE.txt')"
    if ($LASTEXITCODE -ne 0 -or -not $pythonLicense) {
        throw "Could not locate the CPython license file."
    }
    Copy-RequiredFile $pythonLicense (Join-Path $packagedLicenses "CPython-$($Versions.Python)-LICENSE.txt")

    $nuitkaLicenseDirectory = & $PythonExecutable -c "import importlib.metadata as m; from pathlib import Path; d=m.distribution('Nuitka'); print(next(Path(d.locate_file(p)).parent for p in d.files if p.name == 'LICENSE-RUNTIME.txt'))"
    if ($LASTEXITCODE -ne 0 -or -not $nuitkaLicenseDirectory) {
        throw "Could not locate Nuitka's legal files."
    }
    Copy-RequiredFile (Join-Path $nuitkaLicenseDirectory "LICENSE.txt") (Join-Path $packagedLicenses "Nuitka-$($Versions.Nuitka)-LICENSE.txt")
    Copy-RequiredFile (Join-Path $nuitkaLicenseDirectory "LICENSE-RUNTIME.txt") (Join-Path $packagedLicenses "Nuitka-$($Versions.Nuitka)-LICENSE-RUNTIME.txt")
    Copy-RequiredFile (Join-Path $nuitkaLicenseDirectory "NOTICE.txt") (Join-Path $packagedLicenses "Nuitka-$($Versions.Nuitka)-NOTICE.txt")

    Copy-RequiredFile (Join-Path $Ffmpeg.Root "LICENSE") (Join-Path $packagedLicenses "FFmpeg-9.0-LICENSE.txt")
    Copy-RequiredFile (Join-Path $Zig.Root "lib\libc\mingw\COPYING") (Join-Path $packagedLicenses "mingw-w64-COPYING.txt")

    $count = (Get-ChildItem -LiteralPath $packagedLicenses -File -Recurse).Count
    Write-Host "Packaged $count legal files in $packagedLicenses"
}

Export-ModuleMember -Function Copy-ClipTrimLegalFiles
