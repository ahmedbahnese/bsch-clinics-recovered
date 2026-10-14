@echo off
setlocal
cd /d "%~dp0"
set BSCH_OPERATING_MODE=standalone_offline
set BSCH_HOST=127.0.0.1
set BSCH_PORT=4173
if not exist bsch_clinics.sqlite3 echo سيتم إنشاء قاعدة البيانات المحلية عند التشغيل الأول.
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3.11 أو أحدث غير مثبت على هذا الجهاز.
  echo ثبّت Python ثم شغّل هذا الملف مرة أخرى.
  pause
  exit /b 1
)
python app.py
pause
