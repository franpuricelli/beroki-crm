import re
from dataclasses import dataclass

from . import hours, kairon, ledger, phones
from .config import WHATSAPP

CRM = WHATSAPP["crm"]
MARKS = {name: tuple(re.compile(p, re.IGNORECASE) for p in patterns) for name, patterns in WHATSAPP["marks"].items()}
WHATSAPP_HISTORY = tuple(re.compile(p, re.IGNORECASE) for p in WHATSAPP["whatsapp_history"])


@dataclass(frozen=True)
class Context:
    contact: object
    deal: object
    contact_activities: tuple
    deal_activities: tuple
    companies: tuple
    shared_phones: frozenset
    exclusions: object


@dataclass(frozen=True)
class Verdict:
    reason: str | None
    phone: object = None
    zones: object = None


def truthy(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in ("", "false", "no", "0")
    return False


def words(activity):
    return f"{activity.subject or ''}\n{activity.body or ''}"


def matches(patterns, activity):
    return any(pattern.search(words(activity)) for pattern in patterns)


def relevant_deal_activities(context):
    return [
        activity for activity in context.deal_activities
        if activity.contact_id in (None, context.contact.id) and not ledger.is_ledger(activity)
    ]


def own_activities(context):
    return [activity for activity in context.contact_activities if not ledger.is_ledger(activity)]


def mark_reason(context):
    notes = own_activities(context) + relevant_deal_activities(context)
    for name, patterns in MARKS.items():
        if any(matches(patterns, activity) for activity in notes):
            return "crm_mark_" + name
    return None


def history_reason(context):
    if any(matches(WHATSAPP_HISTORY, activity) for activity in own_activities(context)):
        return "crm_whatsapp_history"
    for activity in relevant_deal_activities(context):
        if matches(WHATSAPP_HISTORY, activity):
            return "crm_whatsapp_history" if activity.contact_id else "crm_whatsapp_history_ambiguous"
    return None


def ledger_reason(context):
    standing = ledger.standing(context.contact_activities)
    if standing.sent:
        return "already_sent"
    if standing.unresolved:
        return "reservation_unresolved"
    return None


def screen(context, moment):
    contact, deal = context.contact, context.deal
    if not any(item.id == deal.id for item in contact.deals) or contact.id not in deal.contact_ids:
        return Verdict("deal_not_linked")
    if contact.archived:
        return Verdict("contact_archived")
    if truthy(contact.fields.get(CRM["no_contact_field"])):
        return Verdict("contact_no_contactar")
    if any(truthy(contact.fields.get(key)) or truthy(deal.fields.get(key)) for key in CRM["flag_fields"]):
        return Verdict("crm_flag_field")
    parsed = phones.normalize(contact.phone)
    if parsed.reason:
        return Verdict(parsed.reason)
    phone = parsed.phone
    if phone.e164 in context.shared_phones:
        return Verdict("phone_shared", phone)
    if any(company.phone and phones.digits_of(company.phone) == phone.digits for company in context.companies):
        return Verdict("phone_is_company_phone", phone)
    if any(item.stage not in CRM["contact_open_stages"] for item in contact.deals):
        return Verdict("contact_other_deal_advanced", phone)
    if any(stage in CRM["company_blocking_stages"] for company in context.companies for stage in company.deal_stages):
        return Verdict("company_active_proposal", phone)
    for check in (mark_reason, history_reason, ledger_reason):
        reason = check(context)
        if reason:
            return Verdict(reason, phone)
    reason = kairon.person_reason(context.exclusions, contact) or kairon.company_reason(context.exclusions, contact, deal)
    if reason:
        return Verdict(reason, phone)
    verified = contact.fields.get(CRM["zone_field"])
    zone = hours.contact_zones(phone.country, verified if isinstance(verified, str) else None)
    if zone.reason:
        return Verdict(zone.reason, phone)
    if not hours.in_window(moment, zone.zones):
        return Verdict("outside_hours", phone, zone.zones)
    return Verdict(None, phone, zone.zones)


def volt_reason(volt, phone, scheduled):
    if phone.jid in scheduled or any(recipient.split("@")[0] == phone.digits for recipient in scheduled):
        return "volt_scheduled"
    if any(not recipient.endswith(("@s.whatsapp.net", "@g.us")) for recipient in scheduled):
        return "volt_chat_alternate_identity"
    for chat in volt.chats_matching(phone.digits):
        if chat.is_group:
            continue
        if chat.jid.split("@")[0] == phone.digits:
            return "volt_chat_exists"
        return "volt_chat_alternate_identity"
    if volt.has_history(phone.jid):
        return "volt_chat_history"
    return None
