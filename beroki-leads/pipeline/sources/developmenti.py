import datetime as dt
import re
from urllib.parse import urlencode

from ..common import closing_stage, is_residential, normalize, normalize_stage, outcome, plain, row, text, unit_count
from ..config import STAGE
from ..documents import (brisbane_documents, brisbane_form, first_plan, goldcoast_documents,
                         sunshinecoast_documents)
from ..quality import brisbane, download


HOSTS = {
    "brisbane": {"council": "Brisbane", "lodged_field": "submitted", "type": "Material Change of Use"},
    "goldcoast": {"council": "Gold Coast", "lodged_field": "lodged", "type": ""},
    "sunshinecoast": {"council": "Sunshine Coast", "lodged_field": "submitted", "type": "Material Change Of Use"},
    "ipswich": {"council": "Ipswich", "lodged_field": "", "type": ""},
}
APPROVED_LABELS = {"development permit", "preliminary approval", "devel.perm", "deemed approval"}
MCU_CARRIERS = re.compile(r"combined application|priority development area|superseded planning scheme", re.I)
EXCLUDED_STAGES = re.compile(r"^change to", re.I)
CHANGE_APPLICATION = re.compile(
    r"minor change|other change|change to (?:an |the )?(?:existing )?(?:development )?approval|"
    r"generally in accordance|extension (?:to|of) (?:the )?(?:currency|relevant) period|change application", re.I)
VERSIONED = re.compile(r"\.\d+$")
LIST_STAGES = {
    "lodgement": STAGE["lodged"],
    "action notice sent": STAGE["lodged"],
    "application": STAGE["assessment"],
    "application undergoing assessment": STAGE["assessment"],
    "decision": STAGE["assessment"],
    "decision period commenced": STAGE["assessment"],
    "end information request": STAGE["assessment"],
    "information request part": STAGE["info_request"],
    "information response": STAGE["info_request"],
    "further information required": STAGE["info_request"],
    "public notification": STAGE["notification"],
    "notification stage": STAGE["notification"],
}
DETAIL_STAGES = [
    (re.compile(r"pre-assessment|confirmation notice", re.I), STAGE["lodged"]),
    (re.compile(r"information request", re.I), STAGE["info_request"]),
]


def base_url(host):
    return f"https://developmenti.{host}.qld.gov.au"


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


def sunshinecoast_parties(description):
    parts = [p.strip() for p in plain(description).split(" - ")]
    found = {"address": parts[0]} if parts else {}
    if len(parts) >= 3:
        found["applicant"] = parts[2]
    if len(parts) >= 4:
        found["planner_firm"] = parts[3]
    return found


def epoch_ms(day):
    return int(dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp() * 1000)


def payload(progress, field, since=None, until=None, application_type="", number=""):
    body = {
        "Progress": progress, "DateRangeField": field, "SortField": field or "decided",
        "IncludeDA": True, "IncludeBA": False, "IncludePlumb": False,
        "ShowCode": True, "ShowImpact": True, "ShowOther": True,
        "ShowIAGA": True, "ShowIAGI": True, "ShowNotifiableCode": True,
        "ShowReferralResponse": True, "ShowRequest": True,
        "PagingStartIndex": 0, "MaxRecords": 1000, "IncludeAroundMe": False,
        "SortAscending": False, "PixelWidth": 800, "PixelHeight": 800,
    }
    if since:
        body.update(StartDateUnixEpochNumber=epoch_ms(since),
                    EndDateUnixEpochNumber=epoch_ms(until + dt.timedelta(days=1)) - 1)
    if application_type:
        body["ApplicationTypeId"] = application_type
    if number:
        body["DANumber"] = number
    return body


def pages(client, host, body, stats):
    seen = set()
    while True:
        data = client.json("POST", base_url(host) + "/Home/ApplicationFilterCSVPaged", json=body)
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
            yield item
        offset = body["PagingStartIndex"] + len(applications)
        if offset >= int(data["totalRecords"]):
            break
        if not applications or not page_new:
            raise ValueError("Development.i pagination made no progress")
        body["PagingStartIndex"] = offset


def application_type(host, item):
    if host == "sunshinecoast" and text(item.get("groupCode")) in {"MCU", "QMCU"}:
        return "Material Change of Use"
    return text(item.get("applicationType"))


