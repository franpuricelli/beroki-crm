import argparse
import json
from pathlib import Path

from .config import LEAD
from .storage import read_rows

OUTPUT_FIELDS = [
    "council", "state", "country", "application_number", "address", "suburb", "postcode",
    "description", "use", "units", "storeys", "date_decided", "decision", "applicant", "developer",
    "owner", "planner_firm", "planner_contacts", "architect", "contractor", "documents_url",
    "source_url", "related_applications", "relationship_notes",
]


def classify(row):
    if row["decision"] != LEAD["approved_decision"]:
        return "unverified_decision"
    if row["units_known"] != "true" or not row["units"].isdigit():
        return "unknown_units"
    if int(row["units"]) < LEAD["min_units"]:
        return "under_min_units"
    return "eligible"


def select(rows):
    skipped = {"unverified_decision": 0, "unknown_units": 0, "under_min_units": 0}
    eligible = []
    for row in rows:
        result = classify(row)
        if result == "eligible":
            eligible.append({f: row[f] for f in OUTPUT_FIELDS})
        else:
            skipped[result] += 1
    eligible.sort(key=lambda r: (-int(r["units"]), r["council"], r["application_number"]))
    return {"eligible": eligible, "skipped": skipped}


def main():
    p = argparse.ArgumentParser(description="List approved multifamily projects that qualify as leads")
    p.add_argument("--db-dir", type=Path, required=True)
    args = p.parse_args()
    rows = read_rows(args.db_dir.resolve() / "approvals.csv").values()
    print(json.dumps(select(rows), indent=2))


if __name__ == "__main__":
    main()
