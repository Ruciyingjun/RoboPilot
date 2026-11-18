"""Durable workflow checkpoints and a single-writer lease for one robot run."""
import fcntl
import json
from pathlib import Path
import sqlite3

from .storage import _atomic_write


class CheckpointStore:
    def __init__(self, directory):
        self.root = Path(directory)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lease = (self.root/'runtime.lock').open('a+')
        try:
            fcntl.flock(self.lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise RuntimeError('Another workflow owns this run directory') from None
        self.db = sqlite3.connect(self.root/'runtime.sqlite3')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS checkpoints (
            revision INTEGER PRIMARY KEY, event TEXT NOT NULL, context_json TEXT NOT NULL)''')

    def load(self):
        row = self.db.execute('SELECT context_json FROM checkpoints ORDER BY revision DESC LIMIT 1').fetchone()
        return json.loads(row[0]) if row else None

    def save(self, context, event):
        encoded = json.dumps(context, ensure_ascii=False, allow_nan=False, indent=2)
        with self.db:
            self.db.execute('INSERT INTO checkpoints(event,context_json) VALUES (?,?)', (event, encoded))
        # SQLite is authoritative; this file is an inspectable, replaceable projection.
        _atomic_write(self.root/'context.json', encoded+'\n')

    def close(self):
        self.db.close()
        self.lease.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
