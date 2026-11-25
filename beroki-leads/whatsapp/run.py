import argparse
import collections
import datetime as dt
import os
import re
import sys

from . import checks
from .clients import Agent, Crm, Kairon, ServiceError, Uncertain, Volt
from .config import WHATSAPP

FIELDS = WHATSAPP["fields"]
MARKER = WHATSAPP["marker"] + ":"
REQUIRED = ("CRM_API_URL", "CRM_API_KEY", "VOLT_API_KEY", "KAIRON_API_KEY", "AGENT_URL", "DA_WHATSAPP_DRAFT_SECRET",
            "DA_WHATSAPP_SERVICES", "DA_WHATSAPP_VOLT_INSTANCE_ID", "DA_WHATSAPP_SENDER")


class Stop(RuntimeError):
    pass


def settings(env, mode):
    missing = [name for name in REQUIRED if not (env.get(name) or "").strip()]
    if missing:
        raise Stop("missing configuration: " + ", ".join(missing))
    batch = (env.get("DA_WHATSAPP_BATCH_SIZE") or "").strip() or str(WHATSAPP["batch"]["default"])
    if not batch.isdigit() or not 1 <= int(batch) <= WHATSAPP["batch"]["max"]:
        raise Stop(f"DA_WHATSAPP_BATCH_SIZE must be a whole number from 1 to {WHATSAPP['batch']['max']}")
    services = [" ".join(s.split()) for s in re.split(r"[\n;]", env["DA_WHATSAPP_SERVICES"]) if s.strip()]
    if not 1 <= len(services) <= 8 or any(len(s) > 120 for s in services):
        raise Stop("DA_WHATSAPP_SERVICES needs 1 to 8 services of up to 120 characters, separated by ; or new lines")
    if mode == "send":
        branch = (env.get("DA_WHATSAPP_DEFAULT_BRANCH") or "").strip()
        if env.get("DA_WHATSAPP_SEND_ENABLED") != "true" or env.get("GITHUB_ACTIONS") != "true" or not branch or env.get("GITHUB_REF") != "refs/heads/" + branch:
            raise Stop("send mode needs DA_WHATSAPP_SEND_ENABLED=true, GitHub Actions and the default branch")
    return int(batch), services


def evaluate(crm, exclusions, moment, report):
    deals = []
    for deal_id in crm.deal_ids():
        try:
            deal = crm.deal(deal_id)
            fields = deal["fields"]
            if deal["archived"] or deal["stage"] not in WHATSAPP["stages"] or not str(fields.get(FIELDS["da"]) or "").strip():
                report["deals"]["skipped"] += 1
            elif fields.get(FIELDS["channel"]) not in (None, "", WHATSAPP["channel"]):
                report["deals"]["other_channel"] += 1
            else:
                deals.append((deal, crm.notes("dealId", deal_id)))
        except ServiceError:
            report["deals"]["unreadable"] += 1
    report["deals"]["used"] = len(deals)
    contacts, notes, companies = {}, {}, {}
    for contact_id in {cid for deal, _ in deals for cid in deal["roles"]}:
        try:
            contacts[contact_id], notes[contact_id] = crm.contact(contact_id), crm.notes("contactId", contact_id)
        except ServiceError:
            contacts[contact_id] = None
    owners = collections.defaultdict(set)
    for contact in filter(None, contacts.values()):
        number, _ = checks.phone(contact["phone"])
        if number:
            owners[number[0]].add(contact["id"])
    shared = {number for number, ids in owners.items() if len(ids) > 1}
    chosen = {}
    for deal, deal_notes in deals:
        for contact_id in deal["roles"]:
            previous = chosen.get(contact_id)
            if previous and previous["reason"] is None:
                continue
            contact = contacts[contact_id]
            item = {"contact": contact or {"id": contact_id}, "deal": deal, "reason": "crm_unverifiable", "phone": None, "zones": None}
            if contact:
                try:
                    ids = {(contact["company"] or {}).get("id"), deal["company"]["id"]} - {None}
                    related = [companies[cid] if cid in companies else companies.setdefault(cid, crm.company(cid)) for cid in ids]
                    item["reason"], item["phone"], item["zones"] = checks.screen(contact, deal, notes[contact_id], deal_notes, related, shared, exclusions, moment)
                except ServiceError:
                    pass
            if previous is None or item["reason"] is None:
                chosen[contact_id] = item
    return list(chosen.values())


