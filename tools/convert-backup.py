"""Read an existing ELINK SQLite backup without changing it; export Web JSON."""
import argparse
import base64
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


def convert(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if not source.is_file() or target.exists():
        raise ValueError("Input must exist; output must be a new file")
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"devices", "templates", "jobs", "plans", "reminders"} <= tables:
            raise ValueError("Not an ELINK manager backup")
        value = {"format": "elink-web", "schema": 1}
        for name in ("devices", "templates", "jobs", "plans", "reminders"):
            value[name] = [dict(r) for r in db.execute("SELECT * FROM " + name)]
    defaults = {"mode": 1, "full_every": 60, "refresh_minutes": 5,
                "advertise_minutes": 1, "window_seconds": 0, "clock_timezone": "local"}
    for d in value["devices"]:
        d["settings"] = {**defaults, **json.loads(d["settings"]), "window_seconds": 0}
        d["state"] = {}
    for t in value["templates"]:
        frame = t["frame"]
        if len(frame) != 8000 or hashlib.sha256(frame).hexdigest() != t["sha256"]:
            raise ValueError("Invalid native template payload")
        for name in ("frame", "png"):
            t[name] = base64.b64encode(t[name]).decode("ascii")
    for j in value["jobs"]:
        j["payload"], j["receipt"] = json.loads(j["payload"]), json.loads(j["receipt"])
    for r in value["reminders"]:
        r["due"] = int(r["due"])
        r.setdefault("options", "{}")
        r["previous_token"] = r.get("previous_token") or 0
    for p in value["plans"]:
        p["enabled"] = False
    with target.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False)
    return len(value["templates"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="ELINK SQLite backup")
    parser.add_argument("target", help="New JSON output file")
    args = parser.parse_args()
    print("Exported", convert(args.source, args.target), "templates; input unchanged")
