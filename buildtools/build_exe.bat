@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0\.."

set "BUILD_ROOT=build"
set "STAGING=%BUILD_ROOT%\nuitka"
set "NUITKA_DIST=%STAGING%\cliptrim.dist"
set "DIST=%BUILD_ROOT%\ClipTrim"

if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv. Run setup.bat first.
    exit /b 1
)

call .venv\Scripts\activate.bat
uv sync --locked --python 3.14 --managed-python
if errorlevel 1 exit /b 1

python buildtools\build_icon.py icon.svg buildtools\icon.ico
if errorlevel 1 exit /b 1

if exist "%BUILD_ROOT%" rmdir /s /q "%BUILD_ROOT%"
mkdir "%STAGING%"
if errorlevel 1 exit /b 1

set "NATIVE_RUNTIME_LAYOUT="
python -m nuitka --help | findstr /c:"--put-runtime-files-in" >nul
if not errorlevel 1 set "NATIVE_RUNTIME_LAYOUT=1"

if defined NATIVE_RUNTIME_LAYOUT (
    echo Nuitka supports native runtime-folder layout.
    python -m nuitka ^
      --mode=standalone ^
      --enable-plugin=pyside6 ^
      --include-qt-plugins=multimedia ^
      --windows-console-mode=attach ^
      --assume-yes-for-downloads ^
      --output-dir="%STAGING%" ^
      --output-filename=ClipTrim.exe ^
      --windows-icon-from-ico=buildtools\icon.ico ^
      --put-runtime-files-in=runtime ^
      cliptrim.py
    if errorlevel 1 exit /b 1

    if not exist "%NUITKA_DIST%\ClipTrim.exe" (
        echo Build finished but %NUITKA_DIST%\ClipTrim.exe was not found.
        exit /b 1
    )
    move "%NUITKA_DIST%" "%DIST%" >nul
    if errorlevel 1 (
        echo Could not create final distributable folder: %DIST%
        exit /b 1
    )
) else (
    echo Nuitka does not support --put-runtime-files-in; using the native launcher layout.
    python -m nuitka ^
      --mode=standalone ^
      --enable-plugin=pyside6 ^
      --include-qt-plugins=multimedia ^
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
    "!ZIG!" rc /fo "%STAGING%\cliptrim_launcher.res" buildtools\cliptrim_launcher.rc
    if errorlevel 1 exit /b 1
    "!ZIG!" cc -target x86_64-windows-gnu -std=c11 -Os -s ^
      buildtools\cliptrim_launcher.c "%STAGING%\cliptrim_launcher.res" ^
      -lshell32 -luser32 "-Wl,--subsystem,windows" -o "%DIST%\ClipTrim.exe"
    if errorlevel 1 exit /b 1
)

if not exist "%DIST%\ClipTrim.exe" (
    echo Final root launcher/executable was not created.
    exit /b 1
)
if not exist "%DIST%\runtime" (
    echo Final runtime dependency folder was not created.
    exit /b 1
)

if exist "%STAGING%" rmdir /s /q "%STAGING%"

for %%D in (bin config logs .tmp) do (
    if not exist "%DIST%\%%D" mkdir "%DIST%\%%D"
) 
copy /y "buildtools\icon.ico" "%DIST%\icon.ico" >nul
if errorlevel 1 exit /b 1

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo WARNING: ffmpeg was not found on PATH and was not bundled.
) else (
    for /f "delims=" %%F in ('where ffmpeg') do if not exist "%DIST%\bin\ffmpeg.exe" copy /y "%%F" "%DIST%\bin\ffmpeg.exe" >nul
)

where ffprobe >nul 2>nul
if errorlevel 1 (
    echo WARNING: ffprobe was not found on PATH and was not bundled.
) else (
    for /f "delims=" %%F in ('where ffprobe') do if not exist "%DIST%\bin\ffprobe.exe" copy /y "%%F" "%DIST%\bin\ffprobe.exe" >nul
)

echo.
echo EXE: %cd%\%DIST%\ClipTrim.exe
