-- Fix Amene Sadeghi 09365614779 - correct column names
PRINT '=== User (including deleted) by phone/username ===';
SELECT id, tenantId, username, email, phone, displayName, status, deletedAt FROM [User] WHERE phone='09365614779' OR username='amene.sadeghi' OR username='09365614779' OR displayName LIKE N'%آمنه%' OR email LIKE '%amene%';

PRINT '=== IdentityMobileAccount ===';
SELECT userId, phone, mustChangePassword FROM [IdentityMobileAccount] WHERE phone='09365614779';

PRINT '=== AdministrativeIdentity (if exists) ===';
SELECT id, ownerUserId, username FROM [AdministrativeIdentity] WHERE username='amene.sadeghi' OR username='09365614779';

-- === FIX: پاکسازی برای ثبت مجدد ===
PRINT 'Applying fix...';
-- حذف موبایل بلوکه شده
DELETE FROM [IdentityMobileAccount] WHERE phone='09365614779';
-- حذف کاربر حذف‌شده (اگر soft-delete بود، hard delete)
DELETE FROM [User] WHERE phone='09365614779' AND deletedAt IS NOT NULL;
DELETE FROM [User] WHERE username='amene.sadeghi' AND deletedAt IS NOT NULL;
-- حذف هویت ادمین اگر بود
DELETE FROM [AdministrativeIdentity] WHERE username='amene.sadeghi';

PRINT 'DONE - حالا می‌تونی آمنه صادقی (09365614779) رو دوباره بسازی';
SELECT 'Fixed' as status;
