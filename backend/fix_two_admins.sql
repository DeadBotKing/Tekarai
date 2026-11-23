-- Only platform-admin + Mahdi Yarmohammadi should keep role access
PRINT '--- Before ---';
SELECT u.displayName, u.username, r.code FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE r.code IN ('tenantAdmin','platformAdmin') ORDER BY r.code, u.displayName;

DECLARE @mahdiId CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE displayName LIKE N'%مهدی%' OR displayName LIKE N'%یارمحمدی%' OR username LIKE '%mahdi%' ORDER BY createdAt DESC);
DECLARE @platformId CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='platform-admin' OR username='platform_admin' OR displayName LIKE N'%platform%' ORDER BY createdAt ASC);
-- fallback: also try AdministrativeIdentity owner if platform user not in User table
IF @platformId IS NULL SET @platformId = (SELECT TOP 1 userId FROM UserRole WHERE roleId=(SELECT id FROM Role WHERE code='platformAdmin'));

PRINT 'Mahdi:'; SELECT @mahdiId as mahdiId;
PRINT 'Platform:'; SELECT @platformId as platformId;
SELECT displayName, username FROM [User] WHERE id IN (@mahdiId, @platformId);

DECLARE @tenantAdminId CHAR(32) = (SELECT id FROM Role WHERE code='tenantAdmin');
DECLARE @platformAdminId CHAR(32) = (SELECT id FROM Role WHERE code='platformAdmin');

-- ensure both have tenantAdmin (so they can enter /app/administration)
IF @tenantAdminId IS NOT NULL
BEGIN
  IF @mahdiId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@mahdiId AND roleId=@tenantAdminId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt) SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @mahdiId, @tenantAdminId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@mahdiId;
  IF @platformId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@platformId AND roleId=@tenantAdminId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt) SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @platformId, @tenantAdminId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@platformId;
  -- remove from everyone else
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
