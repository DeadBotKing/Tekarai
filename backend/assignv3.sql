-- v3: team visibility via reportsToUserId + matrix scope=team for bosses, scope=all for Mehdi
-- NO password change, NO UserRole change, NO department move
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
SET NOCOUNT ON;
PRINT '=== v3 start ===';
BEGIN TRY
  BEGIN TRANSACTION;

  DECLARE @mehdi CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09129432012');
  DECLARE @mostafa CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09120535494');
  DECLARE @mehrshad CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09183689891');
  DECLARE @abbas CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09196189256');
  DECLARE @ebrahim CHAR(32)=(SELECT TOP 1 id FROM [User] WHERE username='09113282043');
  PRINT 'Boss IDs:'; SELECT displayName,username,id FROM [User] WHERE id IN (@mehdi,@mostafa,@mehrshad,@abbas,@ebrahim);

  -- 1) Team members -> reportsTo boss (by exact username from DB)
  DECLARE @t TABLE(phone NVARCHAR(20), boss CHAR(32));
  INSERT INTO @t VALUES
  -- Mostafa 15
  ('09184939450',@mostafa),('09330146665',@mostafa),('09002550821',@mostafa),
  ('09359959538',@mostafa),('09190512839',@mostafa),('09358422007',@mostafa),
  ('09127569668',@mostafa),('09128840364',@mostafa),('09186230775',@mostafa),
  ('09183936442',@mostafa),('09120262857',@mostafa),('09190522042',@mostafa),
  ('09167563107',@mostafa),('09198720900',@mostafa),('09193551129',@mostafa),
  -- Mehrshad 7
  ('09185072143',@mehrshad),('09370398323',@mehrshad),('09193560513',@mehrshad),
  ('09933181900',@mehrshad),('09100823904',@mehrshad),('09193561023',@mehrshad),
  ('09223540245',@mehrshad),
  -- Abbas 9 (Farshad 09378985255, Emad 09116498513)
  ('09189169465',@abbas),('09184341321',@abbas),('09196562494',@abbas),
  ('09376557247',@abbas),('09128554542',@abbas),('09398308536',@abbas),
  ('09168535529',@abbas),('09378985255',@abbas),('09116498513',@abbas),
  -- Ebrahim 4
  ('09363822395',@ebrahim),('09193499439',@ebrahim),('09167453720',@ebrahim),
  ('09195231690',@ebrahim);

  UPDATE oa SET reportsToUserId=t.boss, updatedAt=GETDATE()
  FROM OrganizationAssignment oa
  JOIN [User] u ON u.id=oa.userId
  JOIN @t t ON t.phone=u.username
  WHERE oa.isActive=1;
  PRINT 'Members updated:'; SELECT @@ROWCOUNT;

  -- 2) Bosses report to Mehdi (Mehdi sees all via tenantAdmin anyway)
  UPDATE OrganizationAssignment SET reportsToUserId=@mehdi, updatedAt=GETDATE()
  WHERE userId IN (@mostafa,@mehrshad,@abbas,@ebrahim) AND isActive=1;

  -- 3) Matrix scope: boss positions -> team, Mehdi position -> all
  DECLARE @bossPos TABLE(posId CHAR(32));
  INSERT INTO @bossPos SELECT DISTINCT positionId FROM OrganizationAssignment
    WHERE userId IN (@mostafa,@mehrshad,@abbas,@ebrahim) AND isActive=1;
  UPDATE OrganizationAccessRule SET scope='team', updatedAt=GETDATE()
  WHERE positionId IN (SELECT posId FROM @bossPos)
    AND capability IN ('workOrder','device','purchaseRequisition','permitToWork','report','organizationUnit','unitMembers');
  PRINT 'Boss matrix -> team:'; SELECT @@ROWCOUNT;

  DECLARE @mehdiPos CHAR(32)=(SELECT TOP 1 positionId FROM OrganizationAssignment WHERE userId=@mehdi AND isActive=1);
  UPDATE OrganizationAccessRule SET scope='all', updatedAt=GETDATE()
  WHERE positionId=@mehdiPos;
  PRINT 'Mehdi matrix -> all:'; SELECT @@ROWCOUNT;

  -- 4) Department manager display fields
  UPDATE d SET managerUserId=u.id, managerName=u.displayName, updatedAt=GETDATE()
  FROM OrganizationDepartment d
  JOIN OrganizationAssignment oa ON oa.departmentId=d.id AND oa.isActive=1
  JOIN [User] u ON u.id=oa.userId
  WHERE oa.userId IN (@mostafa,@mehrshad,@abbas,@ebrahim);

  PRINT '--- Verification team sizes ---';
  SELECT boss.displayName, boss.username, COUNT(*) AS teamSize
  FROM OrganizationAssignment oa JOIN [User] boss ON boss.id=oa.reportsToUserId
  WHERE oa.isActive=1 GROUP BY boss.displayName,boss.username ORDER BY teamSize DESC;
  PRINT '--- Verification matrix scopes (boss positions) ---';
  SELECT p.code, r.capability, r.scope, COUNT(*) AS cells
  FROM OrganizationAccessRule r JOIN OrganizationPosition p ON p.id=r.positionId
  WHERE r.positionId IN (SELECT posId FROM @bossPos)
  GROUP BY p.code,r.capability,r.scope ORDER BY p.code,r.capability;
  PRINT '--- Mehdi matrix ---';
  SELECT p.code, r.capability, r.scope, COUNT(*) AS cells
  FROM OrganizationAccessRule r JOIN OrganizationPosition p ON p.id=r.positionId
  WHERE r.positionId=@mehdiPos GROUP BY p.code,r.capability,r.scope ORDER BY r.capability;

  COMMIT TRANSACTION;
  PRINT 'COMMIT OK v3';
END TRY
BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK TRANSACTION;
  PRINT 'ROLLBACK: '+ERROR_MESSAGE(); THROW;
END CATCH
