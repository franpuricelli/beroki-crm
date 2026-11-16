"""Unit-count evidence, bounded document extraction and ACT DA Finder join."""
import hashlib
import io
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from pypdf import PdfReader

from .common import date, plain, text, unit_count
from .storage import atomic_text


ACT_LIST = ("https://services1.arcgis.com/E5n4f1VY84i0xSjy/arcgis/rest/services/"
            "ACTGOV_DAFINDER_LIST_VIEW/FeatureServer/0/query")
ACT_PAGE = ("https://www.planning.act.gov.au/applications-and-assessments/development-applications/"
            "browse-das/development-application-details")
ACT_DOCS = ("https://services1.arcgis.com/E5n4f1VY84i0xSjy/arcgis/rest/services/"
            "ACTGOV_DAFINDER_DETAILED_VIEW/FeatureServer/0/query")
BRISBANE = "https://developmenti.brisbane.qld.gov.au"


def cache(client):
    path = Path(getattr(client, "cache_dir", None) or Path(__file__).resolve().parent.parent / "db" / "quality_cache")
    path.mkdir(parents=True, exist_ok=True)
    return path


def cached_json(client, name, method, url, **kwargs):
    path = cache(client) / (name + ".json")
    if path.exists():
        return json.loads(path.read_text())
    data = client.json(method, url, **kwargs)
    atomic_text(path, json.dumps(data))
    return data


def download(client, url, maximum=20_000_000):
    with client.session.get(url, timeout=(15, client.timeout), stream=True) as response:
        response.raise_for_status()
        chunks = []
        length = 0
        for part in response.iter_content(65536):
            length += len(part)
            if length > maximum:
                raise ValueError("Document exceeds 20MB limit")
            chunks.append(part)
        return b"".join(chunks)


def pdf_text(client, url):
    name = hashlib.sha256(url.encode()).hexdigest()
    path = cache(client) / (name + ".txt")
    if path.exists():
        return path.read_text()
    data = download(client, url)
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("Document response is not PDF")
    reader = PdfReader(io.BytesIO(data), strict=False)
    value = "\n".join(page.extract_text() or "" for page in reader.pages[:5])
    atomic_text(path, value)
    atomic_text(cache(client) / (name + ".evidence.json"), json.dumps({
        "url": url, "pages_read": min(5, len(reader.pages)), "bytes": len(data),
    }))
    return value


def proposal_excerpt(value):
    for pattern in [r"Description\s+of\s+Proposal\s*:\s*(.*?)(?:APPLICANT\s+DETAILS|SITE\s+DETAILS)",
                    r"PROPOSED\s+DEVELOPMENT\s*[:\n]\s*(.*?)(?:APPLICANT\s+DETAILS|SITE\s+DETAILS)"]:
        match = re.search(pattern, value, re.I | re.S)
        if match:
            return plain(match.group(1))
    return value


def doc_rank(doc):
    label = (text(doc.get("fileName")) + " " + text(doc.get("category"))).lower()
    if "decision notice" in label and "notice about" not in label:
        return 0
    if ("planning" in label and "report" in label) or "town planning" in label:
        return 1
    if "delegate decision" in label or "assessment report" in label:
        return 2
    return 99


def brisbane(client, row, stats, logger):
    app = row["application_number"]
    url = BRISBANE + "/Home/ApplicationDetail?" + urlencode({"type": "development", "id": app})
    row["documents_url"] = BRISBANE + "/DocumentSearch/GetAllDocument?" + urlencode({"applicationId": app})
    version = app + "_" + row["date_decided"]
    evidence = cache(client) / ("brisbane_" + version + ".evidence.json")
    if evidence.exists():
        saved = json.loads(evidence.read_text())
        if saved.get("parser_version") != 4:
            evidence.unlink()
            return brisbane(client, row, stats, logger)
        if saved.get("units") is not None:
            row.update(units=str(saved["units"]), units_known="true")
        return row
    try:
        detail_path = cache(client) / ("brisbane_" + version + ".html")
        if detail_path.exists():
            detail = detail_path.read_text()
        else:
            detail = download(client, url).decode("utf-8", "replace")
            atomic_text(detail_path, detail)
        # Do not interpret JavaScript, other application links or property tables as the proposal.
        header = re.sub(r"<script\b[^>]*>.*?</script>", "", detail, flags=re.S | re.I)
        header = header.split("More details:", 1)[0]
        count = unit_count(plain(header))
        result = {"units": count, "source_url": url, "excerpt": plain(header)[:800], "documents_tried": [], "parser_version": 4}
        if count is None:
            listing = cached_json(client, "brisbane_" + version + "_docs", "POST", BRISBANE + "/DocumentSearch/GetResult",
                                  params={"searchText": "", "datefile": "", "applicationId": app, "isSubCategory": "false"},
                                  data={"draw": 1, "start": 0, "length": 1000})
            if not isinstance(listing.get("data"), list):
                raise ValueError("Brisbane document listing lacks data")
            docs = sorted([d for d in listing["data"] if d.get("fileextension") == "pdf" and doc_rank(d) < 99],
                          key=lambda d: (doc_rank(d), -(int(date(d.get("fileDate")).replace("-", "") or "0"))))
            for doc in docs[:3]:
                doc_url = BRISBANE + "/DocumentSearch/downloadFile?" + urlencode(
                    {"fileId": doc["documentId"], "fileName": doc["fileName"]})
                result["documents_tried"].append(doc_url)
                try:
                    value = proposal_excerpt(pdf_text(client, doc_url))
                    count = unit_count(value)
                    if count is not None:
                        result.update(units=count, source_url=doc_url, excerpt=value[:1200])
                        break
                except Exception as exc:
                    logger.warning("Brisbane %s document unavailable: %s", app, exc)
        atomic_text(evidence, json.dumps(result, indent=2))
        if result["units"] is not None:
            row.update(units=str(result["units"]), units_known="true")
    except Exception as exc:
        stats.error(logger, "Brisbane unit lookup %s failed: %s", app, exc)
    return row


