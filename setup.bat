@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title ClipTrim Development Setup

set "PYTHON_VERSION=3.14.7"
set "VENV_PYTHON=.venv\Scripts\python.exe"
set "UV_CMD="
set "FFMPEG_CMD="
set "FFPROBE_CMD="

echo [1/5] Checking the uv environment manager...
call :find_uv
if defined UV_CMD goto :uv_ready

echo uv was not found. Installing it now...
call :install_uv
if errorlevel 1 goto :failed
call :find_uv
if not defined UV_CMD (
    echo ERROR: uv was installed but could not be located in this session.
    echo Close this window, open a new terminal, and run setup.bat again.
    goto :failed
)

:uv_ready
"%UV_CMD%" --version
if errorlevel 1 (
    echo ERROR: uv could not be started.
    goto :failed
)

echo.
echo [2/5] Installing the managed Python %PYTHON_VERSION% runtime...
"%UV_CMD%" python install %PYTHON_VERSION%
if errorlevel 1 (
    echo ERROR: Python %PYTHON_VERSION% could not be installed or located.
    goto :failed
)

echo.
echo [3/5] Creating and synchronizing .venv from uv.lock...
"%UV_CMD%" sync --locked --python %PYTHON_VERSION% --managed-python
if errorlevel 1 (
    echo ERROR: The locked Python dependencies could not be installed.
    goto :failed
)
if not exist "%VENV_PYTHON%" (
    echo ERROR: uv completed without creating %VENV_PYTHON%.
    goto :failed
)

echo.
echo [4/5] Verifying PySide6 and Nuitka inside .venv...
"%VENV_PYTHON%" -c "import PySide6; print('PySide6', PySide6.__version__)"
if errorlevel 1 (
    echo ERROR: PySide6 is not usable from .venv.
    goto :failed
)
"%VENV_PYTHON%" -m nuitka --version
if errorlevel 1 (
    echo ERROR: Nuitka is not usable from .venv.
    goto :failed
)

echo.
echo [5/5] Checking FFmpeg and FFprobe...
call :find_media_tools
if defined FFMPEG_CMD if defined FFPROBE_CMD goto :media_ready

echo FFmpeg or FFprobe was not found. Installing Gyan.FFmpeg with WinGet...
where winget >nul 2>nul
if errorlevel 1 (
    echo ERROR: WinGet is required to install FFmpeg automatically.
    echo Install Windows App Installer, then run setup.bat again.
    goto :failed
)
winget install --id Gyan.FFmpeg --exact --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
if errorlevel 1 (
    echo ERROR: WinGet could not install Gyan.FFmpeg.
    goto :failed
)
call :find_media_tools
if not defined FFMPEG_CMD (
    echo ERROR: FFmpeg was installed but is not visible on PATH yet.
    echo Close this window, open a new terminal, and run setup.bat again.
    goto :failed
)
if not defined FFPROBE_CMD (
    echo ERROR: FFprobe was installed but is not visible on PATH yet.
    echo Close this window, open a new terminal, and run setup.bat again.
    goto :failed
)

:media_ready
"%FFMPEG_CMD%" -version >nul 2>nul
if errorlevel 1 (
    echo ERROR: FFmpeg was found but could not be started.
    goto :failed
)
"%FFPROBE_CMD%" -version >nul 2>nul
if errorlevel 1 (
    echo ERROR: FFprobe was found but could not be started.
    goto :failed
)

echo.
echo Development setup complete.
echo.
echo Run from source:  run.bat
echo Build the app:    buildtools\build_exe.bat
echo Nuitka command:   .venv\Scripts\python.exe -m nuitka
echo.
echo Nuitka will download its supported compiler tools automatically during
echo the first build because build_exe.bat uses --assume-yes-for-downloads.
pause
exit /b 0

:failed
echo.
echo ClipTrim development setup failed. Review the error above and rerun setup.bat.
pause
exit /b 1

:find_uv
set "UV_CMD="
for /f "delims=" %%F in ('where uv 2^>nul') do if not defined UV_CMD set "UV_CMD=%%F"
if not defined UV_CMD if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "UV_CMD=%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
if not defined UV_CMD if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_CMD=%USERPROFILE%\.local\bin\uv.exe"
exit /b 0

:install_uv
where winget >nul 2>nul
if errorlevel 1 goto :install_uv_official
winget install --id astral-sh.uv --exact --source winget --silent --accept-source-agreements --accept-package-agreements --disable-interactivity
if not errorlevel 1 exit /b 0
echo WinGet could not install uv; trying the official Astral installer...

:install_uv_official
where powershell >nul 2>nul
if errorlevel 1 (
    echo ERROR: Neither WinGet nor Windows PowerShell is available to install uv.
    exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
exit /b %errorlevel%

:find_media_tools
set "FFMPEG_CMD="
set "FFPROBE_CMD="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FFMPEG_CMD set "FFMPEG_CMD=%%F"
for /f "delims=" %%F in ('where ffprobe 2^>nul') do if not defined FFPROBE_CMD set "FFPROBE_CMD=%%F"
exit /b 0
