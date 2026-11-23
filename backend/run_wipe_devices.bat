@echo off
chcp 65001 >nul
echo Wiping Devices/Locations/SpareParts...
sqlcmd -S localhost\SQLEXPRESS -E -d TekaraiLive -I -i "%~dp0wipe_devices_locations.sql"
echo DONE
pause