def act_index(client, applications):
    result = defaultdict(list)
    apps = sorted(set(applications))
    for start in range(0, len(apps), 50):
        group = apps[start:start + 50]
        where = "DA_NUMBER IN (" + ",".join("'" + a.replace("'", "''") + "'" for a in group) + ")"
        offset = 0
        while True:
            data = client.json("GET", ACT_LIST, params={"where": where, "outFields": "*", "f": "json",
                               "returnGeometry": "false", "resultRecordCount": 1000, "resultOffset": offset,
                               "orderByFields": "OBJECTID ASC"})
            for feature in data["features"]:
                value = feature["attributes"]
                result[text(value["DA_NUMBER"])].append(value)
            if not data.get("exceededTransferLimit"):
                break
            if not data["features"]:
                raise ValueError("ACT detail pagination made no progress")
            offset += len(data["features"])
    atomic_text(cache(client) / "act_latest_matches.json", json.dumps(dict(result)))
    return result


def act(row, records):
    decided = [r for r in records if date(r.get("DECISION_DATE")) and r.get("DA_STAGE") == "Decided"]
    if not decided:
        return row
    # Match the completed decision, not a newer still-pending amendment.
    same = [r for r in decided if date(r.get("DECISION_DATE")) == row["date_decided"]]
    selected = max(same or decided, key=lambda r: (r.get("DECISION_DATE") or 0, r.get("DATECREATED") or 0))
    proposal = text(selected.get("PROPOSAL_TEXT"))
    if proposal:
        row["description"] = proposal
        count = unit_count(proposal)
        row.update(units=text(count), units_known=str(count is not None).lower())
    row.update(address=text(selected.get("STREET_ADDRESS")), suburb=text(selected.get("SUBURB")),
               applicant=text(selected.get("COMPANYORG_NAME")) or text(selected.get("APPLICANT_NAME")),
               lon=text(selected.get("CENTROID_LONG")), lat=text(selected.get("CENTROID_LAT")),
               source_url=ACT_PAGE + "?" + urlencode({"da-number": row["application_number"],
                                                       "amendment-version": selected.get("AMENDMENT_VERSION") or ""}))
    return row


def act_documents(client, row, stats, logger):
    if row["units"]:
        return row
    app = row["application_number"]
    try:
        result = cached_json(client, "act_docs_" + app + "_" + row["date_decided"], "GET", ACT_DOCS,
                             params={"where": "DA_NUMBER=" + str(int(app)), "outFields": "*",
                                     "f": "json", "resultRecordCount": 1000})
        version = parse_qs(urlparse(row["source_url"]).query).get("amendment-version", [""])[0]
        docs = [f["attributes"] for f in result["features"]
                if text(f["attributes"].get("AMENDMENT_VERSION")) == version]
        selected = [d for d in docs if re.search(r"NOTICEOFDECISION|DEVOUTCOMEREP|PLANNING", text(d.get("DOCUMENT_NAME")), re.I)]
        for doc in sorted(selected, key=lambda d: "NOTICEOFDECISION" not in text(d.get("DOCUMENT_NAME")))[:3]:
            name = text(doc.get("DOCUMENT_NAME"))
            if not name.lower().endswith(".pdf") or "/" in name:
                continue
            url = "https://dafinder.blob.core.windows.net/dadocuments/DOCs/" + name
            try:
                value = proposal_excerpt(pdf_text(client, url))
                count = unit_count(value)
                if count is not None:
                    row.update(units=str(count), units_known="true", documents_url=url)
                    break
            except Exception as exc:
                logger.warning("ACT %s notice unavailable: %s", app, exc)
    except Exception as exc:
        stats.error(logger, "ACT %s documents failed: %s", app, exc)
    return row
