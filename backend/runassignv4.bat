@echo off
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i assignv4.sql
pause
