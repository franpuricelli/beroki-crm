import datetime as dt
import itertools

from whatsapp.config import WHATSAPP
from whatsapp.crm import Activity, ActivityPage, Company, Contact, ContactDeal, CrmError, Deal, DealPage, DealRow
from whatsapp.kairon import Exclusions
from whatsapp.volt import Chat, Identity, SendResult, VoltError, VoltUncertain

INSTANCE = "inst-test-0001"
SENDER = "61491570110"


def utc(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc)


IN_AU_WINDOW = utc(2026, 11, 25, 3, 17)


class Clock:
    def __init__(self, *moments):
        self.moments = list(moments)

    def __call__(self):
        if len(self.moments) > 1:
            return self.moments.pop(0)
        return self.moments[0]


def contact(contact_id, phone="+61 491 570 006", deals=(), company=("co_dev", "Fictional Developments Pty Ltd", "fictional.example"), **overrides):
    values = dict(
        id=contact_id,
        first_name="Alex",
        last_name="Example" + contact_id,
        email=f"{contact_id}@fictional.example",
        phone=phone,
        linkedin_url=f"https://www.linkedin.com/in/alex-example-{contact_id}/",
        archived=False,
        company_id=company[0] if company else None,
        company_name=company[1] if company else None,
        company_domain=company[2] if company else None,
        fields={},
        deals=tuple(ContactDeal(deal_id, stage) for deal_id, stage in deals),
    )
    values.update(overrides)
    return Contact(**values)


def deal(deal_id, contact_ids, stage="TO_CONTACT", da="DA-0001", channel="DA Automation", company=("co_dev", "Fictional Developments Pty Ltd", "fictional.example"), **overrides):
    fields = {"da_number": da}
    if channel is not None:
        fields["channel"] = channel
    values = dict(
        id=deal_id,
        stage=stage,
        archived=False,
        company_id=company[0],
        company_name=company[1],
        company_domain=company[2],
        fields=fields,
        contact_ids=tuple(contact_ids),
    )
    values.update(overrides)
    return Deal(**values)


def note(activity_id, body, contact_id=None, deal_id=None, subject=None):
    return Activity(activity_id, "NOTE", subject, body, contact_id, deal_id)


class FakeCrm:
    def __init__(self, deals, contacts, companies=(), activities=(), events=None):
        self.deals = {item.id: item for item in deals}
        self.order = [item.id for item in deals]
        self.contacts = {item.id: item for item in contacts}
        self.companies = {item.id: item for item in companies}
        self.activities = list(activities)
        self.ids = itertools.count(1)
        self.notes = []
        self.events = events if events is not None else []
        self.fail_writes = set()
        self.fail_reads = set()
        self.write_count = 0
        self.pages_requested = []

    def check(self, key):
        if key in self.fail_reads:
            raise CrmError(f"fake CRM read failed: {key}")

    def deal_page(self, page):
        self.check("search")
        self.pages_requested.append(page)
        size = WHATSAPP["crm"]["page_size"]
        listed = [
            DealRow(deal_id, f"2026-11-{index + 1:02d}T00:00:00Z")
            for index, deal_id in enumerate(self.order)
            if self.deals[deal_id].stage in WHATSAPP["crm"]["stages"] and not self.deals[deal_id].archived
        ]
        return DealPage(tuple(listed[(page - 1) * size: page * size]), len(listed))

    def deal(self, deal_id):
        self.check("deal:" + deal_id)
        return self.deals[deal_id]

    def contact(self, contact_id):
        self.check("contact:" + contact_id)
        return self.contacts[contact_id]

    def company(self, company_id):
        self.check("company:" + company_id)
        return self.companies.get(company_id) or Company(company_id, "Fictional Co", None, None, ())

    def activity_page(self, anchor, anchor_id, cursor):
        self.check("activities:" + anchor_id)
        key = "contact_id" if anchor == "contactId" else "deal_id"
        matched = [item for item in self.activities if getattr(item, key) == anchor_id]
        start = int(cursor or 0)
        chunk = matched[start:start + 2]
        following = str(start + 2) if start + 2 < len(matched) else None
        return ActivityPage(tuple(chunk), following)

    def create_note(self, contact_id, deal_id, subject, body, occurred_at):
        self.write_count += 1
        state = body.splitlines()[0].split(": ", 1)[1]
        self.events.append(("crm_write", state, contact_id))
        if state in self.fail_writes:
            raise CrmError(f"fake CRM write failed: {state}")
        created = Activity(f"act_{next(self.ids)}", "NOTE", subject, body, contact_id, deal_id)
        self.activities.append(created)
        self.notes.append(created)
        return created


class FakeVolt:
    def __init__(self, scheduled=(), chats=None, history=(), events=None, identity=None):
        self.identity_value = identity or Identity(INSTANCE, "connected", SENDER)
        self.scheduled = frozenset(scheduled)
        self.chats = dict(chats or {})
        self.history = set(history)
        self.events = events if events is not None else []
        self.send_results = []
        self.sent = []
        self.fail_reads = False

    def identity(self):
        return self.identity_value

    def scheduled_recipients(self):
        if self.fail_reads:
            raise VoltError("fake Volt read failed")
        return self.scheduled

    def chats_matching(self, digits):
        if self.fail_reads:
            raise VoltError("fake Volt read failed")
        return tuple(Chat(jid, False) for jid in self.chats.get(digits, ()))

    def has_history(self, jid):
        return jid in self.history

    def send(self, digits, message):
        self.events.append(("volt_send", digits))
        self.sent.append((digits, message))
        outcome = self.send_results.pop(0) if self.send_results else "ok"
        if outcome == "uncertain":
            raise VoltUncertain("fake timeout")
        return SendResult(f"msg_{len(self.sent)}")


class FakeKairon:
    def __init__(self, exclusions=None):
        self.value = exclusions or Exclusions((), ())

    def exclusions(self):
        return self.value
