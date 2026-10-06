@echo off
REM ===========================================================================
REM Tekarai - start the whole platform with one double-click.
REM
REM Windows refuses to run run_dev.ps1 directly unless the script is digitally
REM signed or the machine policy has been changed, which is a security setting
REM most people cannot or should not alter just to start a dev server. A .cmd
REM file is not subject to the PowerShell execution policy at all, so this
REM launcher hands the script to PowerShell with the policy bypassed for that
REM one process only. Nothing on the machine is changed.
REM
REM   run_dev.cmd                 - SQL Server (SQL Express), the default
REM   run_dev.cmd -UseSqlite      - offline SQLite, no database server needed
REM   run_dev.cmd -DemoMode       - offline demo login
REM
REM Every switch run_dev.ps1 accepts is forwarded unchanged.
REM ===========================================================================

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_dev.ps1" %*
set "TEKARAI_EXIT=%ERRORLEVEL%"

if not "%TEKARAI_EXIT%"=="0" (
  echo.
  echo Tekarai stopped with exit code %TEKARAI_EXIT%.
  echo Scroll up for the error, or check the logs\ folder.
  echo.
  pause
)

exit /b %TEKARAI_EXIT%
