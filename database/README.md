# Database

The production backend uses SQLite through `BSCH_DB_PATH`. The default local path is `bsch_clinics.sqlite3` and the sanitized demo database is `data/bsch_clinics_demo.sqlite3`.

Never commit a live patient database. Use the application backup/restore procedures and keep backups outside Git.
