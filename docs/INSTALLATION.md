# دليل التثبيت والإنتاج

## Web / Standalone Offline

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
./scripts/standalone-offline.sh
```

افتح `http://127.0.0.1:4173/`. لا يحتاج هذا الوضع إلى Internet أو خدمة خارجية.

## Hospital Server

على جهاز الخادم داخل المستشفى:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
./scripts/hospital-server.sh
```

اسمح بالمنفذ 4173 من شبكة المستشفى، ثم ضع `http://SERVER-IP:4173/` في Android أو `server-url.txt` بجوار برنامج Windows.

## Windows 7

فك `BSCHClinics-win32-ia32.zip`، انسخ `server-url.example.txt` باسم `server-url.txt`، ثم شغّل `BSCHClinics.exe`. يعمل البرنامج على Windows 7 32-bit عبر Electron 13.6.9.

## Android

ثبّت APK. عند أول تشغيل أدخل عنوان الخادم المحلي أو `http://127.0.0.1:4173/` إذا كان الخادم على نفس الجهاز.
