from urllib.parse import urlencode

from ..common import text
from .arcgis import local_date, records
from .us_permits import count, group, issued, project_id


URL = "https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer/0"


def parse(a):
    if a.get("PermitType") not in {"BLDG", "MBLD"} or a.get("ApplicationTypeDescription") != "NEW" or a.get("ProposedUseDescription") != "5 UNITS OR MORE  - RESIDENTIAL":
        return None
    if not issued(a.get("PermitIssuedDate")):
        return None
    permit = text(a.get("PermitNumber"))
    if not permit:
        raise ValueError("Issued Miami-Dade permit lacks number")
    architect = text(a.get("ArchitectName"))
    return dict(
        council="Miami-Dade County", state="FL", country="US",
        application_number=project_id(folio=a.get("FolioNumber"), master=a.get("MasterPermitNumber"), address=a.get("PropertyAddress")),
        permit_numbers=permit, address=a.get("PropertyAddress"), suburb=a.get("City"),
        description="Multifamily new construction. " + text(a.get("DetailDescriptionComments")),
        use="Apartments", units=count(a.get("StructureUnits")), storeys=a.get("StructureFloors"),
        owner=a.get("OwnerName"), architect="" if architect.upper() in {"NOT LISTED", "N/A"} else architect,
        contractor=a.get("ContractorName"), contractor_contacts=a.get("ContractorPhone"),
        valuation=a.get("EstimatedValue"), decision="Approved", date_decided=local_date(a.get("PermitIssuedDate"), "America/New_York"),
        date_lodged=local_date(a.get("ApplicationDate"), "America/New_York"),
        source_url=URL + "/query?" + urlencode({"f":"json", "where":"PermitNumber='" + permit.replace("'", "''") + "'", "outFields":"*"}),
    )


def fetch(client, since, until, stats, logger):
    where = ("PermitType IN ('BLDG','MBLD') AND ApplicationTypeDescription='NEW' "
             "AND ProposedUseDescription='5 UNITS OR MORE  - RESIDENTIAL'")
    rows = (parse(a) for a in records(client, URL, where, stats, logger, oid="ObjectId"))
    yield from group(rows, since, until)
