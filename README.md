# العيادات الخارجية — مشروع مستقل Production

مشروع عربي RTL مستقل لإدارة حجوزات العيادات الخارجية والانتظار. يحتوي على Backend حقيقي بـ Flask وقاعدة SQLite وواجهة Web متجاوبة وتطبيق Android وعميل Windows 7 32-bit. لا يعتمد تشغيل النظام على Whacka أو أي خدمة مستضافة من Whacka.

النظام مخصص للحجوزات والانتظار وإدارة التشغيل، وليس EMR ولا يخزن سجلاً طبياً متكاملاً ولا يتخذ قراراً طبياً.

## المكونات

- `app.py`: Backend المستقل وواجهات API وقاعدة البيانات والصلاحيات.
- `templates/` و`static/`: Web Production بنفس تصميم RTL.
- `mobile/android/`: تطبيق Android يتصل بعنوان Backend قابل للتغيير.
- `desktop/windows7-ia32/`: عميل Windows 7 32-bit للأجهزة الضعيفة.
- `scripts/`: تشغيل Online وHospital Server وStandalone Offline.
- `database/`: توثيق SQLite وقواعد الخصوصية.
- `tests/`: اختبارات API والتدفقات الأساسية.
- `docs/`: أدلة التشغيل وAPI وقاعدة البيانات والأوضاع.

## التشغيل السريع

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

افتح `http://127.0.0.1:4173`.

## أوضاع التشغيل

### Online

```bash
./scripts/online-server.sh
```

يعمل Backend على خادم عام. يمكن تفعيل AI وWhatsApp وTelegram فقط عند إعداد مفاتيح وخدمات المؤسسة. الحجز الداخلي لا يعتمد عليها.

### Hospital Server

```bash
BSCH_HOST=0.0.0.0 BSCH_PORT=4173 ./scripts/hospital-server.sh
```

ثبت المشروع على جهاز داخل المستشفى، وافتح المنفذ 4173 في جدار الحماية. يكتب Android عنوان الخادم عند أول تشغيل، ويقرأ Windows العنوان من `server-url.txt` أو `BSCH_SERVER_URL`.

### Standalone Offline

```bash
./scripts/standalone-offline.sh
```

يعمل Backend وSQLite على جهاز واحد بدون Internet أو Cloud. الوظائف الداخلية مثل المستخدمين والحجوزات والدور والتقارير والتدقيق تعمل محلياً.

## الحسابات التجريبية

| الدور | المستخدم | كلمة المرور |
|---|---|---|
| المؤسس | `founder` | `founder` |
| موظف الحجز | `bsch` | `bsch` |
| الطبيب | `bschdr` | `bschdr` |
| التمريض | `bschnurse` | `bschnurse` |

غير كلمات المرور في بيئة الإنتاج.

## الوظائف

الحجز والتحقق من الأيام والساعات والسعة والخدمات، منع الحجز المكرر، التأكيد والإلغاء وإعادة الجدولة والتحويل بين العيادات، أرقام الانتظار ونداء/التالي/تخطي/إعادة، إدارة العيادات والأطباء والخدمات، التقارير والتصدير، الطباعة وPDF، قوالب الرسائل، سجل التدقيق، وتسجيل الرسائل.

تحليل الرسائل وAI الخارجي اختياري ويعمل فقط في Online عند إعداد `OPENAI_API_KEY` و`OPENAI_API_BASE` وتفعيل الإعدادات. لا يؤكد AI الحجز ولا يتخذ قراراً طبياً.

## Android

ابنِ التطبيق من `mobile/android` أو حمّل APK Production من GitHub Release. عند أول تشغيل يمكن إدخال عنوان Backend، مثل:

```text
http://192.168.1.10:4173/
```

يجب أن يكون الهاتف على نفس شبكة المستشفى في وضع Hospital Server. التطبيق يستخدم نفس Backend، وليس نسخة Static منفصلة.

## Windows 7 32-bit

```bash
cd desktop/windows7-ia32
npm install
npm run package:win32
```

لبناء Installer:

```bash
npm run package:installer -- --publish never
```

ضع `server-url.txt` بجوار التطبيق أو استخدم `BSCH_SERVER_URL` لتحديد Backend.

## Environment Variables

انسخ `.env.example` إلى `.env`. أهم المتغيرات: `BSCH_OPERATING_MODE` و`BSCH_HOST` و`BSCH_PORT` و`BSCH_DB_PATH` و`BSCH_SECRET_KEY` و`OPENAI_API_KEY` و`OPENAI_API_BASE`. لا ترفع `.env` أو أي مفاتيح حقيقية.

## Backup وRestore

قاعدة التشغيل الافتراضية هي `bsch_clinics.sqlite3`، بينما `data/bsch_clinics_demo.sqlite3` قاعدة Demo معقمة. احفظ نسخ SQLite خارج Git، واستخدم أدوات النسخ الاحتياطي المؤمنة في بيئة المستشفى.

## الاختبارات

شغل الخادم ثم:

```bash
python3 -m pytest -q
# أو
python3 tests/test_api.py
```

تغطي الاختبارات Login، الصلاحيات، الأوضاع، إنشاء الحجز، منع التكرار، الدور العام، التقارير والقوالب وقاعدة البيانات. تم أيضاً فحص Python وJavaScript وبناء Android وWindows Installer.

## الخصوصية وعدم الاعتماد على Whacka

تم فحص الكود والواجهة والإعدادات بحثاً عن Whacka ولم يبق رابط أو خدمة ضرورية منه. روابط npm أو GitHub في ملفات dependency ليست اعتماد تشغيل. لا تضع بيانات مرضى حقيقية أو أسراراً في GitHub.

## GitHub Releases

إصدار المشروع المستقل المطلوب في هذه المرحلة هو [v1.0.0](https://github.com/ahmedbahnese/bsch-clinics-recovered/releases/tag/v1.0.0)، ويحتوي على Web Production وHospital Server وAndroid Production وWindows Installer ونسخة Windows المحمولة وChecksums. الإصدارات اللاحقة تحافظ على نفس Backend وقاعدة البيانات والواجهات.
