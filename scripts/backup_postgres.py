#!/usr/bin/env python3
"""Create a compressed JSON backup from the central PostgreSQL database."""
import gzip, json, os, sys
from datetime import date, datetime
import psycopg
url=os.environ.get('DATABASE_URL')
if not url: raise SystemExit('DATABASE_URL is required')
out=sys.argv[1] if len(sys.argv)>1 else f'bsch-backup-{datetime.utcnow():%Y%m%d-%H%M%S}.json.gz'
with psycopg.connect(url) as con, gzip.open(out,'wt',encoding='utf-8') as fp:
    tables=[r[0] for r in con.execute("select tablename from pg_tables where schemaname='public' order by tablename")]
    payload={'format':'bsch-postgres-json-v1','created_at':datetime.utcnow().isoformat()+'Z','tables':{}}
    for table in tables:
        rows=con.execute(f' select * from "{table}"').fetchall(); cols=[d.name for d in con.execute(f' select * from "{table}" limit 0').description]
        def enc(v): return v.isoformat() if isinstance(v,(date,datetime)) else v
        payload['tables'][table]={'columns':cols,'rows':[[enc(v) for v in row] for row in rows]}
    json.dump(payload,fp,ensure_ascii=False)
print(out)
