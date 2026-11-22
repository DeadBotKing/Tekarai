-- پیدا کردن آمنه صادقی - حتی حذف‌شده‌ها
PRINT '=== User (including deleted) ===';
SELECT id, username, displayName, email, mobile, status, deletedAt, createdAt FROM [User] WHERE mobile='09365614779' OR username='09365614779' OR displayName LIKE N'%آمنه%' OR email LIKE '%amene%';

PRINT '=== IdentityMobileAccount ===';
SELECT * FROM [IdentityMobileAccount] WHERE mobile='09365614779' OR userId IN (SELECT id FROM [User] WHERE displayName LIKE N'%آمنه%');

PRINT '=== AdministrativeIdentity ===';
SELECT * FROM [AdministrativeIdentity] WHERE mobile='09365614779' OR identifier='09365614779' OR displayName LIKE N'%آمنه%';

PRINT '=== Check unique blocker ===';
-- ببین کجای دیگه شماره گیر کرده
SELECT 'User' as tbl, COUNT(*) as cnt FROM [User] WHERE mobile='09365614779'
UNION ALL
SELECT 'IdentityMobileAccount', COUNT(*) FROM [IdentityMobileAccount] WHERE mobile='09365614779'
UNION ALL
SELECT 'AdministrativeIdentity', COUNT(*) FROM [AdministrativeIdentity] WHERE mobile='09365614779';

-- === FIX: پاکسازی کامل برای ثبت مجدد ===
-- اگر می‌خوای دوباره از صفر ثبتش کنی، این بخش رو اجرا کن:
PRINT '=== FIX APPLIED - now you can re-add ===';
-- حذف از جدول‌های جانبی که شماره را بلوکه کرده
DELETE FROM [IdentityMobileAccount] WHERE mobile='09365614779';
DELETE FROM [AdministrativeIdentity] WHERE mobile='09365614779' OR identifier='09365614779';
-- حذف کاربر حذف‌شده (اگر soft-delete بود)
DELETE FROM [User] WHERE mobile='09365614779' AND deletedAt IS NOT NULL;
-- اگر بخوای برگردونی به جای حذف، این رو جای ۲ خط بالا بزن:
-- UPDATE [User] SET deletedAt=NULL, status='active', displayName=N'آمنه صادقی', username='09365614779' WHERE mobile='09365614779';

PRINT 'DONE - حالا می‌تونی از پنل دوباره آمنه صادقی رو بسازی (09365614779 - مدیر برنامه ریزی)';
