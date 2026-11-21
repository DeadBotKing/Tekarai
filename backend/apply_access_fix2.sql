-- Apply TekaraiLive RBAC - 5 levels (Director/Head/Supervisor/Specialist/Facility)
-- Tenant: platform 0df1a1daa7f94610ae0d96455183fb8e
DECLARE @tenantId CHAR(32) = '0df1a1daa7f94610ae0d96455183fb8e';

PRINT '=== STEP 1: Create Roles ===';
IF NOT EXISTS (SELECT 1 FROM [Role] WHERE code='tech_director')
    INSERT INTO [Role] (id, code, name, scopeType, isActive, createdAt) VALUES ('0c73506d2d7d475c83bb5d790fdae93c', 'tech_director', N'مدیر فنی و مهندسی - دسترسی کامل', 'TENANT', 1, SYSDATETIMEOFFSET());
ELSE PRINT 'tech_director exists';

IF NOT EXISTS (SELECT 1 FROM [Role] WHERE code='tech_head')
    INSERT INTO [Role] (id, code, name, scopeType, isActive, createdAt) VALUES ('b935c3883a80438eb7784bb5bd829ab8', 'tech_head', N'رییس واحد فنی', 'TENANT', 1, SYSDATETIMEOFFSET());
ELSE PRINT 'tech_head exists';

IF NOT EXISTS (SELECT 1 FROM [Role] WHERE code='tech_supervisor')
    INSERT INTO [Role] (id, code, name, scopeType, isActive, createdAt) VALUES ('c2acd8d592a74fa38f918f1d3111627a', 'tech_supervisor', N'سرپرست فنی', 'TENANT', 1, SYSDATETIMEOFFSET());
ELSE PRINT 'tech_supervisor exists';

IF NOT EXISTS (SELECT 1 FROM [Role] WHERE code='tech_specialist')
    INSERT INTO [Role] (id, code, name, scopeType, isActive, createdAt) VALUES ('49a186f02030441fadb0521c2a18644f', 'tech_specialist', N'کارشناس فنی', 'TENANT', 1, SYSDATETIMEOFFSET());
ELSE PRINT 'tech_specialist exists';

IF NOT EXISTS (SELECT 1 FROM [Role] WHERE code='tech_facility')
    INSERT INTO [Role] (id, code, name, scopeType, isActive, createdAt) VALUES ('a7784d1648e8474c989657ec5369983e', 'tech_facility', N'پرسنل تاسیسات و موتورخانه', 'TENANT', 1, SYSDATETIMEOFFSET());
ELSE PRINT 'tech_facility exists';

-- Clean old permissions for these 5 roles to allow re-run
DELETE FROM [RolePermission] WHERE roleId IN ('0c73506d2d7d475c83bb5d790fdae93c','b935c3883a80438eb7784bb5bd829ab8','c2acd8d592a74fa38f918f1d3111627a','49a186f02030441fadb0521c2a18644f','a7784d1648e8474c989657ec5369983e');

PRINT '=== STEP 2: Grant Permissions ===';

-- Helper: insert permission by code
-- tech_director: FULL (all maintenance + org + audit + export)
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), '0c73506d2d7d475c83bb5d790fdae93c', p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.attachment.manage','maintenance.attachment.view','maintenance.costs.view','maintenance.device.export','maintenance.device.list','maintenance.device.manage','maintenance.device.view','maintenance.document.manage','maintenance.document.upload','maintenance.document.view','maintenance.inventory.consume','maintenance.inventory.export','maintenance.inventory.manage','maintenance.inventory.view','maintenance.meter.ingest','maintenance.meter.manage','maintenance.meter.record','maintenance.meter.view','maintenance.review.manage','maintenance.workorder.approve','maintenance.workorder.assign','maintenance.workorder.close','maintenance.workorder.create','maintenance.workorder.delete','maintenance.workorder.escalate','maintenance.workorder.export','maintenance.workorder.list','maintenance.workorder.logTime','maintenance.workorder.route','maintenance.workorder.update','maintenance.workorder.view','organization.department.view','organization.position.view','organization.assignment.view','organization.assignment.manage','organization.department.manage','organization.position.manage','organization.accessRule.view','organization.accessRule.manage','audit.view','analytics.metricDefinition.view','analytics.metricReading.view','analytics.metricReading.record','analytics.metric.export','project.view','project.list','project.create','project.update','task.create','task.list','task.update','procurement.supplier.view','procurement.requisition.create','procurement.purchaseOrder.create'
);

-- tech_head: unit head - view/approve within own dept
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'b935c3883a80438eb7784bb5bd829ab8', p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.attachment.view','maintenance.attachment.manage','maintenance.costs.view','maintenance.device.list','maintenance.device.view','maintenance.document.view','maintenance.inventory.view','maintenance.meter.view','maintenance.meter.record','maintenance.workorder.approve','maintenance.workorder.assign','maintenance.workorder.close','maintenance.workorder.create','maintenance.workorder.escalate','maintenance.workorder.export','maintenance.workorder.list','maintenance.workorder.logTime','maintenance.workorder.route','maintenance.workorder.update','maintenance.workorder.view','organization.department.view','organization.position.view','organization.assignment.view','audit.view','analytics.metricDefinition.view','analytics.metricReading.view','project.view','project.list'
);

