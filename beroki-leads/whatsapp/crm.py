from dataclasses import dataclass

import requests

from .config import WHATSAPP
from .parsing import ParseError, items, obj, scalar, text, text_or_none

CRM = WHATSAPP["crm"]


class CrmError(RuntimeError):
    pass


@dataclass(frozen=True)
class DealRow:
    id: str
    created_at: str


@dataclass(frozen=True)
class DealPage:
    rows: tuple
    total: int


@dataclass(frozen=True)
class Deal:
    id: str
    stage: str
    archived: bool
    company_id: str
    company_name: str
    company_domain: str | None
    fields: dict
    contact_ids: tuple


@dataclass(frozen=True)
class ContactDeal:
    id: str
    stage: str


@dataclass(frozen=True)
class Contact:
    id: str
    first_name: str
    last_name: str | None
    email: str | None
    phone: str | None
    linkedin_url: str | None
    archived: bool
    company_id: str | None
    company_name: str | None
    company_domain: str | None
    fields: dict
    deals: tuple


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    domain: str | None
    phone: str | None
    deal_stages: tuple


@dataclass(frozen=True)
class Activity:
    id: str
    type: str
    subject: str | None
    body: str | None
    contact_id: str | None
    deal_id: str | None


@dataclass(frozen=True)
class ActivityPage:
    entries: tuple
    next_cursor: str | None


def field_values(raw, where):
    values = {}
    for index, entry in enumerate(items(raw, where)):
        entry = obj(entry, f"{where}[{index}]")
        key = text(entry.get("key"), f"{where}[{index}].key")
        value = scalar(entry.get("value"), f"{where}[{index}].value")
        if entry.get("type") == "SELECT" and isinstance(value, str):
            for option in items(entry.get("options", []), f"{where}[{index}].options"):
                option = obj(option, f"{where}[{index}].options")
                if option.get("id") == value:
                    value = text(option.get("label"), f"{where}[{index}].options.label")
        values[key] = value
    return values


def parse_deal_page(raw):
    raw = obj(raw, "deals.search")
    rows = []
    for index, row in enumerate(items(raw.get("rows"), "deals.search.rows")):
        row = obj(row, f"deals.search.rows[{index}]")
        rows.append(DealRow(
            id=text(row.get("id"), f"deals.search.rows[{index}].id"),
            created_at=text(row.get("createdAt"), f"deals.search.rows[{index}].createdAt"),
        ))
    total = raw.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise ParseError("deals.search.total: expected a count")
    return DealPage(tuple(rows), total)


def parse_deal(raw):
    raw = obj(raw, "deal")
    company = obj(raw.get("company"), "deal.company")
    contacts = items(raw.get("contacts"), "deal.contacts")
    return Deal(
        id=text(raw.get("id"), "deal.id"),
        stage=text(raw.get("stage"), "deal.stage"),
        archived=text_or_none(raw.get("archivedAt"), "deal.archivedAt") is not None,
        company_id=text(company.get("id"), "deal.company.id"),
        company_name=text(company.get("name"), "deal.company.name"),
        company_domain=text_or_none(company.get("domain"), "deal.company.domain"),
        fields=field_values(raw.get("fields"), "deal.fields"),
        contact_ids=tuple(
            text(obj(contact, "deal.contacts[]").get("id"), "deal.contacts[].id") for contact in contacts
        ),
    )


def parse_contact(raw):
    raw = obj(raw, "contact")
    company = raw.get("company")
    company = obj(company, "contact.company") if company is not None else None
    deals = []
    for index, deal in enumerate(items(raw.get("deals"), "contact.deals")):
        deal = obj(deal, f"contact.deals[{index}]")
        deals.append(ContactDeal(
            id=text(deal.get("id"), f"contact.deals[{index}].id"),
            stage=text(deal.get("stage"), f"contact.deals[{index}].stage"),
        ))
    return Contact(
        id=text(raw.get("id"), "contact.id"),
        first_name=text(raw.get("firstName"), "contact.firstName"),
        last_name=text_or_none(raw.get("lastName"), "contact.lastName"),
        email=text_or_none(raw.get("email"), "contact.email"),
        phone=text_or_none(raw.get("phone"), "contact.phone"),
        linkedin_url=text_or_none(raw.get("linkedinUrl"), "contact.linkedinUrl"),
        archived=text_or_none(raw.get("archivedAt"), "contact.archivedAt") is not None,
        company_id=text(company.get("id"), "contact.company.id") if company else None,
        company_name=text(company.get("name"), "contact.company.name") if company else None,
        company_domain=text_or_none(company.get("domain"), "contact.company.domain") if company else None,
        fields=field_values(raw.get("fields"), "contact.fields"),
        deals=tuple(deals),
    )


