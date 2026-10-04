# BSCH Clinics — Windows 7 32-bit

نسخة Electron legacy خفيفة تستهدف `win32 ia32` وتعمل على Windows 7 والأجهزة الضعيفة.

## إعداد السيرفر الداخلي

قبل تشغيل البرنامج، انسخ `server-url.example.txt` إلى ملف باسم `server-url.txt` بجوار ملف التشغيل، وعدّل العنوان، مثال:

```text
http://192.168.1.10:4173/
```

يمكن بدلاً من ذلك تشغيل البرنامج بالمتغير:

```bat
set BSCH_SERVER_URL=http://192.168.1.10:4173/
BSCHClinics.exe
```

تُقرأ الأولوية من `BSCH_SERVER_URL` ثم `server-url.txt` ثم العنوان العام الافتراضي.

## البناء على Windows أو Linux

```bash
npm install
npm run package:win32
```

ينتج مجلد `dist/BSCHClinics-win32-ia32` ويمكن نقله إلى الجهاز الضعيف. الحزمة المضغوطة الجاهزة موجودة في GitHub Release.

يحتاج التطبيق إلى خادم Flask متاح؛ لا يتم تضمين قاعدة بيانات المرضى داخل برنامج Windows. احتفظ بقاعدة البيانات على جهاز الخادم ولا تنقل بيانات المرضى إلى جهاز مشترك.
