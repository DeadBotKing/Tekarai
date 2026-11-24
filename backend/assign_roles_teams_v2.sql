SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET NOCOUNT ON;
PRINT '=== Tekarai Roles+Teams v2 — correct schema, NO password change ===';

BEGIN TRY
  BEGIN TRANSACTION;

  -- Role IDs from inspect output (13 roles)
  DECLARE @r_maintenanceManager CHAR(32)='086b5a0756084e5d88de3e64a0e80c81';
  DECLARE @r_tech_director CHAR(32)='0c73506d2d7d475c83bb5d790fdae93c';
  DECLARE @r_tech_head CHAR(32)='b935c3883a80438eb7784bb5bd829ab8';
  DECLARE @r_tech_supervisor CHAR(32)='c2acd8d592a74fa38f918f1d3111627a';
  DECLARE @r_tech_specialist CHAR(32)='49a186f02030441fadb0521c2a18644f';
  DECLARE @r_tech_facility CHAR(32)='a7784d1648e8474c989657ec5369983e';
  DECLARE @r_maintenanceTech CHAR(32)='cc7548cc1bd7416a9eab01e9d8394a7c';
  DECLARE @r_tenantAdmin CHAR(32)='3ffaf92e9bb1475e9d7768331d4ff9c0';
  DECLARE @r_platformAdmin CHAR(32)='25aac6dfe3ee43bebf1c330e6e6f8467';

  -- Boss IDs (username = phone, no password touched)
  DECLARE @mehdi CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09129432012' OR displayName LIKE N'%مهدی یارمحمدی%');
  DECLARE @mostafa CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09120535494' OR displayName LIKE N'%مصطفی صفا%');
  DECLARE @mehrshad CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username LIKE '%8369891' OR displayName LIKE N'%مهرشاد کهریزی%');
  DECLARE @abbas CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09196189256' OR displayName LIKE N'%عباس فرخ%');
  DECLARE @ebrahim CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09113282043' OR displayName LIKE N'%ابراهیم محمدی%');
  PRINT 'Bosses:'; SELECT displayName,username FROM [User] WHERE id IN (@mehdi,@mostafa,@mehrshad,@abbas,@ebrahim);

  -- Ensure Mehdi stays tenantAdmin
  IF @mehdi IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@mehdi AND roleId=@r_tenantAdmin)
    INSERT INTO UserRole (id,userId,roleId,tenantId,scopeType,scopeRef,grantedAt)
    SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')),@mehdi,@r_tenantAdmin,tenantId,'TENANT','',GETDATE() FROM [User] WHERE id=@mehdi;

  -- Clear old roles for bosses (keep tenantAdmin/platformAdmin)
  DECLARE @bossList TABLE(uid CHAR(32)); INSERT INTO @bossList VALUES (@mostafa),(@mehrshad),(@abbas),(@ebrahim);
  DELETE FROM UserRole WHERE userId IN (SELECT uid FROM @bossList WHERE uid IS NOT NULL) AND roleId NOT IN (@r_tenantAdmin,@r_platformAdmin);
  -- Assign tech_head + maintenanceManager to bosses (two roles each)
  INSERT INTO UserRole (id,userId,roleId,tenantId,scopeType,scopeRef,grantedAt)
  SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')),b.uid,@r_tech_head,u.tenantId,'TENANT','',GETDATE() FROM @bossList b JOIN [User] u ON u.id=b.uid WHERE b.uid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole ur WHERE ur.userId=b.uid AND ur.roleId=@r_tech_head);
  INSERT INTO UserRole (id,userId,roleId,tenantId,scopeType,scopeRef,grantedAt)
  SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')),b.uid,@r_maintenanceManager,u.tenantId,'TENANT','',GETDATE() FROM @bossList b JOIN [User] u ON u.id=b.uid WHERE b.uid IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole ur WHERE ur.userId=b.uid AND ur.roleId=@r_maintenanceManager);
  PRINT 'Bosses -> tech_head + maintenanceManager';

  -- Staging for members: phone, nameLike, roleId, bossId
  DECLARE @a TABLE(phone NVARCHAR(20), nameLike NVARCHAR(100), roleId CHAR(32), boss CHAR(32));

  -- Team MOSTAFA 15 -> tech_supervisor / tech_specialist (all کارشناس/سرپرست)
  INSERT INTO @a VALUES
  (N'09184939450',N'%هادی قاسمی%',@r_tech_specialist,@mostafa),
  (N'09330146665',N'%آیهان حیدری%',@r_tech_specialist,@mostafa),
  (N'09002550821',N'%میلاد محمدی%',@r_tech_specialist,@mostafa),
  (N'09359959538',N'%مصطفی فرد%',@r_tech_supervisor,@mostafa),
  (N'09105952839',N'%احمد شهابی راد%',@r_tech_supervisor,@mostafa),
  (N'09358422007',N'%علی نعمتی%',@r_tech_specialist,@mostafa),
  (N'09127569668',N'%مرتضی رضایی مقدم%',@r_tech_specialist,@mostafa),
  (N'09128840364',N'%سجاد کهنسال%',@r_tech_supervisor,@mostafa),
  (N'09186230775',N'%میلاد رایگان%',@r_tech_specialist,@mostafa),
  (N'09183936442',N'%امیرحسین زلفی%',@r_tech_specialist,@mostafa),
  (N'09120262857',N'%جواد منعمی%',@r_tech_specialist,@mostafa),
  (N'09190522042',N'%فرزاد فرمانیان%',@r_tech_specialist,@mostafa),
  (N'09176563107',N'%سامان صارمی%',@r_tech_specialist,@mostafa),
  (N'09198720900',N'%احسان مروی%',@r_tech_specialist,@mostafa),
  (N'09193551129',N'%میثم حاصلی%',@r_tech_specialist,@mostafa);

  -- Team MEHRSHAD 7 -> tech_facility / maintenanceTechnician (برق)
  INSERT INTO @a VALUES
  (N'09185072143',N'%آرش حیدری%',@r_tech_facility,@mehrshad),
  (N'09370398323',N'%محمد چورکش%',@r_tech_facility,@mehrshad),
  (N'0933560513',N'%جواد امیرشاهی%',@r_maintenanceTech,@mehrshad),
  (N'09933181900',N'%دانیال امینی%',@r_tech_facility,@mehrshad),
  (N'09100823904',N'%بهروز رسولی%',@r_maintenanceTech,@mehrshad),
  (N'09123561023',N'%محمد جعفری%',@r_tech_facility,@mehrshad),
  (N'09223540245',N'%امیرحسین حاجی لو%',@r_tech_facility,@mehrshad);

  -- Team ABBAS 9 -> tech_facility (Hvac/تاسیسات)
  INSERT INTO @a VALUES
  (N'09189469465',N'%مجید نظری%',@r_tech_facility,@abbas),
  (N'09196542494',N'%ناصر سالاری%',@r_tech_facility,@abbas),
  (N'09376557247',N'%علی زمانی%',@r_tech_facility,@abbas),
  (N'09128554542',N'%علی پورعوض%',@r_tech_facility,@abbas),
  (N'09398308536',N'%یونس فراهانی%',@r_tech_facility,@abbas),
  (N'09378985255',N'%حسین کرد%',@r_tech_facility,@abbas),
  (N'0936853529',N'%اسعد هلالی%',@r_tech_facility,@abbas),
  (N'09116498513',N'%فرشاد رجبی%',@r_tech_facility,@abbas),
  (N'09116498513',N'%عماد رضانی%',@r_tech_facility,@abbas);

  -- Team EBRAHIM 4 -> tech_specialist
  INSERT INTO @a VALUES
  (N'09363822395',N'%کرمی شهبازی%',@r_tech_specialist,@ebrahim),
  (N'09193499439',N'%پیمان یاری%',@r_tech_specialist,@ebrahim),
  (N'09167453720',N'%حسن عین پور%',@r_tech_specialist,@ebrahim),
  (N'09195231690',N'%یونس صالح%',@r_tech_specialist,@ebrahim);

  -- Process each member: clear old roles (except admin), assign new role, set reportsToUserId
  DECLARE @ph NVARCHAR(20), @nm NVARCHAR(100), @rid CHAR(32), @boss CHAR(32);
  DECLARE c CURSOR FOR SELECT phone,nameLike,roleId,boss FROM @a;
  OPEN c; FETCH NEXT FROM c INTO @ph,@nm,@rid,@boss;
  WHILE @@FETCH_STATUS=0
  BEGIN
    DECLARE @uid CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username=@ph OR phone=@ph OR displayName LIKE @nm);
    IF @uid IS NOT NULL AND @uid NOT IN (@mehdi,@mostafa,@mehrshad,@abbas,@ebrahim)
    BEGIN
      DELETE FROM UserRole WHERE userId=@uid AND roleId NOT IN (@r_tenantAdmin,@r_platformAdmin);
      IF NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@uid AND roleId=@rid)
        INSERT INTO UserRole (id,userId,roleId,tenantId,scopeType,scopeRef,grantedAt)
        SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')),@uid,@rid,tenantId,'TENANT','',GETDATE() FROM [User] WHERE id=@uid;
      -- Team: set reportsToUserId in OrganizationAssignment
      IF @boss IS NOT NULL
      BEGIN
        IF EXISTS (SELECT 1 FROM OrganizationAssignment WHERE userId=@uid AND isPrimary=1 AND isActive=1)
          UPDATE OrganizationAssignment SET reportsToUserId=@boss, updatedAt=GETDATE() WHERE userId=@uid AND isPrimary=1 AND isActive=1;
        ELSE
          INSERT INTO OrganizationAssignment (id,tenantId,userId,userDisplayName,departmentId,positionId,isPrimary,isActive,reportsToUserId,startedAt,createdAt,updatedAt)
          SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), tenantId, @uid, displayName,
                 (SELECT TOP 1 departmentId FROM OrganizationAssignment WHERE userId=@boss),
                 (SELECT TOP 1 positionId FROM OrganizationAssignment WHERE userId=@uid),
                 1,1,@boss,GETDATE(),GETDATE(),GETDATE() FROM [User] WHERE id=@uid;
        PRINT 'Assigned '+@ph+' '+@nm;
      END
    END
    ELSE IF @uid IS NULL PRINT 'WARNING not found: '+@ph+' '+@nm;
    FETCH NEXT FROM c INTO @ph,@nm,@rid,@boss;
  END
  CLOSE c; DEALLOCATE c;

  PRINT '--- Verification roles ---';
  SELECT r.code, r.name, COUNT(*) cnt FROM UserRole ur JOIN Role r ON r.id=ur.roleId GROUP BY r.code,r.name ORDER BY r.code;
  PRINT '--- Team sizes (reportsTo) ---';
  SELECT b.displayName as boss, b.username, COUNT(*) as teamSize FROM OrganizationAssignment oa JOIN [User] b ON b.id=oa.reportsToUserId GROUP BY b.displayName,b.username ORDER BY teamSize DESC;
  PRINT '--- Mehdi sees all check ---';
  SELECT displayName,username FROM [User] WHERE id=@mehdi;

  COMMIT TRANSACTION;
  PRINT 'COMMIT OK — roles+teams v2, passwords untouched';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
  PRINT 'ROLLBACK: '+ERROR_MESSAGE(); THROW;
END CATCH
