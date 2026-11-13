import datetime as dt
from collections import defaultdict

from ..common import normalize, row, text
from ..quality import act as enrich, act_index, act_documents


URL = ("https://services1.arcgis.com/E5n4f1VY84i0xSjy/ArcGIS/rest/services/"
       "ACTGOV_COMPLETED_DEVELOPMENT_APPLICATIONS/FeatureServer/0/query")


def fetch(client, since, until, stats, logger):
    where = (f"DECISION_DATE >= TIMESTAMP '{since} 00:00:00' AND "
             f"DECISION_DATE < TIMESTAMP '{until + dt.timedelta(days=1)} 00:00:00'")
    offset = 0
    applications = defaultdict(list)
    while True:
        data = client.json("GET", URL, params={
            "where": where, "outFields": "*", "returnGeometry": "false",
            "resultRecordCount": 1000, "resultOffset": offset,
            "orderByFields": "OBJECTID ASC", "f": "json",
        })
        if not isinstance(data.get("features"), list):
            raise ValueError("ACT response lacks features")
        features = data["features"]
        stats.fetched += len(features)
        for feature in features:
            a = feature["attributes"]
            applications[text(a["DA_NUMBER"])].append(a)
        offset += len(features)
        logger.info("ACT fetched %d spatial/activity records", offset)
        if not data.get("exceededTransferLimit"):
            break
        if not features:
            raise ValueError("ACT pagination made no progress")
    try:
        details = act_index(client, [a for a, rs in applications.items()
                                    if any(r.get("SUBCLASS") == "MULTI DWELLING" for r in rs)])
    except Exception as exc:
        stats.error(logger, "ACT detail join failed: %s", exc)
        details = {}
    for app, records in applications.items():
        residential = [r for r in records if r.get("SUBCLASS") == "MULTI DWELLING"]
        if not residential:
            stats.rejected.add(("ACT", app))
            continue
        record = max(residential, key=lambda r: r.get("DECISION_DATE") or 0)
        values = row(
            council="ACT", state="ACT", application_number=app,
            suburb=record.get("DIVISION"),
            description="Multi dwelling; " + "; ".join(sorted({
                f"Block {text(r.get('BLOCK'))} Section {text(r.get('SECTION'))} {text(r.get('DIVISION'))}"
                for r in records
            })),
            use="; ".join(sorted({text(r.get("SUBCLASS")) for r in records})),
            date_lodged=record.get("LODGEMENT_DATE"), date_decided=record.get("DECISION_DATE"),
            decision=record.get("DECISION"), source_url=URL + "?where=DA_NUMBER%3D" + app + "&f=json",
        )
        values = enrich(values, details.get(app, []))
        if details.get(app):
            values = act_documents(client, values, stats, logger)
        normalized = normalize(values, since, until)
        if normalized:
            yield normalized
        else:
            stats.rejected.add(("ACT", app))
