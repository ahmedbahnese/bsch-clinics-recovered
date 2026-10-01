from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
import hashlib
import secrets
import sqlite3
from flask import Flask, jsonify, request, session, render_template, g

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bsch_clinics.sqlite3"
app = Flask(__name__)
app.config.update(SECRET_KEY=secrets.token_hex(32), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

ROLES = {"booking": "موظف الحجز", "doctor": "طبيب", "nurse": "تمريض"}

def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn: conn.close()

def hash_password(password):
    return hashlib.scrypt(password.encode(), salt=b"bsch-clinics", n=2**14, r=8, p=1).hex()

def now(): return datetime.now().isoformat(timespec="seconds")
def today(): return date.today().isoformat()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS Users (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('booking','doctor','nurse')), active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS Clinics (id INTEGER PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', work_days TEXT NOT NULL DEFAULT '0,1,2,3,4', start_time TEXT NOT NULL DEFAULT '09:00', end_time TEXT NOT NULL DEFAULT '14:00', visit_minutes INTEGER NOT NULL DEFAULT 15, daily_limit INTEGER NOT NULL DEFAULT 30, active INTEGER NOT NULL DEFAULT 1);
    CREATE TABLE IF NOT EXISTS ClinicSchedules (id INTEGER PRIMARY KEY, clinic_id INTEGER NOT NULL REFERENCES Clinics(id) ON DELETE CASCADE, weekday INTEGER NOT NULL, start_time TEXT NOT NULL, end_time TEXT NOT NULL, UNIQUE(clinic_id, weekday));
    CREATE TABLE IF NOT EXISTS Bookings (id INTEGER PRIMARY KEY, booking_no TEXT UNIQUE NOT NULL, patient_name TEXT NOT NULL, phone TEXT NOT NULL, clinic_id INTEGER NOT NULL REFERENCES Clinics(id), visit_date TEXT NOT NULL, appointment_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending','Confirmed','Cancelled','Completed')), source TEXT NOT NULL DEFAULT 'external', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS QueueEntries (id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE, clinic_id INTEGER NOT NULL REFERENCES Clinics(id), queue_date TEXT NOT NULL, queue_no INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'Waiting' CHECK(state IN ('Waiting','Called','InExam','Skipped','Completed')), current INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, UNIQUE(clinic_id, queue_date, queue_no));
    CREATE TABLE IF NOT EXISTS QueueEvents (id INTEGER PRIMARY KEY, queue_entry_id INTEGER NOT NULL REFERENCES QueueEntries(id) ON DELETE CASCADE, event_type TEXT NOT NULL, actor_id INTEGER REFERENCES Users(id), details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS Transfers (id INTEGER PRIMARY KEY, booking_id INTEGER NOT NULL REFERENCES Bookings(id) ON DELETE CASCADE, from_clinic_id INTEGER NOT NULL REFERENCES Clinics(id), to_clinic_id INTEGER NOT NULL REFERENCES Clinics(id), queue_entry_id INTEGER REFERENCES QueueEntries(id), actor_id INTEGER REFERENCES Users(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS Notifications (id INTEGER PRIMARY KEY, booking_id INTEGER REFERENCES Bookings(id) ON DELETE CASCADE, channel TEXT NOT NULL DEFAULT 'in_app', message TEXT NOT NULL, read_at TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS AuditLogs (id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES Users(id), action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id INTEGER, details TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_bookings_phone ON Bookings(phone); CREATE INDEX IF NOT EXISTS idx_queue_day ON QueueEntries(clinic_id, queue_date);
    """)
    users = [("bsch", "bsch", "موظف الحجز", "booking"), ("bschdr", "bschdr", "الطبيب", "doctor"), ("bschnurse", "bschnurse", "التمريض", "nurse")]
    for username, password, display, role in users:
        conn.execute("INSERT OR IGNORE INTO Users(username,password_hash,display_name,role,created_at) VALUES(?,?,?,?,?)", (username, hash_password(password), display, role, now()))
    if conn.execute("SELECT COUNT(*) FROM Clinics").fetchone()[0] == 0:
        clinics = [("عيادة الأطفال", "الدور الأول", "0,1,2,3,4", "09:00", "14:00", 15, 30), ("عيادة القلب", "الدور الثاني", "0,1,2,3,4", "09:00", "14:00", 20, 20), ("عيادة الباطنة", "الدور الأول", "0,1,2,3,4", "10:00", "15:00", 15, 25)]
        for c in clinics:
            cur=conn.execute("INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit) VALUES(?,?,?,?,?,?,?)", c)
            cid=cur.lastrowid
            for weekday in map(int,c[2].split(',')): conn.execute("INSERT INTO ClinicSchedules(clinic_id,weekday,start_time,end_time) VALUES(?,?,?,?)", (cid,weekday,c[3],c[4]))
    conn.commit(); conn.close()

def audit(action, entity_type, entity_id=None, details=""):
    actor = session.get("user_id")
    db().execute("INSERT INTO AuditLogs(actor_id,action,entity_type,entity_id,details,created_at) VALUES(?,?,?,?,?,?)", (actor,action,entity_type,entity_id,details,now())); db().commit()

def user_row():
    uid=session.get("user_id")
    return db().execute("SELECT id,username,display_name,role FROM Users WHERE id=? AND active=1",(uid,)).fetchone() if uid else None

def auth_required(roles=None):
    def deco(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user=user_row()
            if not user: return jsonify(error="يجب تسجيل الدخول"), 401
            if roles and user["role"] not in roles: return jsonify(error="ليس لديك صلاحية لهذه العملية"), 403
            g.user=user; return fn(*args, **kwargs)
        return wrapped
    return deco

def booking_json(row):
    if not row: return None
    d=dict(row); d["clinic_name"]=d.pop("clinic_name", ""); d["queue_no"]=d.get("queue_no"); return d

def get_booking(bid):
    return db().execute("""SELECT b.*, c.name clinic_name, q.id queue_id, q.queue_no, q.state queue_state, q.current queue_current
      FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id ORDER BY q.id DESC LIMIT 1""").fetchone() if False else db().execute("""SELECT b.*, c.name clinic_name, q.id queue_id, q.queue_no, q.state queue_state, q.current queue_current FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.id=?""", (bid,)).fetchone()

def make_booking(data, source="external"):
    required=["patient_name","phone","clinic_id","visit_date","appointment_time"]
    if any(not str(data.get(x," ")).strip() for x in required): raise ValueError("الاسم والهاتف والعيادة والتاريخ والموعد حقول مطلوبة")
    clinic=db().execute("SELECT * FROM Clinics WHERE id=? AND active=1",(int(data["clinic_id"]),)).fetchone()
    if not clinic: raise ValueError("العيادة غير متاحة")
    if data["visit_date"] < today(): raise ValueError("لا يمكن الحجز في تاريخ سابق")
    count=db().execute("SELECT COUNT(*) FROM Bookings WHERE clinic_id=? AND visit_date=? AND status<>'Cancelled'",(clinic["id"],data["visit_date"])).fetchone()[0]
    if count >= clinic["daily_limit"]: raise ValueError("اكتمل العدد المسموح لهذه العيادة في هذا اليوم")
    booking_no=f"B{datetime.now().strftime('%y%m%d')}-{secrets.token_hex(3).upper()}"
    cur=db().execute("INSERT INTO Bookings(booking_no,patient_name,phone,clinic_id,visit_date,appointment_time,status,source,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(booking_no,data["patient_name"].strip(),data["phone"].strip(),clinic["id"],data["visit_date"],data["appointment_time"],"Pending" if source=="external" else "Confirmed",source,now(),now()))
    bid=cur.lastrowid
    if source != "external": assign_queue(bid)
    db().execute("INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)",(bid,"تم استلام طلب الحجز وسيتم تأكيده من موظف الحجز",now())); db().commit(); audit("create_booking","Booking",bid,source)
    return get_booking(bid)

def assign_queue(bid, clinic_id=None):
    b=db().execute("SELECT * FROM Bookings WHERE id=?",(bid,)).fetchone(); clinic_id=clinic_id or b["clinic_id"]
    existing=db().execute("SELECT id FROM QueueEntries WHERE booking_id=? AND clinic_id=? AND queue_date=?",(bid,clinic_id,b["visit_date"])).fetchone()
    if existing: return existing["id"]
    maxno=db().execute("SELECT COALESCE(MAX(queue_no),0) FROM QueueEntries WHERE clinic_id=? AND queue_date=?",(clinic_id,b["visit_date"])).fetchone()[0]
    cur=db().execute("INSERT INTO QueueEntries(booking_id,clinic_id,queue_date,queue_no,state,current,created_at) VALUES(?,?,?,?,?,?,?)",(bid,clinic_id,b["visit_date"],maxno+1,"Waiting",0,now()))
    db().execute("INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)",(cur.lastrowid,"created",session.get("user_id"),now())); db().commit(); return cur.lastrowid

@app.route("/")
def home(): return render_template("index.html")

@app.get("/api/me")
def me():
    u=user_row(); return jsonify(user=dict(u) if u else None)

@app.post("/api/login")
def login():
    data=request.get_json() or {}; u=db().execute("SELECT * FROM Users WHERE username=? AND active=1",(data.get("username",""),)).fetchone()
    if not u or hash_password(data.get("password","")) != u["password_hash"]: return jsonify(error="بيانات الدخول غير صحيحة"), 401
    session["user_id"]=u["id"]; audit("login","User",u["id"]); return jsonify(user=dict(user_row()))

@app.post("/api/logout")
def logout(): session.clear(); return jsonify(ok=True)

@app.get("/api/clinics")
def clinics(): return jsonify(clinics=[dict(x) for x in db().execute("SELECT * FROM Clinics WHERE active=1 ORDER BY name")])

@app.post("/api/clinics")
@auth_required({"booking"})
def create_clinic():
    data=request.get_json() or {}; required=["name","location","work_days","start_time","end_time","visit_minutes","daily_limit"]
    if any(not str(data.get(x," ")).strip() for x in required): return jsonify(error="كل بيانات العيادة مطلوبة"),400
    cur=db().execute("INSERT INTO Clinics(name,location,work_days,start_time,end_time,visit_minutes,daily_limit,active) VALUES(?,?,?,?,?,?,?,1)",(data["name"],data["location"],data["work_days"],data["start_time"],data["end_time"],int(data["visit_minutes"]),int(data["daily_limit"])))
    cid=cur.lastrowid
    for weekday in map(int,str(data["work_days"]).split(',')): db().execute("INSERT OR REPLACE INTO ClinicSchedules(clinic_id,weekday,start_time,end_time) VALUES(?,?,?,?)",(cid,weekday,data["start_time"],data["end_time"]))
    db().commit(); audit("create_clinic","Clinic",cid); return jsonify(clinic=dict(db().execute("SELECT * FROM Clinics WHERE id=?",(cid,)).fetchone())),201

@app.patch("/api/clinics/<int:cid>")
@auth_required({"booking"})
def update_clinic(cid):
    data=request.get_json() or {}; allowed={k:data[k] for k in ["name","location","work_days","start_time","end_time","visit_minutes","daily_limit","active"] if k in data}
    if not allowed: return jsonify(error="لا توجد تغييرات"),400
    set_sql=",".join(f"{k}=?" for k in allowed); db().execute(f"UPDATE Clinics SET {set_sql} WHERE id=?",[*allowed.values(),cid]); db().commit(); audit("update_clinic","Clinic",cid); return jsonify(clinic=dict(db().execute("SELECT * FROM Clinics WHERE id=?",(cid,)).fetchone()))

@app.post("/api/bookings")
def create_booking():
    try: return jsonify(booking=booking_json(make_booking(request.get_json() or {}))), 201
    except (ValueError, sqlite3.IntegrityError) as e: return jsonify(error=str(e)), 400

@app.get("/api/bookings/track")
def track():
    phone=request.args.get("phone","").strip(); no=request.args.get("booking_no","").strip()
    row=db().execute("SELECT b.*, c.name clinic_name, q.id queue_id, q.queue_no, q.state queue_state, q.current queue_current FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE b.phone=? AND b.booking_no=?",(phone,no)).fetchone()
    return jsonify(booking=booking_json(row)) if row else (jsonify(error="لم يتم العثور على الحجز"),404)

@app.get("/api/bookings")
@auth_required({"booking","doctor","nurse"})
def list_bookings():
    q=request.args.get("q","").strip(); clinic=request.args.get("clinic_id"); day=request.args.get("date")
    sql="SELECT b.*,c.name clinic_name,q.queue_no,q.state queue_state FROM Bookings b JOIN Clinics c ON c.id=b.clinic_id LEFT JOIN QueueEntries q ON q.booking_id=b.id AND q.id=(SELECT MAX(id) FROM QueueEntries WHERE booking_id=b.id) WHERE 1=1"; args=[]
    if q: sql += " AND (b.patient_name LIKE ? OR b.phone LIKE ? OR b.booking_no LIKE ? OR CAST(q.queue_no AS TEXT)=?)"; args += [f"%{q}%"]*3+[q]
    if clinic: sql += " AND b.clinic_id=?"; args.append(clinic)
    if day: sql += " AND b.visit_date=?"; args.append(day)
    sql += " ORDER BY b.visit_date,b.appointment_time,b.id DESC LIMIT 300"; return jsonify(bookings=[dict(x) for x in db().execute(sql,args)])

@app.post("/api/bookings/<int:bid>/confirm")
@auth_required({"booking"})
def confirm(bid):
    b=db().execute("SELECT * FROM Bookings WHERE id=?",(bid,)).fetchone()
    if not b or b["status"]=="Cancelled": return jsonify(error="الحجز غير صالح"),400
    db().execute("UPDATE Bookings SET status='Confirmed',updated_at=? WHERE id=?",(now(),bid)); assign_queue(bid); db().execute("INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)",(bid,"تم تأكيد حجزك وإصدار رقم الدخول",now())); db().commit(); audit("confirm_booking","Booking",bid); return jsonify(booking=booking_json(get_booking(bid)))

@app.post("/api/bookings/<int:bid>/cancel")
@auth_required({"booking"})
def cancel(bid):
    db().execute("UPDATE Bookings SET status='Cancelled',updated_at=? WHERE id=?",(now(),bid)); db().commit(); audit("cancel_booking","Booking",bid); return jsonify(ok=True)

@app.post("/api/bookings/<int:bid>/reschedule")
@auth_required({"booking"})
def reschedule(bid):
    data=request.get_json() or {}; b=db().execute("SELECT * FROM Bookings WHERE id=?",(bid,)).fetchone()
    if not b: return jsonify(error="الحجز غير موجود"),404
    if not data.get("visit_date") or not data.get("appointment_time"): return jsonify(error="التاريخ والموعد مطلوبان"),400
    db().execute("UPDATE Bookings SET visit_date=?,appointment_time=?,status='Pending',updated_at=? WHERE id=?",(data["visit_date"],data["appointment_time"],now(),bid)); db().execute("INSERT INTO Notifications(booking_id,message,created_at) VALUES(?,?,?)",(bid,"تمت إعادة جدولة الحجز ويحتاج إلى تأكيد جديد",now())); db().commit(); audit("reschedule_booking","Booking",bid); return jsonify(booking=booking_json(get_booking(bid)))

@app.post("/api/bookings/internal")
@auth_required({"booking"})
def internal_booking():
    try: return jsonify(booking=booking_json(make_booking(request.get_json() or {},"internal"))),201
    except ValueError as e: return jsonify(error=str(e)),400

@app.get("/api/queue")
@auth_required({"booking","doctor","nurse"})
def queue():
    clinic_id=request.args.get("clinic_id"); day=request.args.get("date",today())
    rows=db().execute("SELECT q.*,b.booking_no,b.patient_name,b.phone,b.appointment_time,c.name clinic_name FROM QueueEntries q JOIN Bookings b ON b.id=q.booking_id JOIN Clinics c ON c.id=q.clinic_id WHERE q.clinic_id=? AND q.queue_date=? ORDER BY q.queue_no",(clinic_id,day)).fetchall()
    return jsonify(queue=[dict(x) for x in rows])

@app.post("/api/queue/<int:qid>/action")
@auth_required({"doctor","nurse","booking"})
def queue_action(qid):
    action=(request.get_json() or {}).get("action"); allowed={"call":"Called","start":"InExam","next":"Completed","skip":"Skipped","resume":"Waiting","complete":"Completed"}
    if action not in allowed: return jsonify(error="إجراء غير معروف"),400
    q=db().execute("SELECT * FROM QueueEntries WHERE id=?",(qid,)).fetchone()
    if not q: return jsonify(error="الحالة غير موجودة"),404
    db().execute("UPDATE QueueEntries SET state=?, current=? WHERE id=?",(allowed[action],1 if action in {"call","start"} else 0,qid)); db().execute("INSERT INTO QueueEvents(queue_entry_id,event_type,actor_id,created_at) VALUES(?,?,?,?)",(qid,action,session.get("user_id"),now()));
    if action in {"next","complete"}: db().execute("UPDATE Bookings SET status='Completed',updated_at=? WHERE id=?",(now(),q["booking_id"]))
    db().commit(); audit(action,"QueueEntry",qid); return jsonify(ok=True)

@app.post("/api/bookings/<int:bid>/transfer")
@auth_required({"doctor","nurse"})
def transfer(bid):
    data=request.get_json() or {}; target=int(data.get("clinic_id",0)); b=db().execute("SELECT * FROM Bookings WHERE id=?",(bid,)).fetchone(); c=db().execute("SELECT * FROM Clinics WHERE id=? AND active=1",(target,)).fetchone()
    if not b or not c: return jsonify(error="الحجز أو العيادة غير موجود"),400
    old=b["clinic_id"]; db().execute("UPDATE Bookings SET clinic_id=?,updated_at=? WHERE id=?",(target,now(),bid)); qid=assign_queue(bid,target); db().execute("INSERT INTO Transfers(booking_id,from_clinic_id,to_clinic_id,queue_entry_id,actor_id,created_at) VALUES(?,?,?,?,?,?)",(bid,old,target,qid,session.get("user_id"),now())); db().commit(); audit("transfer","Booking",bid,f"{old}->{target}"); return jsonify(booking=booking_json(get_booking(bid)))

@app.get("/api/tv")
def tv():
    rows=db().execute("SELECT c.id,c.name,q.queue_date,MAX(CASE WHEN q.current=1 THEN q.queue_no END) current_no,MIN(CASE WHEN q.state='Waiting' THEN q.queue_no END) next_no FROM Clinics c LEFT JOIN QueueEntries q ON q.clinic_id=c.id AND q.queue_date=? WHERE c.active=1 GROUP BY c.id,c.name,q.queue_date",(request.args.get("date",today()),)).fetchall(); return jsonify(clinics=[dict(x) for x in rows])

@app.errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'): return jsonify(error="المسار غير موجود"),404
    return render_template("index.html")

if __name__ == "__main__":
    init_db(); app.run(host="0.0.0.0", port=4173, debug=False)
else:
    init_db()
