# Windows 7 32-bit / الأجهزة الضعيفة

هذه نسخة Electron legacy تستهدف `win32 ia32` باستخدام Electron 13.6.9، وهو آخر مسار عملي قديم يمكن اختباره مع Windows 7. التطبيق خفيف ويعرض نفس الويب/PWA.

## البناء على Windows أو Linux

```bash
npm install
npm run package:win32
```

ينتج مجلد `dist/BSCHClinics-win32-ia32` ويمكن نقله إلى الجهاز الضعيف. لتغيير عنوان الخادم:

```bat
set BSCH_SERVER_URL=https://your-server.example/
BSCHClinics.exe
```

يحتاج التطبيق إلى خادم Flask متاح؛ لا يتم تضمين قاعدة بيانات المرضى داخل برنامج Windows. احتفظ بقاعدة البيانات على جهاز الخادم ولا تنقل بيانات المرضى إلى جهاز مشترك.
