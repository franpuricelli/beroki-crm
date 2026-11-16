import json

from ..common import normalize, row, text


URL = "https://api.apps1.nsw.gov.au/eplanning/data/v0/OnlineDA"


def fetch(client, since, until, stats, logger):
    page = 1
    seen = set()
    while True:
        data = client.json("GET", URL, headers={
            "PageSize": "1000", "PageNumber": str(page),
            "filters": json.dumps({"filters": {"DeterminationDateFrom": str(since),
                                                "DeterminationDateTo": str(until)}}),
        })
        if not isinstance(data.get("Application"), list):
            raise ValueError("NSW response lacks Application list")
        applications = data["Application"]
        stats.fetched += len(applications)
        progress = 0
        for item in applications:
            app = text(item.get("PlanningPortalApplicationNumber"))
            if app in seen:
                continue
            seen.add(app)
            progress += 1
            if item.get("ApplicationType") != "Development Application":
                continue
            types = "; ".join(t.get("DevelopmentType", "") for t in item.get("DevelopmentType", []))
            sites = item.get("Location") or [{}]
            site = sites[0]
            # NSW X/Y in the public feed are longitude/latitude, not the reverse.
            normalized = normalize(row(
                council=item.get("Council", {}).get("CouncilName"), state="NSW",
                application_number=app, address="; ".join(text(s.get("FullAddress")) for s in sites),
                suburb=site.get("Suburb"), postcode=site.get("Postcode"),
                lon=site.get("X"), lat=site.get("Y"), description=item.get("DevelopmentDescription") or types,
                use=types, units=item.get("NumberOfNewDwellings"), storeys=item.get("NumberOfStoreys"),
                assessment_level=item.get("AssessmentType"), date_lodged=item.get("LodgementDate") or item.get("SubmissionDate"),
                date_decided=item.get("DeterminationDate"),
                decision=item.get("DeterminationOutcome") or item.get("ApplicationStatus"),
                applicant=item.get("ApplicantName"), source_url=URL,
            ), since, until)
            if normalized:
                yield normalized
            else:
                stats.rejected.add((text(item.get("Council", {}).get("CouncilName")), app))
        total_pages = int(data.get("TotalPages", 0))
        logger.info("NSW page=%d/%d fetched=%d", page, total_pages, stats.fetched)
        if page >= total_pages:
            break
        if not applications or not progress:
            raise ValueError("NSW pagination made no progress")
        page += 1
