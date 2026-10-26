"""Independent SQLite writer: hold an uncommitted insert until killed/released."""

import json
import sqlite3
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    database, ready, release, mode = sys.argv[1:]
    with sqlite3.connect(database, isolation_level=None) as db:
        db.execute("BEGIN EXCLUSIVE" if mode == "exclusive" else "BEGIN IMMEDIATE")
        if mode == "insert":
            db.execute("INSERT INTO reservations VALUES ('uncommitted',123456)")
        Path(ready).write_text(json.dumps({"transaction": mode}), encoding="utf-8")
        deadline = time.monotonic() + 45
        while not Path(release).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        db.execute("ROLLBACK")
