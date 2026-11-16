import datetime as dt
import hashlib
import json
import re
from zoneinfo import ZoneInfo

from ..common import date, numbers, text, unit_count


def records(client, url, where, stats, logger, oid="OBJECTID", size=1000):
    offset = 0
    seen = set()
    while True:
        data = client.json("GET", url + "/query", params={
            "f": "json", "where": where, "outFields": "*", "returnGeometry": "false",
            "orderByFields": oid + " ASC", "resultOffset": offset, "resultRecordCount": size,
        })
        if not isinstance(data, dict) or not isinstance(data.get("features"), list) or data.get("error"):
            raise ValueError("ArcGIS response lacks a valid features list")
        rows = data["features"]
        if not rows:
            if data.get("exceededTransferLimit"):
                raise ValueError("ArcGIS empty page claims more records")
            break
        signature = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
        if signature in seen:
            raise ValueError("ArcGIS pagination made no progress")
        seen.add(signature)
        stats.fetched += len(rows)
        for item in rows:
            if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
                raise ValueError("ArcGIS feature lacks attributes")
            yield item["attributes"]
        offset += len(rows)
        logger.info("%s ArcGIS offset=%d", stats.source, offset)
        if data.get("exceededTransferLimit") is False or (
                not data.get("exceededTransferLimit") and len(rows) < size):
            break


def local_date(value, zone="Australia/Brisbane"):
    if isinstance(value, (int, float)):
        try:
            return dt.datetime.fromtimestamp(value / 1000, ZoneInfo(zone)).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return ""
    return date(value)


def window(field, since, until, local=False):
    start = since - dt.timedelta(days=1) if local else since
    end = until + dt.timedelta(days=1)
    return f"{field} >= date '{start}' AND {field} < date '{end}'"


def residential_units(description):
    count = unit_count(description)
    if count is not None:
        return count
    s = re.sub(r"[‘’'\"“”]", "", numbers(description))
    noun = r"(?:dwellings?|units?|apartments?|town\s*houses?)"
    s = re.sub(r"(\d+)-(?=" + noun + r"\b)", r"\1 ", s, flags=re.I)
    s = re.sub(r"\b(\d+)\s*x\s*(?:(?:new|additional)\s+)?(" + noun + r")\b", r"\1 \2", s, flags=re.I)
    qualifiers = r"new|additional|build.to.rent|btr|affordable|social|residential|townhouse|multiple|co.living|public|housing|relocatable|independent|living"
    s = re.sub(r"\b(\d+)\s+(?:(?:" + qualifiers + r")\s+){1,5}(" + noun + r")\b", r"\1 \2", s, flags=re.I)
    s = re.sub(r"\b(" + noun + r"|multiple\s+dwelling(?:\s+units?)?)\s*(?:x\s*|\(\s*x?\s*)(\d+)\b", r"\2 dwellings", s, flags=re.I)
    revised = re.search(r"\b" + noun + r"\s+from\s+\d+\s+to\s+(\d+)\b", s, re.I)
    return int(revised.group(1)) if revised else unit_count(s)


def join_values(values):
    return "; ".join(sorted({text(v) for v in values if text(v)}))
