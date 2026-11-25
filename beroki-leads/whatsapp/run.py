import argparse
import collections
import os
import sys
from dataclasses import dataclass, field

from . import drafting, hours, ledger, phones, screening
from .config import REASONS, WHATSAPP
from .crm import CrmClient, CrmError, all_activities, all_deal_rows
from .kairon import KaironClient, KaironError
from .drafting import AgentClient, DraftError
from .settings import SettingsError, load
from .volt import VoltClient, VoltError, VoltUncertain

CRM = WHATSAPP["crm"]
VOLT = WHATSAPP["volt"]
DRAFT = WHATSAPP["draft"]


class Abort(RuntimeError):
    pass


class ReadOnlyError(RuntimeError):
    pass


@dataclass
class Evaluation:
    contact_id: str
    deal: object
    contact: object = None
    reason: str | None = None
    phone: object = None
    zones: object = None


@dataclass
class Report:
    mode: str
    started: str
    batch: int
    deals: collections.Counter = field(default_factory=collections.Counter)
    reasons: collections.Counter = field(default_factory=collections.Counter)
    contacts: int = 0
    repeated_links: int = 0
    ready: int = 0
    sent: int = 0
    alerts: list = field(default_factory=list)
    aborted: str | None = None


class ReadOnlyCrm:
    def __init__(self, crm):
        self.crm = crm

    def __getattr__(self, name):
        if name == "create_note":
            raise ReadOnlyError("dry-run attempted a CRM write")
        return getattr(self.crm, name)


class ReadOnlyVolt:
    def __init__(self, volt):
        self.volt = volt

    def __getattr__(self, name):
        if name == "send":
            raise ReadOnlyError("dry-run attempted a Volt send")
        return getattr(self.volt, name)


def gather_deals(crm, report):
    rows, total = all_deal_rows(crm)
    report.deals["listed"] = len(rows)
    if len(rows) != total:
        report.deals["listing_changed_during_paging"] = 1
    used = []
    for row in sorted(rows, key=lambda item: (item.created_at, item.id)):
        try:
            deal = crm.deal(row.id)
        except CrmError:
            report.deals["unverifiable"] += 1
            continue
        if deal.archived or deal.stage not in CRM["stages"]:
            report.deals["changed_stage"] += 1
            continue
        if not str(deal.fields.get(CRM["da_field"]) or "").strip():
            report.deals["not_da"] += 1
            continue
        channel = deal.fields.get(CRM["channel_field"])
        if channel not in (None, "") and channel != CRM["channel"]:
            report.deals["channel_not_da"] += 1
            continue
        try:
            activities = all_activities(crm, "dealId", deal.id)
        except CrmError:
            report.deals["unverifiable"] += 1
            continue
        report.deals["used"] += 1
        used.append((deal, activities))
    return used


def company_of(crm, cache, company_id):
    if company_id not in cache:
        cache[company_id] = crm.company(company_id)
    return cache[company_id]


def evaluate(crm, exclusions, moment, report):
    deals = gather_deals(crm, report)
    contacts, timelines, companies = {}, {}, {}
    evaluations = []
    for deal, deal_activities in deals:
        for contact_id in deal.contact_ids:
            evaluation = Evaluation(contact_id, deal)
            evaluations.append((evaluation, deal_activities))
            if contact_id in contacts:
                continue
            try:
                contacts[contact_id] = crm.contact(contact_id)
                timelines[contact_id] = all_activities(crm, "contactId", contact_id)
            except CrmError:
                contacts[contact_id] = None
    numbers = collections.defaultdict(set)
    for contact_id, contact in contacts.items():
        if contact is None:
            continue
        parsed = phones.normalize(contact.phone)
        if parsed.phone:
            numbers[parsed.phone.e164].add(contact_id)
    shared = frozenset(number for number, owners in numbers.items() if len(owners) > 1)
    for evaluation, deal_activities in evaluations:
        contact = contacts.get(evaluation.contact_id)
        evaluation.contact = contact
        if contact is None:
            evaluation.reason = "crm_unverifiable"
            continue
        try:
            related = tuple(
                company_of(crm, companies, company_id)
                for company_id in dict.fromkeys(filter(None, (contact.company_id, evaluation.deal.company_id)))
            )
        except CrmError:
            evaluation.reason = "crm_unverifiable"
            continue
        verdict = screening.screen(screening.Context(
            contact=contact,
            deal=evaluation.deal,
            contact_activities=timelines[contact.id],
            deal_activities=deal_activities,
            companies=related,
            shared_phones=shared,
            exclusions=exclusions,
        ), moment)
        evaluation.reason, evaluation.phone, evaluation.zones = verdict.reason, verdict.phone, verdict.zones
    return dedupe([evaluation for evaluation, _ in evaluations], report)