def deliver(item, message, crm, volt, clock, report):
    contact_id, deal_id = item["contact"]["id"], item["deal"]["id"]
    reservation = checks.new_reservation()

    def write(state, text=None, **extra):
        stamp = clock().isoformat()
        crm.add_note(contact_id, deal_id, *checks.ledger_note(state, reservation, contact_id, deal_id, stamp, text, **extra), stamp)

    def alert(kind):
        report["alerts"].append((kind, contact_id, deal_id, reservation))

    def close(reason):
        try:
            write("not-sent", reason=reason)
        except ServiceError:
            alert("reservation_left_open")
        return reason

    if not checks.in_window(clock(), item["zones"]):
        return "outside_hours"
    try:
        write("reserved", phone=item["phone"][0], run=os.environ.get("GITHUB_RUN_ID", "local"))
    except ServiceError as exc:
        raise Stop(f"crm_reservation_failed: {exc}") from exc
    try:
        ledger_notes = [n for n in crm.notes("contactId", contact_id) if n["body"].startswith(MARKER)]
    except ServiceError as exc:
        alert("reservation_unconfirmed")
        raise Stop(f"crm_reservation_unconfirmed: {exc}") from exc
    mine = [n for n in ledger_notes if f"reservation: {reservation}" in n["body"]]
    if not mine or checks.ledger([n for n in ledger_notes if n not in mine]):
        alert("reservation_conflict")
        return close("reservation_unresolved")
    try:
        reason = checks.volt_reason(volt, item["phone"][0], volt.scheduled())
    except ServiceError as exc:
        close("volt_unverifiable")
        raise Stop(f"volt_unverifiable: {exc}") from exc
    if reason or not checks.in_window(clock(), item["zones"]):
        return close(reason or "outside_hours")
    sent_at = clock().isoformat()
    try:
        message_id = volt.send(item["phone"][0][1:], message)
    except Uncertain as exc:
        try:
            write("uncertain", detail=str(exc)[:200])
        except ServiceError:
            pass
        alert("send_uncertain")
        raise Stop("send_uncertain") from exc
    try:
        write("accepted", message, volt_message_id=message_id, sent_at=sent_at, status="accepted by Volt; this is not a delivery receipt")
    except ServiceError as exc:
        alert("accepted_not_recorded")
        raise Stop(f"crm_accepted_not_recorded: {exc}") from exc
    report["sent"] += 1
    return "sent"


def run(mode, batch, services, crm, volt, kairon, agent, instance, sender, clock):
    report = {"mode": mode, "started": clock().isoformat(timespec="seconds"), "deals": collections.Counter(),
              "reasons": collections.Counter(), "sent": 0, "drafted": 0, "alerts": [], "stopped": None}
    items = []
    try:
        if volt.identity() != (instance, "connected", sender):
            raise Stop("volt_identity_mismatch")
        exclusions = (kairon.entries("people"), kairon.entries("companies"))
        items = evaluate(crm, exclusions, clock(), report)
        scheduled = volt.scheduled()
        checked = failures = 0
        for item in items:
            if item["reason"] is not None:
                continue
            if report["sent"] >= batch or report["drafted"] >= batch:
                item["reason"] = "batch_full"
                continue
            if checked >= WHATSAPP["max_volt_checks"]:
                item["reason"] = "volt_not_checked"
                continue
            checked += 1
            item["reason"] = checks.volt_reason(volt, item["phone"][0], scheduled)
            if item["reason"]:
                continue
            payload, item["reason"] = checks.draft_payload(item["contact"], item["deal"], services)
            if item["reason"]:
                continue
            try:
                message = agent.draft(payload)
                failures = 0
            except ServiceError as exc:
                failures += 1
                item["reason"] = "draft_failed"
                if failures >= WHATSAPP["max_draft_failures"]:
                    raise Stop(f"drafting_unavailable: {exc}") from exc
                continue
            if message is None:
                item["reason"] = "draft_review"
                continue
            report["drafted"] += 1
            item["reason"] = deliver(item, message, crm, volt, clock, report) if mode == "send" else "draft_ready"
    except Stop as exc:
        report["stopped"] = str(exc)
    except ServiceError as exc:
        report["stopped"] = f"{type(exc).__name__}: {exc}"
    for item in items:
        if item["reason"] == "reservation_unresolved":
            report["alerts"].append(("reservation_unresolved", item["contact"]["id"], item["deal"]["id"], ""))
        report["reasons"][item["reason"] or ("not_reached" if report["stopped"] else "eligible")] += 1
    return report


def summary(report):
    lines = [
        f"## DA WhatsApp · {report['mode']}", "",
        f"- Started (UTC): {report['started']}",
        "- Deals: " + (", ".join(f"{k} {v}" for k, v in sorted(report["deals"].items())) or "none read"),
        f"- Drafted: {report['drafted']} · Accepted by Volt: {report['sent']}",
    ]
    if report["stopped"]:
        lines.append(f"- **Stopped:** {report['stopped']}")
    lines += ["", "| Result | Contacts |", "| --- | --- |"] + [f"| {k} | {v} |" for k, v in sorted(report["reasons"].items())]
    if report["alerts"]:
        lines += ["", "### Alerts: reconcile with the Volt chat before you release a reservation", ""]
        if report["mode"] == "send":
            lines += [f"- {kind}: contact {contact}, deal {deal}, reservation {res or '(see the contact notes)'}" for kind, contact, deal, res in report["alerts"]]
        else:
            lines += [f"- {kind}: {count}" for kind, count in collections.Counter(a[0] for a in report["alerts"]).items()]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send the first DA WhatsApp message to a small hourly batch")
    parser.add_argument("--mode", choices=("dry-run", "send"), default="dry-run")
    mode = parser.parse_args(argv).mode
    env = os.environ
    try:
        batch, services = settings(env, mode)
    except Stop as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    sending = mode == "send"
    instance = env["DA_WHATSAPP_VOLT_INSTANCE_ID"].strip()
    report = run(
        mode, batch, services,
        Crm(env["CRM_API_URL"], env["CRM_API_KEY"], writable=sending),
        Volt(env["VOLT_API_KEY"], instance, can_send=sending),
        Kairon(env["KAIRON_API_KEY"]),
        Agent(env["AGENT_URL"], env["DA_WHATSAPP_DRAFT_SECRET"]),
        instance, checks.digits(env["DA_WHATSAPP_SENDER"]),
        lambda: dt.datetime.now(dt.timezone.utc),
    )
    text = summary(report)
    print(text)
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as handle:
            handle.write(text)
    return 2 if report["alerts"] else 1 if report["stopped"] else 0


if __name__ == "__main__":
    sys.exit(main())
