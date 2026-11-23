@echo off
chcp 65001 >nul
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i "%~dp0wipe_devices_v2.sql"
echo DONE
pause
