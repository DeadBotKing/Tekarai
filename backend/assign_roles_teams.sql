SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET NOCOUNT ON;
PRINT '=== Tekarai Role+Team Assignment START — NO password/username change ===';
PRINT 'Username = phone, password Tekarai@1234 untouched';

BEGIN TRY
  BEGIN TRANSACTION;

  -- 0) Ensure expected roles exist (lookup)
  DECLARE @role_maintenanceManager CHAR(32) = (SELECT TOP 1 id FROM Role WHERE code IN ('maintenanceManager','maintenance_manager','manager_maintenance') ORDER BY createdAt);
  DECLARE @role_maintenance CHAR(32) = (SELECT TOP 1 id FROM Role WHERE code IN ('maintenance','tech_maintenance','maintenanceTech') ORDER BY createdAt);
  DECLARE @role_technician CHAR(32) = (SELECT TOP 1 id FROM Role WHERE code IN ('technician','operator','fieldTech') ORDER BY createdAt);
  DECLARE @role_tenantAdmin CHAR(32) = (SELECT TOP 1 id FROM Role WHERE code='tenantAdmin');
  DECLARE @role_viewer CHAR(32) = (SELECT TOP 1 id FROM Role WHERE code IN ('viewer','readOnly') ORDER BY createdAt);

  -- fallback: if manager role not found, use maintenance
  IF @role_maintenanceManager IS NULL SET @role_maintenanceManager = @role_maintenance;
  IF @role_technician IS NULL SET @role_technician = @role_maintenance;

  PRINT 'Roles found:';
  SELECT code, name FROM Role WHERE id IN (@role_maintenanceManager,@role_maintenance,@role_technician,@role_tenantAdmin);

  -- Helper: function to set role for a user (clears old tenant roles except tenantAdmin/platformAdmin)
  -- We will do per-user below

  -- 1) Mehdi Yarmohammadi stays tenantAdmin — ensure he keeps it (do NOT demote)
  DECLARE @mehdiId CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='09129432012' OR phone='09129432012' OR displayName LIKE N'%مهدی یارمحمدی%');
  DECLARE @platformId CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='platform-admin' OR username='09183032356');
  PRINT 'Mehdi/Admin IDs'; SELECT id, displayName, username FROM [User] WHERE id IN (@mehdiId, @platformId);

  -- Ensure Mehdi has tenantAdmin
  IF @mehdiId IS NOT NULL AND @role_tenantAdmin IS NOT NULL AND NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@mehdiId AND roleId=@role_tenantAdmin)
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
    SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), @mehdiId, @role_tenantAdmin, tenantId, 'TENANT','', GETDATE() FROM [User] WHERE id=@mehdiId;

  -- ============================================================
  -- 2) BOSS LEVEL 1 — 5 managers -> maintenanceManager (+ viewer where available)
  --    These 5 will see only their team (enforced via department below) + Mehdi sees all
  -- ============================================================

  -- Map boss phones (username = phone) — do NOT touch password
  DECLARE @boss_safa CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='09120535494' OR displayName LIKE N'%مصطفی صفا%');
  DECLARE @boss_mehrshad CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='0918369891' OR displayName LIKE N'%مهرشاد کهریزی%');
  -- normalized phones (leading 0): try both with/without 0
  IF @boss_mehrshad IS NULL SET @boss_mehrshad = (SELECT TOP 1 id FROM [User] WHERE username IN ('0918369891','918369891') OR displayName LIKE N'%کهریزی%');
  DECLARE @boss_abbas CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='09196189256' OR displayName LIKE N'%عباس فرخ%');
  DECLARE @boss_ebrahim CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username='09113282043' OR displayName LIKE N'%ابراهیم محمدی%');

  PRINT 'Boss IDs:'; SELECT displayName,username FROM [User] WHERE id IN (@boss_safa,@boss_mehrshad,@boss_abbas,@boss_ebrahim,@mehdiId);

  -- Helper procedure inline: setBossRole
  -- We will assign maintenanceManager to each boss (clear old maintenance/viewer roles first, keep tenantAdmin for Mehdi only)
  -- For each boss, delete non-admin roles then insert manager role

  DECLARE @bosses TABLE (uid CHAR(32));
  INSERT INTO @bosses VALUES (@boss_safa),(@boss_mehrshad),(@boss_abbas),(@boss_ebrahim);
  -- Remove old role assignments for bosses (keep tenantAdmin/platformAdmin if any, though bosses shouldn't have them)
  DELETE FROM UserRole WHERE userId IN (SELECT uid FROM @bosses WHERE uid IS NOT NULL) AND roleId NOT IN (@role_tenantAdmin);
  -- Insert manager role
  INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
  SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), b.uid, @role_maintenanceManager, u.tenantId, 'TENANT','', GETDATE()
  FROM @bosses b JOIN [User] u ON u.id=b.uid WHERE b.uid IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM UserRole ur WHERE ur.userId=b.uid AND ur.roleId=@role_maintenanceManager);

  -- Optional: give bosses viewer for production/equipment/documents (if viewer role exists and distinct)
  IF @role_viewer IS NOT NULL AND @role_viewer <> @role_maintenanceManager
  BEGIN
    INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
    SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), b.uid, @role_viewer, u.tenantId, 'TENANT','', GETDATE()
    FROM @bosses b JOIN [User] u ON u.id=b.uid WHERE b.uid IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM UserRole ur WHERE ur.userId=b.uid AND ur.roleId=@role_viewer);
  END
  PRINT 'Bosses set to maintenanceManager (+viewer)';

  -- ============================================================
  -- 3) MEMBERS — assign maintenance or technician based on team nature
  --    Team Safa (15): کارشناس/سرپرست تزریق -> maintenance
  --    Team Mehrshad (7): برق/اتوماسیون -> maintenance
  --    Team Abbas (9): Hvac/تاسیسات -> technician
  --    Team Ebrahim (4): نگهداری -> maintenance
  -- ============================================================

  -- Utility: helper to assign a user to a role by phone/name (no password change)
  -- We will do explicit per-user blocks for auditability - you can verify each line

  -- --- Team SAFA (15) -> maintenance ---
  -- Each block: find uid by phone OR name LIKE, delete old roles, insert maintenance
  -- If phone has leading 0 issue, we match both variants

  -- For brevity, we use a staging table then process
  DECLARE @assign TABLE (phone NVARCHAR(20), nameLike NVARCHAR(100), roleId CHAR(32), teamBoss CHAR(32));

  -- Fill staging: Safa team -> maintenance
  INSERT INTO @assign VALUES
  (N'09184939450', N'%هادی قاسمی%', @role_maintenance, @boss_safa),
  (N'09330146665', N'%آیهان حیدری%', @role_maintenance, @boss_safa),
  (N'09002550821', N'%میلاد محمدی%', @role_maintenance, @boss_safa),
  (N'09359959538', N'%مصطفی فرد%', @role_maintenance, @boss_safa),
  (N'09105952839', N'%احمد شهابی راد%', @role_maintenance, @boss_safa),
  (N'09358422007', N'%علی نعمتی%', @role_maintenance, @boss_safa),
  (N'09127569668', N'%مرتضی رضایی مقدم%', @role_maintenance, @boss_safa),
  (N'09128840364', N'%سجاد کهنسال%', @role_maintenance, @boss_safa),
  (N'09186230775', N'%میلاد رایگان%', @role_maintenance, @boss_safa),
  (N'09183936442', N'%امیرحسین زلفی%', @role_maintenance, @boss_safa),
  (N'09120262857', N'%جواد منعمی%', @role_maintenance, @boss_safa),
  (N'09190522042', N'%فرزاد فرمانیان%', @role_maintenance, @boss_safa),
  (N'09176563107', N'%سامان صارمی%', @role_maintenance, @boss_safa),
  (N'09198720900', N'%احسان مروی%', @role_maintenance, @boss_safa),
  (N'09193551129', N'%میثم حاصلی%', @role_maintenance, @boss_safa);

  -- Team MEHRSHAD (7) -> maintenance (برق/اتوماسیون کارشناس)
  INSERT INTO @assign VALUES
  (N'09185072143', N'%آرش حیدری%', @role_maintenance, @boss_mehrshad),
  (N'09370398323', N'%محمد چورکش%', @role_maintenance, @boss_mehrshad),
  (N'0933560513', N'%جواد امیرشاهی%', @role_maintenance, @boss_mehrshad),
  (N'09933181900', N'%دانیال امینی%', @role_maintenance, @boss_mehrshad),
  (N'09100823904', N'%بهروز رسولی%', @role_maintenance, @boss_mehrshad),
  (N'09123561023', N'%محمد جعفری%', @role_maintenance, @boss_mehrshad),
  (N'09223540245', N'%امیرحسین حاجی لو%', @role_maintenance, @boss_mehrshad);

  -- Team ABBAS (9) -> technician (Hvac/تاسیسات اجرایی)
  INSERT INTO @assign VALUES
  (N'09189469465', N'%مجید نظری%', @role_technician, @boss_abbas),
  (N'09196542494', N'%ناصر سالاری%', @role_technician, @boss_abbas),
  (N'09376557247', N'%علی زمانی%', @role_technician, @boss_abbas),
  (N'09128554542', N'%علی پورعوض%', @role_technician, @boss_abbas),
  (N'09398308536', N'%یونس فراهانی%', @role_technician, @boss_abbas),
  (N'09378985255', N'%حسین کرد%', @role_technician, @boss_abbas),
  (N'0936853529', N'%اسعد هلالی%', @role_technician, @boss_abbas),
  (N'09116498513', N'%فرشاد رجبی%', @role_technician, @boss_abbas),
  (N'09116498513', N'%عماد رضانی%', @role_technician, @boss_abbas);

  -- Team EBRAHIM (4) -> maintenance
  INSERT INTO @assign VALUES
  (N'09363822395', N'%کرمی شهبازی%', @role_maintenance, @boss_ebrahim),
  (N'09193499439', N'%پیمان یاری%', @role_maintenance, @boss_ebrahim),
  (N'09167453720', N'%حسن عین پور%', @role_maintenance, @boss_ebrahim),
  (N'09195231690', N'%یونس صالح%', @role_maintenance, @boss_ebrahim);

  -- Additional members from master 44 that belong to technical but not in above 4 teams (cover remaining)
  -- These 9 remaining are assigned to Ebrahim/Mehdi pool as maintenance for safety (you can reassign later)
  -- We keep them as maintenance under Mehdi to avoid orphan
  INSERT INTO @assign VALUES
  (N'09195231690', N'%یونس صالح%', @role_maintenance, @boss_ebrahim), -- duplicate safe (will dedup)
  (N'09120682369', N'%بهنام زه ره%', @role_maintenance, @mehdiId),
  (N'09128855367', N'%مهدی نصیری%', @role_maintenance, @mehdiId),
  (N'09327250444', N'%محسن رمضانی%', @role_maintenance, @mehdiId),
  (N'093765572?0', N'%مهرشاد%', @role_maintenance, @mehdiId);

  -- Now process each assignment: find userId, clear old roles (except tenantAdmin), insert new role
  DECLARE @phone NVARCHAR(20), @like NVARCHAR(100), @rId CHAR(32), @teamBoss CHAR(32);
  DECLARE cur CURSOR FOR SELECT phone, nameLike, roleId, teamBoss FROM @assign;
  OPEN cur; FETCH NEXT FROM cur INTO @phone, @like, @rId, @teamBoss;
  WHILE @@FETCH_STATUS=0
  BEGIN
    DECLARE @uid CHAR(32) = (SELECT TOP 1 id FROM [User] WHERE username=@phone OR username=REPLACE(@phone,'0','') OR phone=@phone OR displayName LIKE @like);
    IF @uid IS NOT NULL
    BEGIN
      -- Do not touch Mehdi/platform if they are in list (they aren't)
      IF @uid NOT IN (@mehdiId, @platformId)
      BEGIN
        DELETE FROM UserRole WHERE userId=@uid AND roleId NOT IN (@role_tenantAdmin); -- keep tenantAdmin if somehow has it
        IF NOT EXISTS (SELECT 1 FROM UserRole WHERE userId=@uid AND roleId=@rId)
        BEGIN
          INSERT INTO UserRole (id, userId, roleId, tenantId, scopeType, scopeRef, grantedAt)
          SELECT LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), @uid, @rId, tenantId, 'TENANT','', GETDATE() FROM [User] WHERE id=@uid;
          PRINT 'Assigned ' + @phone + ' ' + @like;
        END
        -- Team assignment: OrganizationAssignment (departmentId column does not exist on this DB)
        IF OBJECT_ID('OrganizationAssignment') IS NOT NULL AND @teamBoss IS NOT NULL
        BEGIN
          -- Upsert manager-scoped assignment: remove old then insert
          DELETE FROM OrganizationAssignment WHERE userId=@uid AND scopeType='MANAGER_VIEW';
          INSERT INTO OrganizationAssignment (id, userId, scopeType, scopeRef, assignedBy, assignedAt)
          VALUES (LOWER(REPLACE(CAST(NEWID() AS NVARCHAR(36)),'-','')), @uid, 'MANAGER_VIEW', @teamBoss, @mehdiId, GETDATE());
        END
      END
    END
    ELSE
    BEGIN
      PRINT 'WARNING: user not found for ' + @phone + ' ' + @like;
    END
    FETCH NEXT FROM cur INTO @phone, @like, @rId, @teamBoss;
  END
  CLOSE cur; DEALLOCATE cur;

  -- ============================================================
  -- 4) Verification — does NOT show passwords
  -- ============================================================
  PRINT '--- Verification: role counts ---';
  SELECT r.code, r.name, COUNT(*) as userCount FROM UserRole ur JOIN Role r ON r.id=ur.roleId GROUP BY r.code, r.name ORDER BY r.code;
  PRINT '--- Team verification (per boss) ---';
  IF OBJECT_ID('OrganizationAssignment') IS NOT NULL
    SELECT b.displayName as boss, COUNT(*) as teamSize FROM OrganizationAssignment oa JOIN [User] b ON b.id=oa.scopeRef JOIN [User] u ON u.id=oa.userId WHERE oa.scopeType='MANAGER_VIEW' GROUP BY b.displayName;
  ELSE
    SELECT 'OrganizationAssignment table not found - team view must be enforced via DepartmentId or app config' as note;

  PRINT '--- Users sample (no password shown) ---';
  SELECT TOP 10 u.displayName, u.username, u.phone, r.code FROM [User] u JOIN UserRole ur ON ur.userId=u.id JOIN Role r ON r.id=ur.roleId WHERE r.code IN ('maintenanceManager','maintenance','technician') ORDER BY r.code, u.displayName;

  COMMIT TRANSACTION;
  PRINT 'COMMIT OK — roles+teams assigned, passwords untouched (Tekarai@1234)';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
  PRINT 'ROLLBACK — error: ' + ERROR_MESSAGE();
  THROW;
END CATCH
