import json
import unittest
from unittest import mock

from whatsapp import ledger, run
from whatsapp.config import WHATSAPP
from whatsapp.crm import Company
from whatsapp.kairon import Exclusions, parse_companies
from whatsapp.settings import Settings
from whatsapp.volt import Identity

from .fakes import IN_AU_WINDOW, INSTANCE, SENDER, Clock, FakeAgent, FakeCrm, FakeKairon, FakeVolt, contact, deal, note, utc

SERVICES = ("Exterior renders", "Interior renders", "Launch imagery")
NUMBERS = ("+61 491 570 006", "+61 491 570 156", "+61 491 570 157", "+61 491 570 158", "+61 491 570 159")


def settings(mode="dry-run", batch=3):
    return Settings(mode, batch, SERVICES, "https://crm.invalid", "k", "k", "k", "https://agent.invalid", "s", INSTANCE, SENDER, "run-1")


def population(count=4):
    contacts = [contact(f"c{i}", NUMBERS[i], deals=[(f"d{i}", "TO_CONTACT")]) for i in range(count)]
    deals = [deal(f"d{i}", [f"c{i}"], da=f"DA-{i}") for i in range(count)]
    return deals, contacts


def execute(crm, volt=None, mode="dry-run", batch=3, clock=None, exclusions=None, agent=None):
    volt = volt or FakeVolt()
    agent = agent or FakeAgent()
    report = run.run(settings(mode, batch), crm, volt, FakeKairon(exclusions), agent, clock or Clock(IN_AU_WINDOW))
    return report, volt


