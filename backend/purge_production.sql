-- purge_production.sql — پاکسازی کامل دیتای تستی روی SQL Server اصلی (Tekarai)
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
GO

PRINT '=== PURGE START ===';

-- 1) شناسایی کاربران محافظت‌شده
DECLARE @protected TABLE (id UNIQUEIDENTIFIER);
INSERT INTO @protected
SELECT id FROM [User] WHERE username IN ('platform-admin','platform_admin','admin','superadmin','root')
UNION
SELECT userId FROM [UserRole] WHERE roleId = (SELECT id FROM [Role] WHERE code='platformAdmin');

PRINT 'Protected users:';
SELECT username, displayName FROM [User] WHERE id IN (SELECT id FROM @protected);

-- 2) پاکسازی وابسته‌ها - ترتیب مهم (فرزندها اول)
PRINT 'Deleting dependent rows...';

-- Sessions / Memberships / Roles of test users
DELETE FROM [Session] WHERE userId NOT IN (SELECT id FROM @protected);
PRINT 'Sessions deleted';

DELETE FROM [TenantMembership] WHERE userId NOT IN (SELECT id FROM @protected);
PRINT 'Memberships deleted';

DELETE FROM [UserRole] WHERE userId NOT IN (SELECT id FROM @protected);
PRINT 'UserRoles deleted';

-- Organization assignments
DELETE FROM [OrganizationAssignment] WHERE userId NOT IN (SELECT id FROM @protected);
PRINT 'Org Assignments deleted';

-- Other app data - کامل پاک (ترتیب خیلی مهم نیست، FK ندارند یا cascade ندارند)
-- اگر جدولی وجود نداشت خطا را نادیده بگیر
BEGIN TRY DELETE FROM [OrganizationAudit]; PRINT 'Org Audit deleted'; END TRY BEGIN CATCH PRINT 'Skip Org Audit'; END CATCH
BEGIN TRY DELETE FROM [WorkOrderLabourEntry]; PRINT 'Labour deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrderPartUsage]; PRINT 'PartUsage deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrderHistory]; PRINT 'WOHistory deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [DeviceHistory]; PRINT 'DeviceHistory deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [WorkOrder]; PRINT 'WorkOrder deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Device]; PRINT 'Device deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [SparePart]; PRINT 'SparePart deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Project]; PRINT 'Project deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Task]; PRINT 'Task deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [ProcurementApproval]; PRINT 'ProcurementApproval deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [PurchaseRequisitionLine]; PRINT 'ReqLine deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [PurchaseRequisition]; PRINT 'Req deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [PurchaseOrderLine]; PRINT 'POLine deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [PurchaseOrder]; PRINT 'PO deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [Supplier]; PRINT 'Supplier deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [NotificationRecord]; PRINT 'Notifications deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [AuditEvent]; PRINT 'AuditEvent deleted'; END TRY BEGIN CATCH END CATCH
BEGIN TRY DELETE FROM [SecurityEvent]; PRINT 'SecurityEvent deleted'; END TRY BEGIN CATCH END CATCH

-- 3) در نهایت خود کاربران تستی
DECLARE @before INT = (SELECT COUNT(*) FROM [User]);
DELETE FROM [User] WHERE id NOT IN (SELECT id FROM @protected);
DECLARE @after INT = (SELECT COUNT(*) FROM [User]);
PRINT CONCAT('Users: before=', @before, ' after=', @after, ' deleted=', @before-@after);

PRINT '=== PURGE DONE - فقط platform-admin باقی ماند ===';
-- نمایش باقی‌مانده
SELECT COUNT(*) AS RemainingUsers FROM [User];
SELECT username, displayName, status FROM [User];
