import hashlib
import math
import re
from collections import defaultdict

from ..common import date, normalize, text
from .arcgis import join_values


def numeric(value):
    try:
        result = float(text(value).replace(",", "").replace("$", ""))
        return result if math.isfinite(result) and result >= 0 else None
    except ValueError:
        return None


def count(value):
    n = numeric(value)
    return int(n) if n is not None and n.is_integer() else None


def identifier(value):
    s = text(value)
    if not s or s.lower() in {"none", "null", "n/a"} or re.fullmatch(r"0+(?:\.0)?", s):
        return ""
    return s.removesuffix(".0")


def project_id(master=None, folio=None, address=None):
    for prefix, value in [("FOLIO", folio), ("MASTER", master)]:
        if identifier(value):
            return prefix + ":" + identifier(value)
    street = re.sub(r"\b(?:BLDG|BUILDING|UNIT|APT)\b.*", "", text(address).upper())
    street = " ".join(street.split())
    if not street:
        raise ValueError("Issued permit lacks a project grouping identifier/address")
    return "ADDRESS:" + hashlib.sha256(street.encode()).hexdigest()[:20]


def issued(value, status=""):
    return bool(date(value)) and not re.search(r"cancel|void|withdraw|denied|refus|revok", text(status), re.I)


def group(rows, since, until, force_unknown=False):
    projects = defaultdict(dict)
    for row in rows:
        if row is not None and date(row["date_decided"]) <= until.isoformat():
            projects[(row["council"], row["application_number"])][row["permit_numbers"]] = row
    for permits in projects.values():
        records = sorted(permits.values(), key=lambda r: (r["date_decided"], r["permit_numbers"]))
        latest = records[-1]
        merged = latest.copy()
        for field in ["address", "applicant", "applicant_contacts", "owner", "owner_contacts", "contractor",
                      "contractor_contacts", "architect", "planner_firm", "permit_numbers", "description"]:
            merged[field] = join_values(r.get(field) for r in records)
        dates = [date(r.get("date_lodged")) for r in records if date(r.get("date_lodged"))]
        merged["date_lodged"] = min(dates, default="")
        buildings = defaultdict(list)
        for r in records:
            buildings[" ".join(text(r.get("address")).upper().split()) or r["permit_numbers"]].append(count(r.get("units")))
        unknown = force_unknown or any(None in counts for counts in buildings.values())
        merged["units"] = "" if unknown else sum(max(counts) for counts in buildings.values())
        values = [numeric(r.get("valuation")) for r in records]
        merged["valuation"] = max((v for v in values if v is not None), default="")
        merged["relationship_notes"] = (
            "Grouped issued building permits; date_decided is latest issue, not initial planning consent. "
            "Units sum distinct building addresses, taking maximum within each address (no revision double-count); "
            "not a final approved-plan project total. Valuation is maximum permit value, not summed."
        )
        if force_unknown:
            merged["relationship_notes"] += " Multifamily new construction >= USD 1m valuation proxy; units not supplied by source."
        record = normalize(merged, since, until, infer_units=not unknown)
        if record:
            if unknown:
                record.update(units="", units_known="false")
            yield record


def reconcile_miami(rows, now):
    county = {key[1].removeprefix("FOLIO:").lstrip("0"): key for key in rows
              if key[0] == "Miami-Dade County" and key[1].startswith("FOLIO:")}
    removed = 0
    for key in list(rows):
        if key[0] != "City of Miami" or not key[1].startswith("FOLIO:"):
            continue
        parent = county.get(key[1].removeprefix("FOLIO:").lstrip("0"))
        if not parent:
            continue
        city, primary = rows[key], rows[parent]
        merged = primary.copy()
        for field in ["permit_numbers", "address", "applicant", "applicant_contacts", "owner", "owner_contacts",
                      "contractor", "contractor_contacts", "architect", "planner_firm"]:
            merged[field] = join_values(
                value for r in [primary, city] for value in text(r.get(field)).split("; "))
        merged["date_decided"] = max(primary["date_decided"], city["date_decided"])
        values = [numeric(r.get("valuation")) for r in [primary, city]]
        merged["valuation"] = text(max((v for v in values if v is not None), default=""))
        note = "City of Miami source (same normalized folio; county unit evidence takes precedence): " + city["source_url"]
        if note not in merged["relationship_notes"]:
            merged["relationship_notes"] += " " + note
        if merged != primary:
            merged["last_updated"] = now
            rows[parent] = merged
        del rows[key]
        removed += 1
    return removed
