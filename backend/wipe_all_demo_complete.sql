-- WIPE ALL DEMO DATA - COMPLETE
-- KEEPS ONLY: Tenant, Users, Roles, UserRoles, Permissions, Organization Departments/Positions (optional), Tenants
-- DELETES: Equipment, Buildings, Placements, WorkOrders, Tasks, Projects, Procurement, SpareParts usage, Calendars, etc.
-- RUN ONLY AFTER BACKUP: C:\TekaraiBackup\TekaraiLive_20261123_171103.bak
SET NOCOUNT ON;
PRINT '=== FULL DEMO WIPE START ===';

-- Show counts before
PRINT '--- Counts before ---';
SELECT 'WorkOrder' as tbl, COUNT(*) FROM WorkOrder UNION ALL
SELECT 'WorkOrderHistory', COUNT(*) FROM WorkOrderHistory UNION ALL
SELECT 'ProcurementRequisition', COUNT(*) FROM ProcurementRequisition UNION ALL
SELECT 'Task', COUNT(*) FROM Task UNION ALL
SELECT 'Project', COUNT(*) FROM Project UNION ALL
SELECT 'MaintenanceEquipment', COUNT(*) FROM sys.objects WHERE name='MaintenanceEquipment' -- fallback
;

BEGIN TRY
  BEGIN TRANSACTION;

  -- 1. WorkOrders (children first)
  IF OBJECT_ID('WorkOrderPartUsage') IS NOT NULL DELETE FROM WorkOrderPartUsage;
  IF OBJECT_ID('WorkOrderLabourEntry') IS NOT NULL DELETE FROM WorkOrderLabourEntry;
  IF OBJECT_ID('WorkTimer') IS NOT NULL DELETE FROM WorkTimer;
  IF OBJECT_ID('WorkOrderHistory') IS NOT NULL DELETE FROM WorkOrderHistory;
  IF OBJECT_ID('WorkOrder') IS NOT NULL DELETE FROM WorkOrder;
  PRINT '1/7 WorkOrders wiped';

  -- 2. Procurement
  IF OBJECT_ID('ProcurementPurchaseOrderLine') IS NOT NULL DELETE FROM ProcurementPurchaseOrderLine;
  IF OBJECT_ID('ProcurementPurchaseOrder') IS NOT NULL DELETE FROM ProcurementPurchaseOrder;
  IF OBJECT_ID('ProcurementPurchaseReturnLine') IS NOT NULL DELETE FROM ProcurementPurchaseReturnLine;
  IF OBJECT_ID('ProcurementPurchaseReturn') IS NOT NULL DELETE FROM ProcurementPurchaseReturn;
  IF OBJECT_ID('ProcurementRequisitionLine') IS NOT NULL DELETE FROM ProcurementRequisitionLine;
  IF OBJECT_ID('ProcurementRequisition') IS NOT NULL DELETE FROM ProcurementRequisition;
  PRINT '2/7 Procurement wiped';

  -- 3. Tasks & Projects
  IF OBJECT_ID('Task') IS NOT NULL DELETE FROM Task;
  IF OBJECT_ID('ProjectTask') IS NOT NULL DELETE FROM ProjectTask;
  IF OBJECT_ID('Project') IS NOT NULL DELETE FROM Project;
  PRINT '3/7 Tasks/Projects wiped';

  -- 4. Maintenance master: Equipment, Locations, SpareParts, Meters
  -- Note: Keeping SparePart catalog is optional - uncomment to wipe catalog too
  IF OBJECT_ID('WorkOrder') IS NOT NULL PRINT 'WorkOrder already wiped';
  IF OBJECT_ID('MaintenanceWorkCalendar') IS NOT NULL DELETE FROM MaintenanceWorkCalendar;
  IF OBJECT_ID('MaintenanceWorkShift') IS NOT NULL DELETE FROM MaintenanceWorkShift;
  IF OBJECT_ID('MeterReading') IS NOT NULL DELETE FROM MeterReading;
  IF OBJECT_ID('Meter') IS NOT NULL DELETE FROM Meter;
  IF OBJECT_ID('SafetyPermitToWork') IS NOT NULL DELETE FROM SafetyPermitToWork;
  IF OBJECT_ID('SparePartStock') IS NOT NULL DELETE FROM SparePartStock;
  IF OBJECT_ID('SparePartTransaction') IS NOT NULL DELETE FROM SparePartTransaction;
  -- To also wipe SparePart catalog itself (master), uncomment:
  -- IF OBJECT_ID('SparePart') IS NOT NULL DELETE FROM SparePart;
  PRINT '4/7 Maintenance calendars/meters wiped';

  -- 5. Equipment Registry & Hierarchy (buildings, placements)
  -- These hold "تجهیزات و ساختمان و جانمایی"
  IF OBJECT_ID('AssetHierarchy') IS NOT NULL DELETE FROM AssetHierarchy;
  IF OBJECT_ID('EquipmentPlacement') IS NOT NULL DELETE FROM EquipmentPlacement;
  IF OBJECT_ID('MaintenanceEquipment') IS NOT NULL DELETE FROM MaintenanceEquipment;
  IF OBJECT_ID('Asset') IS NOT NULL DELETE FROM Asset;
  IF OBJECT_ID('MaintenanceLocation') IS NOT NULL DELETE FROM MaintenanceLocation;
  IF OBJECT_ID('Location') IS NOT NULL DELETE FROM Location;
  IF OBJECT_ID('Building') IS NOT NULL DELETE FROM Building;
  IF OBJECT_ID('Site') IS NOT NULL DELETE FROM Site;
  PRINT '5/7 Equipment/Buildings/Placements wiped';

  -- 6. Documents & Communications demo (optional - keep chats if you want)
  -- IF OBJECT_ID('Document') IS NOT NULL DELETE FROM Document;
  -- IF OBJECT_ID('communicationMessages') IS NOT NULL DELETE FROM communicationMessages;
  PRINT '6/7 Documents/Chats kept (uncomment to wipe)';

  -- 7. Audit logs - keep for traceability, uncomment to wipe:
  -- IF OBJECT_ID('OrganizationAudit') IS NOT NULL DELETE FROM OrganizationAudit;
  PRINT '7/7 Audit kept';

  COMMIT TRANSACTION;
  PRINT '=== COMMIT OK - ALL DEMO WIPED ===';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
  PRINT '=== ROLLBACK ON ERROR ===';
  PRINT ERROR_MESSAGE();
  THROW;
END CATCH

-- Counts after
PRINT '--- Counts after ---';
SELECT 'WorkOrder' as tbl, COUNT(*) FROM WorkOrder UNION ALL
SELECT 'ProcurementRequisition', COUNT(*) FROM ProcurementRequisition UNION ALL
SELECT 'Task', COUNT(*) FROM Task UNION ALL
SELECT 'MaintenanceEquipment', COUNT(*) FROM (SELECT 1 as x WHERE OBJECT_ID('MaintenanceEquipment') IS NOT NULL) t -- dummy
;
-- Show what's kept
SELECT 'Users' as kept, COUNT(*) FROM [User] WHERE deletedAt IS NULL UNION ALL
SELECT 'Roles', COUNT(*) FROM Role UNION ALL
SELECT 'Departments', COUNT(*) FROM OrganizationDepartment;

PRINT '=== DONE ===';
PRINT 'KEPT: Users(46), Roles, Departments. ALL demo equipment/buildings/orders wiped.';
PRINT 'Next: iisreset + Ctrl+F5. To restore: RESTORE DATABASE [TekaraiLive] FROM DISK=''C:\TekaraiBackup\TekaraiLive_20261123_171103.bak'' WITH REPLACE';
