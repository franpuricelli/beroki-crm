"""Run with python -m pipeline.run from the directory containing pipeline/."""
import argparse
import concurrent.futures
import datetime as dt
import importlib
import json
import logging
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from .common import FIELDS, Stats
from .config import OPEN_STAGES, RECORD_HOSTS
from .frequency import FIELDS as FREQUENCY_FIELDS, calculate
from .http import Client
from .relationships import mark
from .sources.us_permits import reconcile_miami
from .storage import (atomic_text, incremental_lodged_since, incremental_since, key, lock, merge_records,
                      open_keys, read_rows, read_state, removable, upsert, write_csv)


DEFAULT_SOURCES = ["goldcoast", "brisbane", "ipswich", "act", "casey", "nsw",
                   "moretonbay", "sunshinecoast", "logan", "vicministerial", "miamidade", "miami", "austin"]


def adapter_for(name):
    return importlib.import_module(".sources." + name, __package__)


def collect(name, since, until, timeout, lodged_since=None, recheck=()):
    stats = Stats(name, since=str(since))
    logger = logging.getLogger("pipeline." + name)
    adapter = adapter_for(name)
    client = Client(timeout=timeout)
    records = {}
    steps = [("approved", lambda: adapter.fetch(client, since, until, stats, logger))]
    if lodged_since and hasattr(adapter, "fetch_lodged"):
        steps.append(("lodged", lambda: adapter.fetch_lodged(client, lodged_since, until, stats, logger)))
    if recheck and hasattr(adapter, "recheck"):
        steps.append(("recheck", lambda: adapter.recheck(client, recheck, stats, logger)))
    try:
        for step, run in steps:
            try:
                for record in run():
                    records[key(record)] = merge_records(records.get(key(record)), record)
                    if step == "lodged":
                        stats.lodged += 1
                    elif step == "recheck":
                        stats.rechecked += 1
            except Exception as exc:
                stats.error(logger, "%s %s step failed: %s", name, step, exc)
    finally:
        client.close()
    stats.kept = len(records)
    stats.approved = sum(r["decision"] == "Approved" for r in records.values())
    return stats, list(records.values())


def recheck_file(path):
    if not path:
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("Recheck file must be a JSON list")
    keys = []
    for item in data:
        if not isinstance(item, dict) or not item.get("application_number"):
            raise ValueError("Each recheck item needs application_number")
        council = item.get("council") or RECORD_HOSTS.get(urlparse(str(item.get("da_record") or "")).hostname or "")
        if not council:
            raise ValueError("Recheck item needs council or a known da_record: " + str(item["application_number"]))
        keys.append((str(council), str(item["application_number"])))
    return keys


def routes(selected, keys):
    by_source = {name: [] for name in selected}
    unsupported = []
    for council, number in keys:
        names = [n for n in selected if hasattr(adapter_for(n), "recheck")
                 and council in getattr(adapter_for(n), "COUNCILS", ())]
        if names:
            by_source[names[0]].append(number)
        else:
            unsupported.append({"council": council, "application_number": number})
    return by_source, unsupported


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=dt.date.fromisoformat, help="Inclusive decision date override")
    p.add_argument("--lodged-since", type=dt.date.fromisoformat, help="Inclusive lodgement date override")
    p.add_argument("--no-lodged", action="store_true", help="Skip lodged applications")
    p.add_argument("--recheck", type=Path, help="JSON list of {council, application_number} to re-query")
    p.add_argument("--db-dir", type=Path, default=Path(__file__).resolve().parent.parent / "db")
    p.add_argument("--sources", nargs="+", choices=DEFAULT_SOURCES + ["plansa"], default=DEFAULT_SOURCES)
    p.add_argument("--include-plansa", action="store_true", help="Opt into expensive full-history PlanSA scan")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--timeout", type=int, default=60, help="HTTP read timeout in seconds")
    args = p.parse_args(argv)
    if args.workers < 1 or args.timeout < 1:
        p.error("workers and timeout must be positive")
    today = dt.datetime.now(dt.timezone.utc).date()
    if (args.since and args.since > today) or (args.lodged_since and args.lodged_since > today):
        p.error("since cannot be in the future")
    return args


