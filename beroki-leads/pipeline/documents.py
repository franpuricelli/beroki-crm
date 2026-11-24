import html
import io
import re
from urllib.parse import quote, urlencode

from pypdf import PdfReader

from .common import plain, text, unit_count
from .config import DOCUMENTS
from .quality import download


BRISBANE = "https://developmenti.brisbane.qld.gov.au"
GOLDCOAST = "https://integrations.goldcoast.qld.gov.au/pdonline/"
SUNSHINECOAST = "https://publicdocs.scc.qld.gov.au/HPECMWebDrawer/"
NOT_PLAN = re.compile(
    r"landscap|stormwater|drainage|earthwork|detention|civil|services|site\s+levels|waste|traffic|acoustic|"
    r"engineer|survey|bushfire|erosion|sediment|lighting|electrical|hydraulic|vegetation|koala|flood|geotech|"
    r"management\s+plan|sketch\s+register|shadow|submission", re.I)
PLAN = re.compile(r"\bplans?\b|architectur|drawings?|elevations?|floor\s*plans?", re.I)
FORM_ONE = re.compile(r"DA\s+Form\s+1", re.I)
CHANGE_NAME = re.compile(r"\bform\s*5\b|change\s+application", re.I)
FORM_CHANGE = re.compile(r"Change\s+application\s+form|Planning\s+Act\s+Form\s+5", re.I)
DEFINITION = re.compile(r"[^.]*means a residential use of premises[^.]*\.", re.I)


def is_plan(name, category=""):
    label = text(name) + " " + text(category)
    return bool(PLAN.search(label)) and not NOT_PLAN.search(text(name))


def first_plan(documents):
    plans = [d for d in documents if is_plan(d["name"], d.get("category", ""))]
    plans.sort(key=lambda d: (not re.search(r"architectur|proposed|proposal|^plans$", d["name"], re.I), d["name"]))
    return plans[0]["url"] if plans else ""


def brisbane_documents(client, application):
    data = client.json("POST", BRISBANE + "/DocumentSearch/GetResult",
                       params={"searchText": "", "datefile": "", "applicationId": application, "isSubCategory": "false"},
                       data={"draw": 1, "start": 0, "length": 1000})
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Brisbane document listing lacks data")
    return [{
        "name": text(d.get("fileName")), "category": text(d.get("category")),
        "url": BRISBANE + "/DocumentSearch/downloadFile?" + urlencode(
            {"fileId": d.get("documentId"), "fileName": d.get("fileName")}),
    } for d in data["data"] if text(d.get("fileextension")).lower() == "pdf"]


def goldcoast_documents(client, pdonline_id):
    page = download(client, GOLDCOAST + "ViewDocs.aspx?" + urlencode({"id": pdonline_id}),
                    DOCUMENTS["max_bytes"]).decode("utf-8", "replace")
    documents = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, flags=re.S):
        link = re.search(r'href="(default\.aspx\?oid=[^"]+)"', row)
        cells = [plain(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        if link and len(cells) >= 2:
            documents.append({"name": html.unescape(cells[1]), "category": "",
                              "url": GOLDCOAST + html.unescape(link.group(1))})
    return documents


def sunshinecoast_documents(client, application):
    query = ('ApplicationNumberList:"' + application + '" And NOT recType:"Folder" '
             'And NOT recTypedTitle:"*submission*"')
    data = client.json("GET", SUNSHINECOAST + "Record", params={"q": query, "sortBy": "recRegisteredOn-",
                                                                "format": "json", "pageSize": 200})
    if not isinstance(data, dict) or not isinstance(data.get("Results"), list):
        raise ValueError("Sunshine Coast document listing lacks Results")
    return [{
        "name": text((d.get("RecordTitle") or {}).get("Value")), "category": "",
        "url": SUNSHINECOAST + "Record/" + quote(text(d.get("Uri"))) + "/File/document",
    } for d in data["Results"] if text((d.get("RecordExtension") or {}).get("Value")).lower() == "pdf"]


def form_text(client, url):
    data = download(client, url, DOCUMENTS["max_bytes"])
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("Application form is not a PDF")
    reader = PdfReader(io.BytesIO(data), strict=False)
    return " ".join((page.extract_text() or "") for page in reader.pages[:DOCUMENTS["form_pages"]])


def form_units(value):
    s = " ".join(value.split())
    brief = re.search(r"brief description of the proposal.*?\):\s*(.*?)\s*e\)\s*Relevant plans", s, re.I)
    table = re.search(r"Number of dwelling units(.*?)8\.2\)", s, re.I)
    for part in [brief, table]:
        if part:
            count = unit_count(DEFINITION.sub(" ", part.group(1)))
            if count is not None:
                return count
    if table:
        match = re.search(r"(?:detached\.|Multiple\s+Dwellings?)\s*(\d{1,4})(?![\d.])", table.group(1), re.I)
        if match:
            return int(match.group(1))
    return None


def brisbane_form(client, documents):
    if any(CHANGE_NAME.search(d["name"]) for d in documents):
        return {"change": True, "units": None, "form_url": ""}
    forms = [d for d in documents if d["category"].lower().startswith("form - application") or FORM_ONE.search(d["name"])]
    if not forms:
        return {"change": False, "units": None, "form_url": ""}
    value = form_text(client, forms[0]["url"])
    if FORM_CHANGE.search(value[:600]):
        return {"change": True, "units": None, "form_url": forms[0]["url"]}
    return {"change": False, "units": form_units(value) if FORM_ONE.search(value[:600]) else None,
            "form_url": forms[0]["url"]}
