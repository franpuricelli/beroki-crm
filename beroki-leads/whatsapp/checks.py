import re
import unicodedata
import uuid
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import PhoneNumberType

from .config import WHATSAPP

FIELDS = WHATSAPP["fields"]
WINDOW = WHATSAPP["window"]
TYPE_NAMES = {value: name for name, value in vars(PhoneNumberType).items() if name.isupper()}
MARKS = re.compile(WHATSAPP["marks"], re.IGNORECASE)
WHATSAPP_NOTE = re.compile(WHATSAPP["whatsapp_note"], re.IGNORECASE)
LEDGER_LINE = re.compile(r"^([a-z-]+):\s*(.*?)\s*$")


def phone(raw):
    text = (raw or "").strip()
    if not text:
        return None, "phone_missing"
    if re.search(WHATSAPP["ambiguous_phone"], text, re.IGNORECASE) or not text.startswith(("+", "00")):
        return None, "phone_ambiguous"
    try:
        number = phonenumbers.parse("+" + text[2:] if text.startswith("00") else text, None)
    except phonenumbers.NumberParseException:
        return None, "phone_invalid"
    if not phonenumbers.is_valid_number(number):
        return None, "phone_invalid"
    country = phonenumbers.region_code_for_number(number)
    if country not in WHATSAPP["phone_types"]:
        return None, "phone_other_country"
    if TYPE_NAMES.get(phonenumbers.number_type(number)) not in WHATSAPP["phone_types"][country]:
        return None, "phone_not_mobile"
    return (phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164), country), None


def digits(value):
    return re.sub(r"\D", "", value or "")


def in_window(moment, zones):
    for name in zones:
        local = moment.astimezone(ZoneInfo(name))
        if local.weekday() not in WINDOW["weekdays"] or not WINDOW["start"] <= local.hour < WINDOW["end"]:
            return False
    return True


