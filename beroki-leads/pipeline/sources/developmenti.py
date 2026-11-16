import datetime as dt
import re
from urllib.parse import urlencode

from ..common import is_residential, normalize, outcome, plain, row, text, unit_count
from ..quality import brisbane


def features(data):
    result = list(data.get("features", []))
    for value in data.get("multiSpot", {}).values():
        result.extend(value)
    return result


def location(description, brisbane=False):
    s = plain(description)
    if brisbane:
        s = s.split(" - ", 1)[0]
    elif " - " in s:
        s = s.rsplit(" - ", 1)[-1]
    m = re.match(r"^(.*?)\s+QLD\s+(\d{4})$", s, re.I)
    if not m:
        return {}
    address = m.group(1).strip().rstrip(",")
    suburb = address.rsplit(",", 1)[-1].strip() if "," in address else ""
    return {"address": address, "suburb": suburb, "postcode": m.group(2)}


def parties(description):
    found = {}
    tail = plain(description).split(" - ", 2)[-1]
    for m in re.finditer(r"(?:^|,\s*)([^()]+?)\s*\((Primary Applicant|Consultant)\)", tail):
        if m.group(2) == "Primary Applicant":
            found["applicant"] = "; ".join(filter(None, [found.get("applicant"), m.group(1).strip()]))
        elif re.search(r"\b(?:planning|planners?|urbis)\b", m.group(1), re.I):
            found["planner_firm"] = "; ".join(filter(None, [found.get("planner_firm"), m.group(1).strip()]))
    return found


def fetch_deployment(client, since, until, stats, logger, host, council):
    base = f"https://developmenti.{host}.qld.gov.au"
    start = int(dt.datetime.combine(since, dt.time(), dt.timezone.utc).timestamp() * 1000)
    end = int(dt.datetime.combine(until + dt.timedelta(days=1), dt.time(), dt.timezone.utc).timestamp() * 1000) - 1
    payload = {
        "Progress": "Decided", "StartDateUnixEpochNumber": start,
        "EndDateUnixEpochNumber": end, "DateRangeField": "decided",
        "IncludeDA": True, "IncludeBA": False, "IncludePlumb": False,
        "ShowCode": True, "ShowImpact": True, "ShowOther": True,
        "ShowIAGA": True, "ShowIAGI": True, "ShowNotifiableCode": True,
        "ShowReferralResponse": True, "ShowRequest": True,
        "PagingStartIndex": 0, "MaxRecords": 1000, "IncludeAroundMe": False,
        "SortField": "decided", "SortAscending": False,
        "PixelWidth": 800, "PixelHeight": 800,
    }
    seen = set()
    while True:
        data = client.json("POST", base + "/Home/ApplicationFilterCSVPaged", json=payload)
        if not isinstance(data, dict) or not isinstance(data.get("applications"), list):
            raise ValueError("Development.i response lacks applications list")
        applications = data["applications"]
        stats.fetched += len(applications)
        page_new = 0
        for item in applications:
            app = text(item.get("ramId"))
            if app in seen:
                continue
            seen.add(app)
            page_new += 1
            use = "; ".join(filter(None, [item.get("useLevel1"), item.get("useLevel2")]))
            desc = text(item.get("description"))
            if not is_mcu(item.get("applicationType"), desc, use):
                stats.rejected.add((council, app))
                continue
            if not is_residential(use, desc) or not outcome(item.get("stage")):
                stats.rejected.add((council, app))
                continue
            count = unit_count(desc)
            if count is not None and count < 10:
                stats.rejected.add((council, app))
                continue
            link = base + "/Home/FilterDirect?" + urlencode({"filters": urlencode({"DANumber": app})})
            values = row(
                council=council, state="QLD", application_number=app, description=desc,
                use=use, units=count, date_lodged=item.get("dateReceived"),
                date_decided=item.get("dateDecided"), decision=item.get("stage"),
                assessment_level=item.get("assessmentLevel"), source_url=link,
                **location(desc, host == "brisbane"), **parties(desc),
            )
            try:
                detail = client.json("GET", base + "/Geo/GetApplicationById",
                                     params={"applicationId": app, "appType": "development"})
                matches = [f for f in features(detail)
                           if text(f.get("properties", {}).get("application_number")) == app]
                if matches:
                    chosen = next((f for f in matches if "current" in text(
                        f.get("properties", {}).get("land_parcel_relationship")).lower()), matches[0])
                    props = chosen.get("properties", {})
                    coordinates = chosen.get("geometry", {}).get("coordinates", [])
                    if len(coordinates) >= 2:
                        values.update(lon=text(coordinates[0]), lat=text(coordinates[1]))
                    if props.get("decision_desc"):
                        values["decision"] = text(props["decision_desc"])
                    if host == "goldcoast" and props.get("pdonline_id"):
                        values["documents_url"] = (
                            "https://integrations.goldcoast.qld.gov.au/pdonline/ViewDocs.aspx?"
                            + urlencode({"id": props["pdonline_id"]})
                        )
            except Exception as exc:
                stats.error(logger, "%s detail %s failed: %s", stats.source, app, exc)
            if host == "brisbane":
                values = brisbane(client, values, stats, logger)
            normalized = normalize(values, since, until)
            if normalized:
                yield normalized
            else:
                stats.rejected.add((council, app))
        offset = payload["PagingStartIndex"] + len(applications)
        total = int(data["totalRecords"])
        logger.info("%s list page offset=%d total=%d", stats.source, offset, total)
        if offset >= total:
            break
        if not applications or not page_new:
            raise ValueError("Development.i pagination made no progress")
        payload["PagingStartIndex"] = offset


def is_mcu(application_type, description, use):
    return ("material change of use" in text(application_type).lower()
            and not text(description).lower().startswith("pre-construction certification")
            and ("reconfigur" not in text(description).lower()
                 or "material change of use" in text(description).lower())
            and is_residential(use, description))
