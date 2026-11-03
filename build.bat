@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem Double-click: keep the window open at the end. Command line / CI: exit directly.
echo %CMDCMDLINE% | find /i "%~nx0" >nul && set "DBLCLK=1"

echo ============================================
echo   Dufs GUI - one-click build
echo   Output: a single dist\DufsGui-vX.Y.Z.exe
echo ============================================
echo.

where python >nul 2>nul || (
  echo [X] Python not found.
  echo     Install Python 3.12+ from https://www.python.org/downloads/windows/
  goto :fail
)

echo ---------- [1/5] environment ----------
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo Python %PYVER%
python -c "import tkinter" 2>nul || (
  echo [X] tkinter missing - use the official python.org installer, not conda/embeddable.
  goto :fail
)
echo tkinter OK
python -c "import os,sys;sys.exit(0 if os.path.abspath(os.getcwd()).isascii() else 1)" 2>nul || (
  echo [!] Non-ASCII path: %CD%
  echo     Prefer a pure-ASCII path such as C:\build\dufs-gui
)

echo.
echo ---------- [2/5] dufs binary ----------
if exist "bin\dufs.exe" (
  echo bin\dufs.exe present
) else (
  echo bin\dufs.exe missing, downloading pinned v0.47.0 ...
  python tools\fetch_dufs.py
  if errorlevel 1 (
    echo [X] Download failed. Check the message above.
    goto :fail
  )
)

echo.
echo ---------- [3/5] PyInstaller ----------
python -m PyInstaller --version >nul 2>&1 || (
  echo [X] PyInstaller not installed. Run this one line, then retry:
  echo.
  echo     python -m pip install -r requirements.txt
  echo.
  goto :fail
)
for /f "delims=" %%p in ('python -m PyInstaller --version') do set "PIVER=%%p"
echo PyInstaller %PIVER%
if not "%PIVER%"=="6.22.3" (
  echo [!] requirements.txt pins 6.22.3; other versions may produce different bytes
)

echo.
echo ---------- [4/5] build one-file exe ----------
set DUFS_GUI_MODE=onefile
rem Stale exes linger otherwise and get double-clicked by mistake
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
python -m PyInstaller --noconfirm --clean DufsGui.spec
if errorlevel 1 (
  echo [X] Build failed. Run build_debug.bat for the full log.
  goto :fail
)

set "EXE="
for %%f in ("dist\DufsGui*.exe") do set "EXE=%%f"
if not defined EXE (
  echo [X] No exe found in dist\
  goto :fail
)

echo.
echo ---------- [5/5] selftest + checksums ----------
"%EXE%" --selftest
if errorlevel 1 (
  echo [X] selftest failed - the frozen exe cannot start.
  goto :fail
)
python tools\build_info.py "%EXE%"
if errorlevel 1 (
  echo [!] checksum generation failed; the exe itself is OK.
)

echo.
echo ============================================
echo   Done
echo   Output : %CD%\%EXE%
for %%g in ("%EXE%") do echo   Size   : %%~zg bytes
for %%g in ("%EXE%") do echo   Time   : %%~tg
echo   Detail : dist\BUILD-INFO.txt, dist\SHA256SUMS
echo ============================================
if defined DBLCLK (
  echo.
  echo Press any key to close...
  pause >nul
)
exit /b 0

:fail
echo.
echo Build stopped. See the [X] line above.
if defined DBLCLK (
  echo.
  echo Press any key to close...
  pause >nul
)
exit /b 1
