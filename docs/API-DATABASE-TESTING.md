# API وقاعدة البيانات والاختبارات

## API

- `POST /api/login`, `GET /api/me`, `POST /api/logout`
- `GET /api/runtime`, `GET/PATCH /api/settings`
- `GET /api/clinics`, إدارة العيادات والجداول والإغلاق
- `POST /api/bookings`, التأكيد والإلغاء وإعادة الجدولة والتتبع
- `GET /api/queue` وإجراءات النداء والتالي والتخطي والرجوع
- `POST /api/messages/incoming` وواجهات القوالب وإعادة محاولة الرسائل
- `GET /api/reports/bookings` و`/api/reports/export`
- `GET /api/audit-logs`

## SQLite

قاعدة التشغيل `bsch_clinics.sqlite3` تحتوي على Users وSystemSettings وClinics وBookings وQueueEntries وClinicSchedules وClinicServiceSchedules وClinicClosures وClinicDoctors وMessageTemplates وIncomingMessages وOutgoingMessages وAuditLogs وغيرها.

لا ترفع قاعدة التشغيل أو بيانات المرضى أو الأسرار إلى GitHub. قاعدة Demo منفصلة ومطهرة موجودة تحت `data/`.

## الاختبارات

```bash
npm run check
python3 -m py_compile app.py
node --check static/app.js
```

اختبارات التكامل يجب أن تغطي تسجيل الدخول والصلاحيات والحجز والتأكيد والإلغاء وإعادة الجدولة ومنع التكرار والدور والتقارير والطباعة والقوالب والرسائل وأوضاع التشغيل الثلاثة.
