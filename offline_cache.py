"""Bounded local page cache: content-addressed, versioned, atomic SQLite writes."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time

from document_ingest import ENGINE_VERSION, ocr_capabilities


def cache_key(sha):
    config = ocr_capabilities()
    return hashlib.sha256(json.dumps([ENGINE_VERSION, sha, config], sort_keys=True).encode()).hexdigest()


def _connect():
    # Serverless must never share a persistent document store between visitors.
    setting = os.environ.get('SYLEX_CACHE_DIR', '')
    if os.environ.get('VERCEL') or setting.lower() == 'off':
        return None
    folder = Path(setting) if setting else Path(__file__).resolve().parent / '.sylex-cache'
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(folder / 'pages.sqlite3'), timeout=2)
    db.execute('PRAGMA auto_vacuum = FULL')
    db.execute('PRAGMA max_page_count = 32768')  # ~128 MB with default 4 KB pages
    db.execute('CREATE TABLE IF NOT EXISTS pages (key TEXT PRIMARY KEY, payload TEXT NOT NULL, accessed REAL NOT NULL)')
    return db


def get(key):
    db = None
    try:
        db = _connect()
        if db is None:
            return None
        with db:
            row = db.execute('SELECT payload FROM pages WHERE key=? AND accessed>?', (key, time.time()-30*86400)).fetchone()
            if row:
                db.execute('UPDATE pages SET accessed=? WHERE key=?', (time.time(), key))
                return json.loads(row[0])
    except (OSError, sqlite3.Error, ValueError):
        return None  # Storage failure never prevents fresh extraction.
    finally:
        if db is not None:
            db.close()


def put(key, value):
    db = None
    try:
        payload = json.dumps(value, ensure_ascii=False)
        if len(payload.encode()) > 16 * 1024 * 1024:
            return
        db = _connect()
        if db is None:
            return
        with db:
            db.execute('DELETE FROM pages WHERE accessed<?', (time.time()-30*86400,))
            db.execute('INSERT OR REPLACE INTO pages VALUES (?, ?, ?)', (key, payload, time.time()))
            db.execute('DELETE FROM pages WHERE key NOT IN (SELECT key FROM pages ORDER BY accessed DESC LIMIT 32)')
            while db.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM pages').fetchone()[0] > 96*1024*1024:
                db.execute('DELETE FROM pages WHERE key=(SELECT key FROM pages ORDER BY accessed LIMIT 1)')
    except (OSError, sqlite3.Error, ValueError):
        pass
    finally:
        if db is not None:
            db.close()


def clear():
    db = _connect()
    if db is not None:
        try:
            with db:
                db.execute('DELETE FROM pages')
        finally:
            db.close()
