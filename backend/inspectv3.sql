-- Diagnostic v3: show real departments, positions, assignments, bosses
-- Run on TekaraiLive. No changes made.
SET NOCOUNT ON;
PRINT '=== 1) Departments ===';
SELECT code, name, status, managerName FROM OrganizationDepartment ORDER BY code;
GO
PRINT '=== 2) Positions ===';
SELECT code, name, level, isActive FROM OrganizationPosition ORDER BY level DESC, code;
GO
PRINT '=== 3) Counts per department ===';
SELECT d.code, d.name, COUNT(*) AS cnt
FROM OrganizationAssignment oa JOIN OrganizationDepartment d ON d.id=oa.departmentId
WHERE oa.isActive=1 GROUP BY d.code,d.name ORDER BY cnt DESC;
GO
PRINT '=== 4) All assignments: who is where, who reports to whom ===';
SELECT u.displayName, u.username, d.code AS deptCode, d.name AS deptName,
       p.code AS posCode, p.name AS posName,
       boss.displayName AS reportsTo, oa.isPrimary, oa.isActive
FROM OrganizationAssignment oa
JOIN [User] u ON u.id=oa.userId
JOIN OrganizationDepartment d ON d.id=oa.departmentId
JOIN OrganizationPosition p ON p.id=oa.positionId
LEFT JOIN [User] boss ON boss.id=oa.reportsToUserId
ORDER BY d.code, boss.displayName, u.displayName;
GO
PRINT '=== 5) Bosses assignments ===';
SELECT u.displayName, u.username, d.code, p.code, p.name, oa.reportsToUserId
FROM OrganizationAssignment oa
JOIN [User] u ON u.id=oa.userId
JOIN OrganizationDepartment d ON d.id=oa.departmentId
JOIN OrganizationPosition p ON p.id=oa.positionId
WHERE u.displayName LIKE N'%مصطفی صفا%' OR u.displayName LIKE N'%مهرشاد%'
   OR u.displayName LIKE N'%عباس فرخ%' OR u.displayName LIKE N'%ابراهیم محمدی%'
   OR u.displayName LIKE N'%مهدی یارمحمدی%' OR u.username IN ('09120535494','09129432012','09196189256','09113282043');
GO
PRINT '=== 6) Team sizes by reportsTo ===';
SELECT boss.displayName, boss.username, COUNT(*) AS teamSize
FROM OrganizationAssignment oa JOIN [User] boss ON boss.id=oa.reportsToUserId
WHERE oa.isActive=1 GROUP BY boss.displayName,boss.username ORDER BY teamSize DESC;
GO
PRINT '=== 7) Users WITHOUT assignment (why total is 23 not 44) ===';
SELECT displayName, username FROM [User]
WHERE id NOT IN (SELECT userId FROM OrganizationAssignment WHERE isActive=1)
ORDER BY displayName;
GO
PRINT '=== 8) Boss roles (UserRole) ===';
SELECT u.displayName, u.username, r.code, r.name
FROM UserRole ur JOIN [User] u ON u.id=ur.userId JOIN [Role] r ON r.id=ur.roleId
WHERE u.displayName LIKE N'%مصطفی صفا%' OR u.displayName LIKE N'%مهرشاد%'
   OR u.displayName LIKE N'%عباس فرخ%' OR u.displayName LIKE N'%ابراهیم محمدی%'
   OR u.displayName LIKE N'%مهدی یارمحمدی%'
ORDER BY u.displayName, r.code;
GO