def parse_company(raw):
    raw = obj(raw, "company")
    stages = []
    for index, deal in enumerate(items(raw.get("deals"), "company.deals")):
        deal = obj(deal, f"company.deals[{index}]")
        stages.append(text(deal.get("stage"), f"company.deals[{index}].stage"))
    return Company(
        id=text(raw.get("id"), "company.id"),
        name=text(raw.get("name"), "company.name"),
        domain=text_or_none(raw.get("domain"), "company.domain"),
        phone=text_or_none(raw.get("phone"), "company.phone"),
        deal_stages=tuple(stages),
    )


def parse_activity(raw, where="activity"):
    raw = obj(raw, where)
    contact = raw.get("contact")
    deal = raw.get("deal")
    return Activity(
        id=text(raw.get("id"), f"{where}.id"),
        type=text(raw.get("type"), f"{where}.type"),
        subject=text_or_none(raw.get("subject"), f"{where}.subject"),
        body=text_or_none(raw.get("body"), f"{where}.body"),
        contact_id=text(obj(contact, f"{where}.contact").get("id"), f"{where}.contact.id") if contact else None,
        deal_id=text(obj(deal, f"{where}.deal").get("id"), f"{where}.deal.id") if deal else None,
    )


def parse_activity_page(raw):
    raw = obj(raw, "activities")
    entries = tuple(
        parse_activity(entry, f"activities.entries[{index}]")
        for index, entry in enumerate(items(raw.get("entries"), "activities.entries"))
    )
    return ActivityPage(entries, text_or_none(raw.get("nextCursor"), "activities.nextCursor"))


class CrmClient:
    def __init__(self, base_url, api_key, session=None):
        self.base = base_url.rstrip("/") + "/rest"
        self.session = session or requests.Session()
        self.session.headers["x-api-key"] = api_key
        self.writes = 0

    def request(self, method, path, **kwargs):
        try:
            response = self.session.request(method, self.base + path, timeout=CRM["timeout_s"], **kwargs)
        except requests.RequestException as exc:
            raise CrmError(f"CRM {method} {path.split('?')[0]} failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise CrmError(f"CRM {method} {path.split('/')[1]} answered {response.status_code}")
        try:
            return response.json()
        except ValueError as exc:
            raise CrmError(f"CRM {method} {path.split('/')[1]} answered non-JSON") from exc

    def read(self, method, path, parser, **kwargs):
        try:
            return parser(self.request(method, path, **kwargs))
        except ParseError as exc:
            raise CrmError(f"CRM response did not match: {exc}") from exc

    def deal_page(self, page):
        body = {
            "page": page,
            "pageSize": CRM["page_size"],
            "stage": list(CRM["stages"]),
            "archived": False,
            "sort": "",
        }
        return self.read("POST", "/deals/search", parse_deal_page, json=body)

    def deal(self, deal_id):
        return self.read("GET", f"/deals/{deal_id}", parse_deal)

    def contact(self, contact_id):
        return self.read("GET", f"/contacts/{contact_id}", parse_contact)

    def company(self, company_id):
        return self.read("GET", f"/companies/{company_id}", parse_company)

    def activity_page(self, anchor, anchor_id, cursor):
        params = {anchor: anchor_id, "filter": "all"}
        if cursor:
            params["cursor"] = cursor
        return self.read("GET", "/activities", parse_activity_page, params=params)

    def create_note(self, contact_id, deal_id, subject, body, occurred_at):
        payload = {
            "type": "NOTE",
            "subject": subject,
            "body": body,
            "occurredAt": occurred_at,
            "contactId": contact_id,
            "dealId": deal_id,
        }
        self.writes += 1
        return self.read("POST", "/activities", parse_activity, json=payload)


def all_deal_rows(client):
    seen = {}
    first_total = None
    for page in range(1, CRM["max_pages"] + 1):
        result = client.deal_page(page)
        if first_total is None:
            first_total = result.total
        for row in result.rows:
            seen.setdefault(row.id, row)
        if not result.rows or page * CRM["page_size"] >= result.total:
            return tuple(seen.values()), first_total
    raise CrmError("CRM deal search did not end within the page limit")


def all_activities(client, anchor, anchor_id):
    entries = []
    cursor = None
    for _ in range(CRM["max_activity_pages"]):
        page = client.activity_page(anchor, anchor_id, cursor)
        entries.extend(page.entries)
        if not page.next_cursor:
            return tuple(entries)
        cursor = page.next_cursor
    raise CrmError("CRM activity history did not end within the page limit")
