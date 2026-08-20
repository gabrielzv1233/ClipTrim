@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

set "BUILD_ROOT=build"
set "STAGING=%BUILD_ROOT%\nuitka"
set "NUITKA_DIST=%STAGING%\cliptrim.dist"
set "DIST=%BUILD_ROOT%\ClipTrim"
set "PYTHON_VERSION=3.14.7"
set "PYTHON_STANDALONE_BUILD=20260807"
set "PYSIDE_VERSION=6.11.2"
set "NUITKA_VERSION=4.1.3"
set "FFMPEG_SHA256=05F4251BCE9293C2AB492CB17CA7724A0FFD0D06C881BA2EE83B82A89C2FC740"
set "FFPROBE_SHA256=51E0780CD881F83749B029ED716CBB841C2EAC6289F418050F2F2961B158896B"

if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv. Run setup.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat
uv sync --locked --python %PYTHON_VERSION% --managed-python
if errorlevel 1 exit /b 1

python -c "import _decimal, ssl, sys, unicodedata; from pathlib import Path; assert sys.version_info[:3] == (3, 14, 7), sys.version; assert Path(sys.base_prefix, 'BUILD').read_text().strip() == '%PYTHON_STANDALONE_BUILD%'; assert ssl.OPENSSL_VERSION == 'OpenSSL 3.5.7 9 Jun 2026', ssl.OPENSSL_VERSION; assert _decimal.__libmpdec_version__ == '4.0.0'; assert unicodedata.unidata_version == '16.0.0'"
if errorlevel 1 (
    echo Expected the pinned Astral Python %PYTHON_VERSION% build and incorporated libraries.
    exit /b 1
)
python -c "import importlib.metadata as m; expected={'PySide6':'%PYSIDE_VERSION%','PySide6-Essentials':'%PYSIDE_VERSION%','PySide6-Addons':'%PYSIDE_VERSION%','shiboken6':'%PYSIDE_VERSION%','Nuitka':'%NUITKA_VERSION%'}; actual={name:m.version(name) for name in expected}; assert actual == expected, actual"
if errorlevel 1 (
    echo Locked PySide6 or Nuitka version does not match this build's notices.
    exit /b 1
)
set "FFMPEG_PATH="
set "FFPROBE_PATH="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FFMPEG_PATH set "FFMPEG_PATH=%%F"
for /f "delims=" %%F in ('where ffprobe 2^>nul') do if not defined FFPROBE_PATH set "FFPROBE_PATH=%%F"
if not defined FFMPEG_PATH (
    echo FFmpeg was not found on PATH. Run setup.bat first.
    exit /b 1
)
if not defined FFPROBE_PATH (
    echo FFprobe was not found on PATH. Run setup.bat first.
    exit /b 1
)

for %%F in ("!FFMPEG_PATH!") do set "FFMPEG_BIN_DIR=%%~dpF"
for %%F in ("!FFPROBE_PATH!") do set "FFPROBE_BIN_DIR=%%~dpF"
if /i not "!FFMPEG_BIN_DIR!"=="!FFPROBE_BIN_DIR!" (
    echo FFmpeg and FFprobe must come from the same bin directory.
    echo FFmpeg:  !FFMPEG_PATH!
    echo FFprobe: !FFPROBE_PATH!
    exit /b 1
)
for %%F in ("!FFMPEG_BIN_DIR!..") do set "FFMPEG_ROOT=%%~fF"
if not exist "!FFMPEG_ROOT!\LICENSE" (
    echo The FFmpeg distributor LICENSE file was not found at !FFMPEG_ROOT!\LICENSE.
    exit /b 1
)
set "CLIPTRIM_FFMPEG_PATH=!FFMPEG_PATH!"
set "CLIPTRIM_FFPROBE_PATH=!FFPROBE_PATH!"
python -c "import hashlib, os; expected={'CLIPTRIM_FFMPEG_PATH':os.environ['FFMPEG_SHA256'],'CLIPTRIM_FFPROBE_PATH':os.environ['FFPROBE_SHA256']}; actual={name:hashlib.file_digest(open(path, 'rb'), 'sha256').hexdigest().upper() for name,path in ((name,os.environ[name]) for name in expected)}; assert actual == expected, actual"
if errorlevel 1 (
    echo FFmpeg or FFprobe hash does not match the exact binaries documented by the notices.
    exit /b 1
)

python buildtools\build_icon.py icon.svg buildtools\icon.ico
if errorlevel 1 exit /b 1

if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"
mkdir "%STAGING%"
if errorlevel 1 exit /b 1