class DryRunTest(unittest.TestCase):
    def test_reports_totals_without_writing_or_sending(self):
        deals, contacts = population()
        crm = FakeCrm(deals, contacts)
        agent = FakeAgent()
        report, volt = execute(crm, agent=agent)
        self.assertIsNone(report.aborted)
        self.assertEqual((report.reasons["draft_ready"], report.reasons["eligible"]), (3, 1))
        self.assertEqual((crm.write_count, volt.sent, len(agent.contexts)), (0, [], 3))
        text = run.summary(report)
        self.assertNotIn("Franco from Beroki", text)
        for item in contacts:
            self.assertNotIn(item.last_name, text)
            self.assertNotIn(item.phone.replace(" ", ""), text.replace(" ", ""))
            self.assertNotIn(item.id, text)
        self.assertEqual(run.exit_code(report), 0)

    def test_a_write_in_dry_run_is_refused(self):
        guarded = run.ReadOnlyCrm(FakeCrm([], []))
        with self.assertRaises(run.ReadOnlyError):
            guarded.create_note("c1", "d1", "s", "b", "t")
        with self.assertRaises(run.ReadOnlyError):
            run.ReadOnlyVolt(FakeVolt()).send("1", "x")

    def test_reads_every_page(self):
        deals, contacts = population(5)
        crm = FakeCrm(deals, contacts)
        with mock.patch.dict(WHATSAPP["crm"], {"page_size": 2}):
            report, _ = execute(crm)
        self.assertEqual(crm.pages_requested, [1, 2, 3])
        self.assertEqual(report.deals["used"], 5)
        self.assertEqual(report.contacts, 5)

    def test_skips_deals_that_are_not_da_or_have_another_channel(self):
        deals, contacts = population(3)
        deals[1] = deal("d1", ["c1"], da="")
        deals[2] = deal("d2", ["c2"], channel="Inbound")
        report, _ = execute(FakeCrm(deals, contacts))
        self.assertEqual((report.deals["not_da"], report.deals["channel_not_da"], report.contacts), (1, 1, 1))

    def test_repeated_contact_counts_once(self):
        shared = contact("c0", NUMBERS[0], deals=[("d0", "TO_CONTACT"), ("d1", "CONTACTED")])
        deals = [deal("d0", ["c0"]), deal("d1", ["c0"], stage="CONTACTED", da="DA-2")]
        report, _ = execute(FakeCrm(deals, [shared]))
        self.assertEqual((report.contacts, report.repeated_links, report.reasons["draft_ready"]), (1, 1, 1))

    def test_shared_phone_excludes_both_people(self):
        deals, contacts = population(2)
        contacts[1] = contact("c1", NUMBERS[0], deals=[("d1", "TO_CONTACT")])
        report, _ = execute(FakeCrm(deals, contacts))
        self.assertEqual(report.reasons["phone_shared"], 2)

    def test_company_phone_is_not_the_person(self):
        deals, contacts = population(1)
        companies = [Company("co_dev", "Fictional Developments Pty Ltd", "fictional.example", "+61491570006", ())]
        report, _ = execute(FakeCrm(deals, contacts, companies))
        self.assertEqual(report.reasons["phone_is_company_phone"], 1)

    def test_crm_exclusions(self):
        deals, contacts = population(5)
        contacts[0] = contact("c0", NUMBERS[0], deals=[("d0", "TO_CONTACT")], fields={"no_contactar": True})
        contacts[1] = contact("c1", NUMBERS[1], deals=[("d1", "TO_CONTACT"), ("dx", "QUALIFIED_TO_BUY")])
        contacts[2] = contact("c2", NUMBERS[2], deals=[("d2", "TO_CONTACT")], archived=True)
        contacts[3] = contact("c3", NUMBERS[3], deals=[])
        contacts[4] = contact("c4", "0491 570 159", deals=[("d4", "TO_CONTACT")])
        report, _ = execute(FakeCrm(deals, contacts))
        for reason in ("contact_no_contactar", "contact_other_deal_advanced", "contact_archived", "deal_not_linked", "phone_ambiguous"):
            self.assertEqual(report.reasons[reason], 1, reason)

    def test_company_with_an_active_proposal(self):
        deals, contacts = population(1)
        companies = [Company("co_dev", "Fictional Developments Pty Ltd", None, None, ("TO_CONTACT", "CONTRACT_SENT"))]
        report, _ = execute(FakeCrm(deals, contacts, companies))
        self.assertEqual(report.reasons["company_active_proposal"], 1)

    def test_notes_with_marks_or_whatsapp_history(self):
        deals, contacts = population(5)
        activities = [
            note("n0", "Put on hold until March.", "c0"),
            note("n1", "Wrong number, it rings a café.", "c1"),
            note("n2", "Asked to unsubscribe.", "c2"),
            note("n3", "Sent him a WhatsApp in October.", "c3"),
            note("n4", "Chatted on WhatsApp with someone at the developer.", None, "d4"),
            note("n5", "Fictional Holdings owns the site.", None, "d0"),
        ]
        report, _ = execute(FakeCrm(deals, contacts, activities=activities))
        for reason in ("crm_mark_hold", "crm_mark_wrong_number", "crm_mark_unsubscribed", "crm_whatsapp_history", "crm_whatsapp_history_ambiguous"):
            self.assertEqual(report.reasons[reason], 1, reason)

    def test_kairon_exclusions(self):
        deals, contacts = population(2)
        contacts[1] = contact("c1", NUMBERS[1], deals=[("d1", "TO_CONTACT")], company=("co_x", "Excluded Builders", None))
        deals[1] = deal("d1", ["c1"], company=("co_x", "Excluded Builders", None))
        exclusions = Exclusions((), parse_companies([{"companyName": "Excluded Builders", "matchPastEmployees": False}]))
        report, _ = execute(FakeCrm(deals, contacts), exclusions=exclusions)
        self.assertEqual((report.reasons["kairon_company"], report.reasons["draft_ready"]), (1, 1))

    def test_volt_conversation_or_schedule_blocks(self):
        deals, contacts = population(4)
        volt = FakeVolt(
            scheduled={"61491570006@s.whatsapp.net"},
            chats={"61491570156": ["61491570156@s.whatsapp.net"], "61491570157": ["12345@lid"]},
            history={"61491570158@s.whatsapp.net"},
        )
        report, _ = execute(FakeCrm(deals, contacts), volt)
        for reason in ("volt_scheduled", "volt_chat_exists", "volt_chat_alternate_identity", "volt_chat_history"):
            self.assertEqual(report.reasons[reason], 1, reason)

    def test_outside_hours_and_weekend(self):
        deals, contacts = population(2)
        report, _ = execute(FakeCrm(deals, contacts), clock=Clock(utc(2026, 11, 28, 3, 17)))
        self.assertEqual(report.reasons["outside_hours"], 2)

    def test_volt_identity_mismatch_stops_before_reading_the_crm(self):
        deals, contacts = population(1)
        crm = FakeCrm(deals, contacts)
        volt = FakeVolt(identity=Identity(INSTANCE, "connected", "61491570999"))
        report, _ = execute(crm, volt)
        self.assertEqual(report.aborted, "volt_identity_mismatch")
        self.assertEqual(crm.pages_requested, [])
        self.assertEqual(run.exit_code(report), 1)

    def test_crm_failure_while_listing_stops_the_run(self):
        deals, contacts = population(1)
        crm = FakeCrm(deals, contacts)
        crm.fail_reads.add("search")
        report, _ = execute(crm)
        self.assertIn("CrmError", report.aborted)

    def test_unreadable_contact_is_not_eligible(self):
        deals, contacts = population(2)
        crm = FakeCrm(deals, contacts)
        crm.fail_reads.add("activities:c1")
        report, _ = execute(crm)
        self.assertEqual((report.reasons["crm_unverifiable"], report.reasons["draft_ready"]), (1, 1))


