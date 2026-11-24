import argparse
import json
from pathlib import Path

from .config import LEAD, OPEN_STAGES
from .run import recheck_file
from .storage import read_rows

OUTPUT_FIELDS = [
    "council", "state", "country", "application_number", "address", "suburb", "postcode",
    "description", "use", "units", "storeys", "date_lodged", "date_decided", "decision", "etapa", "etapa_desde",
    "historial_etapas", "applicant", "developer", "owner", "planner_firm", "planner_contacts", "architect",
    "contractor", "documents_url", "plans_url", "source_url", "related_applications", "relationship_notes",
]


def units_result(row):
    if row["units_known"] != "true" or not row["units"].isdigit():
        return "unknown_units"
    if int(row["units"]) < LEAD["min_units"]:
        return "under_min_units"
    return "eligible"


def classify(row):
    if row["decision"] != LEAD["approved_decision"]:
        return "unverified_decision"
    return units_result(row)


def classify_lodged(row):
    result = units_result(row)
    if result == "eligible" and not row["plans_url"]:
        return "no_plans"
    return result


def ordered(rows):
    return sorted(rows, key=lambda r: (-int(r["units"]), r["council"], r["application_number"]))


def select(rows):
    skipped = {"unverified_decision": 0, "unknown_units": 0, "under_min_units": 0}
    eligible = []
    for row in rows:
        if row["etapa"] in OPEN_STAGES:
            continue
        result = classify(row)
        if result == "eligible":
            eligible.append({f: row[f] for f in OUTPUT_FIELDS})
        else:
            skipped[result] += 1
    return {"eligible": ordered(eligible), "skipped": skipped}


def select_lodged(rows):
    skipped = {"unknown_units": 0, "under_min_units": 0, "no_plans": 0}
    eligible = []
    for row in rows:
        if row["etapa"] not in OPEN_STAGES:
            continue
        result = classify_lodged(row)
        if result == "eligible":
            eligible.append({**{f: row[f] for f in OUTPUT_FIELDS},
                             "priority": int(row["units"]) >= LEAD["priority_units"]})
        else:
            skipped[result] += 1
    return {"eligible": ordered(eligible), "skipped": skipped}


def select_tracked(rows, keys):
    found = []
    for council, number in keys:
        row = rows.get((council, number))
        found.append({f: row[f] for f in OUTPUT_FIELDS} if row else
                     {"council": council, "application_number": number, "etapa": "", "missing": True})
    return found


def main():
    p = argparse.ArgumentParser(description="List the projects that qualify as leads, approved and lodged")
    p.add_argument("--db-dir", type=Path, required=True)
    p.add_argument("--recheck", type=Path, help="JSON list of {council, application_number} to report")
    args = p.parse_args()
    rows = read_rows(args.db_dir.resolve() / "approvals.csv")
    result = select(rows.values())
    result["lodged"] = select_lodged(rows.values())
    result["tracked"] = select_tracked(rows, recheck_file(args.recheck))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