def dedupe(evaluations, report):
    groups = collections.OrderedDict()
    for evaluation in evaluations:
        groups.setdefault(evaluation.contact_id, []).append(evaluation)
    report.contacts = len(groups)
    report.repeated_links = len(evaluations) - len(groups)
    return [next((item for item in group if item.reason is None), group[0]) for group in groups.values()]


class Drafter:
    def __init__(self, agent, services):
        self.agent = agent
        self.services = services
        self.failures = 0

    def message_for(self, evaluation):
        context, reason = drafting.context_for(evaluation.contact, evaluation.deal, self.services)
        if reason:
            return None, reason
        try:
            draft = self.agent.draft(context)
        except DraftError as exc:
            self.failures += 1
            if self.failures >= DRAFT["max_failures_in_a_row"]:
                evaluation.reason = "draft_failed"
                raise Abort(f"drafting_unavailable: {exc}") from exc
            return None, "draft_failed"
        self.failures = 0
        if draft.status == "review":
            return None, "draft_review"
        da_number = str(evaluation.deal.fields.get(CRM["da_field"]) or "").strip()
        if drafting.problem(draft.message, context, da_number):
            return None, "draft_invalid"
        return draft.message, None


class Sender:
    def __init__(self, settings, crm, volt, clock, report):
        self.settings = settings
        self.crm = crm
        self.volt = volt
        self.clock = clock
        self.report = report

    def alert(self, kind, evaluation, reservation):
        self.report.alerts.append((kind, evaluation.contact_id, evaluation.deal.id, reservation))

    def write(self, state, evaluation, reservation, **extra):
        stamp = self.clock().isoformat()
        subject, body = ledger.note(state, reservation, evaluation.contact_id, evaluation.deal.id, stamp, **extra)
        return self.crm.create_note(evaluation.contact_id, evaluation.deal.id, subject, body, stamp)

    def close(self, evaluation, reservation, reason):
        try:
            self.write("not-sent", evaluation, reservation, reason=reason)
        except CrmError:
            self.alert("reservation_left_open", evaluation, reservation)
        return reason

    def deliver(self, evaluation, message):
        if not hours.in_window(self.clock(), evaluation.zones):
            return "outside_hours"
        reservation = ledger.new_reservation()
        try:
            self.write("reserved", evaluation, reservation, phone=evaluation.phone.e164, run=self.settings.run_id)
        except CrmError as exc:
            raise Abort(f"crm_reservation_failed: {exc}") from exc
        try:
            standing = ledger.standing(all_activities(self.crm, "contactId", evaluation.contact_id))
        except CrmError as exc:
            self.alert("reservation_unconfirmed", evaluation, reservation)
            raise Abort(f"crm_reservation_unconfirmed: {exc}") from exc
        if standing.sent or standing.unresolved != (reservation,):
            self.alert("reservation_conflict", evaluation, reservation)
            return self.close(evaluation, reservation, "reservation_unresolved")
        try:
            reason = screening.volt_reason(self.volt, evaluation.phone, self.volt.scheduled_recipients())
        except VoltError as exc:
            self.close(evaluation, reservation, "volt_unverifiable")
            raise Abort(f"volt_unverifiable: {exc}") from exc
        if reason:
            return self.close(evaluation, reservation, reason)
        if not hours.in_window(self.clock(), evaluation.zones):
            return self.close(evaluation, reservation, "outside_hours")
        sent_at = self.clock().isoformat()
        try:
            result = self.volt.send(evaluation.phone.digits, message)
        except VoltUncertain as exc:
            try:
                self.write("uncertain", evaluation, reservation, detail=str(exc)[:200])
            except CrmError:
                pass
            self.alert("send_uncertain", evaluation, reservation)
            raise Abort("send_uncertain") from exc
        try:
            self.write(
                "accepted", evaluation, reservation,
                text=message,
                volt_message_id=result.message_id,
                volt_instance=self.settings.volt_instance,
                sent_at=sent_at,
                status="accepted by Volt; this is not a delivery receipt",
            )
        except CrmError as exc:
            self.alert("accepted_not_recorded", evaluation, reservation)
            raise Abort(f"crm_accepted_not_recorded: {exc}") from exc
        self.report.sent += 1
        return "sent"


