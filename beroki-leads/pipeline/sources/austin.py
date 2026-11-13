import json

from ..common import date, text
from .arcgis import join_values
from .us_permits import count, group, issued, project_id


URL = "https://data.austintexas.gov/resource/3syk-w9eu.json"


def parse(a):
    if a.get("permittype") != "BP" or a.get("work_class") != "New" or a.get("permit_class") != "C- 105 Five or More Family Bldgs" or not issued(a.get("issue_date"), a.get("status_current")):
        return None
    permit = text(a.get("permit_number"))
    if not permit:
        raise ValueError("Issued Austin permit lacks number")
    link = a.get("link") or {}
    return dict(
        council="Austin", state="TX", country="US", application_number=project_id(master=a.get("masterpermitnum"), address=a.get("permit_location")),
        permit_numbers=permit, address=a.get("permit_location"), suburb=a.get("original_city"), postcode=a.get("original_zip"),
        description=text(a.get("description")), use="Apartments", units=count(a.get("housing_units")), storeys=a.get("number_of_floors"),
        valuation=a.get("total_job_valuation"), applicant=join_values([a.get("applicant_org"), a.get("applicant_full_name")]),
        applicant_contacts=a.get("applicant_phone"), contractor=join_values([a.get("contractor_company_name"), a.get("contractor_full_name")]),
        contractor_contacts=a.get("contractor_phone"), date_decided=date(a.get("issue_date")), date_lodged=date(a.get("applieddate")),
        decision="Approved", source_url=link.get("url", "") if isinstance(link, dict) else text(link),
    )


def fetch(client, since, until, stats, logger):
    offset = 0
    seen = set()
    parsed = []
    while True:
        data = client.json("GET", URL, params={
            "$where":"permittype='BP' AND work_class='New' AND permit_class='C- 105 Five or More Family Bldgs' AND issue_date IS NOT NULL",
            "$order":"project_id ASC", "$limit":1000, "$offset":offset,
        })
        if not isinstance(data, list) or any(not isinstance(a, dict) for a in data):
            raise ValueError("Austin SODA response must be a record list")
        signature = json.dumps(data, sort_keys=True)
        if data and signature in seen:
            raise ValueError("Austin pagination made no progress")
        seen.add(signature)
        stats.fetched += len(data)
        parsed.extend(parse(a) for a in data)
        logger.info("Austin permits offset=%d", offset)
        if len(data) < 1000:
            break
        offset += len(data)
    yield from group(parsed, since, until)