class SendTest(unittest.TestCase):
    def test_sends_the_batch_and_records_each_message(self):
        events = []
        deals, contacts = population(4)
        crm = FakeCrm(deals, contacts, events=events)
        volt = FakeVolt(events=events)
        report, _ = execute(crm, volt, mode="send", agent=FakeAgent(events=events))
        self.assertIsNone(report.aborted)
        self.assertEqual((report.sent, report.reasons["sent"], report.reasons["batch_full"]), (3, 3, 1))
        expected = "Hi Alex, I'm Franco from Beroki. I came across Harbor Lane d0 and thought we could help with the renders. Would it be useful if I sent a few examples?"
        self.assertEqual(volt.sent[0], ("61491570006", expected))
        first_send = events.index(("volt_send", "61491570006"))
        self.assertEqual(events[first_send - 2:first_send], [("agent_draft", "Alex"), ("crm_write", "reserved", "c0")])
        self.assertEqual(events[first_send + 1], ("crm_write", "accepted", "c0"))
        accepted = [item for item in crm.notes if item.body.startswith("da-whatsapp: accepted")]
        self.assertEqual(len(accepted), 3)
        self.assertIn("volt-message-id: msg_1", accepted[0].body)
        self.assertIn("sent-at: 2026-11-25T03:17:00+00:00", accepted[0].body)
        self.assertIn("not a delivery receipt", accepted[0].body)
        self.assertTrue(accepted[0].body.endswith("\n\n" + expected))
        self.assertEqual(run.exit_code(report), 0)

    def test_next_run_does_not_send_twice(self):
        deals, contacts = population(1)
        crm = FakeCrm(deals, contacts)
        execute(crm, mode="send")
        report, volt = execute(crm, mode="send")
        self.assertEqual((report.reasons["already_sent"], volt.sent), (1, []))

    def test_uncertain_volt_result_keeps_the_reservation_and_stops(self):
        deals, contacts = population(3)
        crm = FakeCrm(deals, contacts)
        volt = FakeVolt()
        volt.send_results = ["uncertain"]
        report, _ = execute(crm, volt, mode="send")
        self.assertEqual(report.aborted, "send_uncertain")
        self.assertEqual(len(volt.sent), 1)
        self.assertEqual(report.alerts[0][:2], ("send_uncertain", "c0"))
        states = [item.body.splitlines()[0] for item in crm.notes]
        self.assertEqual(states, ["da-whatsapp: reserved", "da-whatsapp: uncertain"])
        self.assertEqual(run.exit_code(report), 2)
        retry, volt_again = execute(crm, mode="send")
        self.assertEqual(retry.reasons["reservation_unresolved"], 1)
        self.assertEqual(volt_again.sent[0][0], "61491570156")
        self.assertIn(("reservation_unresolved", "c0", "d0", ""), retry.alerts)

    def test_released_reservation_frees_the_contact(self):
        deals, contacts = population(1)
        reserved = ledger.note("reserved", "r_old", "c0", "d0", "t")
        released = ledger.note("released", "r_old", "c0", "d0", "t")
        activities = [note("a1", reserved[1], "c0", "d0"), note("a2", released[1], "c0", "d0")]
        report, volt = execute(FakeCrm(deals, contacts, activities=activities), mode="send")
        self.assertEqual(len(volt.sent), 1)

    def test_crm_failure_before_sending_sends_nothing(self):
        deals, contacts = population(2)
        crm = FakeCrm(deals, contacts)
        crm.fail_writes.add("reserved")
        report, volt = execute(crm, mode="send")
        self.assertIn("crm_reservation_failed", report.aborted)
        self.assertEqual(volt.sent, [])
        self.assertEqual(run.exit_code(report), 1)

    def test_crm_failure_after_sending_alerts_and_stops(self):
        deals, contacts = population(3)
        crm = FakeCrm(deals, contacts)
        crm.fail_writes.add("accepted")
        report, volt = execute(crm, mode="send")
        self.assertEqual(len(volt.sent), 1)
        self.assertIn("crm_accepted_not_recorded", report.aborted)
        self.assertEqual(report.alerts[0][0], "accepted_not_recorded")
        self.assertEqual(run.exit_code(report), 2)
        crm.fail_writes.clear()
        retry, volt_again = execute(crm, mode="send")
        self.assertEqual(retry.reasons["reservation_unresolved"], 1)
        self.assertNotIn("61491570006", [digits for digits, _ in volt_again.sent])

    def test_window_is_checked_again_just_before_sending(self):
        deals, contacts = population(1)
        crm = FakeCrm(deals, contacts)
        late = utc(2026, 11, 25, 6, 0)
        report, volt = execute(crm, mode="send", clock=Clock(IN_AU_WINDOW, IN_AU_WINDOW, IN_AU_WINDOW, IN_AU_WINDOW, late))
        self.assertEqual(volt.sent, [])
        self.assertEqual(report.reasons["outside_hours"], 1)
        self.assertEqual(crm.notes[-1].body.splitlines()[0], "da-whatsapp: not-sent")

    def test_conversation_found_after_reserving_is_not_sent(self):
        deals, contacts = population(1)
        crm = FakeCrm(deals, contacts)
        volt = FakeVolt()
        original = volt.scheduled_recipients
        calls = []

        def scheduled():
            calls.append(1)
            return frozenset({"61491570006@s.whatsapp.net"}) if len(calls) > 1 else original()

        volt.scheduled_recipients = scheduled
        report, _ = execute(crm, volt, mode="send")
        self.assertEqual(volt.sent, [])
        self.assertEqual(report.reasons["volt_scheduled"], 1)
        self.assertIn("reason: volt_scheduled", crm.notes[-1].body)

    def test_volt_failure_before_sending_stops(self):
        deals, contacts = population(1)
        volt = FakeVolt()
        volt.fail_reads = True
        report, _ = execute(FakeCrm(deals, contacts), volt, mode="send")
        self.assertIn("VoltError", report.aborted)
        self.assertEqual(volt.sent, [])