-- tech_supervisor: create/approve/report for own line
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'c2acd8d592a74fa38f918f1d3111627a', p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.attachment.view','maintenance.attachment.manage','maintenance.costs.view','maintenance.device.list','maintenance.device.view','maintenance.document.view','maintenance.document.upload','maintenance.inventory.view','maintenance.inventory.consume','maintenance.meter.view','maintenance.meter.record','maintenance.workorder.approve','maintenance.workorder.close','maintenance.workorder.create','maintenance.workorder.escalate','maintenance.workorder.export','maintenance.workorder.list','maintenance.workorder.logTime','maintenance.workorder.update','maintenance.workorder.view','organization.department.view','organization.position.view','organization.assignment.view','analytics.metricReading.view','analytics.metricDefinition.view'
);

-- tech_specialist: create own work, NO approve
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), '49a186f02030441fadb0521c2a18644f', p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.attachment.view','maintenance.device.list','maintenance.device.view','maintenance.document.view','maintenance.inventory.view','maintenance.meter.view','maintenance.meter.record','maintenance.workorder.create','maintenance.workorder.list','maintenance.workorder.logTime','maintenance.workorder.update','maintenance.workorder.view','organization.department.view','organization.position.view','organization.assignment.view'
);

-- tech_facility: minimal - only report for own unit
INSERT INTO [RolePermission] (id, roleId, permissionId, actionPattern)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), 'a7784d1648e8474c989657ec5369983e', p.id, p.code FROM [Permission] p WHERE p.code IN (
 'maintenance.attachment.view','maintenance.device.view','maintenance.document.view','maintenance.meter.view','maintenance.workorder.create','maintenance.workorder.list','maintenance.workorder.view','organization.department.view','organization.position.view','organization.assignment.view'
);

PRINT '=== STEP 3: Assign Users to Roles ===';
-- Clear old tech roles for these 44 users (allow re-run)
DELETE FROM [UserRole] WHERE roleId IN ('0c73506d2d7d475c83bb5d790fdae93c','b935c3883a80438eb7784bb5bd829ab8','c2acd8d592a74fa38f918f1d3111627a','49a186f02030441fadb0521c2a18644f','a7784d1648e8474c989657ec5369983e') AND tenantId=@tenantId;

-- Temp mapping
IF OBJECT_ID('tempdb..#Map') IS NOT NULL DROP TABLE #Map;
CREATE TABLE #Map (phone NVARCHAR(20), roleCode NVARCHAR(30));

INSERT INTO #Map (phone, roleCode) VALUES
(N'09129432012', 'tech_director'),
(N'09120535494', 'tech_head'), (N'09183689891', 'tech_head'), (N'09196189256', 'tech_head'), (N'09113282043', 'tech_head'),
(N'09184939450', 'tech_supervisor'), (N'09127569668', 'tech_supervisor'), (N'09128840364', 'tech_supervisor'), (N'09370398323', 'tech_supervisor'), (N'09198720900', 'tech_supervisor'), (N'09116498513', 'tech_supervisor'),
(N'09189169465', 'tech_facility'), (N'09184341321', 'tech_facility'), (N'09196562494', 'tech_facility'), (N'09376557247', 'tech_facility'), (N'09128554542', 'tech_facility'), (N'09398308536', 'tech_facility'), (N'09168535529', 'tech_facility'), (N'09378985255', 'tech_facility'),
(N'09363822395', 'tech_specialist'), (N'09193499439', 'tech_specialist'), (N'09167453720', 'tech_specialist'), (N'09195231690', 'tech_specialist'),
(N'09330146665', 'tech_specialist'), (N'09002550821', 'tech_specialist'), (N'09359959538', 'tech_specialist'), (N'09190512839', 'tech_specialist'),
(N'09358422007', 'tech_specialist'), (N'09186230775', 'tech_specialist'), (N'09183936442', 'tech_specialist'), (N'09120262857', 'tech_specialist'),
(N'09190522042', 'tech_specialist'), (N'09167563107', 'tech_specialist'), (N'09120682369', 'tech_specialist'), (N'09128855367', 'tech_specialist'),
(N'09372750444', 'tech_specialist'), (N'09185072143', 'tech_specialist'), (N'09193560513', 'tech_specialist'), (N'09933181900', 'tech_specialist'),
(N'09100823904', 'tech_specialist'), (N'09193561023', 'tech_specialist'), (N'09223540245', 'tech_specialist'), (N'09183032356', 'tech_specialist'),
(N'09193551129', 'tech_specialist');

-- Insert
INSERT INTO [UserRole] (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)), '-', '')), u.id, r.id, @tenantId, 'TENANT', NULL, SYSDATETIMEOFFSET())
FROM #Map m
JOIN [User] u ON u.username = m.phone AND u.deletedAt IS NULL
JOIN [Role] r ON r.code = m.roleCode;

DROP TABLE #Map;

PRINT '=== DONE ===';
SELECT r.code, r.name, COUNT(ur.id) as assigned FROM [Role] r LEFT JOIN [UserRole] ur ON ur.roleId=r.id AND ur.tenantId=@tenantId WHERE r.code IN ('tech_director','tech_head','tech_supervisor','tech_specialist','tech_facility') GROUP BY r.code, r.name ORDER BY r.code;
SELECT u.username, u.displayName, r.code as roleCode, r.name as roleName, d.name as department, po.name as position
FROM [User] u
JOIN [UserRole] ur ON ur.userId=u.id AND ur.tenantId=@tenantId
JOIN [Role] r ON r.id=ur.roleId
LEFT JOIN [OrganizationAssignment] oa ON oa.userId=u.id AND oa.isActive=1 AND oa.isPrimary=1
LEFT JOIN [OrganizationDepartment] d ON d.id=oa.departmentId
LEFT JOIN [OrganizationPosition] po ON po.id=oa.positionId
WHERE r.code LIKE 'tech_%' ORDER BY r.code, u.username;
