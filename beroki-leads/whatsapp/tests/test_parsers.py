import json
import unittest

from whatsapp import crm, kairon, ledger, mcp, volt
from whatsapp.parsing import ParseError

from .fakes import contact, deal, note


class VoltParserTest(unittest.TestCase):
    def test_identity(self):
        value = "Own WhatsApp identity:\nInstance: Default WhatsApp (inst-test-0001)\nStatus: connected\nJID: 61491570110@s.whatsapp.net"
        self.assertEqual(volt.parse_identity(value), volt.Identity("inst-test-0001", "connected", "61491570110"))
        with self.assertRaises(ParseError):
            volt.parse_identity("connected")

    def test_chats(self):
        value = json.dumps({"chats": [{"jid": "61491570006@s.whatsapp.net", "is_group": False, "archived": True}]})
        self.assertEqual(volt.parse_chats(value), (volt.Chat("61491570006@s.whatsapp.net", False),))
        self.assertEqual(volt.parse_chats('{"chats":[]}'), ())
        for bad in ("No chats", '{"items": []}', '{"chats": [{"jid": 1, "is_group": false}]}'):
            with self.assertRaises(ParseError):
                volt.parse_chats(bad)

    def test_scheduled(self):
        value = (
            "2 scheduled message(s):\n"
            "sched-1 · pending · 2026-11-25T22:00:00Z → 61491570006@s.whatsapp.net: \"Hi …\"\n"
            "sched-2 · pending · 2026-11-25T22:00:00Z → 61491570156@s.whatsapp.net: \"Hello …\""
        )
        self.assertEqual(volt.parse_scheduled(value), {"61491570006@s.whatsapp.net", "61491570156@s.whatsapp.net"})
        self.assertEqual(volt.parse_scheduled("No scheduled messages."), frozenset())
        for bad in ("", "3 scheduled message(s):\nsched-1 · pending · t → 1@s.whatsapp.net: \"x\"", "Something else"):
            with self.assertRaises(ParseError):
                volt.parse_scheduled(bad)

    def test_history(self):
        jid = "61491570006@s.whatsapp.net"
        self.assertFalse(volt.parse_history(f"No messages found in chat {jid}.", jid))
        self.assertTrue(volt.parse_history("[2026-11-20] Alex: hi", jid))
        self.assertTrue(volt.parse_history("", jid))

    def test_send_needs_a_message_id(self):
        self.assertEqual(volt.parse_send('{"message_id": "3EB0ABCDEF12"}').message_id, "3EB0ABCDEF12")
        self.assertEqual(volt.parse_send("Message sent. Message ID: 3EB0ABCDEF12").message_id, "3EB0ABCDEF12")
        with self.assertRaises(ParseError):
            volt.parse_send("Message queued")


class FakeResponse:
    def __init__(self, status=200, body=None, kind="application/json", headers=None, raw=None):
        self.status_code = status
        self.body = body
        self.text = raw if raw is not None else json.dumps(body)
        self.headers = {"Content-Type": kind, **(headers or {})}

    def json(self):
        if self.body is None:
            raise ValueError("no JSON")
        return self.body


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.posts = []
        self.gets = []

    def post(self, url, json=None, timeout=None):
        self.posts.append(json)
        return self.responses.pop(0)

    def get(self, url, timeout=None):
        self.gets.append(url)
        return self.responses.pop(0)

    def request(self, method, url, timeout=None, **kwargs):
        self.posts.append((method, url, kwargs))
        return self.responses.pop(0)


def tool_reply(request_id, text, is_error=False):
    return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "isError": is_error}}


