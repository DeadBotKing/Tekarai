-- Fix production planning edit access - need production.manage not just view
-- Check Amene current roles
SELECT u.username, u.displayName, r.code, r.name FROM [User] u
JOIN [UserRole] ur ON ur.userId=u.id
JOIN [Role] r ON r.id=ur.roleId
WHERE u.username='amene.sadeghi' OR u.phone='09365614779' OR u.displayName LIKE N'%آمنه%' OR u.email LIKE '%amene%';

-- Check what perms her roles have
SELECT r.code as roleCode, r.name, p.code as permCode FROM [Role] r
JOIN [RolePermission] rp ON rp.roleId=r.id
JOIN [Permission] p ON p.id=rp.permissionId
WHERE r.code IN (SELECT r2.code FROM [Role] r2 JOIN [UserRole] ur ON ur.roleId=r2.id JOIN [User] u ON u.id=ur.userId WHERE u.username='amene.sadeghi' OR u.phone='09365614779')
ORDER BY r.code, p.code;

-- Ensure production.manage exists
IF NOT EXISTS (SELECT 1 FROM [Permission] WHERE code='production.manage')
  INSERT INTO [Permission] (id, code, module, description) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'production.manage', 'production', 'Manage production planning');

-- Grant production.manage to relevant roles (director, head, and planning manager role if exists)
DECLARE @permId CHAR(32) = (SELECT id FROM [Permission] WHERE code='production.manage');
DECLARE @dir CHAR(32) = (SELECT id FROM [Role] WHERE code='tech_director');
DECLARE @head CHAR(32) = (SELECT id FROM [Role] WHERE code='tech_head');
DECLARE @sup CHAR(32) = (SELECT id FROM [Role] WHERE code='tech_supervisor');

-- Add to director
IF @dir IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [RolePermission] WHERE roleId=@dir AND permissionId=@permId)
  INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @dir, @permId, 'production.manage');
-- Add to head
IF @head IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [RolePermission] WHERE roleId=@head AND permissionId=@permId)
  INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @head, @permId, 'production.manage');
-- Add to supervisor (optional, comment out if not needed)
-- IF @sup IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [RolePermission] WHERE roleId=@sup AND permissionId=@permId)
--   INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @sup, @permId, 'production.manage');

-- Also ensure production.view for same
DECLARE @permView CHAR(32) = (SELECT id FROM [Permission] WHERE code='production.view');
IF @dir IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [RolePermission] WHERE roleId=@dir AND permissionId=@permView)
  INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @dir, @permView, 'production.view');
IF @head IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [RolePermission] WHERE roleId=@head AND permissionId=@permView)
  INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @head, @permView, 'production.view');

-- Directly grant to Amene if her role still missing (as fallback, direct user permission)
DECLARE @ameneUserId CHAR(32) = (SELECT id FROM [User] WHERE username='amene.sadeghi' OR phone='09365614779');
IF @ameneUserId IS NOT NULL AND NOT EXISTS (SELECT 1 FROM [UserPermission] WHERE userId=@ameneUserId AND actionPattern='production.manage')
  INSERT INTO [UserPermission] (id, userId, permissionId, actionPattern, effect, scopeType, scopeRef, grantedAt)
  VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @ameneUserId, @permId, 'production.manage', 'allow', 'TENANT', '', SYSDATETIMEOFFSET());

PRINT 'DONE - Amene should now see Edit button after re-login';
SELECT r.code, COUNT(rp.id) as perms FROM [Role] r LEFT JOIN [RolePermission] rp ON rp.roleId=r.id WHERE r.code IN ('tech_director','tech_head','tech_supervisor') GROUP BY r.code;
