@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" cliptrim.py %*
    exit /b
)
where py >nul 2>nul && (py -3 cliptrim.py %* & exit /b)
python cliptrim.py %*
