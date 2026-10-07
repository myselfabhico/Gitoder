@echo off
rem One-click build: creates the venv if missing, installs deps, builds Gitoder.exe
setlocal
cd /d "%~dp0"

if not exist .venv (
    python -m venv .venv || goto :error
)
call .venv\Scripts\activate.bat || goto :error
python -m pip install --disable-pip-version-check --quiet -r requirements.txt || goto :error

.venv\Scripts\pyinstaller.exe --noconfirm --clean gitoder.spec || goto :error

echo.
echo Build finished: dist\Gitoder.exe
goto :eof

:error
echo BUILD FAILED with error %errorlevel%
exit /b %errorlevel%
