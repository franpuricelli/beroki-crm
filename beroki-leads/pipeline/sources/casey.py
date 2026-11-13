from ..common import date, normalize, outcome, row


URL = ("https://data.casey.vic.gov.au/api/v2/catalog/datasets/"
       "planning-permit-applications-register-only/exports/json")


def fetch(client, since, until, stats, logger):
    data = client.json("GET", URL)
    if not isinstance(data, list):
        raise ValueError("Casey export is not a list")
    stats.fetched += len(data)
    for item in data:
        # A notice of intention to grant is not an issued permit.
        stage = item.get("stage_decision") or ""
        if not outcome(stage):
            stats.rejected.add(("Casey", item.get("application_number")))
            continue
        decision = stage if stage in ["Permit Issued", "Amended Permit Approved"] else item.get("decision_new")
        if "Notice Of Decision" in stage:
            decision = "Determined"
        normalized = normalize(row(
            council="Casey", state="VIC", application_number=item.get("application_number"),
            address=item.get("plnpermitaddress"), suburb=item.get("suburb"), postcode=item.get("postcode"),
            description=item.get("description"), use=item.get("description"),
            date_lodged=item.get("lodged_date"), date_decided=item.get("decision_date"),
            decision=decision, source_url=URL,
        ), since, until)
        if normalized:
            yield normalized
        else:
            # Only remove an existing record if this row belongs to the refresh window.
            if str(since) <= date(item.get("decision_date")) <= str(until):
                stats.rejected.add(("Casey", item.get("application_number")))
