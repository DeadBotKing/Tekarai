-- Fix all role Persian names (correct UTF-8)
UPDATE [Role] SET name = N'مدیر نگهداری' WHERE code='maintenanceManager';
UPDATE [Role] SET name = N'مدیر منابع انسانی' WHERE code='hrManager';
UPDATE [Role] SET name = N'درخواست‌دهنده نگهداری' WHERE code='maintenanceRequester';
UPDATE [Role] SET name = N'تکنسین نگهداری' WHERE code='maintenanceTechnician';
UPDATE [Role] SET name = N'مدیر فنی و مهندسی (کامل)' WHERE code='tech_director';
UPDATE [Role] SET name = N'رئیس واحد فنی' WHERE code='tech_head';
UPDATE [Role] SET name = N'سرپرست فنی' WHERE code='tech_supervisor';
UPDATE [Role] SET name = N'کارشناس فنی' WHERE code='tech_specialist';
UPDATE [Role] SET name = N'پرسنل تاسیسات' WHERE code='tech_facility';
SELECT code, name FROM [Role] ORDER BY code;
