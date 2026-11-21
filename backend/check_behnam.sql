-- Check Behnam permissions
DECLARE @uid CHAR(32) = (SELECT id FROM [User] WHERE username='09120682369');
SELECT u.username, u.displayName, r.code, r.name FROM [User] u JOIN [UserRole] ur ON ur.userId=u.id JOIN [Role] r ON r.id=ur.roleId WHERE u.id=@uid;
SELECT p.code, p.module FROM [Permission] p JOIN [RolePermission] rp ON rp.permissionId=p.id JOIN [Role] r ON r.id=rp.roleId JOIN [UserRole] ur ON ur.roleId=r.id WHERE ur.userId=@uid ORDER BY p.code;
SELECT COUNT(*) as roleCount FROM [UserRole] WHERE userId=@uid;
