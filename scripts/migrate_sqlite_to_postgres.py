#!/usr/bin/env python3
"""One-way, repeatable migration preserving IDs and verifying every table.
Run with DATABASE_URL set. It never deletes the SQLite source."""
import os, sqlite3, sys
from pathlib import Path
import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
source = Path(os.environ.get('BSCH_SQLITE_PATH', Path(__file__).resolve().parents[1] / 'bsch_clinics.sqlite3'))
url = os.environ.get('DATABASE_URL')
if not url:
    raise SystemExit('DATABASE_URL is required; SQLite source was not changed.')
if not source.exists():
    raise SystemExit(f'SQLite source not found: {source}')

# Importing app creates the PostgreSQL schema and seeds only missing defaults.
os.environ['DATABASE_URL'] = url
import app  # noqa: E402

src = sqlite3.connect(source)
src.row_factory = sqlite3.Row
with psycopg.connect(url) as dst:
    tables = [r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    # Parents first, then children; all current tables have integer IDs.
    ordered = ['Users','SystemSettings','Clinics','ClinicSchedules','ClinicServiceSchedules','ClinicClosures','ClinicDoctors','Bookings','QueueEntries','QueueEvents','Transfers','Notifications','AuditLogs','MessageTemplates','IncomingMessages','OutgoingMessages']
    tables = [t for t in ordered if t in tables] + [t for t in tables if t not in ordered]
    counts = {}
    for table in reversed(tables):
        dst.execute(f'DELETE FROM "{table.lower()}"')
    for table in tables:
        cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")')]
        rows = src.execute(f'SELECT {", ".join(chr(34)+c+chr(34) for c in cols)} FROM "{table}"').fetchall()
        if rows:
            placeholders = ','.join(['%s'] * len(cols))
            sql = f'INSERT INTO "{table.lower()}" ({", ".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({placeholders})'
            with dst.cursor() as cur:
                cur.executemany(sql, [tuple(row) for row in rows])
        if 'id' in cols:
            dst.execute(f"SELECT setval(pg_get_serial_sequence(%s, 'id'), COALESCE((SELECT MAX(id) FROM \"{table.lower()}\"), 1), true)", (table.lower(),))
        counts[table] = len(rows)
    dst.commit()
    for table, expected in counts.items():
        actual = dst.execute(f'SELECT COUNT(*) FROM "{table.lower()}"').fetchone()[0]
        if actual != expected:
            raise SystemExit(f'COUNT MISMATCH {table}: source={expected} target={actual}')

print('MIGRATION_OK')
for table, count in counts.items(): print(f'{table}: {count}')
print(f'SQLITE_SOURCE_PRESERVED={source}')
