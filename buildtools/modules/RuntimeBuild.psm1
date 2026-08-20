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

function New-ClipTrimRuntime {
    param(
        [Parameter(Mandatory)] [string]$RepositoryRoot,
        [Parameter(Mandatory)] [string]$BuildRoot,
        [Parameter(Mandatory)] [string]$PythonExecutable
    )

    $buildTools = Join-Path $RepositoryRoot "buildtools"
    $icon = Join-Path $buildTools "icon.ico"
    Invoke-CheckedCommand $PythonExecutable @(
        (Join-Path $buildTools "build_icon.py"),
        (Join-Path $RepositoryRoot "icon.svg"),
        $icon
    )

    if (Test-Path -LiteralPath $BuildRoot) {
        $resolvedBuild = [System.IO.Path]::GetFullPath($BuildRoot)
        $resolvedRepository = [System.IO.Path]::GetFullPath($RepositoryRoot) + [System.IO.Path]::DirectorySeparatorChar
        if (-not $resolvedBuild.StartsWith($resolvedRepository, [System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove build directory outside the repository: $resolvedBuild"
        }
        Remove-Item -LiteralPath $resolvedBuild -Recurse -Force
    }

    $staging = Join-Path $BuildRoot "nuitka"
    New-Item -ItemType Directory -Path $staging -Force | Out-Null
    $arguments = @(
        "-m", "nuitka",
        "--mode=standalone",
        "--enable-plugin=pyside6",
        "--include-qt-plugins=multimedia",
        "--noinclude-qt-plugins=iconengines",
        "--noinclude-qt-plugins=tls",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qgif.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qicns.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qico.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qpdf.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qsvg.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qtga.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qtiff.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qwbmp.dll",
        "--noinclude-dlls=PySide6/qt-plugins/imageformats/qwebp.dll",
        "--noinclude-dlls=PySide6/qt-plugins/multimedia/ffmpegmediaplugin.dll",
        "--noinclude-dlls=PySide6/qt-plugins/platforms/qdirect2d.dll",
        "--noinclude-dlls=PySide6/qt-plugins/platforms/qminimal.dll",
        "--noinclude-dlls=PySide6/qt-plugins/platforms/qoffscreen.dll",
        "--noinclude-dlls=avcodec-*.dll",
        "--noinclude-dlls=avformat-*.dll",
        "--noinclude-dlls=avutil-*.dll",
        "--noinclude-dlls=swresample-*.dll",
        "--noinclude-dlls=swscale-*.dll",
        "--noinclude-dlls=qt6pdf.dll",
        "--noinclude-dlls=qt6svg.dll",
        "--windows-console-mode=attach",
        "--assume-yes-for-downloads",
        "--output-dir=$staging",
        "--output-filename=ClipTrim.runtime.exe",
        "--windows-icon-from-ico=$icon",
        (Join-Path $RepositoryRoot "cliptrim.py")
    )

    Write-Host "Building ClipTrim."
    Push-Location $RepositoryRoot
    try {
        Invoke-CheckedCommand $PythonExecutable $arguments
    }
    finally {
        Pop-Location
    }

    $nuitkaDistribution = Join-Path $staging "cliptrim.dist"
    $runtimeExecutable = Join-Path $nuitkaDistribution "ClipTrim.runtime.exe"
    if (-not (Test-Path -LiteralPath $runtimeExecutable -PathType Leaf)) {
        throw "Nuitka completed but ClipTrim.runtime.exe was not created."
    }

    $distribution = Join-Path $BuildRoot "ClipTrim"
    New-Item -ItemType Directory -Path $distribution -Force | Out-Null
    Move-Item -LiteralPath $nuitkaDistribution -Destination (Join-Path $distribution "runtime")
}

Export-ModuleMember -Function New-ClipTrimRuntime
