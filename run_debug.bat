@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo %CMDCMDLINE% | find /i "%~nx0" >nul && set "DBLCLK=1"

set "LOGF=%TEMP%\dufs_gui_run.txt"
set "EXE=dist\DufsGui.exe"
if not "%~1"=="" set "EXE=%~1"

echo ============================================
echo   Dufs GUI - run and capture output
echo   target : %EXE%
echo   logfile: %LOGF%
echo ============================================
echo.

if not exist "%EXE%" (
  echo [X] Not found: %EXE%
  echo     Drag the exe onto this bat, or edit the EXE variable.
  goto :done
)

echo ---- [1/2] selftest (no GUI needed) ----
"%EXE%" --selftest > "%LOGF%" 2>&1
set RC=!ERRORLEVEL!
type "%LOGF%"
echo [exit code !RC!]
echo.
if defined DBLCLK pause

echo ---- [2/2] run main program ----
echo If OK: a window appears, close it manually, then come back here.
echo If it crashes: returns immediately, error stays in the log below.
echo.
"%EXE%" > "%LOGF%" 2>&1
set RC=!ERRORLEVEL!
type "%LOGF%"
echo [exit code !RC!]
echo.

echo ---- crash.log ----
if exist "%LOCALAPPDATA%\DufsGui\crash.log" (
  type "%LOCALAPPDATA%\DufsGui\crash.log"
) else (
  echo (none)
)

:done
echo.
echo Done. Copy everything above and send it.
if defined DBLCLK (
  echo.
  echo Press any key to close...
  pause >nul
)
endlocal
