@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo %CMDCMDLINE% | find /i "%~nx0" >nul && set "DBLCLK=1"

set "LOGF=%TEMP%\dufs_gui_debug.txt"
set "EXE="

echo ============================================
echo   Dufs GUI - diagnostic build (ONE FILE)
echo   Output: a single dist\DufsGui-vX.Y.Z-debug.exe
echo   Console is kept ON so errors stay visible
echo ============================================
echo.

where python >nul 2>nul || (echo [X] python not found& goto :fail)

echo ---------- [1/4] environment check ----------
for /f "delims=" %%v in ('python -c "import sys;print(sys.version.split()[0])"') do set PYVER=%%v
echo Python: %PYVER%

python -c "import sys;v=sys.version_info;sys.exit(1 if (v[0]==3 and v[1]==13 and v[2]==0) else 0)" 2>nul || (
  echo [!] Python 3.13.0 has a known tkinter bug on Windows venv
  echo     Upgrade to 3.13.1+ or use 3.12.x
)

python -c "import tkinter;print('tkinter: OK  Tk',tkinter.TkVersion)" 2>nul || (
  echo [X] tkinter NOT available - this is the #1 cause of crashes
  echo     Use official python.org installer, not conda/embeddable
)

python -c "import os,sys;sys.exit(0 if os.path.abspath(os.getcwd()).isascii() else 1)" 2>nul || (
  echo [!] Path has non-ASCII characters: %CD%
  echo     Move to a pure-ASCII path such as C:\build\dufs-gui
)

python -m PyInstaller --version >nul 2>nul && (
  for /f "delims=" %%p in ('python -m PyInstaller --version') do echo PyInstaller: %%p
) || (
  echo PyInstaller: not installed, installing...
  python -m pip install -U pyinstaller -i https://mirrors.cloud.tencent.com/pypi/simple
)
echo.
if defined DBLCLK pause

echo ---------- [2/4] build ONE FILE + console ----------
if not exist "bin\dufs.exe" (
  echo [!] bin\dufs.exe missing, trying to download...
  python tools\fetch_dufs.py
)
set DUFS_GUI_MODE=onefile
set DUFS_GUI_CONSOLE=1
rem Wipe dist first: stale exes linger otherwise and get double-clicked
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

python -m PyInstaller --noconfirm --clean DufsGui.spec
if errorlevel 1 (echo [X] Build failed& goto :fail)
echo.
if defined DBLCLK pause

echo ---------- [3/4] selftest ----------
for %%f in ("dist\DufsGui*.exe") do set "EXE=%%f"
if not defined EXE (echo [X] no exe found in dist\& goto :fail)
echo exe: %EXE%
for %%f in ("%EXE%") do echo size: %%~zf bytes
"%EXE%" --selftest > "%LOGF%" 2>&1
set RC1=!ERRORLEVEL!
echo ---- selftest output ----
type "%LOGF%"
echo ---- exit code !RC1! ----
echo.
if defined DBLCLK pause

echo ---------- [4/4] run main program ----------
echo If OK: a window appears. Close it manually, then come back here.
echo If it crashes: returns immediately, error stays in the log below.
echo.
"%EXE%" > "%LOGF%" 2>&1
set RC2=!ERRORLEVEL!
echo ---- run output ----
type "%LOGF%"
echo ---- exit code !RC2! ----
echo.

echo ---------- crash.log ----------
if exist "%LOCALAPPDATA%\DufsGui\crash.log" (
  type "%LOCALAPPDATA%\DufsGui\crash.log"
) else (
  echo (none)
)
goto :done

:fail
echo.
echo Something went wrong. Copy everything above and send it.

:done
echo.
echo ============================================
echo   Done. Full output at %LOGF%
echo ============================================
if defined DBLCLK (
  echo.
  echo Press any key to close...
  pause >nul
)
endlocal
