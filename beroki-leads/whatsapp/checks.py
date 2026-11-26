import re
import unicodedata
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import PhoneNumberType
from pipeline.config import LEAD

from .config import WHATSAPP

FIELDS = WHATSAPP["fields"]
WINDOW = WHATSAPP["window"]
LIMITS = WHATSAPP["draft_limits"]
MARKER = WHATSAPP["marker"] + ":"
TYPE_NAMES = {value: name for name, value in vars(PhoneNumberType).items() if name.isupper()}
MARKS = re.compile(WHATSAPP["marks"], re.IGNORECASE)
WHATSAPP_NOTE = re.compile(WHATSAPP["whatsapp_note"], re.IGNORECASE)


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


def canonical_slug(value):
    value = unquote((value or "").strip()).lower()
    return value if re.fullmatch(WHATSAPP["linkedin_slug"], value) else ""


def linkedin_slug(url):
    parts = [p for p in urlparse(url if "://" in (url or "") else "https://" + (url or "")).path.split("/") if p]
    return canonical_slug(parts[1]) if len(parts) >= 2 and parts[0] == "in" else ""


def person_identity(entry):
    raw_slug, url = (entry.get("slug") or "").strip(), (entry.get("linkedinUrl") or "").strip()
    from_slug = canonical_slug(raw_slug) if raw_slug else ""
    from_url = linkedin_slug(url) if url else ""
    if (raw_slug and not from_slug) or (url and not from_url):
        raise ValueError("a person entry has a LinkedIn identity that is not a valid profile")
    if from_slug and from_url and from_slug != from_url:
        raise ValueError("a person entry has a slug and a LinkedIn URL that disagree")
    slug = from_slug or from_url
    name = fold(entry.get("fullName") or "") or fold(f"{entry.get('firstName') or ''} {entry.get('lastName') or ''}")
    if not slug and len(name.split()) < 2:
        raise ValueError("a person entry has no LinkedIn profile and no full name after normalizing")
    return slug, name


def prepare_exclusions(people, companies):
    for entry in people + companies:
        if any(v is not None and not isinstance(v, (str, bool)) for k, v in entry.items() if k in ("slug", "linkedinUrl", "fullName", "firstName", "lastName", "companyName", "pageName", "domain", "matchPastEmployees")):
            raise ValueError("an entry has a field of an unexpected type")
    if any(c.get("matchPastEmployees") for c in companies):
        raise ValueError("a company entry also covers past employees, which the CRM cannot show")
    identities = [person_identity(p) for p in people]
    slugs = {slug for slug, _ in identities}
    names = {name for _, name in identities}
    company_names = [{company_key(c.get("companyName")), company_key(c.get("pageName"))} - {""} for c in companies]
    domains = [domain_key(c.get("domain")) for c in companies]
    if any(not (n or d) for n, d in zip(company_names, domains, strict=True)):
        raise ValueError("a company entry has no name and no domain")
    return {
        "slugs": slugs - {""},
        "names": names - {""},
        "slug_names": {re.sub(r"(\s+\S*\d\S*)+$", "", fold(slug)) for slug in slugs} - {""},
        "companies": set().union(*company_names),
        "domains": set(domains) - {""},
    }


def kairon_reason(ex, contact, deal):
    slug = linkedin_slug(contact["linkedin"])
    full = fold(f"{contact['first_name']} {contact['last_name'] or ''}")
    if (slug and slug in ex["slugs"]) or full in ex["names"] or (not slug and full in ex["slug_names"]):
        return "kairon_person"
    real = contact["fields"].get(FIELDS["real_company"])
    company = contact["company"] or {}
    words = [company_key(n).split() for n in (company.get("name"), deal["company"]["name"], real if isinstance(real, str) else None)]
    prefixes = {" ".join(w[:i]) for w in words for i in range(1, len(w) + 1)}
    domains = {domain_key(d) for d in (contact["email"], company.get("domain"), deal["company"]["domain"])} - {""}
    return "kairon_company" if prefixes & ex["companies"] or domains & ex["domains"] else None


def ledger_field(note, key):
    lines = note["body"].partition("\n")[2].split("\n\n")[0].splitlines()
    return next((line.split(":", 1)[1].strip() for line in lines if line.startswith(key + ":")), "")


