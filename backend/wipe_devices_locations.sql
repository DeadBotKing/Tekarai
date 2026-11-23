SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET NOCOUNT ON;
PRINT '=== WIPE DEVICES/LOCATIONS/SPAREPARTS ===';
BEGIN TRY
  BEGIN TRANSACTION;

  -- Children first
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

  -- Core masters
  IF OBJECT_ID('Device') IS NOT NULL BEGIN DELETE FROM Device; PRINT 'Device wiped'; END
  IF OBJECT_ID('SparePart') IS NOT NULL BEGIN DELETE FROM SparePart; PRINT 'SparePart wiped'; END
  IF OBJECT_ID('MaintenancePersonnel') IS NOT NULL BEGIN DELETE FROM MaintenancePersonnel; PRINT 'MaintenancePersonnel wiped'; END
  IF OBJECT_ID('MaintenanceLocation') IS NOT NULL BEGIN DELETE FROM MaintenanceLocation; PRINT 'MaintenanceLocation wiped'; END

  COMMIT TRANSACTION;
  PRINT '=== COMMIT OK - DEVICES/LOCATIONS WIPED ===';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
  PRINT ERROR_MESSAGE();
  THROW;
END CATCH

SELECT 'Device' as kept, COUNT(*) FROM Device UNION ALL
SELECT 'MaintenanceLocation', COUNT(*) FROM MaintenanceLocation UNION ALL
SELECT 'SparePart', COUNT(*) FROM SparePart UNION ALL
SELECT 'PmPlan', COUNT(*) FROM PmPlan;
PRINT 'DONE. iisreset required';
