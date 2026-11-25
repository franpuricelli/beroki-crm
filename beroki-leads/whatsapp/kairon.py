import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

import requests

from .config import WHATSAPP
from .parsing import ParseError, flag, items, obj, text_or_none

KAIRON = WHATSAPP["kairon"]
LIST_KEYS = ("items", "data", "results", "entries")
PAGING_KEYS = ("nextCursor", "next_cursor", "next", "hasMore", "has_more")
COMPANY_SUFFIXES = ("pty ltd", "pty limited", "ltd", "limited", "llc", "inc", "corp", "corporation", "co")


class KaironError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExcludedPerson:
    slug: str | None
    full_name: str | None


@dataclass(frozen=True)
class ExcludedCompany:
    names: tuple
    domain: str | None
    past_employees: bool
    matchable: bool


@dataclass(frozen=True)
class Exclusions:
    people: tuple
    companies: tuple


def fold(value):
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char)).lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def company_key(value):
    folded = fold(value)
    for suffix in COMPANY_SUFFIXES:
        if folded.endswith(" " + suffix):
            folded = folded[: -len(suffix) - 1].strip()
    return folded


def domain_key(value):
    if not value:
        return ""
    value = value.strip().lower()
    if "@" in value:
        value = value.rsplit("@", 1)[1]
    if "://" in value:
        value = urlparse(value).hostname or ""
    value = value.split("/")[0]
    return value[4:] if value.startswith("www.") else value


def linkedin_slug(value):
    if not value:
        return ""
    path = urlparse(value if "://" in value else "https://" + value).path
    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "in":
        return unquote(parts[1]).lower()
    return ""


def slug_name(slug):
    tokens = [token for token in fold(unquote(slug or "")).split() if token]
    while tokens and any(char.isdigit() for char in tokens[-1]):
        tokens.pop()
    return " ".join(tokens)


def entry_list(raw, facet):
    if isinstance(raw, list):
        return raw
    raw = obj(raw, f"exclusion.{facet}")
    for key in PAGING_KEYS:
        if raw.get(key):
            raise ParseError(f"exclusion.{facet}: the answer is paginated; the full list is not verified")
    for key in (facet,) + LIST_KEYS:
        if key in raw:
            return items(raw[key], f"exclusion.{facet}.{key}")
    raise ParseError(f"exclusion.{facet}: no list in the answer")


def parse_people(raw):
    people = []
    for index, entry in enumerate(entry_list(raw, "people")):
        entry = obj(entry, f"exclusion.people[{index}]")
        first = text_or_none(entry.get("firstName"), "firstName") or ""
        last = text_or_none(entry.get("lastName"), "lastName") or ""
        full = text_or_none(entry.get("fullName"), "fullName") or f"{first} {last}".strip()
        slug = text_or_none(entry.get("slug"), "slug") or linkedin_slug(text_or_none(entry.get("linkedinUrl"), "linkedinUrl"))
        if not slug and not full:
            raise ParseError(f"exclusion.people[{index}]: no identity")
        people.append(ExcludedPerson(slug.lower() if slug else None, fold(full) or None))
    return tuple(people)


def parse_companies(raw):
    companies = []
    for index, entry in enumerate(entry_list(raw, "companies")):
        entry = obj(entry, f"exclusion.companies[{index}]")
        names = tuple(
            name for name in (
                company_key(text_or_none(entry.get("companyName"), "companyName")),
                company_key(text_or_none(entry.get("pageName"), "pageName")),
            ) if name
        )
        domain = domain_key(text_or_none(entry.get("domain"), "domain")) or None
        past = entry.get("matchPastEmployees", False)
        flag(past, f"exclusion.companies[{index}].matchPastEmployees")
        page = text_or_none(entry.get("slug"), "slug") or text_or_none(entry.get("linkedinUrl"), "linkedinUrl")
        if not names and not domain and not page:
            raise ParseError(f"exclusion.companies[{index}]: no identity")
        companies.append(ExcludedCompany(names, domain, past, bool(names or domain)))
    return tuple(companies)


def name_covers(excluded, candidate):
    return candidate == excluded or candidate.startswith(excluded + " ")


def person_reason(exclusions, contact):
    full = fold(f"{contact.first_name} {contact.last_name or ''}")
    slug = linkedin_slug(contact.linkedin_url)
    for person in exclusions.people:
        if slug and person.slug and slug == person.slug:
            return "kairon_person"
        if person.full_name and person.full_name == full:
            return "kairon_person"
        if not slug and person.slug and slug_name(person.slug) == full:
            return "kairon_person"
    return None


def company_reason(exclusions, contact, deal):
    real_company = contact.fields.get("real_company")
    sources = (contact.company_name, deal.company_name, real_company if isinstance(real_company, str) else None)
    names = {company_key(value) for value in sources if value}
    names.discard("")
    domains = {domain_key(value) for value in (contact.email, contact.company_domain, deal.company_domain) if value}
    domains.discard("")
    for company in exclusions.companies:
        if company.domain and company.domain in domains:
            return "kairon_company"
        if any(name_covers(excluded, candidate) for excluded in company.names for candidate in names):
            return "kairon_company"
    if any(company.past_employees for company in exclusions.companies):
        return "kairon_past_employees_unverifiable"
    if any(not company.matchable for company in exclusions.companies):
        return "kairon_company_unverifiable"
    return None


class KaironClient:
    def __init__(self, api_key, session=None):
        self.session = session or requests.Session()
        self.session.headers["x-api-key"] = api_key

    def get(self, path, parser):
        try:
            response = self.session.get(KAIRON["url"] + path, timeout=KAIRON["timeout_s"])
        except requests.RequestException as exc:
            raise KaironError(f"Kairon exclusions failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise KaironError(f"Kairon exclusions answered HTTP {response.status_code}")
        try:
            return parser(response.json())
        except (ValueError, ParseError) as exc:
            raise KaironError(f"Kairon exclusions did not match: {exc}") from exc

    def exclusions(self):
        return Exclusions(
            people=self.get(KAIRON["people_path"], parse_people),
            companies=self.get(KAIRON["companies_path"], parse_companies),
        )
