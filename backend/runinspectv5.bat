@echo off
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i inspectv5.sql
pause