def fetch_deployment(client, since, until, stats, logger, host, council):
    body = payload("Decided", "decided", since, until)
    for item in pages(client, host, body, stats):
        app = text(item.get("ramId"))
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
        values = row(
            council=council, state="QLD", application_number=app, description=desc,
            use=use, units=count, date_lodged=item.get("dateReceived"),
            date_decided=item.get("dateDecided"), decision=item.get("stage"),
            assessment_level=item.get("assessmentLevel"), source_url=direct_link(host, app),
            **location(desc, host == "brisbane"), **parties(desc),
        )
        try:
            values.update(geo(client, host, app))
        except Exception as exc:
            stats.error(logger, "%s detail %s failed: %s", stats.source, app, exc)
        if host == "brisbane":
            values = brisbane(client, values, stats, logger)
        normalized = normalize(values, since, until)
        if normalized:
            yield normalized
        else:
            stats.rejected.add((council, app))
    logger.info("%s decided list done", stats.source)


def direct_link(host, app):
    return base_url(host) + "/Home/FilterDirect?" + urlencode({"filters": urlencode({"DANumber": app})})


def geo(client, host, app):
    detail = client.json("GET", base_url(host) + "/Geo/GetApplicationById",
                         params={"applicationId": app, "appType": "development"})
    matches = [f for f in features(detail) if text(f.get("properties", {}).get("application_number")) == app]
    if not matches:
        return {}
    chosen = next((f for f in matches if "current" in text(
        f.get("properties", {}).get("land_parcel_relationship")).lower()), matches[0])
    props = chosen.get("properties", {})
    values = {}
    coordinates = chosen.get("geometry", {}).get("coordinates", [])
    if len(coordinates) >= 2:
        values.update(lon=text(coordinates[0]), lat=text(coordinates[1]))
    if props.get("decision_desc"):
        values["decision"] = text(props["decision_desc"])
    if host == "goldcoast" and props.get("pdonline_id"):
        values["pdonline_id"] = text(props["pdonline_id"])
        values["documents_url"] = ("https://integrations.goldcoast.qld.gov.au/pdonline/ViewDocs.aspx?"
                                   + urlencode({"id": props["pdonline_id"]}))
    return values