def execute(args):
    today = dt.datetime.now(dt.timezone.utc).date()
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    db = args.db_dir.resolve()
    with lock(db):
        existing = read_rows(db / "approvals.csv")
        state = read_state(db / "state.json")
        since = args.since or incremental_since(existing, today)
        lodged_since = None if args.no_lodged else (args.lodged_since or incremental_lodged_since(existing, today))
        logs = db / "runs"
        logs.mkdir(exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log_path = logs / (stamp + ".log")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(handler)
        try:
            selected = list(dict.fromkeys(args.sources + (["plansa"] if args.include_plansa else [])))
            requested = list(dict.fromkeys(open_keys(existing) + recheck_file(args.recheck)))
            by_source, unsupported = routes(selected, requested)
            dates = {}
            for name in selected:
                pending = state["pending"].get(name)
                dates[name] = min(since, dt.date.fromisoformat(pending)) if pending else since
            logging.info("Run since=%s lodged_since=%s until=%s initial_rows=%d recheck=%d sources=%s",
                         since, lodged_since, today, len(existing), len(requested), selected)
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(collect, name, dates[name], today, args.timeout,
                                       lodged_since, by_source[name]): name for name in selected}
                for future in concurrent.futures.as_completed(futures):
                    name = futures[future]
                    results[name] = future.result()
                    s, _ = results[name]
                    logging.info("SOURCE %s fetched=%d kept=%d approved=%d lodged=%d rechecked=%d errors=%d since=%s",
                                 name, s.fetched, s.kept, s.approved, s.lodged, s.rechecked, s.errors, s.since)
            removed = 0
            for stats, _ in results.values():
                for rejected in stats.rejected:
                    if rejected in existing and removable(existing[rejected]):
                        del existing[rejected]
                        removed += 1
            combined = {}
            for name in selected:
                for r in results[name][1]:
                    combined[key(r)] = merge_records(combined.get(key(r)), r)
            incoming = {k: {f: r.get(f, "") for f in FIELDS} for k, r in combined.items()}
            before = set(existing)
            merged_miami = reconcile_miami(incoming, now)
            inserted, updated, unchanged, changes = upsert(existing, incoming.values(), now)
            merged_miami = max(merged_miami, reconcile_miami(existing, now))
            mark(existing, now)
            rows = sorted(existing.values(), key=key)
            write_csv(db / "approvals.csv", FIELDS, rows)
            write_csv(db / "frequency.csv", FREQUENCY_FIELDS, calculate(rows, today))
            stats_output = []
            for name in selected:
                stats, _ = results[name]
                if stats.errors:
                    state["pending"][name] = str(dates[name])
                else:
                    state["pending"].pop(name, None)
                stats_output.append({f: getattr(stats, f) for f in [
                    "source", "since", "fetched", "kept", "approved", "lodged", "rechecked", "errors"
                ]})
            state["last_run"] = now
            atomic_text(db / "state.json", json.dumps(state, indent=2) + "\n")
            new_lodged = Counter(k[0] for k in set(existing) - before if existing[k]["etapa"] in OPEN_STAGES)
            missing = [{"council": c, "application_number": n} for c, n in requested
                       if (c, n) not in combined and {"council": c, "application_number": n} not in unsupported]
            summary = {"started_at": now, "since": str(since), "lodged_since": str(lodged_since or ""),
                       "until": str(today), "sources": stats_output,
                       "inserted": inserted, "updated": updated, "unchanged": unchanged,
                       "new_lodged_by_council": dict(sorted(new_lodged.items())),
                       "stage_changes": changes, "recheck_requested": len(requested),
                       "recheck_missing": missing, "recheck_unsupported": unsupported,
                       "removed_no_longer_eligible": removed, "merged_miami_overlap": merged_miami,
                       "rows": len(rows), "duplicate_keys": 0,
                       "plansa_default_exclusion": "Opt-in only: no verified decision-date search; requires complete historical scan"}
            atomic_text(logs / (stamp + ".json"), json.dumps(summary, indent=2) + "\n")
            atomic_text(db / "last_run.json", json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary, indent=2), flush=True)
            return 1 if any(s["errors"] for s in stats_output) else 0
        finally:
            logging.getLogger().removeHandler(handler)
            handler.close()


def main(argv=None):
    args = arguments(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    try:
        return execute(args)
    except Exception:
        logging.exception("Pipeline could not commit run")
        return 2


if __name__ == "__main__":
    sys.exit(main())
