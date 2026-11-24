import csv
import datetime as dt
import json
import io
import os
import tempfile
from contextlib import contextmanager

from .common import FIELDS, LEGACY_FIELDS, PREVIOUS_FIELDS, date, decided_stage, months_before
from .config import CLOSED_STAGES, FINAL_STAGES, LEAD, OPEN_STAGES, STAGE

SCHEMAS = [FIELDS, PREVIOUS_FIELDS, PREVIOUS_FIELDS[:-2], LEGACY_FIELDS, LEGACY_FIELDS[:-2]]


def key(row):
    return row["council"], row["application_number"]


def read_rows(path):
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames not in SCHEMAS:
            raise ValueError("Unexpected approvals.csv schema; refusing to overwrite")
        rows = {}
        for row in reader:
            row = {f: row.get(f, "") for f in FIELDS}
            row["country"] = row["country"] or ("US" if row["state"] in {"FL", "TX"} else "AU")
            if not row["etapa"]:
                row["etapa"] = decided_stage(row["decision"], row["country"])
                day = date(row["date_decided"]) or date(row["first_seen"])
                row["etapa_desde"] = day if row["etapa"] else ""
                row["historial_etapas"] = row["etapa"] + ":" + day if row["etapa"] else ""
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


STAGE_FIELDS = ["etapa", "etapa_desde", "historial_etapas"]


def stage_rank(stage):
    if stage in FINAL_STAGES:
        return 2
    if stage in OPEN_STAGES:
        return 1
    return 0


def merge_records(old, new):
    if not old:
        return dict(new)
    if stage_rank(old.get("etapa")) > stage_rank(new.get("etapa")):
        keep = {f: old[f] for f in ["etapa", "decision", "date_decided"] if f in old}
        return {**old, **{f: v for f, v in new.items() if v != ""}, **keep}
    return {**old, **{f: v for f, v in new.items() if v != ""}}


def stage_date(row, now):
    if row.get("etapa") in FINAL_STAGES and date(row.get("date_decided")):
        return date(row["date_decided"])
    if row.get("etapa") == STAGE["lodged"] and date(row.get("date_lodged")):
        return date(row["date_lodged"])
    return now[:10]


def upsert(existing, incoming, now):
    inserted = updated = unchanged = 0
    changes = []
    for r in incoming:
        k = key(r)
        old = existing.get(k)
        if old is None:
            day = stage_date(r, now)
            existing[k] = {**r, "first_seen": now, "last_updated": now, "etapa_desde": day if r["etapa"] else "",
                           "historial_etapas": r["etapa"] + ":" + day if r["etapa"] else ""}
            inserted += 1
            continue
        if old["etapa"] in FINAL_STAGES and r.get("etapa") in OPEN_STAGES:
            changes.append({"council": k[0], "application_number": k[1], "from": old["etapa"],
                            "to": r["etapa"], "date": now[:10], "ignored": "final stage kept"})
            unchanged += 1
            continue
        merged = old.copy()
        for field in FIELDS:
            if field not in ["first_seen", "last_updated", *STAGE_FIELDS] and r.get(field, "") != "":
                merged[field] = r[field]
        if r.get("units_known") == "false":
            merged["units"] = ""
        if r.get("etapa") in OPEN_STAGES:
            merged.update(decision="", date_decided="")
        if r.get("etapa") and r["etapa"] != old["etapa"]:
            day = stage_date(r, now)
            merged["etapa"] = r["etapa"]
            merged["etapa_desde"] = day
            merged["historial_etapas"] = ";".join(filter(None, [old["historial_etapas"], r["etapa"] + ":" + day]))
            changes.append({"council": k[0], "application_number": k[1], "from": old["etapa"],
                            "to": r["etapa"], "date": day})
        if merged == old:
            unchanged += 1
        else:
            merged["last_updated"] = now
            existing[k] = merged
            updated += 1
    return inserted, updated, unchanged, changes


def open_keys(rows):
    return sorted(k for k, r in rows.items() if r["etapa"] in OPEN_STAGES)


def from_lodgement(row):
    return row["historial_etapas"].split(":", 1)[0] in OPEN_STAGES


def removable(row):
    return row["etapa"] not in OPEN_STAGES + CLOSED_STAGES and not from_lodgement(row)


def incremental_since(existing, today):
    dates = [date(r.get("date_decided")) for r in existing.values() if r["etapa"] not in OPEN_STAGES]
    dates = [d for d in dates if d and d <= str(today)]
    lookback = dt.timedelta(days=LEAD["lookback_days"])
    return dt.date.fromisoformat(max(dates)) - lookback if dates else months_before(today, 12)


def incremental_lodged_since(existing, today):
    dates = [date(r.get("date_lodged")) for r in existing.values() if from_lodgement(r)]
    dates = [d for d in dates if d and d <= str(today)]
    lookback = dt.timedelta(days=LEAD["lookback_days"])
    return dt.date.fromisoformat(max(dates)) - lookback if dates else today - lookback


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
