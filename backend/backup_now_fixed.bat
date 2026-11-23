@echo off
chcp 65001 >nul
if not exist "C:\TekaraiBackup" mkdir "C:\TekaraiBackup"
for /f %%I in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set stamp=%%I
set file=C:\TekaraiBackup\TekaraiLive_%stamp%.bak
echo Backing up to %file% ...
sqlcmd -S localhost\SQLEXPRESS -E -Q "BACKUP DATABASE [TekaraiLive] TO DISK='%file%' WITH INIT, COMPRESSION, STATS=10"
if %errorlevel% NEQ 0 echo FAILED & pause & exit /b 1
echo Verifying...
sqlcmd -S localhost\SQLEXPRESS -E -Q "RESTORE VERIFYONLY FROM DISK='%file%'"
echo DONE: %file%
dir "%file%"
pause
