@echo off
chcp 65001 >nul
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0list_users.sql"
pause
