@echo off
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i assignv3.sql
pause
