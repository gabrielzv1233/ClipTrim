$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)] [string]$FilePath,
        [Parameter(Mandatory)] [string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE."
    }
}

function Get-Sha256 {
    param([Parameter(Mandatory)] [string]$Path)

    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "")
    }
    finally {
        $stream.Dispose()
        $algorithm.Dispose()
    }
}

function Initialize-BuildEnvironment {
    param(
        [Parameter(Mandatory)] [string]$RepositoryRoot,
        [Parameter(Mandatory)] [string]$PythonExecutable,
        [Parameter(Mandatory)] [hashtable]$Versions
    )

    if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
        throw "Missing .venv. Run setup.bat first."
    }

    Push-Location $RepositoryRoot
    try {
        Invoke-CheckedCommand "uv" @("sync", "--locked", "--python", $Versions.Python, "--managed-python")

        $runtimeCheck = @"
import _decimal, ssl, sys, unicodedata
from pathlib import Path
assert '.'.join(map(str, sys.version_info[:3])) == '$($Versions.Python)', sys.version
assert Path(sys.base_prefix, 'BUILD').read_text().strip() == '$($Versions.PythonBuild)'
assert ssl.OPENSSL_VERSION == 'OpenSSL 3.5.7 9 Jun 2026', ssl.OPENSSL_VERSION
assert _decimal.__libmpdec_version__ == '4.0.0'
assert unicodedata.unidata_version == '16.0.0'
"@
        Invoke-CheckedCommand $PythonExecutable @("-c", $runtimeCheck)

        $packageCheck = @"
import importlib.metadata as metadata
expected = {
    'PySide6': '$($Versions.PySide)',
    'PySide6-Essentials': '$($Versions.PySide)',
    'PySide6-Addons': '$($Versions.PySide)',
    'shiboken6': '$($Versions.PySide)',
    'Nuitka': '$($Versions.Nuitka)',
}
actual = {name: metadata.version(name) for name in expected}
assert actual == expected, actual
"@
        Invoke-CheckedCommand $PythonExecutable @("-c", $packageCheck)
    }
    finally {
        Pop-Location
    }
}

function Get-ValidatedFfmpeg {
    param([Parameter(Mandatory)] [hashtable]$ExpectedHashes)

    $ffmpegPath = (Get-Command "ffmpeg.exe" -ErrorAction Stop).Source
    $ffprobePath = (Get-Command "ffprobe.exe" -ErrorAction Stop).Source
    $ffmpegBin = Split-Path $ffmpegPath -Parent
    $ffprobeBin = Split-Path $ffprobePath -Parent
    if ($ffmpegBin -ne $ffprobeBin) {
        throw "FFmpeg and FFprobe must come from the same bin directory."
    }

    $root = [System.IO.Path]::GetFullPath((Join-Path $ffmpegBin ".."))
    if (-not (Test-Path -LiteralPath (Join-Path $root "LICENSE") -PathType Leaf)) {
        throw "The FFmpeg distributor LICENSE file was not found in $root."
    }

    $actualFfmpeg = Get-Sha256 $ffmpegPath
    $actualFfprobe = Get-Sha256 $ffprobePath
    if ($actualFfmpeg -ne $ExpectedHashes.Ffmpeg -or $actualFfprobe -ne $ExpectedHashes.Ffprobe) {
        throw "FFmpeg or FFprobe does not match the binaries documented by the notices."
    }

    [pscustomobject]@{
        FfmpegPath = $ffmpegPath
        FfprobePath = $ffprobePath
        Root = $root
    }
}

function Get-ZigToolchain {
    $cacheRoot = Join-Path $env:LOCALAPPDATA "Nuitka\Nuitka\Cache\downloads\pip"
    $executable = Get-ChildItem -LiteralPath $cacheRoot -Filter "zig.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
    if (-not $executable) {
        throw "Nuitka's Zig compiler was not found; the root launcher cannot be built."
    }

    $root = Split-Path $executable -Parent
    if (-not (Test-Path -LiteralPath (Join-Path $root "lib\libc\mingw\COPYING") -PathType Leaf)) {
        throw "mingw-w64 COPYING was not found in the Zig toolchain."
    }

    [pscustomobject]@{
        Executable = $executable
        Root = $root
    }
}

Export-ModuleMember -Function Initialize-BuildEnvironment, Get-ValidatedFfmpeg, Get-ZigToolchain
