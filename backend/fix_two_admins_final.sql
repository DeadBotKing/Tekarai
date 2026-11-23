-- Only platform-admin (09183032356) + Mahdi Yarmohammadi (09129432012) keep admin
PRINT '--- Before ---';
SELECT u.displayName, u.username, r.code FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE r.code IN ('tenantAdmin','platformAdmin') ORDER BY r.code, u.displayName;

DECLARE @mahdiId CHAR(32) = (SELECT id FROM [User] WHERE username='09129432012');
DECLARE @platformId CHAR(32) = (SELECT id FROM [User] WHERE username='platform-admin');
IF @mahdiId IS NULL SET @mahdiId = (SELECT TOP 1 id FROM [User] WHERE displayName LIKE N'%یارمحمدی%');
IF @platformId IS NULL SET @platformId = (SELECT TOP 1 id FROM [User] WHERE phone='09183032356');

PRINT 'Mahdi'; SELECT displayName, username FROM [User] WHERE id=@mahdiId;
PRINT 'Platform'; SELECT displayName, username FROM [User] WHERE id=@platformId;

DECLARE @tenantAdminId CHAR(32) = (SELECT id FROM Role WHERE code='tenantAdmin');
DECLARE @platformAdminId CHAR(32) = (SELECT id FROM Role WHERE code='platformAdmin');

IF @tenantAdminId IS NOT NULL
BEGIN
  IF @mahdiId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@mahdiId AND roleId=@tenantAdminId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt) SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @mahdiId, @tenantAdminId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@mahdiId;
  IF @platformId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@platformId AND roleId=@tenantAdminId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt) SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @platformId, @tenantAdminId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@platformId;
  DELETE FROM UserRole WHERE roleId=@tenantAdminId AND userId NOT IN (@mahdiId, @platformId);
  PRINT 'Cleaned tenantAdmin';
END
IF @platformAdminId IS NOT NULL
BEGIN
  DELETE FROM UserRole WHERE roleId=@platformAdminId AND userId NOT IN (@mahdiId, @platformId);
  PRINT 'Cleaned platformAdmin';
END

PRINT '--- After ---';
SELECT u.displayName, u.username, r.code FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE r.code IN ('tenantAdmin','platformAdmin') ORDER BY r.code, u.displayName;
PRINT 'DONE - iisreset';
