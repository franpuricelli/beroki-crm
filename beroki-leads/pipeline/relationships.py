import json
from pathlib import Path


def mark(rows, now=None):
    for group in json.loads(Path(__file__).with_name("relationships.json").read_text()):
        for app in group["applications"]:
            key = group["council"], app
            if key in rows:
                related = "; ".join(a for a in group["applications"] if a != app)
                changed = rows[key].get("related_applications") != related or rows[key].get("relationship_notes") != group["note"]
                rows[key]["related_applications"] = related
                rows[key]["relationship_notes"] = group["note"]
                if changed and now:
                    rows[key]["last_updated"] = now
