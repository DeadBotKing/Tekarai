SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
GO
PRINT '=== PURGE START SIMPLE ===';

-- فقط با نام کاربری محافظت می‌کنیم (کافی است)
PRINT 'Protected: platform-admin';

-- 1) حذف وابسته‌ها با subquery مستقیم روی User (بدون متغیر)
BEGIN TRY
  DELETE FROM [Session] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Sessions deleted';
END TRY BEGIN CATCH PRINT CONCAT('Sessions skip: ', ERROR_MESSAGE()); END CATCH

BEGIN TRY
  DELETE FROM [TenantMembership] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Memberships deleted';
END TRY BEGIN CATCH PRINT CONCAT('Membership skip: ', ERROR_MESSAGE()); END CATCH

BEGIN TRY
  DELETE FROM [UserRole] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'UserRoles deleted';
END TRY BEGIN CATCH PRINT CONCAT('UserRole skip: ', ERROR_MESSAGE()); END CATCH

BEGIN TRY
  DELETE FROM [OrganizationAssignment] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Org Assignments deleted';
END TRY BEGIN CATCH PRINT CONCAT('OrgAssign skip: ', ERROR_MESSAGE()); END CATCH

-- سایر داده‌ها
BEGIN TRY DELETE FROM [OrganizationAudit]; PRINT 'Org Audit deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrderLabourEntry]; PRINT 'Labour deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrderPartUsage]; PRINT 'PartUsage deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrderHistory]; PRINT 'WOHistory deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [DeviceHistory]; PRINT 'DeviceHistory deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrder]; PRINT 'WorkOrder deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Device]; PRINT 'Device deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Project]; PRINT 'Project deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Task]; PRINT 'Task deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [AuditEvent]; PRINT 'AuditEvent deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [SecurityEvent]; PRINT 'SecurityEvent deleted'; END TRY BEGIN CATCH END CATCH

-- 2) خود کاربران تستی
DECLARE @before INT = (SELECT COUNT(*) FROM [User]);
BEGIN TRY
  DELETE FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root');
  PRINT 'Users deleted';
END TRY BEGIN CATCH PRINT CONCAT('Users error: ', ERROR_MESSAGE()); END CATCH
DECLARE @after INT = (SELECT COUNT(*) FROM [User]);
PRINT CONCAT('Users: before=', @before, ' after=', @after, ' deleted=', @before-@after);

PRINT '=== PURGE DONE ===';
SELECT COUNT(*) AS RemainingUsers FROM [User];
SELECT username, displayName, status FROM [User];
