SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET NOCOUNT ON;
PRINT '=== WIPE DEVICES V2 (with FK junction) ===';
BEGIN TRY
  BEGIN TRANSACTION;
  -- Junction first
  IF OBJECT_ID('documents_document_relatedDevices') IS NOT NULL BEGIN DELETE FROM documents_document_relatedDevices; PRINT 'documents_document_relatedDevices wiped'; END
  IF OBJECT_ID('documents_document') IS NOT NULL BEGIN DELETE FROM documents_document; PRINT 'documents_document wiped'; END

  -- Children
  IF OBJECT_ID('DeviceBom') IS NOT NULL BEGIN DELETE FROM DeviceBom; PRINT 'DeviceBom wiped'; END
  IF OBJECT_ID('DeviceAssignment') IS NOT NULL BEGIN DELETE FROM DeviceAssignment; PRINT 'DeviceAssignment wiped'; END
  IF OBJECT_ID('DeviceSpecification') IS NOT NULL BEGIN DELETE FROM DeviceSpecification; PRINT 'DeviceSpecification wiped'; END
  IF OBJECT_ID('DeviceHistory') IS NOT NULL BEGIN DELETE FROM DeviceHistory; PRINT 'DeviceHistory wiped'; END
  IF OBJECT_ID('AssetMovement') IS NOT NULL BEGIN DELETE FROM AssetMovement; PRINT 'AssetMovement wiped'; END
  IF OBJECT_ID('PartReservation') IS NOT NULL BEGIN DELETE FROM PartReservation; PRINT 'PartReservation wiped'; END
  IF OBJECT_ID('PartTransaction') IS NOT NULL BEGIN DELETE FROM PartTransaction; PRINT 'PartTransaction wiped'; END
  IF OBJECT_ID('InspectionRecord') IS NOT NULL BEGIN DELETE FROM InspectionRecord; PRINT 'InspectionRecord wiped'; END
  IF OBJECT_ID('InspectionTemplate') IS NOT NULL BEGIN DELETE FROM InspectionTemplate; PRINT 'InspectionTemplate wiped'; END
  IF OBJECT_ID('PmExecution') IS NOT NULL BEGIN DELETE FROM PmExecution; PRINT 'PmExecution wiped'; END
  IF OBJECT_ID('PmPlan') IS NOT NULL BEGIN DELETE FROM PmPlan; PRINT 'PmPlan wiped'; END

  IF OBJECT_ID('Device') IS NOT NULL BEGIN DELETE FROM Device; PRINT 'Device wiped'; END
  IF OBJECT_ID('SparePart') IS NOT NULL BEGIN DELETE FROM SparePart; PRINT 'SparePart wiped'; END
  IF OBJECT_ID('MaintenancePersonnel') IS NOT NULL BEGIN DELETE FROM MaintenancePersonnel; PRINT 'MaintenancePersonnel wiped'; END
  IF OBJECT_ID('MaintenanceLocation') IS NOT NULL BEGIN DELETE FROM MaintenanceLocation; PRINT 'MaintenanceLocation wiped'; END

  COMMIT TRANSACTION;
  PRINT '=== COMMIT OK ===';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
  PRINT ERROR_MESSAGE();
  THROW;
END CATCH
SELECT 'Device' as tbl, COUNT(*) FROM Device UNION ALL SELECT 'MaintenanceLocation', COUNT(*) FROM MaintenanceLocation UNION ALL SELECT 'SparePart', COUNT(*) FROM SparePart;
PRINT 'DONE';
