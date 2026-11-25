import re
from dataclasses import dataclass

import requests

from .config import WHATSAPP
from .parsing import ParseError, obj, text

DRAFT = WHATSAPP["draft"]
UNCONFIRMED = tuple(re.compile(pattern, re.IGNORECASE) for pattern in DRAFT["unconfirmed_role"])
DA_SUFFIX = re.compile(r"\s*[–—-]\s*DA\b.*$", re.IGNORECASE)
POSTCODE = re.compile(r",?\s*(QLD|NSW|VIC|ACT|SA|WA|TAS|NT|[A-Z]{2})?\s*\d{4,5}(-\d{4})?\s*$")
FORBIDDEN = (re.compile(r"https?://|\bwww\.|@", re.IGNORECASE), re.compile(r"[\[\]{}<>\n]"))


class DraftError(RuntimeError):
    pass


@dataclass(frozen=True)
class DraftContext:
    first_name: str
    role: str
    project: str
    contact_company: str | None
    developer: str
    facts: tuple
    services: tuple

    def payload(self):
        return {
            "firstName": self.first_name,
            "role": self.role,
            "project": self.project,
            "contactCompany": self.contact_company,
            "developer": self.developer,
            "facts": list(self.facts),
            "services": list(self.services),
        }


@dataclass(frozen=True)
class Draft:
    status: str
    message: str | None
    reason: str | None


def clip(value, limit):
    value = " ".join((value or "").split())
    return value if 0 < len(value) <= limit else None


def project_name(deal):
    da = str(deal.fields.get(WHATSAPP["crm"]["da_field"]) or "").strip()
    name = DA_SUFFIX.sub("", deal.name).strip()
    name = POSTCODE.sub("", name).strip(" ,")
    if not name or (da and da.lower() in name.lower()):
        return None
    return clip(name, DRAFT["limits"]["project"])


def verified_facts(deal):
    facts = []
    units = deal.fields.get("units")
    if isinstance(units, (int, float)) and not isinstance(units, bool) and units > 0 and float(units).is_integer():
        facts.append(f"Dwellings: {int(units)}")
    if deal.fields.get("decision") == DRAFT["approved_decision"]:
        facts.append(f"Planning status: {DRAFT['approved_decision']}")
    return tuple(facts)


def context_for(contact, deal, services):
    role = clip(deal.contact_roles.get(contact.id), DRAFT["limits"]["role"])
    if not role or any(pattern.search(role) for pattern in UNCONFIRMED):
        return None, "draft_role_unconfirmed"
    first_name = clip(contact.first_name, DRAFT["limits"]["first_name"])
    project = project_name(deal)
    facts = verified_facts(deal)
    developer = clip(deal.company_name, DRAFT["limits"]["company"])
    if not (first_name and project and facts and developer):
        return None, "draft_missing_facts"
    return DraftContext(
        first_name=first_name,
        role=role,
        project=project,
        contact_company=clip(contact.company_name, DRAFT["limits"]["company"]),
        developer=developer,
        facts=facts,
        services=tuple(services),
    ), None


def problem(message, context, da_number):
    if len(message) > DRAFT["max_chars"]:
        return "too long"
    if any(pattern.search(message) for pattern in FORBIDDEN):
        return "link, address or placeholder"
    if not re.search(rf"(?<!\w){re.escape(context.first_name)}(?!\w)", message, re.IGNORECASE):
        return "no greeting by name"
    if message.count("?") != 1:
        return "not exactly one question"
    if da_number and da_number.lower() in message.lower():
        return "the DA number"
    known = " ".join((context.role, context.project, context.contact_company or "", context.developer, *context.facts, *context.services))
    if any(number not in known for number in re.findall(r"\d+", message)):
        return "a number that is not in the context"
    return None


def parse_reply(raw):
    raw = obj(raw, "draft reply")
    status = raw.get("status")
    if status == "draft":
        return Draft("draft", text(raw.get("message"), "draft reply.message").strip(), None)
    if status == "review":
        return Draft("review", None, text(raw.get("reason"), "draft reply.reason").strip())
    raise ParseError("draft reply: unknown status")


class AgentClient:
    def __init__(self, base_url, secret, session=None):
        self.url = base_url.rstrip("/") + DRAFT["path"]
        self.session = session or requests.Session()
        self.session.headers["Authorization"] = "Bearer " + secret
        self.calls = 0

    def draft(self, context):
        self.calls += 1
        try:
            response = self.session.post(self.url, json=context.payload(), timeout=DRAFT["timeout_s"])
        except requests.RequestException as exc:
            raise DraftError(f"agent draft failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise DraftError(f"agent draft answered HTTP {response.status_code}")
        try:
            return parse_reply(response.json())
        except (ValueError, ParseError) as exc:
            raise DraftError(f"agent draft answer did not match: {exc}") from exc