def detail_rows(client, host, app):
    page = download(client, base_url(host) + "/Home/ApplicationDetail?"
                    + urlencode({"type": "development", "id": app})).decode("utf-8", "replace")
    start = page.find("table-responsive")
    if start < 0:
        return []
    table = page[start:].split("</table>", 1)[0]
    rows = []
    for raw in re.findall(r"<tr>(.*?)</tr>", table, flags=re.S):
        cells = [plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", raw, flags=re.S)]
        stamps = [int(n) for n in re.findall(r'data-date-number="(-?\d+)"', raw)]
        if cells and stamps:
            rows.append({"name": cells[0], "status": cells[1] if len(cells) > 1 else "", "stamps": stamps})
    return rows


def goldcoast_stage(rows):
    current = next((r for r in rows if r["stamps"][0] > 0 and len(r["stamps"]) > 1 and r["stamps"][1] <= 0), None)
    if current is None:
        started = [r for r in rows if r["stamps"][0] > 0]
        current = started[-1] if started else None
    if current is None:
        return STAGE["lodged"]
    return next((stage for pattern, stage in DETAIL_STAGES if pattern.search(current["name"])), STAGE["assessment"])


def brisbane_customer_stage(rows):
    done = {r["name"].lower(): r["status"].lower() == "completed" for r in rows}
    if done.get("information request sent date") and not done.get("final response received date"):
        return STAGE["info_request"]
    return STAGE["lodged"]


def open_stage(client, host, item, logger):
    if "notification" in text(item.get("progress")).lower():
        return STAGE["notification"]
    label = text(item.get("stage")).lower()
    if host == "goldcoast":
        return goldcoast_stage(detail_rows(client, host, text(item.get("ramId"))))
    if host == "brisbane" and label == "with customer":
        return brisbane_customer_stage(detail_rows(client, host, text(item.get("ramId"))))
    if label not in LIST_STAGES and label:
        logger.info("Development.i %s stage %r mapped to assessment", item.get("ramId"), label)
    return LIST_STAGES.get(label, STAGE["lodged"] if not label else STAGE["assessment"])


def current_stage(client, host, item, logger):
    if text(item.get("progress")).lower().startswith("in progress"):
        return open_stage(client, host, item, logger)
    decision = text(item.get("stage"))
    if outcome(decision) == "Approved" or decision.lower() in APPROVED_LABELS:
        return STAGE["approved"]
    return closing_stage(decision)


def documents(client, host, app, values):
    if host == "brisbane":
        return brisbane_documents(client, app)
    if host == "goldcoast":
        return goldcoast_documents(client, values["pdonline_id"]) if values.get("pdonline_id") else []
    if host == "sunshinecoast":
        return sunshinecoast_documents(client, app)
    return []


def lodged_values(client, host, item, stats, logger):
    cfg = HOSTS[host]
    app = text(item.get("ramId"))
    use = "; ".join(filter(None, [item.get("useLevel1"), item.get("useLevel2")]))
    desc = text(item.get("description"))
    if EXCLUDED_STAGES.search(text(item.get("stage"))) or CHANGE_APPLICATION.search(desc) or VERSIONED.search(app):
        return None
    if not is_mcu(application_type(host, item), desc, use):
        return None
    count = unit_count(desc)
    if count is not None and count < 10:
        return None
    where = sunshinecoast_parties(desc) if host == "sunshinecoast" else {
        **location(desc, host == "brisbane"), **parties(desc)}
    values = dict(council=cfg["council"], state="QLD", country="AU", application_number=app, description=desc,
                  use=use, units=count, date_lodged=item.get("dateReceived"),
                  assessment_level=item.get("assessmentLevel"), source_url=direct_link(host, app), **where)
    values.update(geo(client, host, app))
    values.pop("decision", None)
    values["etapa"] = current_stage(client, host, item, logger)
    if not values["etapa"]:
        return None
    docs = documents(client, host, app, values)
    values["plans_url"] = first_plan(docs)
    if host == "brisbane":
        values["documents_url"] = base_url(host) + "/DocumentSearch/GetAllDocument?" + urlencode({"applicationId": app})
        form = brisbane_form(client, docs)
        if form["change"]:
            return None
        if count is None and form["units"] is not None:
            values["units"] = form["units"]
    if host == "sunshinecoast":
        values["documents_url"] = ("https://publicdocs.scc.qld.gov.au/HPECMWebDrawer/Record?"
                                   + urlencode({"q": 'ApplicationNumberList:"' + app + '"'}))
    values.pop("pdonline_id", None)
    return values


def fetch_lodged_deployment(client, since, until, stats, logger, host):
    cfg = HOSTS[host]
    if not cfg["lodged_field"]:
        return
    body = payload("In Progress", cfg["lodged_field"], since, until, cfg["type"])
    for item in pages(client, host, body, stats):
        desc = text(item.get("description"))
        use = "; ".join(filter(None, [item.get("useLevel1"), item.get("useLevel2")]))
        if not is_residential(use, desc):
            continue
        try:
            values = lodged_values(client, host, item, stats, logger)
        except Exception as exc:
            stats.error(logger, "%s lodged %s failed: %s", stats.source, item.get("ramId"), exc)
            continue
        if values:
            normalized = normalize_stage(values, since, until)
            if normalized:
                yield normalized
    logger.info("%s lodged list done", stats.source)


def recheck_deployment(client, numbers, stats, logger, host):
    cfg = HOSTS[host]
    for number in numbers:
        try:
            body = payload("all", "", number=number)
            items = [i for i in pages(client, host, body, stats) if text(i.get("ramId")) == number]
            if not items:
                logger.info("%s recheck %s not found", stats.source, number)
                continue
            item = items[0]
            desc = text(item.get("description"))
            where = sunshinecoast_parties(desc) if host == "sunshinecoast" else {
                **location(desc, host == "brisbane"), **parties(desc)}
            values = dict(council=cfg["council"], state="QLD", country="AU", application_number=number,
                          description=desc, use="; ".join(filter(None, [item.get("useLevel1"), item.get("useLevel2")])),
                          units="", units_known="", date_lodged=item.get("dateReceived"),
                          date_decided=item.get("dateDecided"), source_url=direct_link(host, number), **where)
            values["etapa"] = current_stage(client, host, item, logger)
            if not values["etapa"]:
                logger.info("%s recheck %s has no mapped stage: %r", stats.source, number, item.get("stage"))
                continue
            normalized = normalize_stage(values, filter_units=False)
            if normalized:
                yield normalized
        except Exception as exc:
            stats.error(logger, "%s recheck %s failed: %s", stats.source, number, exc)


def is_mcu(application_type, description, use):
    kind = text(application_type).lower()
    desc = text(description).lower()
    carried = bool(MCU_CARRIERS.search(kind)) and "material change of use" in desc
    return (("material change of use" in kind or carried)
            and not desc.startswith("pre-construction certification")
            and ("reconfigur" not in desc or "material change of use" in desc)
            and is_residential(use, description))
