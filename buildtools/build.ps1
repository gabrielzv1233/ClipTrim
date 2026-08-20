$ErrorActionPreference = "Stop"

$repositoryRoot = Split-Path $PSScriptRoot -Parent
$modules = Join-Path $PSScriptRoot "modules"
Import-Module (Join-Path $modules "Dependencies.psm1") -Force
Import-Module (Join-Path $modules "RuntimeBuild.psm1") -Force
Import-Module (Join-Path $modules "Package.psm1") -Force
Import-Module (Join-Path $modules "LegalFiles.psm1") -Force

$versions = @{
    Python = "3.14.7"
    PythonBuild = "20260807"
    PySide = "6.11.2"
    Nuitka = "4.1.3"
}
$ffmpegHashes = @{
    Ffmpeg = "05F4251BCE9293C2AB492CB17CA7724A0FFD0D06C881BA2EE83B82A89C2FC740"
    Ffprobe = "51E0780CD881F83749B029ED716CBB841C2EAC6289F418050F2F2961B158896B"
}

$python = Join-Path $repositoryRoot ".venv\Scripts\python.exe"
$buildRoot = Join-Path $repositoryRoot "build"
$distribution = Join-Path $buildRoot "ClipTrim"

try {
    Initialize-BuildEnvironment -RepositoryRoot $repositoryRoot -PythonExecutable $python -Versions $versions
    $ffmpeg = Get-ValidatedFfmpeg -ExpectedHashes $ffmpegHashes

    New-ClipTrimRuntime -RepositoryRoot $repositoryRoot -BuildRoot $buildRoot -PythonExecutable $python
    $zig = Get-ZigToolchain
    New-ClipTrimLauncher -RepositoryRoot $repositoryRoot -BuildRoot $buildRoot -DistributionDirectory $distribution -Zig $zig
    Test-ClipTrimRuntime -DistributionDirectory $distribution

    Initialize-ClipTrimPackage -RepositoryRoot $repositoryRoot -DistributionDirectory $distribution -Ffmpeg $ffmpeg
    Copy-ClipTrimLegalFiles -RepositoryRoot $repositoryRoot -DistributionDirectory $distribution -PythonExecutable $python -Versions $versions -Ffmpeg $ffmpeg -Zig $zig

    Write-Host ""
    Write-Host "EXE: $(Join-Path $distribution 'ClipTrim.exe')"
}
catch {
    Write-Error $_
    exit 1
}
