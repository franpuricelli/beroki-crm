import csv
import datetime as dt
import json
import io
import os
import tempfile
from contextlib import contextmanager

from .common import FIELDS, LEGACY_FIELDS, date, months_before


def key(row):
    return row["council"], row["application_number"]


def read_rows(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames not in [FIELDS, FIELDS[:-2], LEGACY_FIELDS, LEGACY_FIELDS[:-2]]:
            raise ValueError("Unexpected approvals.csv schema; refusing to overwrite")
        rows = {}
        for row in reader:
            row = {f: row.get(f, "") for f in FIELDS}
            row["country"] = row["country"] or ("US" if row["state"] in {"FL", "TX"} else "AU")
            if key(row) in rows:
                raise ValueError("Duplicate key in existing approvals.csv: " + str(key(row)))
            rows[key(row)] = row
        return rows


def atomic_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def write_csv(path, fields, rows):
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    atomic_text(path, buf.getvalue())


def upsert(existing, incoming, now):
    inserted = updated = unchanged = 0
    for r in incoming:
        k = key(r)
        old = existing.get(k)
        if old is None:
            existing[k] = {**r, "first_seen": now, "last_updated": now}
            inserted += 1
            continue
        merged = old.copy()
        for field in FIELDS:
            if field not in ["first_seen", "last_updated"] and r.get(field, "") != "":
                merged[field] = r[field]
        if r.get("units_known") == "false":
            merged["units"] = ""
        if merged == old:
            unchanged += 1
        else:
            merged["last_updated"] = now
            existing[k] = merged
            updated += 1
    return inserted, updated, unchanged


def incremental_since(existing, today):
    dates = [date(r.get("date_decided")) for r in existing.values()]
    dates = [d for d in dates if d and d <= str(today)]
    return dt.date.fromisoformat(max(dates)) - dt.timedelta(days=14) if dates else months_before(today, 12)


@contextmanager
def lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".run.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"Pipeline already locked: {path}; inspect PID before removing a stale lock") from exc
    try:
        with os.fdopen(fd, "w") as f:
            f.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def read_state(path):
    if not path.exists():
        return {"pending": {}}
    data = json.loads(path.read_text())
    if not isinstance(data.get("pending"), dict):
        raise ValueError("Malformed incremental state file")
    return data
