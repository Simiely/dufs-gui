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
echo [1/7] Python %PYVER%

python -c "import tkinter" 2>nul && (
  echo [2/7] tkinter: OK
) || (
  echo [2/7] [X] tkinter NOT available
  echo        Likely conda / embeddable Python. Use python.org installer.
  echo        The exe will probably crash on startup.
)

python -c "import os,sys;sys.exit(0 if os.path.abspath(os.getcwd()).isascii() else 1)" 2>nul && (
  echo [3/7] path check OK
) || (
  echo [3/7] [!] non-ASCII path: %CD%
  echo        Prefer C:\build\dufs-gui
)

if exist "bin\dufs.exe" (
  echo [4/7] bin\dufs.exe present
) else (
  echo [4/7] downloading dufs.exe ...
  python tools\fetch_dufs.py
  if errorlevel 1 (
    echo       [!] download failed. Put dufs.exe into bin\ manually.
  )
)

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo [5/7] [X] PyInstaller NOT installed.
  echo        Install the pinned build dependencies first:
  echo          python -m pip install -r requirements.txt
  echo        ^(verified: PyInstaller 6.22.3 / Python 3.14.6^)
  goto :done
)
for /f "delims=" %%p in ('python -m PyInstaller --version') do set "PIVER=%%p"
echo [5/7] PyInstaller %PIVER%
if not "%PIVER%"=="6.22.3" (
  echo       [!] requirements.txt pins 6.22.3; this version may produce different bytes
)

echo.
echo [6/7] Building one-file exe, please wait 1-3 minutes ...
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

echo [7/7] selftest + build metadata
"%EXE%" --selftest
if errorlevel 1 (
  echo [X] selftest failed - the exe cannot run in a frozen environment.
  goto :done
)
python tools\build_info.py "%EXE%"
if errorlevel 1 (
  echo [!] build metadata generation failed; exe itself is OK.
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