def fold(value):
    value = "".join(c for c in unicodedata.normalize("NFKD", value or "") if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def company_key(value):
    return re.sub(r"\s+(pty ltd|pty limited|ltd|limited|llc|inc|corp|corporation|co)$", "", fold(value))


def domain_key(value):
    value = (value or "").strip().lower().rsplit("@", 1)[-1]
    value = (urlparse(value).hostname or "") if "://" in value else value.split("/")[0]
    return value.removeprefix("www.")


def linkedin_slug(url):
    parts = [p for p in urlparse(url if "://" in (url or "") else "https://" + (url or "")).path.split("/") if p]
    return unquote(parts[1]).lower() if len(parts) >= 2 and parts[0] == "in" else ""


def kairon_reason(exclusions, contact, deal):
    people, companies = exclusions
    slug = linkedin_slug(contact["linkedin"])
    full = fold(f"{contact['first_name']} {contact['last_name'] or ''}")
    for person in people:
        their_slug = (person.get("slug") or linkedin_slug(person.get("linkedinUrl"))).lower()
        name = fold(person.get("fullName") or f"{person.get('firstName') or ''} {person.get('lastName') or ''}")
        slug_name = re.sub(r"(\s+\S*\d\S*)+$", "", fold(unquote(their_slug)))
        if (slug and slug == their_slug) or (name and name == full) or (not slug and their_slug and slug_name == full):
            return "kairon_person"
    real = contact["fields"].get(FIELDS["real_company"])
    names = {company_key(n) for n in ((contact["company"] or {}).get("name"), deal["company"]["name"], real if isinstance(real, str) else None) if n} - {""}
    domains = {domain_key(d) for d in (contact["email"], (contact["company"] or {}).get("domain"), deal["company"]["domain"]) if d} - {""}
    unmatchable = False
    for company in companies:
        excluded = {company_key(company.get(k)) for k in ("companyName", "pageName") if company.get(k)} - {""}
        domain = domain_key(company.get("domain"))
        if (domain and domain in domains) or any(n == e or n.startswith(e + " ") for e in excluded for n in names):
            return "kairon_company"
        if company.get("matchPastEmployees"):
            return "kairon_past_employees_unverifiable"
        unmatchable = unmatchable or not (excluded or domain)
    return "kairon_company_unverifiable" if unmatchable else None


def ledger(notes):
    states = {}
    for note in notes:
        lines = note["body"].strip().splitlines()
        head = LEDGER_LINE.match(lines[0]) if lines else None
        if not head or head.group(1) != WHATSAPP["marker"]:
            continue
        values = dict(m.groups() for m in map(LEDGER_LINE.match, lines[1:lines.index("") if "" in lines else None]) if m)
        states.setdefault(values.get("reservation", note["body"]), set()).add(head.group(2))
    if any("accepted" in found for found in states.values()):
        return "already_sent"
    if any(not found & {"accepted", "not-sent", "released"} for found in states.values()):
        return "reservation_unresolved"
    return None


def ledger_note(state, reservation, contact_id, deal_id, at, text=None, **extra):
    lines = [f"{WHATSAPP['marker']}: {state}", f"reservation: {reservation}", f"contact: {contact_id}", f"deal: {deal_id}", f"at: {at}"]
    lines += [f"{key.replace('_', '-')}: {value}" for key, value in extra.items()]
    return f"DA WhatsApp · {state}", "\n".join(lines + (["", text] if text else []))


def new_reservation():
    return "r_" + uuid.uuid4().hex


def truthy(value):
    return value is True or (isinstance(value, str) and value.strip().lower() not in ("", "false", "no", "0"))


def screen(contact, deal, contact_notes, deal_notes, companies, shared, exclusions, moment):
    if deal["id"] not in contact["deal_stages"] or contact["id"] not in deal["roles"]:
        return "deal_not_linked", None, None
    if contact["archived"]:
        return "contact_archived", None, None
    if truthy(contact["fields"].get(FIELDS["no_contact"])):
        return "contact_no_contactar", None, None
    number, reason = phone(contact["phone"])
    if reason:
        return reason, None, None
    if number[0] in shared:
        return "phone_shared", number, None
    if any(c["phone"] and digits(c["phone"]) == digits(number[0]) for c in companies):
        return "phone_is_company_phone", number, None
    if any(stage not in WHATSAPP["stages"] for stage in contact["deal_stages"].values()):
        return "contact_other_deal_advanced", number, None
    if any(stage in WHATSAPP["company_blocking_stages"] for c in companies for stage in c["stages"]):
        return "company_active_proposal", number, None
    own = [n for n in contact_notes + [d for d in deal_notes if d["contact"] in (None, contact["id"])] if not n["body"].startswith(WHATSAPP["marker"] + ":")]
    if any(MARKS.search(n["text"]) for n in own):
        return "crm_mark", number, None
    if any(WHATSAPP_NOTE.search(n["text"]) for n in own):
        return "crm_whatsapp_history", number, None
    reason = ledger(contact_notes) or kairon_reason(exclusions, contact, deal)
    if reason:
        return reason, number, None
    zones = WHATSAPP["zones"][number[1]]
    verified = contact["fields"].get(FIELDS["zone"])
    if isinstance(verified, str) and verified.strip():
        if verified.strip() not in zones:
            return "zone_conflict", number, None
        zones = [verified.strip()]
    if not in_window(moment, zones):
        return "outside_hours", number, zones
    return None, number, zones


def volt_reason(volt, e164, scheduled):
    wanted = e164[1:]
    if any(jid.split("@")[0] == wanted for jid in scheduled):
        return "volt_scheduled"
    if any(not jid.endswith(("@s.whatsapp.net", "@g.us")) for jid in scheduled):
        return "volt_chat_alternate_identity"
    for jid, is_group in volt.chats(wanted):
        if not is_group:
            return "volt_chat_exists" if jid.split("@")[0] == wanted else "volt_chat_alternate_identity"
    return "volt_chat_history" if volt.has_history(wanted + "@s.whatsapp.net") else None


def draft_payload(contact, deal, services):
    role = " ".join((deal["roles"].get(contact["id"]) or "").split())
    if not role or re.search(WHATSAPP["unconfirmed_role"], role, re.IGNORECASE):
        return None, "draft_role_unconfirmed"
    da = str(deal["fields"].get(FIELDS["da"]) or "").strip()
    project = re.sub(r"\s*[–—-]\s*DA\b.*$", "", deal["name"], flags=re.IGNORECASE)
    project = re.sub(r",?\s*([A-Z]{2,3})?\s*\d{4,5}(-\d{4})?\s*$", "", project).strip(" ,")
    units = deal["fields"].get(FIELDS["units"])
    facts = [f"Dwellings: {int(units)}"] if isinstance(units, (int, float)) and not isinstance(units, bool) and units > 0 else []
    facts += [f"Planning status: {WHATSAPP['approved']}"] if deal["fields"].get(FIELDS["decision"]) == WHATSAPP["approved"] else []
    if not (contact["first_name"].strip() and project and facts) or (da and da.lower() in project.lower()):
        return None, "draft_missing_facts"
    return {
        "firstName": contact["first_name"].strip()[:60], "role": role[:120], "project": project[:160],
        "contactCompany": ((contact["company"] or {}).get("name") or "")[:120] or None, "developer": deal["company"]["name"][:120],
        "facts": facts, "services": list(services),
    }, None
