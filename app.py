from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
import csv, hashlib, io, json, os, re, secrets, sqlite3, urllib.request
from zipfile import ZipFile, ZIP_DEFLATED
from flask import Flask, jsonify, request, session, render_template, g, Response

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('BSCH_DB_PATH', str(BASE_DIR / 'bsch_clinics.sqlite3'))).expanduser()
app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get('BSCH_SECRET_KEY', secrets.token_hex(32)), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
ROLES = {'founder': 'المؤسس', 'booking': 'موظف الحجز', 'doctor': 'طبيب', 'nurse': 'تمريض'}
MANAGERS = {'founder', 'booking'}
TEMPLATE_VARS = ['patientName','clinicName','clinicDays','workingHours','queueNumber','trackingLink','hospitalName','serviceType','appointmentDate','appointmentTime']
HOSPITAL = 'مستشفى الأطفال التخصصي بالبحيرة'
OPERATING_MODES = {'online','hospital_server','standalone_offline'}

CLINIC_SEED = [
 {'name':'عيادة الجهاز الهضمي','location':'','work_days':'6,2','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':75,'services':[{'name':'كشف أول مرة','limit':0},{'name':'متابعة','limit':0}],'documents':'صورة بطاقة الأب والأم + شهادة ميلاد كمبيوتر + تقارير الطفل','instructions':''},
 {'name':'عيادة التغذية','location':'','work_days':'0,3,4','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':50,'services':[{'name':'كشف أول مرة','limit':0},{'name':'متابعة','limit':0}],'documents':'صورة بطاقة الأب والأم + شهادة ميلاد كمبيوتر + تقارير الطفل','instructions':''},
 {'name':'عيادة النفسية والعصبية','location':'','work_days':'6','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':15,'services':[{'name':'كشف أول مرة','limit':0},{'name':'متابعة','limit':0}],'documents':'','instructions':''},
 {'name':'عيادة الأسنان','location':'','work_days':'6,0,1,2,3,4','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':4,'services':[{'name':'خلع','limit':0},{'name':'حشو','limit':0}],'documents':'صورة بطاقة الأب أو الأم','instructions':''},
 {'name':'عيادة الإيكو','location':'أمام عيادة القلب بالدور الرابع','work_days':'6,0,1,2,3,4','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':5,'services':[{'name':'كشف أول مرة','limit':0},{'name':'متابعة','limit':0}],'documents':'','instructions':'الحضور الساعة 8:30 صباحًا أمام عيادة القلب بالدور الرابع.\nللأطفال من 6 شهور حتى 3 سنوات: قد يُطلب تجهيز الطفل بمادة كلورال هيدرات تحت إشراف طبيب عيادة القلب حسب الحالة.\nيجب أن يكون الطفل خاليًا من أعراض البرد.\nإيقاظ الطفل مبكرًا وعدم السماح له بالنوم في الطريق حتى يمكنه النوم أثناء الفحص عند الحاجة.'},
 {'name':'عيادة السمعيات','location':'','work_days':'6,0,1,2,3,4','start_time':'08:30','end_time':'14:00','visit_minutes':20,'daily_limit':0,'services':[{'name':'رسم سمع كمبيوتر (جذع المخ)','limit':3,'instructions':'العمر أقل من 5 سنوات وأكبر من 3 شهور. يجب التأكد من عدم وجود كحة أو رشح أو ارتفاع درجة الحرارة.'},{'name':'رسم سمع (5 سنوات فأكثر)','limit':5,'instructions':'الحضور للمستشفى مبكرًا وبحد أقصى الساعة 8:30 صباحًا.'},{'name':'حالات ضغط الأذن','limit':0,'direct_only':True},{'name':'حالات محولة (مبادرة السمع)','limit':0,'direct_only':True}],'documents':'','instructions':''}
]
DEFAULT_TEMPLATES = [
 ('welcome','رسالة الترحيب','مرحبًا {{patientName}}، أهلاً بك في {{hospitalName}}. يمكننا مساعدتك في طلب حجز بالعيادات الخارجية.'),
 ('missing_data','طلب البيانات الناقصة','مرحبًا {{patientName}}، لاستكمال طلبك نحتاج إلى: {{missingFields}}.'),
 ('booking_confirmation','تأكيد الحجز','تم تأكيد حجز {{patientName}} في {{clinicName}} لخدمة {{serviceType}} يوم {{appointmentDate}} الساعة {{appointmentTime}}. رقم الدخول: {{queueNumber}}. {{trackingLink}}'),
 ('cancellation','الإلغاء','نحيطكم علمًا بإلغاء حجز {{patientName}} في {{clinicName}} بتاريخ {{appointmentDate}}. للاستفسار تواصلوا مع موظف الحجز.'),
 ('reschedule','تعديل/إعادة جدولة الموعد','تم تعديل موعد {{patientName}} في {{clinicName}} إلى {{appointmentDate}} الساعة {{appointmentTime}}.'),
 ('clinic_unavailable','عدم توفر العيادة','نعتذر، عيادة {{clinicName}} غير متاحة للحجز في {{appointmentDate}}. {{clinicDays}}'),
 ('queue_followup','متابعة رقم الانتظار','{{patientName}}، رقم انتظارك في {{clinicName}} هو {{queueNumber}}. يرجى متابعة الشاشة والحضور عند النداء.'),
 ('attendance_instructions','تعليمات الحضور','تعليمات الحضور لـ{{clinicName}}: {{attendanceInstructions}} الأوراق المطلوبة: {{documents}}')
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
def setting(key, default=''):
 row=db().execute('SELECT setting_value FROM SystemSettings WHERE setting_key=?',(key,)).fetchone()
 return row['setting_value'] if row else default
def current_mode():
 mode=os.environ.get('BSCH_OPERATING_MODE') or setting('operating_mode','standalone_offline')
 return mode if mode in OPERATING_MODES else 'standalone_offline'
def setting_bool(key, default=False): return setting(key,'1' if default else '0')=='1'
def ensure_col(conn, table, col, typ):
 try: conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {typ}')
 except sqlite3.OperationalError: pass

def init_db():
 conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys=ON')
 conn.executescript('''
 CREATE TABLE IF NOT EXISTS Users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,display_name TEXT NOT NULL,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS SystemSettings(setting_key TEXT PRIMARY KEY,setting_value TEXT NOT NULL,updated_by INTEGER,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Clinics(id INTEGER PRIMARY KEY,name TEXT NOT NULL,location TEXT NOT NULL DEFAULT '',work_days TEXT NOT NULL DEFAULT '0,1,2,3,4',start_time TEXT NOT NULL DEFAULT '09:00',end_time TEXT NOT NULL DEFAULT '14:00',visit_minutes INTEGER NOT NULL DEFAULT 15,daily_limit INTEGER NOT NULL DEFAULT 30,active INTEGER NOT NULL DEFAULT 1,services_json TEXT NOT NULL DEFAULT '[]',documents TEXT NOT NULL DEFAULT '',instructions TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS ClinicSchedules(id INTEGER PRIMARY KEY,clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE,weekday INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,UNIQUE(clinic_id,weekday));
 CREATE TABLE IF NOT EXISTS ClinicServiceSchedules(id INTEGER PRIMARY KEY,clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE,service_name TEXT NOT NULL,weekday INTEGER NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,daily_limit INTEGER,hourly_limit INTEGER,active INTEGER NOT NULL DEFAULT 1,UNIQUE(clinic_id,service_name,weekday));
 CREATE TABLE IF NOT EXISTS ClinicClosures(id INTEGER PRIMARY KEY,clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE,closure_date TEXT NOT NULL,reason TEXT NOT NULL DEFAULT '',created_by INTEGER,created_at TEXT NOT NULL,UNIQUE(clinic_id,closure_date));
 CREATE TABLE IF NOT EXISTS ClinicDoctors(id INTEGER PRIMARY KEY,clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE,doctor_name TEXT NOT NULL,weekday INTEGER,start_time TEXT,end_time TEXT,active INTEGER NOT NULL DEFAULT 1,created_by INTEGER,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Bookings(id INTEGER PRIMARY KEY,booking_no TEXT UNIQUE NOT NULL,patient_name TEXT NOT NULL,age TEXT NOT NULL DEFAULT '',address TEXT NOT NULL DEFAULT '',phone TEXT NOT NULL,national_id TEXT NOT NULL DEFAULT '',clinic_id INTEGER NOT NULL REFERENCES Clinics(id),visit_date TEXT NOT NULL,appointment_time TEXT NOT NULL,service_type TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT 'Pending',source TEXT NOT NULL DEFAULT 'system',notes TEXT NOT NULL DEFAULT '',instructions_snapshot TEXT NOT NULL DEFAULT '',documents_snapshot TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS QueueEntries(id INTEGER PRIMARY KEY,booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE,clinic_id INTEGER NOT NULL REFERENCES Clinics(id),queue_date TEXT NOT NULL,queue_no INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'Waiting',current INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL,UNIQUE(clinic_id,queue_date,queue_no));
 CREATE TABLE IF NOT EXISTS QueueEvents(id INTEGER PRIMARY KEY,queue_entry_id INTEGER NOT NULL REFERENCES QueueEntries(id) ON DELETE CASCADE,event_type TEXT NOT NULL,actor_id INTEGER,details TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Transfers(id INTEGER PRIMARY KEY,booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE,from_clinic_id INTEGER NOT NULL REFERENCES Clinics(id),to_clinic_id INTEGER NOT NULL REFERENCES Clinics(id),queue_entry_id INTEGER,actor_id INTEGER,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS Notifications(id INTEGER PRIMARY KEY,booking_id INTEGER,message TEXT NOT NULL,read_at TEXT,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS AuditLogs(id INTEGER PRIMARY KEY,actor_id INTEGER,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id INTEGER,details TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS MessageTemplates(id INTEGER PRIMARY KEY,template_key TEXT UNIQUE NOT NULL,name TEXT NOT NULL,body TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,updated_by INTEGER,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS IncomingMessages(id INTEGER PRIMARY KEY,channel TEXT NOT NULL,external_id TEXT, sender TEXT NOT NULL DEFAULT '',message_text TEXT NOT NULL,parsed_json TEXT NOT NULL DEFAULT '{}',missing_json TEXT NOT NULL DEFAULT '[]',status TEXT NOT NULL DEFAULT 'received',booking_id INTEGER,created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS OutgoingMessages(id INTEGER PRIMARY KEY,channel TEXT NOT NULL,recipient TEXT NOT NULL DEFAULT '',message_text TEXT NOT NULL,template_key TEXT,booking_id INTEGER,status TEXT NOT NULL DEFAULT 'queued',error TEXT NOT NULL DEFAULT '',attempts INTEGER NOT NULL DEFAULT 0,sent_at TEXT,created_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS idx_bookings_phone ON Bookings(phone); CREATE INDEX IF NOT EXISTS idx_bookings_duplicate ON Bookings(patient_name,phone,clinic_id,visit_date); CREATE INDEX IF NOT EXISTS idx_queue_day ON QueueEntries(clinic_id,queue_date);
 ''')
 for col,typ in [('services_json',"TEXT NOT NULL DEFAULT '[]'"),('documents',"TEXT NOT NULL DEFAULT ''"),('instructions',"TEXT NOT NULL DEFAULT ''")]: ensure_col(conn,'Clinics',col,typ)
 ensure_col(conn,'ClinicServiceSchedules','hourly_limit','INTEGER')
 for col,typ in [('age',"TEXT NOT NULL DEFAULT ''"),('address',"TEXT NOT NULL DEFAULT ''"),('national_id',"TEXT NOT NULL DEFAULT ''"),('service_type',"TEXT NOT NULL DEFAULT ''"),('source',"TEXT NOT NULL DEFAULT 'system'"),('instructions_snapshot',"TEXT NOT NULL DEFAULT ''"),('documents_snapshot',"TEXT NOT NULL DEFAULT ''")]: ensure_col(conn,'Bookings',col,typ)
 for u,p,n,r in [('Bahnasy','Bahnasy','Ahmed Bahnasy','founder'),('bsch','bsch','موظف الحجز','booking'),('belal','c4e56e5231','بلال — موظف حجز','booking'),('bschdr','bschdr','الطبيب','doctor'),('bschnurse','bschnurse','التمريض','nurse')]: conn.execute('INSERT OR IGNORE INTO Users(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)',(u,hash_password(p),n,r,now()))
 conn.execute("UPDATE Users SET display_name='Ahmed Bahnasy' WHERE username='Bahnasy' AND role='founder'")
 legacy=conn.execute("SELECT id FROM Users WHERE username='founder' AND role='founder'").fetchone()
 if legacy and not conn.execute("SELECT id FROM Users WHERE username='Bahnasy'").fetchone(): conn.execute("UPDATE Users SET username='Bahnasy',password_hash=? WHERE id=?",(hash_password('Bahnasy'),legacy['id']))
 existing={x['name'] for x in conn.execute('SELECT name FROM Clinics')}; old_names={'عيادة الأطفال','عيادة القلب','عيادة الباطنة'}
 if not existing or existing.issubset(old_names):
  conn.execute('DELETE FROM ClinicSchedules'); conn.execute('DELETE FROM Clinics')
  for c in CLINIC_SEED:
   cur=conn.execute('INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit,services_json,documents,instructions) VALUES(?,?,?,?,?,?,?,?,?,?)',(c['name'],c['location'],c['work_days'],c['start_time'],c['end_time'],c['visit_minutes'],c['daily_limit'],json.dumps(c['services'],ensure_ascii=False),c['documents'],c['instructions']))
   for wd in map(int,c['work_days'].split(',')): conn.execute('INSERT OR IGNORE INTO ClinicSchedules(clinic_id,weekday,start_time,end_time) VALUES(?,?,?,?)',(cur.lastrowid,wd,c['start_time'],c['end_time']))
 for seed in CLINIC_SEED:
  row=conn.execute('SELECT id FROM Clinics WHERE name=?',(seed['name'],)).fetchone()
  if row:
   cid=row[0]
   conn.execute('UPDATE Clinics SET location=?,work_days=?,start_time=?,end_time=?,visit_minutes=?,daily_limit=?,services_json=?,documents=?,instructions=? WHERE id=?',(seed['location'],seed['work_days'],seed['start_time'],seed['end_time'],seed['visit_minutes'],seed['daily_limit'],json.dumps(seed['services'],ensure_ascii=False),seed['documents'],seed['instructions'],cid))
   conn.execute('DELETE FROM ClinicSchedules WHERE clinic_id=?',(cid,))
   for wd in map(int,seed['work_days'].split(',')): conn.execute('INSERT OR IGNORE INTO ClinicSchedules(clinic_id,weekday,start_time,end_time) VALUES(?,?,?,?)',(cid,wd,seed['start_time'],seed['end_time']))
 for key,name,body in DEFAULT_TEMPLATES: conn.execute('INSERT OR IGNORE INTO MessageTemplates(template_key,name,body,updated_at) VALUES(?,?,?,?)',(key,name,body,now()))
 for key,value in [('operating_mode',os.environ.get('BSCH_OPERATING_MODE','standalone_offline')),('online_booking','1'),('external_channels','0'),('ai_validation','0'),('hospital_name',HOSPITAL)]: conn.execute('INSERT OR IGNORE INTO SystemSettings(setting_key,setting_value,updated_at) VALUES(?,?,?)',(key,value,now()))
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
 return db().execute('''SELECT b.*,c.name clinic_name,c.location clinic_location,c.work_days clinic_days,c.start_time clinic_start,c.end_time clinic_end,q.id queue_id,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.id=?''',(bid,)).fetchone()
def booking_json(row):
 if not row:return None
 d=dict(row); d['confirmation_url']=f'/confirmation/{d["id"]}'; return d
def service_for(clinic,name): return next((x for x in jloads(clinic['services_json']) if x.get('name')==name),None)
def similar_bookings(data, exclude_id=None):
 sql='''SELECT b.*,c.name clinic_name FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id WHERE b.clinic_id=? AND b.visit_date=? AND b.status NOT IN ('Cancelled','NoShow') AND (lower(trim(b.patient_name))=lower(trim(?)) OR b.phone=? OR (?<>'' AND b.national_id=?))'''
 args=[int(data['clinic_id']),str(data['visit_date']),str(data.get('patient_name','')),str(data.get('phone','')),str(data.get('national_id','')),str(data.get('national_id',''))]
 if exclude_id:sql+=' AND b.id<>?';args.append(exclude_id)
 return [dict(x) for x in db().execute(sql,args).fetchall()]
def validate_booking(data,source='system',exclude_id=None,allow_closed=False):
 required=['patient_name','phone','clinic_id','visit_date','appointment_time','service_type']
 if any(not str(data.get(x,'')).strip() for x in required):raise ValueError('الاسم والهاتف والعيادة والتاريخ والموعد ونوع الخدمة حقول مطلوبة')
 clinic=db().execute('SELECT * FROM Clinics WHERE id=? AND active=1',(int(data['clinic_id']),)).fetchone()
 if not clinic:raise ValueError('العيادة غير متاحة')
 visit=date.fromisoformat(str(data['visit_date']))
 if visit<date.today():raise ValueError('لا يمكن الحجز في تاريخ سابق')
 if not allow_closed and db().execute('SELECT 1 FROM ClinicClosures WHERE clinic_id=? AND closure_date=?',(clinic['id'],str(data['visit_date']))).fetchone():raise ValueError('العيادة مغلقة في هذا اليوم')
 if str(visit.weekday()) not in [x.strip() for x in clinic['work_days'].split(',')]:raise ValueError('اليوم غير مسموح لهذه العيادة')
 service=service_for(clinic,str(data['service_type']).strip())
 if not service:raise ValueError('نوع الخدمة غير متاح لهذه العيادة')
 if service.get('direct_only'):raise ValueError('هذه الخدمة بالحضور المباشر فقط ولا يمكن حجزها إلكترونيًا')
 ss=db().execute('SELECT * FROM ClinicServiceSchedules WHERE clinic_id=? AND service_name=? AND weekday=? AND active=1',(clinic['id'],service['name'],visit.weekday())).fetchall()
 if ss:
  s=ss[0]; tm=str(data['appointment_time']);
  if not (s['start_time']<=tm<=s['end_time']):raise ValueError('الموعد خارج أوقات الخدمة المتاحة')
 total=db().execute("SELECT COUNT(*) FROM Bookings WHERE clinic_id=? AND visit_date=? AND service_type=? AND status NOT IN ('Cancelled','NoShow')",(clinic['id'],data['visit_date'],data['service_type'])).fetchone()[0]
 limit=min(int(clinic['daily_limit']),int(service.get('limit') or clinic['daily_limit']))
 if ss and ss[0]['daily_limit']:limit=min(limit,int(ss[0]['daily_limit']))
 if total>=limit:raise ValueError('اكتملت الطاقة الاستيعابية لهذه الخدمة في هذا اليوم')
 if ss and ss[0]['hourly_limit']:
  hour=str(data['appointment_time'])[:2]
  hourly=db().execute("SELECT COUNT(*) FROM Bookings WHERE clinic_id=? AND visit_date=? AND service_type=? AND substr(appointment_time,1,2)=? AND status NOT IN ('Cancelled','NoShow')",(clinic['id'],data['visit_date'],data['service_type'],hour)).fetchone()[0]
  if hourly>=int(ss[0]['hourly_limit']):raise ValueError('اكتملت سعة هذه الخدمة في هذه الساعة')
 return clinic,service
def assign_queue(bid,clinic_id=None):
 b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone(); clinic_id=clinic_id or b['clinic_id']; old=db().execute('SELECT id FROM QueueEntries WHERE booking_id=? AND clinic_id=? AND queue_date=?',(bid,clinic_id,b['visit_date'])).fetchone()
 if old:return old['id']
 no=db().execute('SELECT COALESCE(MAX(queue_no),0)+1 FROM QueueEntries WHERE clinic_id=? AND queue_date=?',(clinic_id,b['visit_date'])).fetchone()[0]
 cur=db().execute('INSERT INTO QueueEntries(booking_id,clinic_id,queue_date,queue_no,state,created_at) VALUES(?,?,?,?,?,?)',(bid,clinic_id,b['visit_date'],no,'Waiting',now())); db().execute('INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)',(cur.lastrowid,'created',session.get('user_id'),now())); db().commit(); return cur.lastrowid
def make_booking(data,source='system',allow_duplicate=False):
 clinic,service=validate_booking(data,source)
 duplicates=similar_bookings(data)
 if duplicates and not allow_duplicate:raise DuplicateBooking(duplicates)
 no=f'B{datetime.now().strftime("%y%m%d")}-{secrets.token_hex(3).upper()}'
 status='Confirmed' if source in ('manual','internal') else 'Pending'
 cur=db().execute('''INSERT INTO Bookings(booking_no,patient_name,age,address,phone,national_id,clinic_id,visit_date,appointment_time,service_type,status,source,instructions_snapshot,documents_snapshot,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(no,str(data['patient_name']).strip(),str(data.get('age','')).strip(),str(data.get('address','')).strip(),str(data['phone']).strip(),str(data.get('national_id','')).strip(),clinic['id'],data['visit_date'],data['appointment_time'],data['service_type'],status,source,service.get('instructions') or clinic['instructions'],clinic['documents'],now(),now()))
 bid=cur.lastrowid
 if status=='Confirmed':assign_queue(bid)
 db().execute('INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)',(bid,'تم استلام طلب الحجز وسيتم تأكيده من موظف الحجز',now())); db().commit(); audit('create_booking','Booking',bid,source); return booking_json(booking_row(bid))
class DuplicateBooking(Exception):
 def __init__(self,items):self.items=items

def template_row(key):return db().execute('SELECT * FROM MessageTemplates WHERE template_key=? AND active=1',(key,)).fetchone()
def render_template_message(key,values):
 t=template_row(key)
 if not t:raise ValueError('قالب الرسالة غير موجود')
 vals={k:str(values.get(k,'')) for k in TEMPLATE_VARS+['missingFields','attendanceInstructions','documents']}
 return re.sub(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}',lambda m:vals.get(m.group(1),m.group(0)),t['body'])
def booking_values(b):
 return {'patientName':b['patient_name'],'clinicName':b['clinic_name'],'clinicDays':b['clinic_days'],'workingHours':f'{b["clinic_start"]} - {b["clinic_end"]}','queueNumber':b.get('queue_no') or 'سيصدر بعد التأكيد','trackingLink':f'/track?booking_no={b["booking_no"]}&phone={b["phone"]}','hospitalName':HOSPITAL,'serviceType':b['service_type'],'appointmentDate':b['visit_date'],'appointmentTime':b['appointment_time'],'attendanceInstructions':b.get('instructions_snapshot',''),'documents':b.get('documents_snapshot','')}
def queue_message(bid,key='queue_followup',channel='internal'):
 b=booking_json(booking_row(bid)); msg=render_template_message(key,booking_values(b)); cur=db().execute('INSERT INTO OutgoingMessages(channel,recipient,message_text,template_key,booking_id,status,attempts,created_at) VALUES(?,?,?,?,?,?,?,?)',(channel,b.get('phone',''),msg,key,bid,'queued',0,now())); db().commit();audit('queue_message','OutgoingMessage',cur.lastrowid,key);return {'id':cur.lastrowid,'message':msg,'status':'queued'}
def fallback_extract(text):
 out={'patient_name':'','age':'','phone':'','clinic_name':'','service_type':'','visit_date':'','confidence':0.25}
 m=re.search(r'(?:الاسم|اسمي)\s*[:：]?\s*([^،,\n]+)',text); out['patient_name']=m.group(1).strip() if m else ''
 m=re.search(r'(?:سن|العمر)\s*[:：]?\s*(\d{1,3})',text);out['age']=m.group(1) if m else ''
 m=re.search(r'(01\d{9,10}|\+?20\d{10,11})',text);out['phone']=m.group(1) if m else ''
 for c in db().execute('SELECT name FROM Clinics'):
  if c['name'] in text:out['clinic_name']=c['name'];break
 for c in db().execute('SELECT services_json FROM Clinics'):
  for s in jloads(c['services_json']):
   if s.get('name') in text:out['service_type']=s['name'];break
 m=re.search(r'(20\d{2}-\d{2}-\d{2})',text);out['visit_date']=m.group(1) if m else ''
 return out
def ai_extract(text):
 key=os.environ.get('OPENAI_API_KEY'); base=os.environ.get('OPENAI_API_BASE')
 if current_mode() != 'online' or not setting_bool('ai_validation') or not key or not base:return fallback_extract(text), 'local-fallback'
 clinics=[dict(x) for x in db().execute('SELECT id,name,work_days,start_time,end_time,services_json FROM Clinics WHERE active=1')]
 prompt='استخرج بيانات طلب حجز عيادات خارجية فقط. لا تتخذ قراراً طبياً ولا تؤكد الحجز. البيانات المتاحة:\n'+json.dumps(clinics,ensure_ascii=False)+'\nالرسالة:\n'+text
 fields=['patient_name','age','phone','clinic_name','service_type','visit_date','appointment_time','national_id','confidence']
 payload={'model':'gpt-5-mini','messages':[{'role':'system','content':'أخرج JSON فقط. الحقول patient_name, age, phone, clinic_name, service_type, visit_date, appointment_time, national_id, confidence. استخدم نصاً فارغاً عند عدم المعرفة.'},{'role':'user','content':prompt}],'response_format':{'type':'json_schema','json_schema':{'name':'booking_extract','strict':True,'schema':{'type':'object','properties':{k:{'type':'string'} for k in fields},'required':fields,'additionalProperties':False}}},'max_completion_tokens':700}
 try:
  req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=15) as r:data=json.loads(r.read())
  return json.loads(data['choices'][0]['message']['content']),'ai'
 except Exception:return fallback_extract(text),'fallback'
def missing_fields(parsed):
 labels={'patient_name':'الاسم رباعي','age':'السن','phone':'رقم الهاتف','clinic_name':'العيادة','service_type':'نوع الخدمة','visit_date':'اليوم المطلوب','appointment_time':'الساعة'}
 return [label for k,label in labels.items() if not str(parsed.get(k,'')).strip()]

@app.route('/')
def home():return render_template('index.html')
@app.get('/manus-routes.json')
def manus_routes():
 return jsonify(routes=[{'path':'/','title':'الرئيسية'},{'path':'/book','title':'حجز موعد'},{'path':'/track','title':'متابعة حجز'},{'path':'/tv','title':'شاشة الانتظار'},{'path':'/queue','title':'شاشة الدور'},{'path':'/login','title':'دخول الموظفين'},{'path':'/dashboard','title':'الإعدادات'}])
@app.get('/api/me')
def me():u=user_row();return jsonify(user=dict(u) if u else None)
@app.get('/api/runtime')
def runtime():
 return jsonify(mode=current_mode(),online_booking=setting_bool('online_booking',True),external_channels=setting_bool('external_channels'),ai_validation=setting_bool('ai_validation'),hospital_name=setting('hospital_name',HOSPITAL),external_services_enabled=current_mode()=='online' and setting_bool('external_channels'))
@app.get('/api/settings')
@auth_required(MANAGERS)
def get_settings():
 return jsonify(mode=current_mode(),settings={k:setting(k) for k in ['operating_mode','online_booking','external_channels','ai_validation','hospital_name']},modes=[{'id':'online','name':'Online / Cloud','description':'الحجز الخارجي والقنوات والذكاء الاصطناعي عند تفعيلها.'},{'id':'hospital_server','name':'Hospital Server / Local Network','description':'Backend وقاعدة البيانات داخل شبكة المستشفى بدون اعتماد على الإنترنت.'},{'id':'standalone_offline','name':'Standalone Offline','description':'تشغيل محلي على جهاز واحد بدون خادم خارجي أو إنترنت.'}])
@app.patch('/api/settings')
@auth_required({'founder'})
def update_settings():
 data=request.get_json() or {};mode=data.get('operating_mode',current_mode())
 if mode not in OPERATING_MODES:return jsonify(error='وضع تشغيل غير صحيح'),400
 values={'operating_mode':mode,'online_booking':'1' if data.get('online_booking',True) else '0','external_channels':'1' if data.get('external_channels',False) and mode=='online' else '0','ai_validation':'1' if data.get('ai_validation',False) and mode=='online' else '0'}
 if data.get('hospital_name'):values['hospital_name']=str(data['hospital_name']).strip()
 for key,value in values.items():db().execute('INSERT INTO SystemSettings(setting_key,setting_value,updated_by,updated_at) VALUES(?,?,?,?) ON CONFLICT(setting_key) DO UPDATE SET setting_value=excluded.setting_value,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(key,value,session.get('user_id'),now()))
 db().commit();audit('update_operating_mode','SystemSettings',None,json.dumps(values,ensure_ascii=False));return jsonify(mode=current_mode(),settings=values)
@app.post('/api/settings/password')
@auth_required()
def change_account_password():
 data=request.get_json() or {}
 current=str(data.get('current_password',''))
 new=str(data.get('new_password',''))
 confirm=str(data.get('confirm_password',''))
 u=db().execute('SELECT * FROM Users WHERE id=? AND active=1',(session.get('user_id'),)).fetchone()
 if not u or hash_password(current)!=u['password_hash']:
  return jsonify(error='كلمة المرور الحالية غير صحيحة'),400
 if len(new)<6:
  return jsonify(error='كلمة المرور الجديدة يجب أن تكون 6 أحرف أو أرقام على الأقل'),400
 if new!=confirm:
  return jsonify(error='تأكيد كلمة المرور غير مطابق'),400
 db().execute('UPDATE Users SET password_hash=? WHERE id=?',(hash_password(new),u['id']))
 db().commit()
 audit('change_password','User',u['id'],f'تغيير كلمة مرور الحساب {u["username"]}')
 return jsonify(ok=True,message='تم تغيير كلمة المرور بنجاح')

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
@auth_required(MANAGERS)
def clinics_all():return jsonify(clinics=[clinic_dict(x) for x in db().execute('SELECT * FROM Clinics ORDER BY id')])
@app.post('/api/clinics')
@auth_required(MANAGERS)
def create_clinic():
 data=request.get_json() or {}; required=['name','location','work_days','start_time','end_time','visit_minutes','daily_limit','services']
 if any(not data.get(x) for x in required):return jsonify(error='بيانات العيادة والخدمات مطلوبة'),400
 cur=db().execute('INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit,services_json,documents,instructions) VALUES(?,?,?,?,?,?,?,?,?,?)',(data['name'],data['location'],data['work_days'],data['start_time'],data['end_time'],int(data['visit_minutes']),int(data['daily_limit']),json.dumps(data['services'],ensure_ascii=False),data.get('documents',''),data.get('instructions','')));db().commit();audit('create_clinic','Clinic',cur.lastrowid);return jsonify(clinic=clinic_dict(db().execute('SELECT * FROM Clinics WHERE id=?',(cur.lastrowid,)).fetchone())),201
@app.patch('/api/clinics/<int:cid>')
@auth_required(MANAGERS)
def update_clinic(cid):
 data=request.get_json() or {};allowed={k:data[k] for k in ['name','location','work_days','start_time','end_time','visit_minutes','daily_limit','documents','instructions','active'] if k in data}
 if 'services' in data:allowed['services_json']=json.dumps(data['services'],ensure_ascii=False)
 if not allowed:return jsonify(error='لا توجد تغييرات'),400
 sql=','.join(f'{k}=?' for k in allowed);db().execute(f'UPDATE Clinics SET {sql} WHERE id=?',[*allowed.values(),cid]);db().commit();audit('update_clinic','Clinic',cid,json.dumps(data,ensure_ascii=False));return jsonify(clinic=clinic_dict(db().execute('SELECT * FROM Clinics WHERE id=?',(cid,)).fetchone()))
@app.get('/api/clinics/<int:cid>/schedule')
@auth_required(MANAGERS)
def clinic_schedule(cid):return jsonify(closures=[dict(x) for x in db().execute('SELECT * FROM ClinicClosures WHERE clinic_id=? ORDER BY closure_date',(cid,))],service_schedules=[dict(x) for x in db().execute('SELECT * FROM ClinicServiceSchedules WHERE clinic_id=? ORDER BY service_name,weekday',(cid,))],doctors=[dict(x) for x in db().execute('SELECT * FROM ClinicDoctors WHERE clinic_id=? ORDER BY weekday,doctor_name',(cid,))])
@app.post('/api/clinics/<int:cid>/closures')
@auth_required(MANAGERS)
def closure(cid):
 d=request.get_json() or {};day=d.get('closure_date','')
 if not day:return jsonify(error='تاريخ الإغلاق مطلوب'),400
 db().execute('INSERT INTO ClinicClosures(clinic_id,closure_date,reason,created_by,created_at) VALUES(?,?,?,?,?) ON CONFLICT(clinic_id,closure_date) DO UPDATE SET reason=excluded.reason',(cid,day,d.get('reason',''),session.get('user_id'),now()));db().commit();audit('close_clinic_day','Clinic',cid,day);return jsonify(ok=True)
@app.delete('/api/clinics/<int:cid>/closures/<day>')
@auth_required(MANAGERS)
def remove_closure(cid,day):db().execute('DELETE FROM ClinicClosures WHERE clinic_id=? AND closure_date=?',(cid,day));db().commit();audit('open_clinic_day','Clinic',cid,day);return jsonify(ok=True)
@app.post('/api/clinics/<int:cid>/service-schedules')
@auth_required(MANAGERS)
def service_schedule(cid):
 d=request.get_json() or {};required=['service_name','weekday','start_time','end_time']
 if any(k not in d for k in required):return jsonify(error='جدول الخدمة ناقص'),400
 db().execute('INSERT INTO ClinicServiceSchedules(clinic_id,service_name,weekday,start_time,end_time,daily_limit,hourly_limit,active) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(clinic_id,service_name,weekday) DO UPDATE SET start_time=excluded.start_time,end_time=excluded.end_time,daily_limit=excluded.daily_limit,hourly_limit=excluded.hourly_limit,active=excluded.active',(cid,d['service_name'],int(d['weekday']),d['start_time'],d['end_time'],d.get('daily_limit'),d.get('hourly_limit'),int(d.get('active',1))));db().commit();audit('update_service_schedule','Clinic',cid,json.dumps(d,ensure_ascii=False));return jsonify(ok=True)
@app.post('/api/clinics/<int:cid>/doctors')
@auth_required(MANAGERS)
def clinic_doctor(cid):
 d=request.get_json() or {};db().execute('INSERT INTO ClinicDoctors(clinic_id,doctor_name,weekday,start_time,end_time,active,created_by,created_at) VALUES(?,?,?,?,?,?,?,?)',(cid,d.get('doctor_name',''),d.get('weekday'),d.get('start_time'),d.get('end_time'),int(d.get('active',1)),session.get('user_id'),now()));db().commit();audit('assign_clinic_doctor','Clinic',cid,json.dumps(d,ensure_ascii=False));return jsonify(ok=True)
@app.post('/api/bookings')
def create_booking():
 try:return jsonify(booking=make_booking(request.get_json() or {},(request.get_json() or {}).get('source','system'))),201
 except DuplicateBooking as e:return jsonify(error='يوجد حجز مشابه، راجعه قبل إنشاء حجز جديد',duplicates=e.items),409
 except (ValueError,sqlite3.IntegrityError) as e:return jsonify(error=str(e)),400
@app.get('/api/bookings/duplicates')
@auth_required(MANAGERS)
def duplicates():return jsonify(duplicates=similar_bookings(request.args))
@app.get('/api/bookings/track')
def track():
 row=db().execute('SELECT b.*,c.name clinic_name,c.location clinic_location,c.work_days clinic_days,c.start_time clinic_start,c.end_time clinic_end,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.phone=? AND b.booking_no=?',(request.args.get('phone','').strip(),request.args.get('booking_no','').strip())).fetchone();return jsonify(booking=booking_json(row)) if row else (jsonify(error='لم يتم العثور على الحجز'),404)
@app.get('/api/bookings/<int:bid>/confirmation')
def confirmation(bid):
 row=booking_row(bid)
 if not row:return jsonify(error='الحجز غير موجود'),404
 return jsonify(booking=booking_json(row),instructions=row['instructions_snapshot'].splitlines(),documents=row['documents_snapshot'])
@app.get('/api/bookings')
@auth_required({'booking','doctor','nurse','founder'})
def list_bookings():
 q=request.args.get('q','').strip();clinic=request.args.get('clinic_id');day=request.args.get('date');status=request.args.get('status');source=request.args.get('source');sql='SELECT b.*,c.name clinic_name,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE 1=1';args=[]
 if q:sql+=' AND (b.patient_name LIKE ? OR b.phone LIKE ? OR b.booking_no LIKE ? OR b.national_id LIKE ? OR CAST(q.queue_no AS TEXT)=?)';args += [f'%{q}%']*4+[q]
 if clinic:sql+=' AND b.clinic_id=?';args.append(clinic)
 if day:sql+=' AND b.visit_date=?';args.append(day)
 if status:sql+=' AND b.status=?';args.append(status)
 if source:sql+=' AND b.source=?';args.append(source)
 sql+=' ORDER BY b.visit_date,b.appointment_time,b.id DESC LIMIT 500';return jsonify(bookings=[dict(x) for x in db().execute(sql,args)])
@app.post('/api/bookings/<int:bid>/confirm')
@auth_required({'booking','founder'})
def confirm(bid):
 b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone()
 if not b or b['status'] in ('Cancelled','NoShow'):return jsonify(error='الحجز غير صالح'),400
 db().execute("UPDATE Bookings SET status='Confirmed',updated_at=? WHERE id=?",(now(),bid));assign_queue(bid);db().execute('INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)',(bid,'تم تأكيد حجزك وإصدار رقم الدخول',now()));db().commit();audit('confirm_booking','Booking',bid);return jsonify(booking=booking_json(booking_row(bid)))
@app.post('/api/bookings/<int:bid>/cancel')
@auth_required({'booking','founder'})
def cancel(bid):
 d=request.get_json() or {};db().execute("UPDATE Bookings SET status='Cancelled',notes=?,updated_at=? WHERE id=?",(d.get('reason',''),now(),bid));db().commit();audit('cancel_booking','Booking',bid,d.get('reason',''));return jsonify(ok=True)
@app.post('/api/bookings/<int:bid>/reschedule')
@auth_required({'booking','founder'})
def reschedule(bid):
 data=request.get_json() or {};b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone()
 if not b:return jsonify(error='الحجز غير موجود'),404
 try:clinic,service=validate_booking({**dict(b),**data,'clinic_id':data.get('clinic_id',b['clinic_id']),'service_type':data.get('service_type',b['service_type'])},exclude_id=bid)
 except ValueError as e:return jsonify(error=str(e)),400
 db().execute("UPDATE Bookings SET clinic_id=?,visit_date=?,appointment_time=?,service_type=?,status='Pending',instructions_snapshot=?,documents_snapshot=?,updated_at=? WHERE id=?",(clinic['id'],data['visit_date'],data['appointment_time'],data.get('service_type',b['service_type']),service.get('instructions') or clinic['instructions'],clinic['documents'],now(),bid));db().commit();audit('reschedule_booking','Booking',bid);return jsonify(booking=booking_json(booking_row(bid)))
@app.post('/api/bookings/internal')
@auth_required({'booking','founder'})
def internal_booking():
 try:return jsonify(booking=make_booking({**(request.get_json() or {}),'source':'manual'},'manual')),201
 except DuplicateBooking as e:return jsonify(error='يوجد حجز مشابه',duplicates=e.items),409
 except ValueError as e:return jsonify(error=str(e)),400
@app.get('/api/queue/public')
def public_queue():
 rows=db().execute("SELECT q.queue_no,q.state,c.name clinic_name FROM QueueEntries q JOIN Clinics c ON c.id=q.clinic_id WHERE q.clinic_id=? AND q.queue_date=? ORDER BY q.queue_no",(request.args.get('clinic_id'),request.args.get('date',today()))).fetchall()
 items=[dict(x) for x in rows];called=next((x['queue_no'] for x in items if x['state'] in ('Called','InExam')),None);next_no=next((x['queue_no'] for x in items if x['state']=='Waiting'),None)
 return jsonify(queue=items,current=called,next=next_no)
@app.get('/api/queue')
@auth_required({'booking','doctor','nurse','founder'})
def queue():
 rows=db().execute('SELECT q.*,b.booking_no,b.patient_name,b.phone,b.appointment_time,c.name clinic_name FROM QueueEntries q JOIN Bookings b ON b.id=q.booking_id JOIN Clinics c ON c.id=q.clinic_id WHERE q.clinic_id=? AND q.queue_date=? ORDER BY q.queue_no',(request.args.get('clinic_id'),request.args.get('date',today()))).fetchall();return jsonify(queue=[dict(x) for x in rows])
@app.post('/api/queue/<int:qid>/action')
@auth_required({'doctor','nurse','booking','founder'})
def queue_action(qid):
 action=(request.get_json() or {}).get('action');allowed={'call':'Called','start':'InExam','next':'Completed','skip':'Skipped','resume':'Waiting','complete':'Completed','no_show':'NoShow'}
 if action not in allowed:return jsonify(error='إجراء غير معروف'),400
 q=db().execute('SELECT * FROM QueueEntries WHERE id=?',(qid,)).fetchone()
 if not q:return jsonify(error='الحالة غير موجودة'),404
 new=allowed[action];db().execute('UPDATE QueueEntries SET state=?,current=? WHERE id=?',(new,1 if action in {'call','start'} else 0,qid));db().execute('INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)',(qid,action,session.get('user_id'),now()))
 if action in {'next','complete'}:db().execute("UPDATE Bookings SET status='Completed',updated_at=? WHERE id=?",(now(),q['booking_id']))
 if action=='no_show':db().execute("UPDATE Bookings SET status='NoShow',updated_at=? WHERE id=?",(now(),q['booking_id']))
 db().commit();audit(action,'QueueEntry',qid);return jsonify(ok=True)
@app.post('/api/bookings/<int:bid>/transfer')
@auth_required({'doctor','nurse','founder'})
def transfer(bid):
 data=request.get_json() or {};target=int(data.get('clinic_id',0));b=db().execute('SELECT * FROM Bookings WHERE id=?',(bid,)).fetchone();c=db().execute('SELECT * FROM Clinics WHERE id=? AND active=1',(target,)).fetchone()
 if not b or not c:return jsonify(error='الحجز أو العيادة غير موجود'),400
 old=b['clinic_id'];db().execute('UPDATE Bookings SET clinic_id=?,updated_at=? WHERE id=?',(target,now(),bid));qid=assign_queue(bid,target);db().execute('INSERT INTO Transfers(booking_id,from_clinic_id,to_clinic_id,queue_entry_id,actor_id,created_at) VALUES(?,?,?,?,?,?)',(bid,old,target,qid,session.get('user_id'),now()));db().commit();audit('transfer','Booking',bid,f'{old}->{target}');return jsonify(booking=booking_json(booking_row(bid)))
@app.get('/api/tv')
def tv():
 rows=db().execute("SELECT c.id,c.name,q.queue_date,MAX(CASE WHEN q.current=1 THEN q.queue_no END) current_no,MIN(CASE WHEN q.state='Waiting' THEN q.queue_no END) next_no FROM Clinics c LEFT JOIN QueueEntries q ON q.clinic_id=c.id AND q.queue_date=? WHERE c.active=1 GROUP BY c.id,c.name,q.queue_date",(request.args.get('date',today()),)).fetchall();return jsonify(clinics=[dict(x) for x in rows])
@app.get('/api/templates')
@auth_required(MANAGERS)
def templates():return jsonify(templates=[dict(x) for x in db().execute('SELECT * FROM MessageTemplates ORDER BY id')],variables=TEMPLATE_VARS+['missingFields','attendanceInstructions','documents'])
@app.post('/api/templates')
@auth_required({'founder'})
def save_template():
 d=request.get_json() or {};key=d.get('template_key','').strip();name=d.get('name','').strip();body=d.get('body','')
 if not key or not name or not body:return jsonify(error='مفتاح واسم ونص القالب مطلوبة'),400
 unknown=[x for x in re.findall(r'\{\{\s*([A-Za-z0-9_]+)\s*\}\}',body) if x not in TEMPLATE_VARS+['missingFields','attendanceInstructions','documents']]
 if unknown:return jsonify(error='متغيرات غير معروفة',unknown=unknown),400
 db().execute('INSERT INTO MessageTemplates(template_key,name,body,active,updated_by,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(template_key) DO UPDATE SET name=excluded.name,body=excluded.body,active=excluded.active,updated_by=excluded.updated_by,updated_at=excluded.updated_at',(key,name,body,int(d.get('active',1)),session.get('user_id'),now()));db().commit();audit('save_message_template','MessageTemplate',None,key);return jsonify(template=dict(template_row(key)))
@app.post('/api/templates/preview')
@auth_required(MANAGERS)
def template_preview():
 d=request.get_json() or {};return jsonify(message=render_template_message(d.get('template_key',''),d.get('values') or {}))
@app.post('/api/templates/test')
@auth_required(MANAGERS)
def template_test():
 d=request.get_json() or {};msg=render_template_message(d.get('template_key',''),d.get('values') or {});cur=db().execute('INSERT INTO OutgoingMessages(channel,recipient,message_text,template_key,status,attempts,created_at) VALUES(?,?,?,?,?,?,?)',(d.get('channel','test'),d.get('recipient',''),msg,d.get('template_key'),'test',0,now()));db().commit();audit('test_message_template','OutgoingMessage',cur.lastrowid);return jsonify(ok=True,id=cur.lastrowid,message=msg,status='test')
@app.get('/api/messages')
@auth_required(MANAGERS)
def messages():return jsonify(incoming=[dict(x) for x in db().execute('SELECT * FROM IncomingMessages ORDER BY id DESC LIMIT 100')],outgoing=[dict(x) for x in db().execute('SELECT * FROM OutgoingMessages ORDER BY id DESC LIMIT 100')])
@app.post('/api/messages/outgoing/<int:oid>/retry')
@auth_required(MANAGERS)
def retry_outgoing(oid):
 row=db().execute('SELECT * FROM OutgoingMessages WHERE id=?',(oid,)).fetchone()
 if not row:return jsonify(error='الرسالة غير موجودة'),404
 db().execute("UPDATE OutgoingMessages SET status='queued',error='',attempts=attempts+1 WHERE id=?",(oid,));db().commit();audit('retry_outgoing_message','OutgoingMessage',oid);return jsonify(message=dict(db().execute('SELECT * FROM OutgoingMessages WHERE id=?',(oid,)).fetchone()))
@app.post('/api/messages/outgoing/<int:oid>/result')
@auth_required(MANAGERS)
def outgoing_result(oid):
 d=request.get_json() or {};status=d.get('status','failed')
 if status not in ('sent','failed'):return jsonify(error='حالة إرسال غير صحيحة'),400
 db().execute('UPDATE OutgoingMessages SET status=?,error=?,sent_at=? WHERE id=?',(status,d.get('error',''),now() if status=='sent' else None,oid));db().commit();audit('message_send_result','OutgoingMessage',oid,status);return jsonify(ok=True)
@app.post('/api/messages/incoming')
@auth_required(MANAGERS)
def incoming_message():
 d=request.get_json() or {};text=str(d.get('message_text','')).strip();channel=d.get('channel','manual')
 if channel in ('whatsapp','telegram') and (current_mode()!='online' or not setting_bool('external_channels')):return jsonify(error='القنوات الخارجية متوقفة في وضع التشغيل الحالي؛ استخدم الحجز الداخلي أو فعّل Online مع صلاحية المدير'),503
 if not text:return jsonify(error='نص الرسالة مطلوب'),400
 parsed,engine=ai_extract(text);missing=missing_fields(parsed);status='needs_data' if missing else 'ready_for_review'
 cur=db().execute('INSERT INTO IncomingMessages(channel,external_id,sender,message_text,parsed_json,missing_json,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)',(channel,d.get('external_id'),d.get('sender',''),text,json.dumps({**parsed,'engine':engine},ensure_ascii=False),json.dumps(missing,ensure_ascii=False),status,now(),now()));db().commit();audit('receive_message','IncomingMessage',cur.lastrowid,channel)
 reply=None
 if missing:reply=render_template_message('missing_data',{'patientName':parsed.get('patient_name',''), 'missingFields':'، '.join(missing),'hospitalName':HOSPITAL});db().execute('INSERT INTO OutgoingMessages(channel,recipient,message_text,template_key,status,attempts,created_at) VALUES(?,?,?,?,?,?,?)',(channel,d.get('sender',''),reply,'missing_data','queued',0,now()));db().commit()
 return jsonify(incoming_id=cur.lastrowid,parsed=parsed,missing=missing,status=status,reply=reply,engine=engine)
@app.post('/api/messages/<int:mid>/create-booking')
@auth_required({'booking','founder'})
def create_from_message(mid):
 row=db().execute('SELECT * FROM IncomingMessages WHERE id=?',(mid,)).fetchone()
 if not row:return jsonify(error='الرسالة غير موجودة'),404
 p=jloads(row['parsed_json'],{});clinic=next((x for x in db().execute('SELECT id,name FROM Clinics') if x['name']==p.get('clinic_name')),None)
 if not clinic:return jsonify(error='العيادة غير واضحة'),400
 data={**p,'clinic_id':clinic['id'],'source':row['channel']}
 try:b=make_booking(data,row['channel'])
 except DuplicateBooking as e:return jsonify(error='يوجد حجز مشابه',duplicates=e.items),409
 except ValueError as e:return jsonify(error=str(e)),400
 db().execute("UPDATE IncomingMessages SET status='booking_created',booking_id=?,updated_at=? WHERE id=?",(b['id'],now(),mid));db().commit();audit('create_booking_from_message','IncomingMessage',mid);return jsonify(booking=b)
@app.get('/api/reports/bookings')
@auth_required({'booking','founder','doctor','nurse'})
def reports():
 day=request.args.get('date',today());clinic=request.args.get('clinic_id');status=request.args.get('status');source=request.args.get('source');sql='SELECT b.*,c.name clinic_name,q.queue_no,q.state queue_state,q.created_at queue_created FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.visit_date=?';args=[day]
 if clinic:sql+=' AND b.clinic_id=?';args.append(clinic)
 if status:sql+=' AND b.status=?';args.append(status)
 if source:sql+=' AND b.source=?';args.append(source)
 rows=[dict(x) for x in db().execute(sql,args).fetchall()];counts={'total':len(rows),'confirmed':0,'cancelled':0,'no_show':0,'completed':0,'waiting':0,'by_source':{},'average_wait_minutes':0,'examined':0}
 waits=[]
 for b in rows:
  k={'Confirmed':'confirmed','Cancelled':'cancelled','NoShow':'no_show','Completed':'completed'}.get(b['status']);
  if k:counts[k]+=1
  if b.get('queue_state') in ('Waiting','Called','InExam'):counts['waiting']+=1
  counts['by_source'][b['source']]=counts['by_source'].get(b['source'],0)+1
  if b['status']=='Completed':counts['examined']+=1
  if b.get('queue_created'):
   ev=db().execute("SELECT created_at FROM QueueEvents WHERE queue_entry_id=(SELECT id FROM QueueEntries WHERE booking_id=? ORDER BY id DESC LIMIT 1) AND event_type IN ('call','start') ORDER BY id LIMIT 1",(b['id'],)).fetchone()
   if ev:
    try:waits.append(max(0,(datetime.fromisoformat(ev['created_at'])-datetime.fromisoformat(b['queue_created'])).total_seconds()/60))
    except Exception:pass
 counts['average_wait_minutes']=round(sum(waits)/len(waits),1) if waits else 0
 return jsonify(date=day,filters={'clinic_id':clinic,'status':status,'source':source},summary=counts,bookings=rows)
def report_rows(data):
 rows=data.get('bookings',[]);return [['رقم الحجز','الاسم','الهاتف','العيادة','الخدمة','التاريخ','الوقت','الحالة','المصدر','رقم الانتظار']]+[[r.get(k,'') for k in ['booking_no','patient_name','phone','clinic_name','service_type','visit_date','appointment_time','status','source','queue_no']] for r in rows]
def minimal_xlsx(rows):
 def cell(v):return '<c t="inlineStr"><is><t>'+str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')+'</t></is></c>'
 sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join('<row>'+''.join(cell(v) for v in row)+'</row>' for row in rows)+'</sheetData></worksheet>'
 out=io.BytesIO()
 with ZipFile(out,'w',ZIP_DEFLATED) as z:
  z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
  z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
  z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Report" sheetId="1" r:id="rId1"/></sheets></workbook>')
  z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>');z.writestr('xl/worksheets/sheet1.xml',sheet)
 return out.getvalue()
@app.get('/api/reports/export')
@auth_required({'booking','founder','doctor','nurse'})
def report_export():
 data=reports().json;rows=report_rows(data);fmt=request.args.get('format','csv')
 if fmt=='csv':
  s=io.StringIO();csv.writer(s).writerows(rows);return Response('\ufeff'+s.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=bookings-report.csv'})
 if fmt=='xlsx':return Response(minimal_xlsx(rows),mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=bookings-report.xlsx'})
 html='<html dir="rtl"><meta charset="utf-8"><title>تقرير الحجوزات</title><table border="1">'+''.join('<tr>'+''.join(f'<td>{v}</td>' for v in r)+'</tr>' for r in rows)+'</table><script>window.print()</script></html>';return Response(html,mimetype='text/html')
@app.get('/api/audit-logs')
@auth_required(MANAGERS)
def audit_logs():return jsonify(logs=[dict(x) for x in db().execute('SELECT a.*,u.display_name actor_name FROM AuditLogs a LEFT JOIN Users u ON u.id=a.actor_id ORDER BY a.id DESC LIMIT 300')])
@app.errorhandler(404)
def not_found(e):return (jsonify(error='المسار غير موجود'),404) if request.path.startswith('/api/') else render_template('index.html')
init_db()
if __name__=='__main__':app.run(host=os.environ.get('BSCH_HOST','0.0.0.0'),port=int(os.environ.get('BSCH_PORT','4173')),debug=False)
