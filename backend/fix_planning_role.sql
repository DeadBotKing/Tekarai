-- Fix custom "planning manager" role with space -> replace with correct productionPlanner
PRINT '--- Before ---';
SELECT code, name, (SELECT COUNT(*) FROM RolePermission rp WHERE rp.roleId=r.id) as permCount FROM Role r WHERE code IN ('planning manager','planning_manager','productionPlanner') OR name LIKE N'%برنامه%';

-- 1. Ensure correct system role exists (if not, create minimal placeholder - real perms will be synced via Django)
IF NOT EXISTS (SELECT 1 FROM Role WHERE code='productionPlanner')
BEGIN
  INSERT INTO Role (id, code, name, scopeType, isActive, createdAt) VALUES (NEWID(), 'productionPlanner', N'مدیر برنامه‌ریزی تولید', 'TENANT', 1, GETDATE());
  PRINT 'Created productionPlanner';
END

-- 2. Move Amene from custom role to correct role
DECLARE @customId UNIQUEIDENTIFIER = (SELECT id FROM Role WHERE code='planning manager');
DECLARE @correctId UNIQUEIDENTIFIER = (SELECT id FROM Role WHERE code='productionPlanner');
DECLARE @ameneId UNIQUEIDENTIFIER = (SELECT TOP 1 id FROM [User] WHERE displayName LIKE N'%آمنه%' OR phone LIKE '%365614779' ORDER BY createdAt DESC);

IF @customId IS NOT NULL AND @correctId IS NOT NULL AND @ameneId IS NOT NULL
BEGIN
  -- remove custom assignment if exists
  DELETE FROM UserRole WHERE userId=@ameneId AND roleId=@customId;
  -- add correct assignment if not exists
  IF NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@ameneId AND roleId=@correctId)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
    SELECT NEWID(), @ameneId, @correctId, tenantId, 'TENANT', '', GETDATE() FROM [User] WHERE id=@ameneId;
  PRINT 'Moved Amene to productionPlanner';
END

-- 3. Delete custom role if no one else uses it (or force delete perms first)
IF @customId IS NOT NULL
BEGIN
  IF NOT EXISTS (SELECT 1 FROM UserRole WHERE roleId=@customId)
  BEGIN
    DELETE FROM RolePermission WHERE roleId=@customId;
    DELETE FROM Role WHERE id=@customId;
    PRINT 'Deleted custom planning manager role';
  END
  ELSE
    PRINT 'Custom role still assigned to someone else - not deleted, remove assignments first';
END

PRINT '--- After ---';
SELECT code, name, (SELECT COUNT(*) FROM RolePermission rp WHERE rp.roleId=r.id) as permCount FROM Role r WHERE code IN ('planning_manager','productionPlanner') OR name LIKE N'%برنامه%';
SELECT u.displayName, r.code, r.name FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE u.id=@ameneId;

-- Finally sync perms for productionPlanner via Django (run syncPermissionCatalog) to restore 14 correct perms without role.manage
PRINT 'DONE - Now run: python manage.py syncPermissionCatalog  and iisreset';
