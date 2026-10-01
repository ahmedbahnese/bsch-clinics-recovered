from datetime import date, datetime
from functools import wraps
from pathlib import Path
import hashlib, json, secrets, sqlite3
from flask import Flask, jsonify, request, session, render_template, g

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / 'bsch_clinics.sqlite3'
app = Flask(__name__)
app.config.update(SECRET_KEY=secrets.token_hex(32), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
ROLES = {'booking': 'موظف الحجز', 'doctor': 'طبيب', 'nurse': 'تمريض'}

CLINIC_SEED = [
 {'name':'عيادة الجهاز الهضمي','location':'الدور الرابع','work_days':'1,5','start_time':'09:00','end_time':'14:00','visit_minutes':15,'daily_limit':75,'services':[{'name':'كشف أول مرة','limit':75},{'name':'متابعة','limit':75}],'documents':'صورة بطاقة الأب والأم + شهادة ميلاد كمبيوتر + تقارير الطفل.','instructions':'الحضور قبل الموعد بربع ساعة وإحضار الأوراق المطلوبة.'},
 {'name':'عيادة التغذية','location':'الدور الرابع','work_days':'2,3,6','start_time':'09:00','end_time':'14:00','visit_minutes':15,'daily_limit':50,'services':[{'name':'كشف أول مرة','limit':50},{'name':'متابعة','limit':50}],'documents':'صورة بطاقة الأب والأم + شهادة ميلاد كمبيوتر + تقارير الطفل.','instructions':'الحضور قبل الموعد بربع ساعة وإحضار الأوراق المطلوبة.'},
 {'name':'عيادة النفسية والعصبية','location':'الدور الرابع','work_days':'5','start_time':'09:00','end_time':'14:00','visit_minutes':20,'daily_limit':15,'services':[{'name':'كشف أول مرة','limit':15},{'name':'متابعة','limit':15}],'documents':'لا توجد أوراق محددة حاليًا.','instructions':'الحضور في الموعد ومعرفة اسم الطبيب إن وُجد.'},
 {'name':'عيادة الأسنان','location':'الدور الرابع','work_days':'0,1,2,3,5,6','start_time':'09:00','end_time':'14:00','visit_minutes':20,'daily_limit':4,'services':[{'name':'خلع','limit':4},{'name':'حشو','limit':4}],'documents':'صورة بطاقة الأب أو الأم.','instructions':'الحضور مبكرًا لأن العدد اليومي محدود.'},
 {'name':'عيادة الإيكو','location':'أمام عيادة القلب بالدور الرابع','work_days':'0,1,2,3,5,6','start_time':'08:30','end_time':'13:00','visit_minutes':30,'daily_limit':5,'services':[{'name':'كشف أول مرة','limit':5},{'name':'متابعة','limit':5}],'documents':'أي تقارير أو أشعات سابقة إن وجدت.','instructions':'الحضور الساعة 8:30 صباحًا أمام عيادة القلب بالدور الرابع.\nللأطفال من 6 شهور حتى 3 سنوات: قد يُطلب تجهيز الطفل بمادة كلورال هيدرات تحت إشراف طبيب عيادة القلب حسب الحالة.\nيجب أن يكون الطفل خاليًا من أعراض البرد.\nإيقاظ الطفل مبكرًا وعدم السماح له بالنوم في الطريق حتى يمكنه النوم أثناء الفحص عند الحاجة.'},
 {'name':'عيادة السمعيات','location':'الدور الرابع','work_days':'0,1,2,3,5,6','start_time':'08:30','end_time':'13:00','visit_minutes':30,'daily_limit':8,'services':[{'name':'رسم سمع كمبيوتر عن طريق جذع المخ','limit':3,'instructions':'ليلة الاختبار: نوم الطفل الساعة 12 مساءً وإيقاظه الساعة 4 فجراً وعدم السماح له بالنوم حتى الوصول للمستشفى وتهيئته للاختبار.\nفي اليوم السابق للاختبار: غسل الرأس جيدًا بالماء والصابون.\nعدم وضع كريم على الشعر أو البشرة يوم الاختبار.\nالحضور للمستشفى مبكرًا وبحد أقصى الساعة 8:30 صباحًا.\nإحضار كلورال هيدرات إذا قرر الطبيب استخدامه، ويُعطى فقط تحت إشراف طبي.'},{'name':'رسم سمع للسن 5 سنوات فأكثر','limit':5,'instructions':'العمر 5 سنوات فأكثر.\nيجب التأكد من عدم وجود كحة أو رشح أو حرارة.\nالحضور مبكرًا بحد أقصى 8:30 صباحًا.'},{'name':'حالات ضغط الأذن - حضور مباشر','limit':0,'direct_only':True},{'name':'الحالات المحولة من الوحدات الصحية للمواليد - حضور مباشر','limit':0,'direct_only':True}],'documents':'تقارير السمع أو التحويل إن وجدت.','instructions':'شروط رسم السمع: العمر أقل من 5 سنوات وأكبر من 3 شهور، مع استثناء حالات التأخر العقلي أو تأخر الكلام. يجب عدم وجود كحة أو رشح أو ارتفاع درجة الحرارة.'}
]

def db():
 if 'db' not in g:
  g.db=sqlite3.connect(DB_PATH); g.db.row_factory=sqlite3.Row; g.db.execute('PRAGMA foreign_keys=ON')
 return g.db
@app.teardown_appcontext
def close_db(_=None):
 c=g.pop('db',None)
 if c:c.close()
def hash_password(p): return hashlib.scrypt(str(p).encode(),salt=b'bsch-clinics',n=2**14,r=8,p=1).hex()
def now(): return datetime.now().isoformat(timespec='seconds')
def today(): return date.today().isoformat()
def jloads(v, default=None):
 try:return json.loads(v) if v else (default if default is not None else [])
 except Exception:return default if default is not None else []

def init_db():
 conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON')
 conn.executescript('''
 CREATE TABLE IF NOT EXISTS Users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Clinics(id INTEGER PRIMARY KEY,name TEXT NOT NULL,location TEXT NOT NULL DEFAULT '',work_days TEXT NOT NULL DEFAULT '0,1,2,3,4',start_time TEXT NOT NULL DEFAULT '09:00',end_time TEXT NOT NULL DEFAULT '14:00',visit_minutes INTEGER NOT NULL DEFAULT 15,daily_limit INTEGER NOT NULL DEFAULT 30,active INTEGER NOT NULL DEFAULT 1,services_json TEXT NOT NULL DEFAULT '[]',documents TEXT NOT NULL DEFAULT '',instructions TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS ClinicSchedules(id INTEGER PRIMARY KEY,clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE,weekday INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,UNIQUE(clinic_id,weekday));
 CREATE TABLE IF NOT EXISTS Bookings(id INTEGER PRIMARY KEY,booking_no TEXT UNIQUE NOT NULL,patient_name TEXT NOT NULL,age TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL,clinic_id INTEGER NOT NULL REFERENCES Clinics(id),visit_date TEXT NOT NULL,appointment_time TEXT NOT NULL,service_type TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Pending',source TEXT NOT NULL DEFAULT 'external',notes TEXT NOT NULL DEFAULT '',instructions_snapshot TEXT NOT NULL DEFAULT '',documents_snapshot TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS QueueEntries(id INTEGER PRIMARY KEY,booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE,clinic_id INTEGER NOT NULL REFERENCES Clinics(id),queue_date TEXT NOT NULL,queue_no INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'Waiting',current INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(clinic_id,queue_date,queue_no));
 CREATE TABLE IF NOT EXISTS QueueEvents(id INTEGER PRIMARY KEY,queue_entry_id INTEGER NOT NULL REFERENCES QueueEntries(id) ON DELETE CASCADE,event_type TEXT NOT NULL,actor_id INTEGER,details TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Transfers(id INTEGER PRIMARY KEY,booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE,from_clinic_id INTEGER NOT NULL REFERENCES Clinics(id),to_clinic_id INTEGER NOT NULL REFERENCES Clinics(id),queue_entry_id INTEGER,actor_id INTEGER,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Notifications(id INTEGER PRIMARY KEY,booking_id INTEGER,message TEXT NOT NULL,read_at TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS AuditLogs(id INTEGER PRIMARY KEY,actor_id INTEGER,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id INTEGER,details TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS idx_bookings_phone ON Bookings(phone); CREATE INDEX IF NOT EXISTS idx_queue_day ON QueueEntries(clinic_id,queue_date);
 ''')
 # Migrate installations created by the previous version.
 for col,typ in [('services_json','TEXT NOT NULL DEFAULT \'[]\''),('documents','TEXT NOT NULL DEFAULT \'\''),('instructions','TEXT NOT NULL DEFAULT \'\'')]:
  try: conn.execute(f'ALTER TABLE Clinics ADD COLUMN {col} {typ}')
  except sqlite3.OperationalError: pass
 for col,typ in [('age','TEXT NOT NULL DEFAULT \'\''),('address','TEXT NOT NULL DEFAULT \'\''),('service_type','TEXT NOT NULL DEFAULT \'\''),('instructions_snapshot','TEXT NOT NULL DEFAULT \'\''),('documents_snapshot','TEXT NOT NULL DEFAULT \'')]:
  try: conn.execute(f'ALTER TABLE Bookings ADD COLUMN {col} {typ}')
  except sqlite3.OperationalError: pass
 for u,p,n,r in [('bsch','bsch','موظف الحجز','booking'),('bschdr','bschdr','الطبيب','doctor'),('bschnurse','bschnurse','التمريض','nurse')]: conn.execute('INSERT OR IGNORE INTO Users(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)',(u,hash_password(p),n,r,now()))
 # Replace only the old starter clinics, while preserving any user-created clinics.
 old_names={'عيادة الأطفال','عيادة القلب','عيادة الباطنة'}
 existing={x['name'] for x in conn.execute('SELECT name FROM Clinics')}
 if not existing or existing.issubset(old_names):
  conn.execute('DELETE FROM ClinicSchedules'); conn.execute('DELETE FROM Clinics')
  for c in CLINIC_SEED:
   cur=conn.execute('INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit,services_json,documents,instructions) VALUES(?,?,?,?,?,?,?,?,?,?)',(c['name'],c['location'],c['work_days'],c['start_time'],c['end_time'],c['visit_minutes'],c['daily_limit'],json.dumps(c['services'],ensure_ascii=False),c['documents'],c['instructions']))
   for wd in map(int,c['work_days'].split(',')): conn.execute('INSERT INTO ClinicSchedules(clinic_id,weekday,start_time,end_time) VALUES(?,?,?,?)',(cur.lastrowid,wd,c['start_time'],c['end_time']))
 conn.commit(); conn.close()

def audit(action,entity,entity_id=None,details=''):
 db().execute('INSERT INTO AuditLogs(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)',(session.get('user_id'),action,entity,entity_id,details,now())); db().commit()
def user_row():
 uid=session.get('user_id'); return db().execute('SELECT id,username,display_name,role FROM Users WHERE id=? AND active=1',(uid,)).fetchone() if uid else None
def auth_required(roles=None):
 def deco(fn):
  @wraps(fn)
  def wrapped(*a,**kw):
   u=user_row()
   if not u:return jsonify(error='يجب تسجيل الدخول'),401
   if roles and u['role'] not in roles:return jsonify(error='ليس لديك صلاحية لهذه العملية'),403
   g.user=u; return fn(*a,**kw)
  return wrapped
 return deco

def clinic_dict(row):
 d=dict(row); d['services']=jloads(d.pop('services_json','[]')); return d
def booking_row(bid):
 return db().execute('''SELECT b.*,c.name clinic_name,c.location clinic_location,c.services_json,q.id queue_id,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.id=?''',(bid,)).fetchone()
def booking_json(row):
 if not row:return None
 d=dict(row); d['confirmation_url']=f'/confirmation/{d["id"]}'; return d

def service_for(clinic, name):
 return next((x for x in jloads(clinic['services_json']) if x.get('name')==name),None)
def validate_booking(data, source='external'):
 required=['patient_name','phone','clinic_id','visit_date','appointment_time','service_type']
 if any(not str(data.get(x,'')).strip() for x in required):raise ValueError('الاسم والهاتف والعيادة والتاريخ والموعد ونوع الخدمة حقول مطلوبة')
 clinic=db().execute('SELECT * FROM Clinics WHERE id=? AND active=1',(int(data['clinic_id']),)).fetchone()
 if not clinic:raise ValueError('العيادة غير متاحة')
 visit=date.fromisoformat(str(data['visit_date']))
 if visit<date.today():raise ValueError('لا يمكن الحجز في تاريخ سابق')
 if str(visit.weekday()) not in [x.strip() for x in clinic['work_days'].split(',')]:raise ValueError('اليوم غير مسموح لهذه العيادة')
 service=service_for(clinic,str(data['service_type']).strip())
 if not service:raise ValueError('نوع الخدمة غير متاح لهذه العيادة')
 if service.get('direct_only'):raise ValueError('هذه الخدمة بالحضور المباشر فقط ولا يمكن حجزها إلكترونيًا')
 total=db().execute("SELECT COUNT(*) FROM Bookings WHERE clinic_id=? AND visit_date=? AND service_type=? AND status<>'Cancelled'",(clinic['id'],data['visit_date'],data['service_type'])).fetchone()[0]
 limit=min(int(clinic['daily_limit']),int(service.get('limit') or clinic['daily_limit']))
 if total>=limit:raise ValueError('اكتملت الطاقة الاستيعابية لهذه الخدمة في هذا اليوم')
 return clinic,service

def assign_queue(bid,clinic_id=None):
 b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone(); clinic_id=clinic_id or b['clinic_id']
 old=db().execute('SELECT id FROM QueueEntries WHERE booking_id=? AND clinic_id=? AND queue_date=?',(bid,clinic_id,b['visit_date'])).fetchone()
 if old:return old['id']
 no=db().execute('SELECT COALESCE(MAX(queue_no),0)+1 FROM QueueEntries WHERE clinic_id=? AND queue_date=?',(clinic_id,b['visit_date'])).fetchone()[0]
 cur=db().execute('INSERT INTO QueueEntries(booking_id,clinic_id,queue_date,queue_no,state,created_at) VALUES(?,?,?,?,?,?)',(bid,clinic_id,b['visit_date'],no,'Waiting',now())); db().execute('INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)',(cur.lastrowid,'created',session.get('user_id'),now())); db().commit(); return cur.lastrowid

def make_booking(data,source='external'):
 clinic,service=validate_booking(data,source)
 no=f'B{datetime.now().strftime("%y%m%d")}-{secrets.token_hex(3).upper()}'
 cur=db().execute('''INSERT INTO Bookings(booking_no,patient_name,age,address,phone,clinic_id,visit_date,appointment_time,service_type,status,source,instructions_snapshot,documents_snapshot,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(no,str(data['patient_name']).strip(),str(data.get('age','')).strip(),str(data.get('address','')).strip(),str(data['phone']).strip(),clinic['id'],data['visit_date'],data['appointment_time'],data['service_type'],'Confirmed' if source=='internal' else 'Pending',source,service.get('instructions') or clinic['instructions'],clinic['documents'],now(),now()))
 bid=cur.lastrowid
 if source=='internal':assign_queue(bid)
 db().execute('INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)',(bid,'تم استلام طلب الحجز وسيتم تأكيده من موظف الحجز',now())); db().commit(); audit('create_booking','Booking',bid,source); return booking_json(booking_row(bid))

@app.route('/')
def home():return render_template('index.html')
@app.get('/api/me')
def me():
 u=user_row(); return jsonify(user=dict(u) if u else None)
@app.post('/api/login')
def login():
 data=request.get_json() or {};u=db().execute('SELECT * FROM Users WHERE username=? AND active=1',(data.get('username',''),)).fetchone()
 if not u or hash_password(data.get('password',''))!=u['password_hash']:return jsonify(error='بيانات الدخول غير صحيحة'),401
 session['user_id']=u['id'];audit('login','User',u['id']);return jsonify(user=dict(user_row()))
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/clinics')
def clinics():return jsonify(clinics=[clinic_dict(x) for x in db().execute('SELECT * FROM Clinics WHERE active=1 ORDER BY id')])
@app.get('/api/clinics/all')
@auth_required({'booking'})
def clinics_all():return jsonify(clinics=[clinic_dict(x) for x in db().execute('SELECT * FROM Clinics ORDER BY id')])
@app.post('/api/clinics')
@auth_required({'booking'})
def create_clinic():
 data=request.get_json() or {}; required=['name','location','work_days','start_time','end_time','visit_minutes','daily_limit','services']
 if any(not data.get(x) for x in required):return jsonify(error='بيانات العيادة والخدمات مطلوبة'),400
 cur=db().execute('INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit,services_json,documents,instructions) VALUES(?,?,?,?,?,?,?,?,?,?)',(data['name'],data['location'],data['work_days'],data['start_time'],data['end_time'],int(data['visit_minutes']),int(data['daily_limit']),json.dumps(data['services'],ensure_ascii=False),data.get('documents',''),data.get('instructions',''))); db().commit(); audit('create_clinic','Clinic',cur.lastrowid); return jsonify(clinic=clinic_dict(db().execute('SELECT * FROM Clinics WHERE id=?',(cur.lastrowid,)).fetchone())),201
@app.patch('/api/clinics/<int:cid>')
@auth_required({'booking'})
def update_clinic(cid):
 data=request.get_json() or {}; allowed={k:data[k] for k in ['name','location','work_days','start_time','end_time','visit_minutes','daily_limit','documents','instructions','active'] if k in data}
 if 'services' in data:allowed['services_json']=json.dumps(data['services'],ensure_ascii=False)
 if not allowed:return jsonify(error='لا توجد تغييرات'),400
 sql=','.join(f'{k}=?' for k in allowed); db().execute(f'UPDATE Clinics SET {sql} WHERE id=?',[*allowed.values(),cid]); db().commit();audit('update_clinic','Clinic',cid);return jsonify(clinic=clinic_dict(db().execute('SELECT * FROM Clinics WHERE id=?',(cid,)).fetchone()))
@app.post('/api/bookings')
def create_booking():
 try:return jsonify(booking=make_booking(request.get_json() or {})),201
 except (ValueError,sqlite3.IntegrityError) as e:return jsonify(error=str(e)),400
@app.get('/api/bookings/track')
def track():
 row=db().execute('SELECT b.*,c.name clinic_name,c.location clinic_location,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.phone=? AND b.booking_no=?',(request.args.get('phone','').strip(),request.args.get('booking_no','').strip())).fetchone();return jsonify(booking=booking_json(row)) if row else (jsonify(error='لم يتم العثور على الحجز'),404)
@app.get('/api/bookings/<int:bid>/confirmation')
def confirmation(bid):
 row=booking_row(bid)
 if not row:return jsonify(error='الحجز غير موجود'),404
 return jsonify(booking=booking_json(row),instructions=row['instructions_snapshot'].splitlines(),documents=row['documents_snapshot'])
@app.get('/api/bookings')
@auth_required({'booking','doctor','nurse'})
def list_bookings():
 q=request.args.get('q','').strip();clinic=request.args.get('clinic_id');day=request.args.get('date');sql='SELECT b.*,c.name clinic_name,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE 1=1';args=[]
 if q:sql+=' AND (b.patient_name LIKE ? OR b.phone LIKE ? OR b.booking_no LIKE ? OR CAST(q.queue_no AS TEXT)=?)';args += [f'%{q}%']*3+[q]
 if clinic:sql+=' AND b.clinic_id=?';args.append(clinic)
 if day:sql+=' AND b.visit_date=?';args.append(day)
 sql+=' ORDER BY b.visit_date,b.appointment_time,b.id DESC LIMIT 300';return jsonify(bookings=[dict(x) for x in db().execute(sql,args)])
@app.post('/api/bookings/<int:bid>/confirm')
@auth_required({'booking'})
def confirm(bid):
 b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone()
 if not b or b['status']=='Cancelled':return jsonify(error='الحجز غير صالح'),400
 db().execute("UPDATE Bookings SET status='Confirmed',updated_at=? WHERE id=?",(now(),bid));assign_queue(bid);db().execute('INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)',(bid,'تم تأكيد حجزك وإصدار رقم الدخول',now()));db().commit();audit('confirm_booking','Booking',bid);return jsonify(booking=booking_json(booking_row(bid)))
@app.post('/api/bookings/<int:bid>/cancel')
@auth_required({'booking'})
def cancel(bid):db().execute("UPDATE Bookings SET status='Cancelled',updated_at=? WHERE id=?",(now(),bid));db().commit();audit('cancel_booking','Booking',bid);return jsonify(ok=True)
@app.post('/api/bookings/<int:bid>/reschedule')
@auth_required({'booking'})
def reschedule(bid):
 data=request.get_json() or {};b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone()
 if not b:return jsonify(error='الحجز غير موجود'),404
 try:
  clinic,service=validate_booking({**dict(b),**data,'clinic_id':data.get('clinic_id',b['clinic_id']),'service_type':data.get('service_type',b['service_type'])})
 except ValueError as e:return jsonify(error=str(e)),400
 db().execute("UPDATE Bookings SET clinic_id=?,visit_date=?,appointment_time=?,service_type=?,status='Pending',instructions_snapshot=?,documents_snapshot=?,updated_at=? WHERE id=?",(clinic['id'],data['visit_date'],data['appointment_time'],data.get('service_type',b['service_type']),service.get('instructions') or clinic['instructions'],clinic['documents'],now(),bid));db().commit();audit('reschedule_booking','Booking',bid);return jsonify(booking=booking_json(booking_row(bid)))
@app.post('/api/bookings/internal')
@auth_required({'booking'})
def internal_booking():
 try:return jsonify(booking=make_booking(request.get_json() or {},'internal')),201
 except ValueError as e:return jsonify(error=str(e)),400
@app.get('/api/queue')
@auth_required({'booking','doctor','nurse'})
def queue():
 rows=db().execute('SELECT q.*,b.booking_no,b.patient_name,b.phone,b.appointment_time,c.name clinic_name FROM QueueEntries q JOIN Bookings b ON b.id=q.booking_id JOIN Clinics c ON c.id=q.clinic_id WHERE q.clinic_id=? AND q.queue_date=? ORDER BY q.queue_no',(request.args.get('clinic_id'),request.args.get('date',today()))).fetchall();return jsonify(queue=[dict(x) for x in rows])
@app.post('/api/queue/<int:qid>/action')
@auth_required({'doctor','nurse','booking'})
def queue_action(qid):
 action=(request.get_json() or {}).get('action');allowed={'call':'Called','start':'InExam','next':'Completed','skip':'Skipped','resume':'Waiting','complete':'Completed'}
 if action not in allowed:return jsonify(error='إجراء غير معروف'),400
 q=db().execute('SELECT * FROM QueueEntries WHERE id=?',(qid,)).fetchone()
 if not q:return jsonify(error='الحالة غير موجودة'),404
 db().execute('UPDATE QueueEntries SET state=?,current=? WHERE id=?',(allowed[action],1 if action in {'call','start'} else 0,qid));db().execute('INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)',(qid,action,session.get('user_id'),now()))
 if action in {'next','complete'}:db().execute("UPDATE Bookings SET status='Completed',updated_at=? WHERE id=?",(now(),q['booking_id']))
 db().commit();audit(action,'QueueEntry',qid);return jsonify(ok=True)
@app.post('/api/bookings/<int:bid>/transfer')
@auth_required({'doctor','nurse'})
def transfer(bid):
 data=request.get_json() or {};target=int(data.get('clinic_id',0));b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone();c=db().execute('SELECT * FROM Clinics WHERE id=? AND active=1',(target,)).fetchone()
 if not b or not c:return jsonify(error='الحجز أو العيادة غير موجود'),400
 old=b['clinic_id'];db().execute('UPDATE Bookings SET clinic_id=?,updated_at=? WHERE id=?',(target,now(),bid));qid=assign_queue(bid,target);db().execute('INSERT INTO Transfers(booking_id,from_clinic_id,to_clinic_id,queue_entry_id,actor_id,created_at) VALUES(?,?,?,?,?,?)',(bid,old,target,qid,session.get('user_id'),now()));db().commit();audit('transfer','Booking',bid,f'{old}->{target}');return jsonify(booking=booking_json(booking_row(bid)))
@app.get('/api/tv')
def tv():
 rows=db().execute("SELECT c.id,c.name,q.queue_date,MAX(CASE WHEN q.current=1 THEN q.queue_no END) current_no,MIN(CASE WHEN q.state='Waiting' THEN q.queue_no END) next_no FROM Clinics c LEFT JOIN QueueEntries q ON q.clinic_id=c.id AND q.queue_date=? WHERE c.active=1 GROUP BY c.id,c.name,q.queue_date",(request.args.get('date',today()),)).fetchall();return jsonify(clinics=[dict(x) for x in rows])
@app.errorhandler(404)
def not_found(e):return jsonify(error='المسار غير موجود'),404 if request.path.startswith('/api/') else render_template('index.html')
init_db()
if __name__=='__main__':app.run(host='0.0.0.0',port=4173,debug=False)
