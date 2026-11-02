@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo   Dufs GUI - build ONE FILE
echo   Output: a single dist\DufsGui-vX.Y.Z.exe
echo   (no console window)
echo ============================================
echo.

where python >nul 2>nul || (
  echo [X] python not found. Install Python 3.9+ from python.org
  goto :done
)

for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo [1/5] Python %PYVER%

python -c "import tkinter" 2>nul && (
  echo [2/5] tkinter: OK
) || (
  echo [2/5] [X] tkinter NOT available
  echo        Likely conda / embeddable Python. Use python.org installer.
  echo        The exe will probably crash on startup.
)

python -c "import os,sys;sys.exit(0 if os.path.abspath(os.getcwd()).isascii() else 1)" 2>nul && (
  echo [3/5] path check OK
) || (
  echo [3/5] [!] non-ASCII path: %CD%
  echo        Prefer C:\build\dufs-gui
)

if exist "bin\dufs.exe" (
  echo [4/5] bin\dufs.exe present
) else (
  echo [4/5] downloading dufs.exe ...
  python tools\fetch_dufs.py
  if errorlevel 1 (
    echo       [!] download failed. Put dufs.exe into bin\ manually.
  )
)

python -m PyInstaller --version >nul 2>&1 && (
  echo [5/5] PyInstaller ready
) || (
  echo [5/5] installing PyInstaller ...
  python -m pip install -U pyinstaller -i https://mirrors.cloud.tencent.com/pypi/simple
  if errorlevel 1 (echo [X] install failed& goto :done)
)

echo.
echo Building one-file exe, please wait 1-3 minutes ...
set DUFS_GUI_MODE=onefile
rem Wipe dist first: stale exes linger otherwise and get double-clicked
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm --clean DufsGui.spec

if errorlevel 1 (
  echo.
  echo [X] Build failed. Run build_debug.bat to see the real error.
  goto :done
)

set "EXE="
for %%f in ("dist\DufsGui*.exe") do set "EXE=%%f"
if not defined EXE (
  echo [X] no exe found in dist\
  goto :done
)

echo.
echo ============================================
echo   Done
echo   Output : %CD%\%EXE%
for %%g in ("%EXE%") do echo   Size   : %%~zg bytes
for %%g in ("%EXE%") do echo   Time   : %%~tg
echo.
echo   Double-click that NEW file, not an old one.
echo   If it flashes and dies, run build_debug.bat first.
echo ============================================
echo.

:done
echo Press any key to close...
pause >nul
endlocal
