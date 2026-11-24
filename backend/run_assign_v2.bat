@echo off
echo === Assign v2 (correct schema) ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i assign_roles_teams_v2.sql
if %errorlevel% NEQ 0 echo FAILED ^& pause ^& exit /b 1
echo DONE
pause
