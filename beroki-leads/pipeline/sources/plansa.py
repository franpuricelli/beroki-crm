"""Optional complete Decision Made scan; no unverified decision-date filter."""
import base64
import json
from urllib.parse import urlencode

from ..common import date, is_residential, normalize, row, text


URL = "https://cdn.plan.sa.gov.au/prs/fFGE56_reg8R"


def tables(data):
    if not isinstance(data, dict):
        return
    if "Fields" in data and "Values" in data:
        names = [f["FieldCode"] for f in data["Fields"].get("Fields", [])]
        for value in data["Values"]:
            yield dict(zip(names, value.get("FieldValues", [])))
            for child in value.get("ChildQueries", []):
                yield from tables(child.get("Value"))


def request(client, object_name, params, offset=0, limit=1000):
    payload = {"ActionType": "select", "Config": "public_register", "DataObject": object_name,
               "Params": params, "SortDirection": "", "SortExpression": "LodgedNew",
               "RecordNumber": offset, "MaxRecords": limit}
    data = client.json("POST", URL, data={"payload": base64.b64encode(json.dumps(payload).encode()).decode()})
    if data.get("Status") != "OK":
        raise ValueError("PlanSA returned non-OK status")
    return data


def fetch(client, since, until, stats, logger):
    page = 1
    seen = set()
    while True:
        data = request(client, "PublicRegisterSearch", [
            {"name": "Status", "value": "Decision Made"},
            {"name": "Page", "value": str(page)}, {"name": "PageSize", "value": "1000"},
        ], (page - 1) * 1000)
        records = list(tables({**data, "Values": [
            {**v, "ChildQueries": []} for v in data.get("Values", [])
        ]}))
        stats.fetched += len(records)
        if not records:
            break
        progress = 0
        for item in records:
            identity = (text(item.get("Base")), text(item.get("AppId")))
            if identity in seen:
                continue
            seen.add(identity)
            progress += 1
            if not is_residential("", item.get("DevDesc")):
                continue
            try:
                detail = request(client, "DAPRegisterDetail", [
                    {"name": "AppId", "value": identity[1]}, {"name": "Base", "value": identity[0]},
                ], limit=1)
                parts = list(tables(detail))
                # Only final Development Approval grants, not planning/building consents.
                finals = [p for p in parts if text(p.get("ConsentTypeShortName")).startswith("Development Approval")
                          and date(p.get("Date"))]
                if not finals:
                    # Without a verified decision date, a period-filtered decision record cannot be emitted.
                    continue
                final = max(finals, key=lambda p: date(p.get("Date")))
                council = next((text(p["Council"]) for p in parts if p.get("Council")), "South Australia")
                source_url = "https://plan.sa.gov.au/development_application_register?" + urlencode(
                    {"AppId": identity[1], "Base": identity[0]})
                normalized = normalize(row(
                    council=council, state="SA", application_number=identity[1],
                    address=item.get("Addr"), description=item.get("DevDesc"), use=item.get("DevDesc"),
                    date_lodged=item.get("Lodged"), date_decided=final.get("Date"),
                    decision=final.get("Decision") or final.get("ConsentCurrentStatusCode_RO"),
                    applicant=item.get("Applicant"), source_url=source_url,
                ), since, until)
                if normalized:
                    yield normalized
            except Exception as exc:
                stats.error(logger, "PlanSA detail %s failed: %s", identity, exc)
        logger.info("PlanSA complete-history scan page=%d fetched=%d", page, stats.fetched)
        if not progress:
            raise ValueError("PlanSA pagination made no progress")
        # Count is not reliable; last FieldValues TotalRecords and empty-page termination are usable.
        total = max((int(r.get("TotalRecords") or 0) for r in records), default=0)
        if total and page * 1000 >= total:
            break
        page += 1
