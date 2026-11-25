import re
import uuid
from dataclasses import dataclass

from .config import WHATSAPP

LEDGER = WHATSAPP["ledger"]
STATES = ("reserved", "accepted", "uncertain", "not-sent", "released")
RESOLVING = ("accepted", "not-sent", "released")
LINE = re.compile(r"^([a-z-]+):\s*(.*?)\s*$")


@dataclass(frozen=True)
class Entry:
    state: str
    reservation: str
    activity_id: str


@dataclass(frozen=True)
class Standing:
    sent: bool
    unresolved: tuple


def parse_entry(activity):
    lines = (activity.body or "").strip().splitlines()
    if not lines:
        return None
    head = LINE.match(lines[0].strip())
    if not head or head.group(1) != LEDGER["marker"]:
        return None
    values = {}
    for line in lines[1:]:
        if not line.strip():
            break
        match = LINE.match(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    state = head.group(2)
    reservation = values.get("reservation", "")
    if state not in STATES or not reservation:
        return Entry("malformed", reservation or activity.id, activity.id)
    return Entry(state, reservation, activity.id)


def is_ledger(activity):
    return parse_entry(activity) is not None


def standing(activities):
    entries = [entry for entry in map(parse_entry, activities) if entry]
    states = {}
    for entry in entries:
        states.setdefault(entry.reservation, set()).add(entry.state)
    sent = any("accepted" in found for found in states.values())
    unresolved = tuple(sorted(
        reservation for reservation, found in states.items()
        if not found.intersection(RESOLVING)
    ))
    return Standing(sent, unresolved)


def new_reservation():
    return "r_" + uuid.uuid4().hex


def note(state, reservation, contact_id, deal_id, at, text=None, **extra):
    lines = [
        f"{LEDGER['marker']}: {state}",
        f"reservation: {reservation}",
        f"contact: {contact_id}",
        f"deal: {deal_id}",
        f"at: {at}",
    ]
    lines.extend(f"{key.replace('_', '-')}: {value}" for key, value in extra.items())
    if text:
        lines += ["", text]
    return f"{LEDGER['subject']} · {state}", "\n".join(lines)
