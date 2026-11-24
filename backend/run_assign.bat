@echo off
echo === Assign Roles+Teams ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i assign_roles_teams.sql
if %errorlevel% NEQ 0 echo FAILED ^& pause ^& exit /b 1
echo DONE
pause
