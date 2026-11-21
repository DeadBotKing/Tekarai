@echo off
chcp 65001 >nul
echo === Role schema ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='Role' ORDER BY ORDINAL_POSITION"
echo.
echo === Roles (top10)=
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT id, code, name FROM [Role]"
echo.
echo === UserRole schema ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='UserRole' ORDER BY ORDINAL_POSITION"
echo.
echo === UserRole sample ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT TOP 5 id, userId, roleId FROM [UserRole]"
echo.
echo === OrgAssign schema ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='OrganizationAssignment' ORDER BY ORDINAL_POSITION"
echo.
echo === OrgAssign sample ===
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -Q "SELECT TOP 3 id, userId, departmentId, positionId FROM [OrganizationAssignment]"
pause
