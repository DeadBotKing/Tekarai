-- Tighten specialist/facility to own-work only
DECLARE @spec CHAR(32)='49a186f02030441fadb0521c2a18644f';
DECLARE @fac  CHAR(32)='a7784d1648e8474c989657ec5369983e';

-- Clear old perms for these two
DELETE FROM [RolePermission] WHERE roleId IN (@spec, @fac);

-- tech_specialist: only own work (NO approve, NO org/device/inventory)
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @spec, p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.workorder.create','maintenance.workorder.view','maintenance.workorder.list','maintenance.workorder.update','maintenance.workorder.logTime','maintenance.attachment.view'
);

-- tech_facility: only report for own unit
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @fac, p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.workorder.create','maintenance.workorder.view','maintenance.workorder.list','maintenance.attachment.view'
);

-- Also remove org views from head/supervisor that grant "مدیریت و دسترسی" if not needed - keep only needed
-- Keep head/supervisor as is for now, only fix specialist/facility

PRINT 'Fixed minimal perms';
SELECT r.code, COUNT(rp.id) as permCount FROM [Role] r LEFT JOIN [RolePermission] rp ON rp.roleId=r.id WHERE r.code IN ('tech_specialist','tech_facility') GROUP BY r.code;
SELECT code FROM [Permission] WHERE id IN (SELECT permissionId FROM [RolePermission] WHERE roleId=@spec);
