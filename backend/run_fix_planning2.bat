@echo off
chcp 65001 >nul
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -i "%~dp0fix_planning_role2.sql"
echo DONE
pause
