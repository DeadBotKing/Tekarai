-- Fix custom "planning manager" role with space -> replace with correct productionPlanner (CHAR32 ids)
PRINT '--- Before ---';
SELECT code, name, (SELECT COUNT(*) FROM RolePermission rp WHERE rp.roleId=r.id) as permCount FROM Role r WHERE code IN ('planning manager','planning_manager','productionPlanner') OR name LIKE N'%برنامه%';

-- 1. Ensure correct system role exists
IF NOT EXISTS (SELECT 1 FROM Role WHERE code='productionPlanner')
BEGIN
  INSERT INTO Role (id, code, name, scopeType, isActive, createdAt) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'productionPlanner', N'مدیر برنامه‌ریزی تولید', 'TENANT', 1, GETDATE());
  PRINT 'Created productionPlanner';
END

-- 2. Move Amene from custom role to correct role
DECLARE @customId CHAR(32) = (SELECT id FROM Role WHERE code='planning manager');
DECLARE @correctId CHAR(32) = (SELECT id FROM Role WHERE code='productionPlanner');
DECLARE @ameneId CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE displayName LIKE N'%آمنه%' OR phone LIKE '%365614779' ORDER BY createdAt DESC);

IF @customId IS NOT NULL AND @correctId IS NOT NULL AND @ameneId IS NOT NULL
BEGIN
  DELETE FROM UserRole WHERE userId=@ameneId AND roleId=@customId;
  IF NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@ameneId AND roleId=@correctId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
    SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @ameneId, @correctId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@ameneId;
  PRINT 'Moved Amene to productionPlanner';
END

-- 3. Delete custom role if unused
IF @customId IS NOT NULL
BEGIN
  IF NOT EXISTS (SELECT 1 FROM UserRole WHERE roleId=@customId)
  BEGIN
    DELETE FROM RolePermission WHERE roleId=@customId;
    DELETE FROM Role WHERE id=@customId;
    PRINT 'Deleted custom planning manager role';
  END
  ELSE
    PRINT 'Custom role still assigned - not deleted';
END

PRINT '--- After ---';
SELECT code, name, (SELECT COUNT(*) FROM RolePermission rp WHERE rp.roleId=r.id) as permCount FROM Role r WHERE code IN ('planning_manager','productionPlanner') OR name LIKE N'%برنامه%';
SELECT u.displayName, r.code, r.name FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE u.id=@ameneId;

PRINT 'DONE - Now run: python manage.py syncPermissionCatalog  and iisreset';
