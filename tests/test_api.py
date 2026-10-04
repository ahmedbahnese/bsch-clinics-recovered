import datetime as dt, os, sys, requests, time

BASE = os.environ.get('TEST_BASE_URL', 'http://127.0.0.1:4173')
s = requests.Session()

def ok(r, code=200):
    assert r.status_code == code, (r.status_code, r.text[:500])
    return r.json()

me = ok(s.get(BASE + '/api/me'))
assert me.get('user') is None
clinics = ok(s.get(BASE + '/api/clinics'))['clinics']
assert clinics
runtime = ok(s.get(BASE + '/api/runtime'))
assert runtime['mode'] in {'online', 'hospital_server', 'standalone_offline'}
ok(s.post(BASE + '/api/login', json={'username':'founder','password':'founder'}))
settings = ok(s.get(BASE + '/api/settings'))
assert {x['id'] for x in settings['modes']} == {'online','hospital_server','standalone_offline'}

# Pick a valid clinic day in the next two weeks.
clinic = clinics[0]
visit = None
for i in range(200, 400):
    d = dt.date.today() + dt.timedelta(days=i)
    days = clinic.get('work_days', [])
    if isinstance(days, str):
        days = [int(x) for x in days.replace(' ', '').split(',') if x.isdigit()]
    if d.weekday() in days:
        visit = d.isoformat(); break
assert visit, clinic
payload = {'patient_name':'اختبار استقلال النظام '+str(int(time.time())),'age':'10','address':'اختبار','phone':'010'+str(int(time.time()))[-8:],'national_id':'','clinic_id':clinic['id'],'service_type':(clinic.get('services') or [{'name':'كشف أول مرة'}])[0]['name'],'visit_date':visit,'appointment_time':'09:00'}
created = ok(s.post(BASE + '/api/bookings', json=payload), 201)
assert created['booking']['booking_no']
dup_payload = dict(payload); dup_payload['appointment_time'] = '14:00'
dup = s.post(BASE + '/api/bookings', json=dup_payload)
ok(dup, 409)
public_queue = ok(s.get(BASE + f"/api/queue/public?clinic_id={clinic['id']}&date={visit}"))
assert 'queue' in public_queue
report = ok(s.get(BASE + f'/api/reports/bookings?date={visit}'))
assert 'summary' in report and 'bookings' in report
assert ok(s.get(BASE + '/api/templates'))['templates']
print('API_INDEPENDENCE_TEST=PASS')
