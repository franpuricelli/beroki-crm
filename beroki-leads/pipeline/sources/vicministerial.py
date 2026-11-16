import json
import subprocess
from pathlib import Path

from ..common import normalize, text
from .arcgis import residential_units


COUNCIL = "VIC Ministerial / DFP"


def value(metadata, name):
    values = metadata.get(name, [])
    if not isinstance(values, list):
        raise ValueError("Ministerial metadata must contain lists")
    return text(values[0]) if values else ""


def parse(item, since, until):
    metadata = item.get("listMetadata")
    if not isinstance(metadata, dict):
        raise ValueError("Ministerial result lacks listMetadata")
    app = value(metadata, "applicationNumber")
    if not app:
        raise ValueError("Ministerial result lacks applicationNumber")
    if value(metadata, "determinationDecision") != "Permit":
        return None
    desc = value(metadata, "applicationDescription")
    compact = value(metadata, "determinationdateOfDecisionFB")
    decided = value(metadata, "determinationdateOfDecision")
    if not decided and len(compact) == 8:
        decided = compact[:4] + "-" + compact[4:6] + "-" + compact[6:]
    principal = value(metadata, "principalApplicationNumber")
    return normalize(dict(
        council=COUNCIL, state="VIC", country="AU", application_number=app,
        address=value(metadata, "address"), description=desc, units=residential_units(desc),
        date_decided=decided, date_lodged=value(metadata, "applicationReceivedDate"),
        decision="Approved", source_url=item.get("liveUrl"),
        assessment_level="DFP" if value(metadata, "isDFP") == "1" else "Ministerial",
        related_applications=principal if principal != app else "",
        relationship_notes=value(metadata, "applicationType"),
    ), since, until)


def fetch(client, since, until, stats, logger):
    script = Path(__file__).with_name("vicministerial.mjs")
    try:
        result = subprocess.run(["node", str(script)], capture_output=True, text=True,
                                timeout=max(120, client.timeout * 5), check=True)
    except subprocess.CalledProcessError as exc:
        raise ValueError("Ministerial CDP export failed: " + exc.stderr[-1500:]) from exc
    rows = json.loads(result.stdout)
    if not isinstance(rows, list):
        raise ValueError("Ministerial CDP export must be a list")
    stats.fetched += len(rows)
    logger.info("Ministerial browser export: %d indexed records", len(rows))
    for item in rows:
        record = parse(item, since, until)
        if record:
            yield record
