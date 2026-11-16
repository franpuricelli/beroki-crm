import re

from ..common import normalize, text
from .arcgis import join_values, local_date, records, residential_units, window


SOURCES = {
    "sunshinecoast": {
        "council": "Sunshine Coast", "url": "https://geopublic.scc.qld.gov.au/arcgis/rest/services/PlanningCadastre/Applications_SCRC/MapServer/1",
        "date": "d_decision_made", "app": "ram_id", "oid": "ram_process_ctr",
    },
    "logan": {
        "council": "Logan", "url": "https://services5.arcgis.com/ZUCWDRj8F77Xo351/arcgis/rest/services/Logan_City_Decided_Development_Applications/FeatureServer/0",
        "date": "Application_LatestDecision_Date", "app": "Application_Number", "oid": "OBJECTID",
    },
    "moretonbay": {
        "council": "Moreton Bay", "url": "https://services-ap1.arcgis.com/152ojN3Ts9H3cdtl/ArcGIS/rest/services/MyStreet/FeatureServer/0",
        "date": "DECISION_DATE", "app": "FORMATTED_APPLICATION_NUMBER", "oid": "OBJECTID",
    },
}


def application(source, attributes):
    number = text(attributes.get(SOURCES[source]["app"]))
    amendment = text(attributes.get("Application_Amendment")) if source == "logan" else ""
    if amendment and not number.endswith("/" + amendment):
        number += "/" + amendment
    return number


def parse(source, a, since, until):
    cfg = SOURCES[source]
    app = application(source, a)
    if not app:
        raise ValueError("Council record lacks application number")
    values = dict(council=cfg["council"], state="QLD", country="AU", application_number=app,
                  date_decided=local_date(a.get(cfg["date"])), decision="Approved")
    if source == "sunshinecoast":
        if a.get("ram_primary_group") not in {"MCU", "QMCU"} or a.get("decision") not in {"DevPermit", "Approved", "#APPROVED"}:
            return None
        desc = text(a.get("description"))
        values.update(description=desc, use="", address=desc.split(" - ", 1)[0],
                      date_lodged=local_date(a.get("d_date_rec")), assessment_level=a.get("assessment_level"),
                      source_url="https://developmenti.sunshinecoast.qld.gov.au/Home/FilterDirect?filters=DANumber%3D" + app)
    elif source == "logan":
        if a.get("Application_Decision_Type") not in {"Application Approved", "Negotiated Decision Approved"}:
            return None
        kind = text(a.get("Application_Development_Type_Co"))
        if not kind.startswith("MCU") and a.get("Application_Development_Type_De") != "Combined Application":
            return None
        desc = text(a.get("Application_Description"))
        values.update(description=desc, date_lodged=local_date(a.get("Application_Lodgement_Date")),
                      address=a.get("Application_Property_Address"), suburb=a.get("Application_Property_Suburb"),
                      applicant=a.get("Application_Applicant"), assessment_level=a.get("Application_Assessment_Category"),
                      lat=a.get("Latitude"), lon=a.get("Longitude"), source_url=a.get("PDonline_Link"))
    else:
        desc = text(a.get("DESCRIPTION"))
        if a.get("DECISION_TYPE_DESCRIPTION") != "Approved" or "material change of use" not in desc.lower():
            return None
        if re.search(r"superseded planning scheme|preliminary approval", desc, re.I):
            return None
        values.update(description=desc, date_lodged=local_date(a.get("LODGED_DATE")),
                      source_url=a.get("DA_TRACKER_URL"))
    values["units"] = residential_units(desc)
    if values["units"] is None and not re.search(r"multiple\s+dwell|multi[- ]?unit|apartments?|town\s*houses?|build.to.rent|\bbtr\b", desc, re.I):
        return None
    if re.search(r"resort apartments?|serviced apartments?|apartment hotel", desc, re.I) and not re.search(r"multiple\s+dwell|permanent", desc, re.I):
        return None
    return normalize(values, since, until)


def fetch_source(source, client, since, until, stats, logger):
    cfg = SOURCES[source]
    where = window(cfg["date"], since, until, local=True)
    if source == "sunshinecoast":
        where += " AND ram_primary_group IN ('MCU','QMCU')"
    kept = {}
    for a in records(client, cfg["url"], where, stats, logger, oid=cfg["oid"]):
        record = parse(source, a, since, until)
        key = (cfg["council"], application(source, a))
        if record:
            if key in kept:
                record["address"] = join_values([kept[key]["address"], record["address"]])
            kept[key] = record
        elif since.isoformat() <= local_date(a.get(cfg["date"])) <= until.isoformat():
            stats.rejected.add(key)
    stats.rejected.difference_update(kept)
    yield from kept.values()
