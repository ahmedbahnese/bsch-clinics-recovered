# تقرير تجهيز ونشر BSCH Clinics

**الحالة:** جاهز للنشر على PostgreSQL وRender، ولم يتم النشر الخارجي بعد لعدم وجود اتصال مصرح به بحساب Neon أو Render.

## ما تم فحصه

- التطبيق الحالي: Flask/Python مع واجهة عربية JavaScript/CSS.
- قاعدة البيانات الأصلية: SQLite في `bsch_clinics.sqlite3`.
- الأدوار الحالية: المؤسس، موظف الحجز، الطبيب، التمريض.
- المسارات والوظائف الحالية محفوظة ولم يبدأ المشروع من الصفر.
- تم إنشاء نسخة احتياطية قبل التعديل في:
  - `/home/ubuntu/bsch-clinics-backups/20261011/bsch_clinics.sqlite3`
  - `/home/ubuntu/bsch-clinics-backups/20261011/project-copy/`
  - `/home/ubuntu/bsch-clinics-backups/20261011/SHA256SUMS`

## البيانات قبل الترحيل

| الجدول | السجلات |
|---|---:|
| Users | 5 |
| SystemSettings | 6 |
| Clinics | 6 |
| ClinicSchedules | 24 |
| ClinicServiceSchedules | 0 |
| ClinicClosures | 0 |
| ClinicDoctors | 0 |
| Bookings | 4 |
| QueueEntries | 4 |
| QueueEvents | 4 |
| Transfers | 0 |
| Notifications | 7 |
| AuditLogs | 47 |
| MessageTemplates | 8 |
| IncomingMessages | 0 |
| OutgoingMessages | 0 |

## التغييرات المنفذة

- إضافة `db_compat.py` لدعم PostgreSQL عبر `DATABASE_URL` مع إبقاء SQLite متاحًا للتشغيل المحلي.
- إضافة مخطط PostgreSQL تلقائيًا مع معرفات `SERIAL`، معاملات، وقراءة صفوف متوافقة مع الكود الحالي.
- إضافة `scripts/migrate_sqlite_to_postgres.py` لترحيل البيانات مع الحفاظ على المعرفات وضبط التسلسلات والتحقق من عدد السجلات.
- إضافة `scripts/backup_postgres.py` و`scripts/restore_postgres.py` لنسخ PostgreSQL واستعادته.
- إضافة `render.yaml` و`Procfile` وتشغيل Gunicorn بدل خادم Flask التطويري.
- إضافة `gunicorn` و`psycopg` إلى `requirements.txt`.
- ضبط جلسات HTTPS في النشر عبر `BSCH_COOKIE_SECURE=1` و`SameSite=None`.
- تحديث اختبار API لاستخدام حساب المؤسس الحالي `Bahnasy` بدل الحساب القديم `founder`.
- عدم وضع أي كلمة مرور أو مفتاح فعلي داخل GitHub.

## نتيجة اختبار PostgreSQL المحلي

تم إنشاء قاعدة PostgreSQL محلية مؤقتة واختبار الترحيل عليها.

| البيان | النتيجة |
|---|---|
| ترحيل SQLite إلى PostgreSQL | ناجح |
| Users بعد الترحيل | 5 |
| Clinics بعد الترحيل | 6 |
| Bookings بعد الترحيل | 4 |
| QueueEntries بعد الترحيل | 4 |
| AuditLogs بعد الترحيل | 47 عند لحظة الترحيل |
| تشغيل Flask على PostgreSQL | ناجح |
| تسجيل الدخول وعرض العيادات | ناجح |
| النسخ الاحتياطي والاستعادة | ناجح |
| اختبار API المتكامل على SQLite معزولة | `API_INDEPENDENCE_TEST=PASS` |

قاعدة SQLite الأصلية لم تُحذف، وتم التحقق من تطابق بصمتها بعد الاختبار.

## متغيرات البيئة المطلوبة

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require
BSCH_SECRET_KEY=<قيمة عشوائية طويلة>
BSCH_OPERATING_MODE=online
BSCH_COOKIE_SECURE=1
```

لا يتم وضع قيم هذه المتغيرات داخل المستودع.

## خطوات النشر على Render وNeon

1. أنشئ قاعدة PostgreSQL مجانية في Neon أو مزود PostgreSQL مجاني موثوق.
2. انسخ `DATABASE_URL` من Neon، مع إبقاء `sslmode=require`.
3. في Render اختر **New → Web Service** ثم اربط مستودع GitHub:
   `ahmedbahnese/bsch-clinics-recovered`
4. اختر الخطة المجانية.
5. ملف `render.yaml` يحدد أمر البناء والتشغيل تلقائيًا.
6. أضف `DATABASE_URL` كمتغير سري في Render.
7. اترك Render يولد `BSCH_SECRET_KEY` تلقائيًا، أو أدخل قيمة عشوائية طويلة.
8. شغّل Deploy وانتظر نجاح `/api/runtime` كفحص صحة.
9. قبل نقل بيانات حقيقية، شغّل الترحيل مرة واحدة من جهاز آمن:

```bash
export DATABASE_URL='...'
python3 scripts/migrate_sqlite_to_postgres.py
```

10. لا تحذف ملف SQLite قبل مقارنة أعداد السجلات واختبار تسجيل الدخول والحجز والتأكيد والإلغاء.
11. بعد نجاح الاختبار، استخدم رابط Render المجاني عبر HTTPS.

## النسخ الاحتياطي والاستعادة

إنشاء نسخة:

```bash
export DATABASE_URL='...'
python3 scripts/backup_postgres.py backups/bsch-$(date +%Y%m%d-%H%M%S).json.gz
```

استعادة نسخة اختبارية:

```bash
export DATABASE_URL='...'
python3 scripts/restore_postgres.py backups/bsch-YYYYMMDD-HHMMSS.json.gz
```

يجب تجربة الاستعادة على قاعدة منفصلة قبل استعادة قاعدة الإنتاج.

## قيود الخطط المجانية

- قد تدخل خدمة الويب المجانية في وضع السكون، فيتأخر أول طلب.
- موارد المعالجة والذاكرة محدودة.
- قاعدة البيانات المجانية لها حدود تخزين واتصالات ونسخ احتياطية حسب مزود الخدمة.
- المجانية ليست ضمانًا دائمًا؛ قد تتغير الشروط أو الحدود.
- يجب الاحتفاظ بنسخ خارجية منتظمة وعدم الاعتماد على الاستضافة وحدها.

## ما لم يُنفذ بعد

لم يتم إنشاء قاعدة Neon أو خدمة Render ولم يتم نشر الموقع فعليًا؛ لا توجد بيانات اعتماد أو اتصال مصرح به بهذه الحسابات في البيئة الحالية. لذلك لا يوجد رابط إنتاج حقيقي يمكن تسليمه دون أن ينفذ مالك الحساب خطوة الربط ويضيف `DATABASE_URL` في Render.
