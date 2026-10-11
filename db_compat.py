"""Compatibility layer for the SQLite-first Flask application."""
import re
try:
    import psycopg
    from psycopg import errors as pg_errors
except ImportError:
    psycopg = None
    pg_errors = None

class CompatRow(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

class PGCursor:
    def __init__(self, conn):
        self.conn = conn
        self.raw = conn.raw.cursor()
        self._lastrowid = None
    @staticmethod
    def translate(sql):
        if sql.lstrip().upper().startswith('CREATE TABLE'):
            sql = re.sub(r'\bid\s+INTEGER\s+PRIMARY\s+KEY', 'id SERIAL PRIMARY KEY', sql, flags=re.I)
        sql = sql.replace('INSERT OR IGNORE INTO', 'INSERT INTO')
        if sql.lstrip().upper().startswith('INSERT INTO') and 'ON CONFLICT' not in sql.upper():
            sql += ' ON CONFLICT DO NOTHING'
        return re.sub(r'\?', '%s', sql)
    def execute(self, sql, params=()):
        self.raw.execute(self.translate(sql), tuple(params or ()))
        self._lastrowid = None
        if sql.lstrip().upper().startswith('INSERT') and 'RETURNING' not in sql.upper():
            try:
                self.raw.execute('SELECT lastval()')
                self._lastrowid = self.raw.fetchone()[0]
            except Exception:
                self.conn.raw.rollback()
                self.raw = self.conn.raw.cursor()
        return self
    def fetchone(self):
        row = self.raw.fetchone()
        if row is None or isinstance(row, dict): return row
        return CompatRow(zip([d.name for d in self.raw.description], row))
    def fetchall(self):
        rows = self.raw.fetchall()
        if not rows or isinstance(rows[0], dict): return rows
        keys = [d.name for d in self.raw.description]
        return [CompatRow(zip(keys, row)) for row in rows]
    def __iter__(self):
        return iter(self.fetchall())
    def executemany(self, sql, rows):
        self.raw.executemany(self.translate(sql), rows)
        return self
    @property
    def lastrowid(self): return self._lastrowid

class PGConnection:
    is_postgres = True
    def __init__(self, url):
        if psycopg is None: raise RuntimeError('psycopg is required when DATABASE_URL is configured')
        self.raw = psycopg.connect(url)
    def execute(self, sql, params=()): return PGCursor(self).execute(sql, params)
    def executescript(self, script):
        for statement in script.split(';'):
            if statement.strip(): self.execute(statement)
    def commit(self): self.raw.commit()
    def rollback(self): self.raw.rollback()
    def close(self): self.raw.close()

PGIntegrityError = pg_errors.UniqueViolation if pg_errors else Exception
