-- v5: rule counts per position + boss UserRole by username + table types
SET NOCOUNT ON;
PRINT '=== Rules per position ===';
SELECT p.code, p.name, COUNT(r.id) AS ruleCount
FROM OrganizationPosition p LEFT JOIN OrganizationAccessRule r ON r.positionId=p.id
GROUP BY p.code,p.name ORDER BY ruleCount DESC, p.code;
GO
PRINT '=== Boss UserRole by username ===';
SELECT u.displayName, u.username, r.code, r.name
FROM [User] u LEFT JOIN UserRole ur ON ur.userId=u.id LEFT JOIN [Role] r ON r.id=ur.roleId
WHERE u.username IN ('09120535494','09183689891','09196189256','09113282043','09129432012')
ORDER BY u.username, r.code;
GO
PRINT '=== OrganizationAccessRule columns ===';
SELECT COLUMN_NAME, DATA_TYPE, CHARACTER_MAXIMUM_LENGTH FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='OrganizationAccessRule' ORDER BY ORDINAL_POSITION;
GO
PRINT '=== Sample member UserRole (Abbas team) ===';
SELECT u.username, r.code
FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN [Role] r ON r.id=ur.roleId
WHERE u.username IN ('09189169465','09184341321','09378985255','09116498513')
ORDER BY u.username;
GO
