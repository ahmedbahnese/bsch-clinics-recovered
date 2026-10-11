#!/usr/bin/env python3
"""Restore a backup made by backup_postgres.py. The target is wiped first."""
import gzip,json,os,sys,psycopg
url=os.environ.get('DATABASE_URL'); path=sys.argv[1] if len(sys.argv)>1 else ''
if not url or not path: raise SystemExit('DATABASE_URL and backup path are required')
data=json.load(gzip.open(path,'rt',encoding='utf-8'))
with psycopg.connect(url) as con:
    preferred=['users','systemsettings','clinics','clinicschedules','clinicserviceschedules','clinicclosures','clinicdoctors','bookings','queueentries','queueevents','transfers','notifications','auditlogs','messagetemplates','incomingmessages','outgoingmessages']
    tables=[t for t in preferred if t in data['tables']]+[t for t in data['tables'] if t not in preferred]
    for t in reversed(tables): con.execute(f'DELETE FROM "{t}"')
    for t in tables:
        x=data['tables'][t]; cols=x['columns']; marks=','.join(['%s']*len(cols)); quoted=','.join(f'"{c}"' for c in cols)
        if x['rows']: con.cursor().executemany(f'INSERT INTO "{t}" ({quoted}) VALUES ({marks})',x['rows'])
        if 'id' in cols:
            con.execute(f"SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM \"{t}\"), 1), true)",(t,))
    con.commit()
print('RESTORE_OK')
