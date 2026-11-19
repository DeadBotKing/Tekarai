SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
GO
PRINT '=== PURGE START SIMPLE v2 ===';

-- 1) حذف وابسته‌ها - با بررسی وجود جدول
IF EXISTS (SELECT * FROM sys.tables WHERE name='Session')
BEGIN
  DELETE FROM [Session] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Sessions deleted';
END

IF EXISTS (SELECT * FROM sys.tables WHERE name='TenantMembership')
BEGIN
  DELETE FROM [TenantMembership] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Memberships deleted';
END

IF EXISTS (SELECT * FROM sys.tables WHERE name='UserRole')
BEGIN
  DELETE FROM [UserRole] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'UserRoles deleted';
END

IF EXISTS (SELECT * FROM sys.tables WHERE name='OrganizationAssignment')
BEGIN
  DELETE FROM [OrganizationAssignment] WHERE userId IN (SELECT id FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root'));
  PRINT 'Org Assignments deleted';
END
ELSE PRINT 'Org Assignment table not exists - skip';

-- سایر داده‌ها - هر کدام با چک وجود
IF EXISTS (SELECT * FROM sys.tables WHERE name='OrganizationAudit') BEGIN DELETE FROM [OrganizationAudit]; PRINT 'Org Audit deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='WorkOrder') BEGIN DELETE FROM [WorkOrder]; PRINT 'WorkOrder deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='Device') BEGIN DELETE FROM [Device]; PRINT 'Device deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='Project') BEGIN DELETE FROM [Project]; PRINT 'Project deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='Task') BEGIN DELETE FROM [Task]; PRINT 'Task deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='AuditEvent') BEGIN DELETE FROM [AuditEvent]; PRINT 'AuditEvent deleted'; END
IF EXISTS (SELECT * FROM sys.tables WHERE name='SecurityEvent') BEGIN DELETE FROM [SecurityEvent]; PRINT 'SecurityEvent deleted'; END

-- 2) خود کاربران تستی - مهم‌ترین بخش
DECLARE @before INT = (SELECT COUNT(*) FROM [User]);
DELETE FROM [User] WHERE username NOT IN ('platform-admin','platform_admin','admin','superadmin','root');
DECLARE @after INT = (SELECT COUNT(*) FROM [User]);
PRINT CONCAT('Users: before=', @before, ' after=', @after, ' deleted=', @before-@after);

PRINT '=== PURGE DONE ===';
SELECT COUNT(*) AS RemainingUsers FROM [User];
SELECT username, displayName, status FROM [User];