def ledger_entries(notes):
    for note in notes:
        if note["body"].startswith(MARKER):
            head = note["body"].partition("\n")[0]
            yield note, head[len(MARKER):].strip(), ledger_field(note, "reservation") or note["body"]


CLOSED_STATES = {"accepted", "not-sent", "released"}


def ledger_states(notes):
    states = {}
    for _, state, reservation in ledger_entries(notes):
        states.setdefault(reservation, set()).add(state)
    return states


def ledger(notes):
    states = ledger_states(notes)
    if any("accepted" in found for found in states.values()):
        return "already_sent"
    if any(not found & CLOSED_STATES for found in states.values()):
        return "reservation_unresolved"
    return None


def ledger_note(state, reservation, contact_id, deal_id, at, text=None, **extra):
    lines = [f"{MARKER} {state}", f"reservation: {reservation}", f"contact: {contact_id}", f"deal: {deal_id}", f"at: {at}"]
    lines += [f"{key.replace('_', '-')}: {value}" for key, value in extra.items()]
    return f"DA WhatsApp · {state}", "\n".join(lines + (["", text] if text else []))


def truthy(value):
    return value is True or (isinstance(value, str) and value.strip().lower() not in ("", "false", "no", "0"))


def contact_reason(contact, deal, parsed, shared):
    if deal["id"] not in contact["deal_stages"]:
        return "deal_not_linked"
    if contact["archived"]:
        return "contact_archived"
    if truthy(contact["fields"].get(FIELDS["no_contact"])):
        return "contact_no_contactar"
    number, reason = parsed
    if reason:
        return reason
    if number[0] in shared:
        return "phone_shared"
    if any(stage not in WHATSAPP["stages"] for stage in contact["deal_stages"].values()):
        return "contact_other_deal_advanced"
    return None


def notes_reason(contact, contact_notes, deal_notes):
    own = [n for n in contact_notes + [d for d in deal_notes if d["contact"] in (None, contact["id"])] if not n["body"].startswith(MARKER)]
    if any(MARKS.search(n["text"]) for n in own):
        return "crm_mark"
    if any(WHATSAPP_NOTE.search(n["text"]) for n in own):
        return "crm_whatsapp_history"
    return None


def screen(contact, deal, number, companies, contact_notes, deal_notes, exclusions, moment):
    e164, country = number
    if any(c["phone"] and digits(c["phone"]) == digits(e164) for c in companies):
        return "phone_is_company_phone", None
    if any(stage in WHATSAPP["company_blocking_stages"] for c in companies for stage in c["stages"]):
        return "company_active_proposal", None
    reason = notes_reason(contact, contact_notes, deal_notes) or ledger(contact_notes) or kairon_reason(exclusions, contact, deal)
    if reason:
        return reason, None
    reason, zones = contact_zones(contact, country)
    if reason:
        return reason, None
    return (None if in_window(moment, zones) else "outside_hours"), zones


def contact_zones(contact, country):
    zones = WHATSAPP["zones"][country]
    verified = contact["fields"].get(FIELDS["zone"])
    if isinstance(verified, str) and verified.strip():
        if verified.strip() not in zones:
            return "zone_conflict", None
        zones = [verified.strip()]
    return None, zones


def rotated(items, moment, size):
    if len(items) <= size:
        return items
    start = (int(moment.timestamp() // 3600) * size) % len(items)
    return items[start:] + items[:start]


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
    approved = LEAD["approved_decision"]
    facts = [f"Dwellings: {int(units)}"] if isinstance(units, (int, float)) and not isinstance(units, bool) and units > 0 else []
    facts += [f"Planning status: {approved}"] if deal["fields"].get(FIELDS["decision"]) == approved else []
    if not (contact["first_name"].strip() and project and facts) or (da and da.lower() in project.lower()):
        return None, "draft_missing_facts"
    return {
        "firstName": contact["first_name"].strip()[:LIMITS["name"]],
        "role": role[:LIMITS["line"]],
        "project": project[:LIMITS["project"]],
        "contactCompany": ((contact["company"] or {}).get("name") or "")[:LIMITS["line"]] or None,
        "developer": deal["company"]["name"][:LIMITS["line"]],
        "facts": facts,
        "services": list(services),
    }, None