def run(settings, crm, volt, kairon_client, agent, clock):
    report = Report(settings.mode, clock().isoformat(timespec="seconds"), settings.batch)
    if settings.mode != "send":
        crm, volt = ReadOnlyCrm(crm), ReadOnlyVolt(volt)
    unique = []
    try:
        identity = volt.identity()
        if identity.status != "connected" or identity.instance_id != settings.volt_instance or identity.number != settings.sender:
            raise Abort("volt_identity_mismatch")
        exclusions = kairon_client.exclusions()
        unique = evaluate(crm, exclusions, clock(), report)
        scheduled = volt.scheduled_recipients()
        sender = Sender(settings, crm, volt, clock, report)
        drafter = Drafter(agent, settings.services)
        checks = 0
        for evaluation in unique:
            if evaluation.reason is not None:
                continue
            if settings.mode == "send" and report.sent >= settings.batch:
                evaluation.reason = "batch_full"
                continue
            if checks >= VOLT["max_checks_per_run"]:
                evaluation.reason = "volt_not_checked"
                continue
            checks += 1
            evaluation.reason = screening.volt_reason(volt, evaluation.phone, scheduled)
            if evaluation.reason is not None:
                continue
            if settings.mode == "dry-run" and report.ready >= settings.batch:
                continue
            message, evaluation.reason = drafter.message_for(evaluation)
            if evaluation.reason is not None:
                continue
            report.ready += 1
            if settings.mode == "send":
                evaluation.reason = sender.deliver(evaluation, message)
            else:
                evaluation.reason = "draft_ready"
    except Abort as exc:
        report.aborted = str(exc)
    except (CrmError, VoltError, KaironError, DraftError, ReadOnlyError) as exc:
        report.aborted = f"{type(exc).__name__}: {exc}"
    for evaluation in unique:
        if evaluation.reason == "reservation_unresolved":
            report.alerts.append(("reservation_unresolved", evaluation.contact_id, evaluation.deal.id, ""))
    report.reasons.update(result_of(evaluation, settings.mode, report.aborted) for evaluation in unique)
    return report


def result_of(evaluation, mode, aborted):
    if evaluation.reason:
        return evaluation.reason
    if mode == "dry-run":
        return "eligible"
    return "not_reached" if aborted else "eligible"


def summary(report):
    lines = [
        f"## DA WhatsApp · {report.mode}",
        "",
        f"- Started (UTC): {report.started}",
        f"- Batch limit: {report.batch}",
        "- Deals: " + (", ".join(f"{key} {value}" for key, value in sorted(report.deals.items())) or "none read"),
        f"- Unique contacts: {report.contacts} (extra links to a second deal: {report.repeated_links})",
        f"- Drafted and passed every check: {report.ready}",
        f"- Accepted by Volt: {report.sent}",
    ]
    if report.aborted:
        lines.append(f"- **Stopped:** {report.aborted}")
    if report.reasons:
        lines += ["", "| Result | Contacts |", "| --- | --- |"]
        known = {reason: index for index, reason in enumerate(REASONS)}
        for reason, count in sorted(report.reasons.items(), key=lambda item: (known.get(item[0], -1), item[0])):
            lines.append(f"| {reason} | {count} |")
    if report.alerts:
        lines += ["", "### Alerts: reconcile with the Volt chat before you release a reservation", ""]
        if report.mode == "send":
            lines += ["| Alert | CRM contact | CRM deal | Reservation |", "| --- | --- | --- | --- |"]
            lines += [f"| {kind} | {contact} | {deal} | {reservation or '(see the contact notes)'} |" for kind, contact, deal, reservation in report.alerts]
        else:
            for kind, count in sorted(collections.Counter(kind for kind, *_ in report.alerts).items()):
                lines.append(f"- {kind}: {count}")
    return "\n".join(lines) + "\n"


def exit_code(report):
    if report.alerts:
        return 2
    return 1 if report.aborted else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Send the first DA WhatsApp message to a small hourly batch")
    parser.add_argument("--mode", choices=("dry-run", "send"), default=os.environ.get("DA_WHATSAPP_MODE") or "dry-run")
    args = parser.parse_args(argv)
    try:
        settings = load(os.environ, args.mode)
    except SettingsError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    report = run(
        settings,
        CrmClient(settings.crm_url, settings.crm_key),
        VoltClient(settings.volt_key, settings.volt_instance),
        KaironClient(settings.kairon_key),
        AgentClient(settings.agent_url, settings.draft_secret),
        hours.utc_now,
    )
    text = summary(report)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    return exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
