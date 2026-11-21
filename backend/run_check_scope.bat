@echo off
chcp 65001 >nul
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT code, scopeType, isActive FROM [Role]"
echo.
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT userId, roleId, tenantId, scopeType, scopeRef FROM [UserRole] WHERE userId='214f88d803f54b6491cdd1c3c995e9bf'"
echo.
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT COUNT(*) as cnt FROM [UserRole] WHERE tenantId='0df1a1daa7f94610ae0d96455183fb8e'"
pause