class McpTest(unittest.TestCase):
    def test_initialize_then_call_over_event_stream(self):
        stream = "event: message\ndata: " + json.dumps(tool_reply(2, "hello")) + "\n\n"
        session = FakeSession([
            FakeResponse(body={"jsonrpc": "2.0", "id": 1, "result": {}}, headers={"Mcp-Session-Id": "s-1"}),
            FakeResponse(status=202, raw=""),
            FakeResponse(kind="text/event-stream", raw=stream),
        ])
        client = mcp.McpClient("https://mcp.invalid/mcp", "token", "2025-06-18", 5, session)
        self.assertEqual(client.call("list-chats", {}), (False, "hello"))
        self.assertEqual(session.headers["Mcp-Session-Id"], "s-1")
        self.assertEqual(session.headers["Authorization"], "Bearer token")
        self.assertEqual([post.get("method") for post in session.posts], ["initialize", "notifications/initialized", "tools/call"])

    def test_rpc_error_and_http_error(self):
        session = FakeSession([FakeResponse(status=401, body={})])
        client = mcp.McpClient("https://mcp.invalid/mcp", "token", "2025-06-18", 5, session)
        with self.assertRaises(mcp.McpError):
            client.call("list-chats", {})

    def test_send_without_a_result_is_uncertain(self):
        session = FakeSession([
            FakeResponse(body={"jsonrpc": "2.0", "id": 1, "result": {}}),
            FakeResponse(status=202, raw=""),
            FakeResponse(body={"jsonrpc": "2.0", "id": 99, "result": {}}),
        ])
        client = volt.VoltClient("token", "inst", mcp.McpClient("https://mcp.invalid/mcp", "token", "2025-06-18", 5, session))
        with self.assertRaises(volt.VoltUncertain):
            client.send("61491570006", "Hi")

    def test_send_tool_error_is_uncertain(self):
        session = FakeSession([
            FakeResponse(body={"jsonrpc": "2.0", "id": 1, "result": {}}),
            FakeResponse(status=202, raw=""),
            FakeResponse(body=tool_reply(2, "session not connected", True)),
        ])
        client = volt.VoltClient("token", "inst", mcp.McpClient("https://mcp.invalid/mcp", "token", "2025-06-18", 5, session))
        with self.assertRaises(volt.VoltUncertain):
            client.send("61491570006", "Hi")


class KaironTest(unittest.TestCase):
    def test_lists_in_several_shapes(self):
        person = {"slug": "alex-example-c1", "fullName": None}
        self.assertEqual(len(kairon.parse_people([person])), 1)
        self.assertEqual(len(kairon.parse_people({"people": [person]})), 1)
        self.assertEqual(len(kairon.parse_people({"items": [person]})), 1)
        with self.assertRaises(ParseError):
            kairon.parse_people({"items": [person], "nextCursor": "abc"})
        with self.assertRaises(ParseError):
            kairon.parse_people({"unexpected": True})
        with self.assertRaises(ParseError):
            kairon.parse_people([{"slug": None, "fullName": None}])

    def test_person_matches_by_slug_name_or_name_inside_slug(self):
        someone = contact("c1")
        by_slug = kairon.Exclusions(kairon.parse_people([{"slug": "alex-example-c1"}]), ())
        self.assertEqual(kairon.person_reason(by_slug, someone), "kairon_person")
        by_name = kairon.Exclusions(kairon.parse_people([{"fullName": "Álex Examplec1"}]), ())
        self.assertEqual(kairon.person_reason(by_name, someone), "kairon_person")
        no_linkedin = contact("c1", linkedin_url=None, last_name="Sample")
        by_slug_name = kairon.Exclusions(kairon.parse_people([{"slug": "alex-sample-0036b5138"}]), ())
        self.assertEqual(kairon.person_reason(by_slug_name, no_linkedin), "kairon_person")
        other = kairon.Exclusions(kairon.parse_people([{"slug": "someone-else-12ab"}]), ())
        self.assertIsNone(kairon.person_reason(other, someone))

    def test_company_matches_by_name_prefix_or_domain(self):
        someone = contact("c1")
        project = deal("d1", ["c1"])
        by_name = kairon.Exclusions((), kairon.parse_companies([{"companyName": "Fictional Developments", "matchPastEmployees": False}]))
        self.assertEqual(kairon.company_reason(by_name, someone, project), "kairon_company")
        by_domain = kairon.Exclusions((), kairon.parse_companies([{"companyName": "Other", "domain": "https://www.fictional.example/", "matchPastEmployees": False}]))
        self.assertEqual(kairon.company_reason(by_domain, someone, project), "kairon_company")
        unrelated = kairon.Exclusions((), kairon.parse_companies([{"companyName": "Fictional", "matchPastEmployees": False}]))
        self.assertEqual(kairon.company_reason(unrelated, someone, project), "kairon_company")
        different = kairon.Exclusions((), kairon.parse_companies([{"companyName": "Developments", "matchPastEmployees": False}]))
        self.assertIsNone(kairon.company_reason(different, someone, project))

    def test_past_employee_or_unmatchable_entry_blocks(self):
        someone = contact("c1")
        project = deal("d1", ["c1"])
        past = kairon.Exclusions((), kairon.parse_companies([{"companyName": "Elsewhere", "matchPastEmployees": True}]))
        self.assertEqual(kairon.company_reason(past, someone, project), "kairon_past_employees_unverifiable")
        page_only = kairon.Exclusions((), kairon.parse_companies([{"slug": "12345", "matchPastEmployees": False}]))
        self.assertEqual(kairon.company_reason(page_only, someone, project), "kairon_company_unverifiable")

    def test_client_turns_a_bad_answer_into_an_error(self):
        session = FakeSession([FakeResponse(body={"people": []}), FakeResponse(status=500, body={})])
        with self.assertRaises(kairon.KaironError):
            kairon.KaironClient("key", session).exclusions()
        self.assertEqual(session.headers["x-api-key"], "key")


