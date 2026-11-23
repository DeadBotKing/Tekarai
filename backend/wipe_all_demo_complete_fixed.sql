SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET ANSI_PADDING ON;
SET ANSI_WARNINGS ON;
SET CONCAT_NULL_YIELDS_NULL ON;
SET NOCOUNT ON;
PRINT '=== FULL DEMO WIPE START ===';

-- Show counts before
PRINT '--- Counts before ---';
BEGIN TRY
  SELECT 'WorkOrder' as tbl, COUNT(*) FROM WorkOrder UNION ALL
  SELECT 'ProcurementRequisition', COUNT(*) FROM ProcurementRequisition UNION ALL
  SELECT 'Task', COUNT(*) FROM Task;
END TRY BEGIN CATCH PRINT 'Some tables missing, continuing'; END CATCH

BEGIN TRY
  BEGIN TRANSACTION;

  -- 1. WorkOrders (children first)
  IF OBJECT_ID('WorkOrderPartUsage') IS NOT NULL BEGIN DELETE FROM WorkOrderPartUsage; PRINT '1/7 WorkOrderPartUsage wiped'; END
  IF OBJECT_ID('WorkOrderLabourEntry') IS NOT NULL BEGIN DELETE FROM WorkOrderLabourEntry; PRINT 'WorkOrderLabourEntry wiped'; END
  IF OBJECT_ID('WorkTimer') IS NOT NULL BEGIN DELETE FROM WorkTimer; PRINT 'WorkTimer wiped'; END
  IF OBJECT_ID('WorkOrderHistory') IS NOT NULL BEGIN DELETE FROM WorkOrderHistory; PRINT 'WorkOrderHistory wiped'; END
  IF OBJECT_ID('WorkOrder') IS NOT NULL BEGIN DELETE FROM WorkOrder; PRINT 'WorkOrder wiped'; END

  -- 2. Procurement
  IF OBJECT_ID('ProcurementPurchaseOrderLine') IS NOT NULL BEGIN DELETE FROM ProcurementPurchaseOrderLine; PRINT 'ProcurementPurchaseOrderLine wiped'; END
  IF OBJECT_ID('ProcurementPurchaseOrder') IS NOT NULL BEGIN DELETE FROM ProcurementPurchaseOrder; PRINT 'ProcurementPurchaseOrder wiped'; END
  IF OBJECT_ID('ProcurementPurchaseReturnLine') IS NOT NULL BEGIN DELETE FROM ProcurementPurchaseReturnLine; PRINT 'ProcurementPurchaseReturnLine wiped'; END
  IF OBJECT_ID('ProcurementPurchaseReturn') IS NOT NULL BEGIN DELETE FROM ProcurementPurchaseReturn; PRINT 'ProcurementPurchaseReturn wiped'; END
  IF OBJECT_ID('ProcurementRequisitionLine') IS NOT NULL BEGIN DELETE FROM ProcurementRequisitionLine; PRINT 'ProcurementRequisitionLine wiped'; END
  IF OBJECT_ID('ProcurementRequisition') IS NOT NULL BEGIN DELETE FROM ProcurementRequisition; PRINT 'ProcurementRequisition wiped'; END

  -- 3. Tasks & Projects
  IF OBJECT_ID('Task') IS NOT NULL BEGIN DELETE FROM Task; PRINT 'Task wiped'; END
  IF OBJECT_ID('ProjectTask') IS NOT NULL BEGIN DELETE FROM ProjectTask; PRINT 'ProjectTask wiped'; END
  IF OBJECT_ID('Project') IS NOT NULL BEGIN DELETE FROM Project; PRINT 'Project wiped'; END

  -- 4. Maintenance calendars/meters
  IF OBJECT_ID('MaintenanceWorkCalendar') IS NOT NULL BEGIN DELETE FROM MaintenanceWorkCalendar; PRINT 'MaintenanceWorkCalendar wiped'; END
  IF OBJECT_ID('MaintenanceWorkShift') IS NOT NULL BEGIN DELETE FROM MaintenanceWorkShift; PRINT 'MaintenanceWorkShift wiped'; END
  IF OBJECT_ID('MeterReading') IS NOT NULL BEGIN DELETE FROM MeterReading; PRINT 'MeterReading wiped'; END
  IF OBJECT_ID('Meter') IS NOT NULL BEGIN DELETE FROM Meter; PRINT 'Meter wiped'; END
  IF OBJECT_ID('SafetyPermitToWork') IS NOT NULL BEGIN DELETE FROM SafetyPermitToWork; PRINT 'SafetyPermitToWork wiped'; END

  -- 5. Equipment / Buildings / Placements
  IF OBJECT_ID('AssetHierarchy') IS NOT NULL BEGIN DELETE FROM AssetHierarchy; PRINT 'AssetHierarchy wiped'; END
  IF OBJECT_ID('EquipmentPlacement') IS NOT NULL BEGIN DELETE FROM EquipmentPlacement; PRINT 'EquipmentPlacement wiped'; END
  IF OBJECT_ID('MaintenanceEquipment') IS NOT NULL BEGIN DELETE FROM MaintenanceEquipment; PRINT 'MaintenanceEquipment wiped'; END
  IF OBJECT_ID('Asset') IS NOT NULL BEGIN DELETE FROM Asset; PRINT 'Asset wiped'; END
  IF OBJECT_ID('MaintenanceLocation') IS NOT NULL BEGIN DELETE FROM MaintenanceLocation; PRINT 'MaintenanceLocation wiped'; END
  IF OBJECT_ID('Location') IS NOT NULL BEGIN DELETE FROM Location; PRINT 'Location wiped'; END
  IF OBJECT_ID('Building') IS NOT NULL BEGIN DELETE FROM Building; PRINT 'Building wiped'; END
  IF OBJECT_ID('Site') IS NOT NULL BEGIN DELETE FROM Site; PRINT 'Site wiped'; END

  COMMIT TRANSACTION;
  PRINT '=== COMMIT OK - ALL DEMO WIPED ===';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
  PRINT '=== ROLLBACK ON ERROR ===';
  PRINT ERROR_MESSAGE();
  THROW;
END CATCH

PRINT '--- After ---';
SELECT 'Users' as kept, COUNT(*) FROM [User] WHERE deletedAt IS NULL UNION ALL
SELECT 'Roles', COUNT(*) FROM Role UNION ALL
SELECT 'Departments', COUNT(*) FROM OrganizationDepartment;
PRINT 'DONE. Run iisreset';
