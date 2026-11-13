import re
from urllib.parse import urlencode

from ..common import text
from .arcgis import local_date, records
from .us_permits import group, issued, numeric, project_id


URL = "https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/Building_Permits_Since_2014/FeatureServer/0"


def parse(a):
    if a.get("ScopeofWork") != "NEW CONSTRUCTION" or not re.search(r"MULTI[- ]FAMILY|APARTMENT", text(a.get("WorkItems")), re.I):
        return None
    permit = text(a.get("PermitNumber"))
    valuation = numeric(a.get("TotalCost"))
    if not permit.endswith("B001") or valuation is None or valuation < 1_000_000 or not issued(a.get("IssuedDate"), a.get("BuildingPermitStatusDescription")):
        return None
    return dict(
        council="City of Miami", state="FL", country="US", application_number=project_id(folio=a.get("FolioNumber"), address=a.get("DeliveryAddress")),
        permit_numbers=permit, address=a.get("DeliveryAddress"), description=text(a.get("WorkItems")) + " - New construction",
        use="Apartments", units="", valuation=valuation, contractor=a.get("CompanyName"),
        lat=a.get("Latitude"), lon=a.get("Longitude"), decision="Approved",
        date_decided=local_date(a.get("IssuedDate"), "America/New_York"), date_lodged=local_date(a.get("PlanAcceptedDate"), "America/New_York"),
        source_url=URL + "/query?" + urlencode({"f":"json", "where":"PermitNumber='" + permit.replace("'", "''") + "'", "outFields":"*"}),
    )


def fetch(client, since, until, stats, logger):
    where = "ScopeofWork='NEW CONSTRUCTION' AND (WorkItems LIKE '%MULTI%' OR WorkItems LIKE '%APART%' OR WorkItems LIKE '%CONDOMINIUM%')"
    rows = (parse(a) for a in records(client, URL, where, stats, logger, oid="ObjectId"))
    yield from group(rows, since, until, force_unknown=True)