set "ZIG_ROOT="
echo Building ClipTrim.
python -m nuitka ^
      --mode=standalone ^
      --enable-plugin=pyside6 ^
      --include-qt-plugins=multimedia ^
      --noinclude-qt-plugins=iconengines ^
      --noinclude-qt-plugins=tls ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qgif.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qicns.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qico.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qpdf.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qsvg.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qtga.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qtiff.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qwbmp.dll ^
      --noinclude-dlls=PySide6/qt-plugins/imageformats/qwebp.dll ^
      --noinclude-dlls=PySide6/qt-plugins/multimedia/ffmpegmediaplugin.dll ^
      --noinclude-dlls=PySide6/qt-plugins/platforms/qdirect2d.dll ^
      --noinclude-dlls=PySide6/qt-plugins/platforms/qminimal.dll ^
      --noinclude-dlls=PySide6/qt-plugins/platforms/qoffscreen.dll ^
      --noinclude-dlls=avcodec-*.dll ^
      --noinclude-dlls=avformat-*.dll ^
      --noinclude-dlls=avutil-*.dll ^
      --noinclude-dlls=swresample-*.dll ^
      --noinclude-dlls=swscale-*.dll ^
      --noinclude-dlls=qt6pdf.dll ^
      --noinclude-dlls=qt6svg.dll ^
      --windows-console-mode=attach ^
      --assume-yes-for-downloads ^
      --output-dir="%STAGING%" ^
      --output-filename=ClipTrim.runtime.exe ^
      --windows-icon-from-ico=buildtools\icon.ico ^
  cliptrim.py
if errorlevel 1 exit /b 1

if not exist "%NUITKA_DIST%\ClipTrim.runtime.exe" (
    echo Build finished but %NUITKA_DIST%\ClipTrim.runtime.exe was not found.
    exit /b 1
)
mkdir "%DIST%"
move "%NUITKA_DIST%" "%DIST%\runtime" >nul
if errorlevel 1 (
    echo Could not create runtime dependency folder: %DIST%\runtime
    exit /b 1
)

set "ZIG="
for /r "%LOCALAPPDATA%\Nuitka\Nuitka\Cache\downloads\pip" %%F in (zig.exe) do if exist "%%F" if not defined ZIG set "ZIG=%%F"
if not defined ZIG (
    echo Nuitka's Zig compiler was not found; the root launcher cannot be built.
    exit /b 1
)
for %%F in ("!ZIG!") do set "ZIG_ROOT=%%~dpF"
if not exist "!ZIG_ROOT!lib\libc\mingw\COPYING" (
    echo mingw-w64 COPYING was not found in the Zig toolchain.
    exit /b 1
)
"!ZIG!" rc /fo "%STAGING%\cliptrim_launcher.res" buildtools\cliptrim_launcher.rc
if errorlevel 1 exit /b 1
"!ZIG!" cc -target x86_64-windows-gnu -std=c11 -Os -s ^
  buildtools\cliptrim_launcher.c "%STAGING%\cliptrim_launcher.res" ^
  -lshell32 -luser32 "-Wl,--subsystem,windows" -o "%DIST%\ClipTrim.exe"
if errorlevel 1 exit /b 1

if not exist "%DIST%\ClipTrim.exe" (
    echo Final root launcher/executable was not created.
    exit /b 1
)
if not exist "%DIST%\runtime" (
    echo Final runtime dependency folder was not created.
    exit /b 1
)
set "CLIPTRIM_RUNTIME=%DIST%\runtime"
python -c "import fnmatch, os; from pathlib import Path; root=Path(os.environ['CLIPTRIM_RUNTIME']); plugins=root/'PySide6'/'qt-plugins'; allowed={'imageformats/qjpeg.dll','multimedia/windowsmediaplugin.dll','platforms/qwindows.dll','styles/qmodernwindowsstyle.dll'}; actual={p.relative_to(plugins).as_posix().lower() for p in plugins.rglob('*') if p.is_file()}; assert actual == allowed, ('unexpected Qt plugin set', sorted(actual)); patterns=('avcodec-*.dll','avformat-*.dll','avutil-*.dll','swresample-*.dll','swscale-*.dll','qt6pdf*.dll','qt6svg*.dll','qtpdf*.pyd','qtsvg*.pyd'); bad=[str(p) for p in root.rglob('*') if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pattern) for pattern in patterns)]; assert not bad, ('excluded runtimes were packaged', bad)"
if errorlevel 1 exit /b 1
if exist "%STAGING%" rmdir /s /q "%STAGING%"

for %%D in (bin config) do (
    if not exist "%DIST%\%%D" mkdir "%DIST%\%%D"
)
copy /y "buildtools\icon.ico" "%DIST%\icon.ico" >nul
if errorlevel 1 exit /b 1
copy /y "!FFMPEG_PATH!" "%DIST%\bin\ffmpeg.exe" >nul
if errorlevel 1 exit /b 1
copy /y "!FFPROBE_PATH!" "%DIST%\bin\ffprobe.exe" >nul
if errorlevel 1 exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "buildtools\modules\package_licenses.ps1" ^
  -DistributionDirectory "%DIST%" ^
  -PythonExecutable "%cd%\.venv\Scripts\python.exe" ^
  -PythonVersion "%PYTHON_VERSION%" ^
  -NuitkaVersion "%NUITKA_VERSION%" ^
  -FfmpegRoot "!FFMPEG_ROOT!" ^
  -ZigRoot "!ZIG_ROOT!."
if errorlevel 1 exit /b 1

echo.
echo EXE: %cd%\%DIST%\ClipTrim.exe
