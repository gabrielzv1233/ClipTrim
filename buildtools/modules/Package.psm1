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

function New-ClipTrimLauncher {
    param(
        [Parameter(Mandatory)] [string]$RepositoryRoot,
        [Parameter(Mandatory)] [string]$BuildRoot,
        [Parameter(Mandatory)] [string]$DistributionDirectory,
        [Parameter(Mandatory)] [psobject]$Zig
    )

    $resource = Join-Path $BuildRoot "nuitka\cliptrim_launcher.res"
    Invoke-CheckedCommand $Zig.Executable @(
        "rc", "/fo", $resource,
        (Join-Path $RepositoryRoot "buildtools\cliptrim_launcher.rc")
    )
    Invoke-CheckedCommand $Zig.Executable @(
        "cc", "-target", "x86_64-windows-gnu", "-std=c11", "-Os", "-s",
        (Join-Path $RepositoryRoot "buildtools\cliptrim_launcher.c"),
        $resource,
        "-lshell32", "-luser32", "-Wl,--subsystem,windows",
        "-o", (Join-Path $DistributionDirectory "ClipTrim.exe")
    )
}

function Test-ClipTrimRuntime {
    param([Parameter(Mandatory)] [string]$DistributionDirectory)

    $launcher = Join-Path $DistributionDirectory "ClipTrim.exe"
    $runtime = Join-Path $DistributionDirectory "runtime"
    if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) {
        throw "The root ClipTrim executable was not created."
    }

    $pluginRoot = Join-Path $runtime "PySide6\qt-plugins"
    $allowedPlugins = @(
        "imageformats/qjpeg.dll",
        "multimedia/windowsmediaplugin.dll",
        "platforms/qwindows.dll",
        "styles/qmodernwindowsstyle.dll"
    )
    $actualPlugins = Get-ChildItem -LiteralPath $pluginRoot -File -Recurse | ForEach-Object {
        $_.FullName.Substring($pluginRoot.Length).TrimStart('\', '/').Replace('\', '/').ToLowerInvariant()
    }
    $difference = Compare-Object ($allowedPlugins | Sort-Object) ($actualPlugins | Sort-Object)
    if ($difference) {
        throw "The packaged Qt plugin set does not match the expected minimal runtime."
    }

    $excludedPatterns = @(
        "avcodec-*.dll", "avformat-*.dll", "avutil-*.dll", "swresample-*.dll", "swscale-*.dll",
        "qt6pdf*.dll", "qt6svg*.dll", "qtpdf*.pyd", "qtsvg*.pyd"
    )
    $unexpected = Get-ChildItem -LiteralPath $runtime -File -Recurse | Where-Object {
        $name = $_.Name.ToLowerInvariant()
        $excludedPatterns | Where-Object { $name -like $_ }
    }
    if ($unexpected) {
        throw "An excluded Qt/FFmpeg runtime was packaged: $($unexpected.FullName -join ', ')"
    }
}

function Initialize-ClipTrimPackage {
    param(
        [Parameter(Mandatory)] [string]$RepositoryRoot,
        [Parameter(Mandatory)] [string]$DistributionDirectory,
        [Parameter(Mandatory)] [psobject]$Ffmpeg
    )

    $staging = Join-Path $RepositoryRoot "build\nuitka"
    if (Test-Path -LiteralPath $staging) {
        Remove-Item -LiteralPath $staging -Recurse -Force
    }

    $bin = Join-Path $DistributionDirectory "bin"
    New-Item -ItemType Directory -Path $bin -Force | Out-Null
    New-Item -ItemType Directory -Path (Join-Path $DistributionDirectory "config") -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $RepositoryRoot "buildtools\icon.ico") -Destination (Join-Path $DistributionDirectory "icon.ico")
    Copy-Item -LiteralPath $Ffmpeg.FfmpegPath -Destination (Join-Path $bin "ffmpeg.exe")
    Copy-Item -LiteralPath $Ffmpeg.FfprobePath -Destination (Join-Path $bin "ffprobe.exe")
}

Export-ModuleMember -Function New-ClipTrimLauncher, Test-ClipTrimRuntime, Initialize-ClipTrimPackage
