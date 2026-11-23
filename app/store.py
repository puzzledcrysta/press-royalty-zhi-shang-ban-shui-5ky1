import sqlite3
from contextlib import contextmanager
from pathlib import Path
from app import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, source BLOB NOT NULL, book BLOB NOT NULL,
  result TEXT NOT NULL, created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  run_id TEXT NOT NULL REFERENCES runs(id), version INTEGER NOT NULL,
  decision TEXT NOT NULL, note TEXT NOT NULL, changed TEXT NOT NULL,
  PRIMARY KEY(run_id,version)
);
CREATE TABLE IF NOT EXISTS claim_flows (
  run_id TEXT NOT NULL REFERENCES runs(id), flow_id TEXT NOT NULL,
  amount TEXT NOT NULL, line INTEGER NOT NULL, created TEXT NOT NULL,
  PRIMARY KEY(run_id,flow_id)
);
CREATE TABLE IF NOT EXISTS claim_receipts (
  run_id TEXT NOT NULL, flow_id TEXT NOT NULL, statement_key TEXT NOT NULL,
  receipt_id TEXT NOT NULL, amount TEXT NOT NULL, line INTEGER NOT NULL, received TEXT NOT NULL,
  PRIMARY KEY(run_id,flow_id,statement_key)
);
CREATE TABLE IF NOT EXISTS claim_writeoffs (
  run_id TEXT NOT NULL, flow_id TEXT NOT NULL, statement_key TEXT NOT NULL,
  amount TEXT NOT NULL, receipt_line INTEGER NOT NULL, created TEXT NOT NULL,
  PRIMARY KEY(run_id,flow_id,statement_key)
);
"""


@contextmanager
def connection():
    path = Path(settings.DB)
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys = ON')
        db.executescript(SCHEMA)
        with db:
            yield db
    finally:
        db.close()
