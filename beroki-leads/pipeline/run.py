"""Run with python -m pipeline.run from the directory containing pipeline/."""
import argparse
import concurrent.futures
import datetime as dt
import importlib
import json
import logging
import sys
from pathlib import Path

from .common import FIELDS, Stats
from .frequency import FIELDS as FREQUENCY_FIELDS, calculate
from .http import Client
from .relationships import mark
from .sources.us_permits import reconcile_miami
from .storage import atomic_text, incremental_since, key, lock, read_rows, read_state, upsert, write_csv


DEFAULT_SOURCES = ["goldcoast", "brisbane", "ipswich", "act", "casey", "nsw",
                   "moretonbay", "sunshinecoast", "logan", "vicministerial", "miamidade", "miami", "austin"]


def collect(name, since, until, timeout):
    stats = Stats(name, since=str(since))
    logger = logging.getLogger("pipeline." + name)
    adapter = importlib.import_module(".sources." + name, __package__)
    client = Client(timeout=timeout)
    records = {}
    try:
        for record in adapter.fetch(client, since, until, stats, logger):
            records[key(record)] = record
    except Exception as exc:
        stats.error(logger, "%s source failed: %s", name, exc)
    finally:
        client.close()
    stats.kept = len(records)
    stats.approved = sum(r["decision"] == "Approved" for r in records.values())
    return stats, list(records.values())


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=dt.date.fromisoformat, help="Inclusive decision date override")
    p.add_argument("--db-dir", type=Path, default=Path(__file__).resolve().parent.parent / "db")
    p.add_argument("--sources", nargs="+", choices=DEFAULT_SOURCES + ["plansa"], default=DEFAULT_SOURCES)
    p.add_argument("--include-plansa", action="store_true", help="Opt into expensive full-history PlanSA scan")
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--timeout", type=int, default=60, help="HTTP read timeout in seconds")
    args = p.parse_args(argv)
    if args.workers < 1 or args.timeout < 1:
        p.error("workers and timeout must be positive")
    if args.since and args.since > dt.datetime.now(dt.timezone.utc).date():
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
        logs = db / "runs"
        logs.mkdir(exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        log_path = logs / (stamp + ".log")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger().addHandler(handler)
        try:
            selected = list(dict.fromkeys(args.sources + (["plansa"] if args.include_plansa else [])))
            dates = {}
            for name in selected:
                pending = state["pending"].get(name)
                # Replay a failed/partial source from its original lower bound even when others advanced.
                dates[name] = min(since, dt.date.fromisoformat(pending)) if pending else since
            logging.info("Run since=%s until=%s initial_rows=%d sources=%s", since, today, len(existing), selected)
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(collect, name, dates[name], today, args.timeout): name for name in selected}
                for future in concurrent.futures.as_completed(futures):
                    name = futures[future]
                    results[name] = future.result()
                    s, _ = results[name]
                    logging.info("SOURCE %s fetched=%d kept=%d approved=%d errors=%d since=%s",
                                 name, s.fetched, s.kept, s.approved, s.errors, s.since)
            removed = 0
            for stats, _ in results.values():
                for rejected in stats.rejected:
                    if rejected in existing:
                        del existing[rejected]
                        removed += 1
            incoming = [r for name in selected for r in results[name][1]]
            combined = {}
            for r in incoming:
                k = key(r)
                combined[k] = {**combined.get(k, {}), **{
                    f: r[f] for f in FIELDS if r.get(f, "") != ""
                }}
            incoming = [{f: r.get(f, "") for f in FIELDS} for r in combined.values()]
            incoming = {key(r): r for r in incoming}
            merged_miami = reconcile_miami(incoming, now)
            inserted, updated, unchanged = upsert(existing, incoming.values(), now)
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
                    "source", "since", "fetched", "kept", "approved", "errors"
                ]})
            state["last_run"] = now
            atomic_text(db / "state.json", json.dumps(state, indent=2) + "\n")
            summary = {"started_at": now, "since": str(since), "until": str(today), "sources": stats_output,
                       "inserted": inserted, "updated": updated, "unchanged": unchanged,
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
