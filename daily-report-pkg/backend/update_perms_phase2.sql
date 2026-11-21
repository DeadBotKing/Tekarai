-- Phase2: Add equipment view for specialist/facility + production view for director/head
DECLARE @spec CHAR(32)='49a186f02030441fadb0521c2a18644f';
DECLARE @fac  CHAR(32)='a7784d1648e8474c989657ec5369983e';
DECLARE @dir  CHAR(32)='0c73506d2d7d475c83bb5d790fdae93c';
DECLARE @head CHAR(32)='b935c3883a80438eb7784bb5bd829ab8';

-- Add device list/view to specialist/facility to see own-unit equipment (view-only)
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @spec, p.id, p.code FROM [Permission] p WHERE p.code IN ('maintenance.device.list','maintenance.device.view')
AND NOT EXISTS (SELECT 1 FROM [RolePermission] rp WHERE rp.roleId=@spec AND rp.permissionId=p.id);

INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @fac, p.id, p.code FROM [Permission] p WHERE p.code IN ('maintenance.device.list','maintenance.device.view')
AND NOT EXISTS (SELECT 1 FROM [RolePermission] rp WHERE rp.roleId=@fac AND rp.permissionId=p.id);

-- Add production view to director/head (if not exists, create permission)
IF NOT EXISTS (SELECT 1 FROM [Permission] WHERE code='production.view')
  INSERT INTO [Permission] (id, code, module, description) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'production.view', 'production', 'View production planning');
IF NOT EXISTS (SELECT 1 FROM [Permission] WHERE code='production.manage')
  INSERT INTO [Permission] (id, code, module, description) VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'production.manage', 'production', 'Manage production planning');

-- Grant production.view to director/head
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @dir, p.id, p.code FROM [Permission] p WHERE p.code='production.view'
AND NOT EXISTS (SELECT 1 FROM [RolePermission] rp WHERE rp.roleId=@dir AND rp.permissionId=p.id);

INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), @head, p.id, p.code FROM [Permission] p WHERE p.code='production.view'
AND NOT EXISTS (SELECT 1 FROM [RolePermission] rp WHERE rp.roleId=@head AND rp.permissionId=p.id);

-- Verify
SELECT r.code, COUNT(rp.id) as perms FROM [Role] r LEFT JOIN [RolePermission] rp ON rp.roleId=r.id WHERE r.code IN ('tech_specialist','tech_facility','tech_director','tech_head') GROUP BY r.code;
