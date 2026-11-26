-- v4: seed OrganizationAccessRule for positions with 0 rules (bosses etc)
-- HEAD(level>=80)->team, MGR(level>=100)->all, SUPERVISOR(60)->team, SPECIALIST(40), TECHNICIAN(<=35)->own
-- NO password/UserRole/department change. Idempotent (skips existing cells).
SET QUOTED_IDENTIFIER ON; SET ANSI_NULLS ON; SET NOCOUNT ON;
PRINT '=== v4 start ===';
BEGIN TRY
  BEGIN TRANSACTION;

  DECLARE @rules TABLE(capability NVARCHAR(40), action NVARCHAR(16), scope NVARCHAR(16));
  DECLARE @posId CHAR(32), @posLevel INT, @tenant CHAR(32);

  DECLARE c CURSOR FOR
    SELECT p.id, p.level, p.tenantId FROM OrganizationPosition p
    WHERE NOT EXISTS (SELECT 1 FROM OrganizationAccessRule r WHERE r.positionId=p.id AND r.isActive=1);
  OPEN c; FETCH NEXT FROM c INTO @posId,@posLevel,@tenant;
  WHILE @@FETCH_STATUS=0
  BEGIN
    DELETE FROM @rules;
    IF @posLevel>=100
    BEGIN
      INSERT INTO @rules VALUES
      ('workOrder','view','all'),('workOrder','create','all'),('workOrder','edit','all'),('workOrder','delete','all'),('workOrder','approve','all'),('workOrder','assign','all'),('workOrder','close','all'),('workOrder','export','all'),('workOrder','escalate','all'),
      ('device','view','all'),('device','create','all'),('device','edit','all'),('device','export','all'),
      ('preventiveMaintenance','view','all'),('preventiveMaintenance','create','all'),('preventiveMaintenance','edit','all'),
      ('inventory','view','all'),('inventory','export','all'),
      ('purchaseRequisition','view','all'),('purchaseRequisition','create','all'),('purchaseRequisition','approve','all'),
      ('permitToWork','view','all'),('permitToWork','create','all'),
      ('report','view','all'),('report','export','all'),
      ('organizationUnit','view','all'),('organizationUnit','edit','all'),
      ('unitMembers','view','all'),('unitMembers','create','all'),('unitMembers','edit','all'),('unitMembers','delete','all');
    END
    ELSE IF @posLevel>=80
    BEGIN
      INSERT INTO @rules VALUES
      ('workOrder','view','team'),('workOrder','create','team'),('workOrder','edit','team'),('workOrder','approve','team'),('workOrder','assign','team'),('workOrder','close','team'),('workOrder','export','team'),('workOrder','escalate','own'),
      ('device','view','team'),('device','edit','team'),
      ('preventiveMaintenance','view','team'),('preventiveMaintenance','create','team'),('preventiveMaintenance','edit','team'),
      ('inventory','view','all'),
      ('purchaseRequisition','view','team'),('purchaseRequisition','create','team'),
      ('permitToWork','view','team'),('permitToWork','create','team'),
      ('report','view','team'),('report','export','team'),
      ('organizationUnit','view','team'),('organizationUnit','edit','team'),
      ('unitMembers','view','team');
    END
    ELSE IF @posLevel>=60
    BEGIN
      INSERT INTO @rules VALUES
      ('workOrder','view','team'),('workOrder','create','team'),('workOrder','edit','team'),('workOrder','assign','team'),('workOrder','close','team'),('workOrder','escalate','team'),
      ('device','view','department'),('preventiveMaintenance','view','department'),('inventory','view','all'),
      ('purchaseRequisition','view','team'),('purchaseRequisition','create','team'),
      ('permitToWork','view','team'),('permitToWork','create','team'),('permitToWork','assign','team'),
      ('report','view','team');
    END
    ELSE IF @posLevel>=40
    BEGIN
      INSERT INTO @rules VALUES
      ('workOrder','view','department'),('workOrder','create','own'),('workOrder','edit','own'),('workOrder','escalate','own'),
      ('device','view','department'),('preventiveMaintenance','view','department'),('inventory','view','all'),
      ('permitToWork','view','department'),('permitToWork','create','own'),('report','view','department');
    END
    ELSE
    BEGIN
      INSERT INTO @rules VALUES
      ('workOrder','view','own'),('workOrder','edit','own'),('workOrder','escalate','own'),
      ('device','view','department'),('inventory','view','all'),
      ('permitToWork','view','own'),('permitToWork','create','own'),('permitToWork','assign','own');
    END

    INSERT INTO OrganizationAccessRule (id,tenantId,createdAt,updatedAt,positionId,departmentId,capability,action,scope,isActive,updatedByUserId,updatedByName)
    SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), @tenant, GETDATE(), GETDATE(), @posId, NULL, capability, action, scope, 1, NULL, N'v4-seed'
    FROM @rules r
    WHERE NOT EXISTS (SELECT 1 FROM OrganizationAccessRule x WHERE x.positionId=@posId AND x.departmentId IS NULL AND x.capability=r.capability AND x.action=r.action AND x.isActive=1);

    FETCH NEXT FROM c INTO @posId,@posLevel,@tenant;
  END
  CLOSE c; DEALLOCATE c;

  PRINT '--- Rules per position after v4 ---';
  SELECT p.code, p.level, COUNT(r.id) AS ruleCount
  FROM OrganizationPosition p LEFT JOIN OrganizationAccessRule r ON r.positionId=p.id AND r.isActive=1
  GROUP BY p.code,p.level ORDER BY p.level DESC, p.code;
  PRINT '--- Boss scopes sample (Abbas POS_03) ---';
  SELECT p.code, r.capability, r.action, r.scope
  FROM OrganizationAccessRule r JOIN OrganizationPosition p ON p.id=r.positionId
  WHERE p.code='POS_03' ORDER BY r.capability, r.action;

  COMMIT TRANSACTION;
  PRINT 'COMMIT OK v4';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
  PRINT 'ROLLBACK: '+ERROR_MESSAGE(); THROW;
END CATCH
