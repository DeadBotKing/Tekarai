@echo off
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i inspectv3.sql
pause