if __name__ == "__main__":
    unittest.main()


class DraftingTest(unittest.TestCase):
    def test_agent_never_sees_a_phone_or_the_da_number(self):
        deals, contacts = population(1)
        agent = FakeAgent()
        execute(FakeCrm(deals, contacts), agent=agent)
        payload = json.dumps(agent.contexts[0].payload())
        self.assertNotIn("491", payload)
        self.assertNotIn("DA-0", payload)
        self.assertEqual(agent.contexts[0].project, "Harbor Lane d0")
        self.assertEqual(agent.contexts[0].facts, ("Dwellings: 48", "Planning status: Approved"))

    def test_review_invalid_and_failed_drafts_are_skipped_without_a_reservation(self):
        deals, contacts = population(4)
        crm = FakeCrm(deals, contacts)
        bad = "Hi Alex, I'm Franco from Beroki. See www.example.com for Harbor Lane d1?"
        agent = FakeAgent(["review", bad, "error", "draft"])
        report, volt = execute(crm, mode="send", agent=agent)
        for reason in ("draft_review", "draft_invalid", "draft_failed", "sent"):
            self.assertEqual(report.reasons[reason], 1, reason)
        self.assertEqual(len(volt.sent), 1)
        reserved = [item for item in crm.notes if item.body.startswith("da-whatsapp: reserved")]
        self.assertEqual(len(reserved), 1)

    def test_the_agent_failing_again_and_again_stops_the_run(self):
        deals, contacts = population(4)
        report, volt = execute(FakeCrm(deals, contacts), mode="send", agent=FakeAgent(["error"] * 4))
        self.assertIn("drafting_unavailable", report.aborted)
        self.assertEqual(volt.sent, [])
        self.assertEqual(run.exit_code(report), 1)

    def test_unconfirmed_role_or_missing_facts_are_not_drafted(self):
        deals, contacts = population(3)
        deals[0] = deal("d0", ["c0"], role="Director (inferred)")
        deals[1] = deal("d1", ["c1"], role=None)
        deals[2] = deal("d2", ["c2"], fields={"da_number": "DA-2", "channel": "DA Automation", "decision": "Determined (unverified)"})
        agent = FakeAgent()
        report, _ = execute(FakeCrm(deals, contacts), agent=agent)
        self.assertEqual((report.reasons["draft_role_unconfirmed"], report.reasons["draft_missing_facts"]), (2, 1))
        self.assertEqual(agent.contexts, [])

    def test_dry_run_never_reserves_or_sends_even_with_drafts(self):
        deals, contacts = population(2)
        crm = FakeCrm(deals, contacts)
        report, volt = execute(crm, agent=FakeAgent())
        self.assertEqual(report.reasons["draft_ready"], 2)
        self.assertEqual((crm.notes, volt.sent), ([], []))