class CrmParserTest(unittest.TestCase):
    def test_deal_detail_resolves_select_labels(self):
        raw = {
            "id": "d1", "stage": "TO_CONTACT", "archivedAt": None,
            "company": {"id": "co", "name": "Fictional", "domain": None},
            "fields": [
                {"key": "da_number", "type": "TEXT", "value": "DA-1", "options": []},
                {"key": "channel", "type": "SELECT", "value": "opt1", "options": [{"id": "opt1", "label": "DA Automation", "position": 0}]},
            ],
            "contacts": [{"id": "c1", "role": "Director"}],
        }
        parsed = crm.parse_deal(raw)
        self.assertEqual(parsed.fields, {"da_number": "DA-1", "channel": "DA Automation"})
        self.assertEqual(parsed.contact_ids, ("c1",))

    def test_contact_detail_needs_its_deals(self):
        raw = {"id": "c1", "firstName": "Alex", "lastName": None, "email": None, "phone": "+61 491 570 006",
               "linkedinUrl": None, "archivedAt": None, "company": None, "fields": [], "deals": [{"id": "d1", "stage": "CONTACTED"}]}
        self.assertEqual(crm.parse_contact(raw).deals, (crm.ContactDeal("d1", "CONTACTED"),))
        del raw["deals"]
        with self.assertRaises(ParseError):
            crm.parse_contact(raw)

    def test_client_sends_the_key_and_reports_a_mismatch(self):
        session = FakeSession([FakeResponse(body={"rows": [], "total": "x"})])
        client = crm.CrmClient("https://crm.invalid/", "key", session)
        with self.assertRaises(crm.CrmError):
            client.deal_page(1)
        method, url, kwargs = session.posts[0]
        self.assertEqual((method, url), ("POST", "https://crm.invalid/rest/deals/search"))
        self.assertEqual(kwargs["json"]["stage"], ["TO_CONTACT", "CONTACTED"])
        self.assertFalse(kwargs["json"]["archived"])
        self.assertEqual(session.headers["x-api-key"], "key")


class LedgerTest(unittest.TestCase):
    def entry(self, activity_id, state, reservation):
        subject, body = ledger.note(state, reservation, "c1", "d1", "2026-11-25T03:17:00+00:00")
        return note(activity_id, body, "c1", "d1", subject)

    def test_reservation_without_outcome_is_unresolved(self):
        self.assertEqual(ledger.standing([self.entry("a1", "reserved", "r_1")]).unresolved, ("r_1",))
        self.assertEqual(ledger.standing([self.entry("a1", "reserved", "r_1"), self.entry("a2", "uncertain", "r_1")]).unresolved, ("r_1",))

    def test_accepted_is_sent_and_released_frees(self):
        accepted = ledger.standing([self.entry("a1", "reserved", "r_1"), self.entry("a2", "accepted", "r_1")])
        self.assertTrue(accepted.sent)
        self.assertEqual(accepted.unresolved, ())
        released = ledger.standing([self.entry("a1", "reserved", "r_1"), self.entry("a2", "released", "r_1")])
        self.assertFalse(released.sent)
        self.assertEqual(released.unresolved, ())

    def test_malformed_marker_blocks(self):
        broken = note("a1", "da-whatsapp: maybe\nreservation: r_1", "c1")
        self.assertEqual(ledger.standing([broken]).unresolved, ("r_1",))
        self.assertIsNone(ledger.parse_entry(note("a2", "Called about WhatsApp", "c1")))


if __name__ == "__main__":
    unittest.main()
