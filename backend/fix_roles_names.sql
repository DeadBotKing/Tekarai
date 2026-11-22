-- Fix role names - Persian was corrupted due to encoding, set to clear Persian (UTF-8)
UPDATE [Role] SET name = N'مدیر فنی و مهندسی (کامل)' WHERE code='tech_director';
UPDATE [Role] SET name = N'رئیس واحد فنی' WHERE code='tech_head';
UPDATE [Role] SET name = N'سرپرست فنی' WHERE code='tech_supervisor';
UPDATE [Role] SET name = N'کارشناس فنی' WHERE code='tech_specialist';
UPDATE [Role] SET name = N'پرسنل تاسیسات' WHERE code='tech_facility';

-- Verify
SELECT code, name, scopeType FROM [Role] WHERE code LIKE 'tech_%' ORDER BY code;
