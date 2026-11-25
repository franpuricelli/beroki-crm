import json
import re
from dataclasses import dataclass

from .config import WHATSAPP
from .mcp import McpClient, McpError, McpUncertain
from .parsing import ParseError, flag, items, obj, text

VOLT = WHATSAPP["volt"]
REASON = "Hourly DA WhatsApp job checks or sends one approved first message."
IDENTITY_INSTANCE = re.compile(r"^Instance:.*\(([^()\s]+)\)\s*$", re.MULTILINE)
IDENTITY_STATUS = re.compile(r"^Status:\s*(\S+)\s*$", re.MULTILINE)
IDENTITY_JID = re.compile(r"^JID:\s*(\d+)@s\.whatsapp\.net\s*$", re.MULTILINE)
SCHEDULED_HEADER = re.compile(r"^(\d+) scheduled message\(s\):\s*$")
SCHEDULED_EMPTY = re.compile(r"^no\b.*\bscheduled messages?\b", re.IGNORECASE)
SCHEDULED_LINE = re.compile(r"^\S+ · \S+ · \S+ → ([^\s:]+@[^\s:]+):")
NO_MESSAGES = "No messages found in chat {jid}."
MESSAGE_ID = (
    re.compile(r"\bmessage[ _-]?id\b[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_.:-]{6,})", re.IGNORECASE),
)


class VoltError(RuntimeError):
    pass


class VoltUncertain(VoltError):
    pass


@dataclass(frozen=True)
class Identity:
    instance_id: str
    status: str
    number: str


@dataclass(frozen=True)
class Chat:
    jid: str
    is_group: bool


@dataclass(frozen=True)
class SendResult:
    message_id: str


def parse_identity(value):
    instance = IDENTITY_INSTANCE.search(value)
    status = IDENTITY_STATUS.search(value)
    jid = IDENTITY_JID.search(value)
    if not (instance and status and jid):
        raise ParseError("identity: unexpected format")
    return Identity(instance.group(1), status.group(1).lower(), jid.group(1))


def parse_chats(value):
    try:
        raw = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ParseError("list-chats: not JSON") from exc
    chats = []
    for index, chat in enumerate(items(obj(raw, "list-chats").get("chats"), "list-chats.chats")):
        chat = obj(chat, f"list-chats.chats[{index}]")
        chats.append(Chat(
            jid=text(chat.get("jid"), f"list-chats.chats[{index}].jid"),
            is_group=flag(chat.get("is_group"), f"list-chats.chats[{index}].is_group"),
        ))
    return tuple(chats)


def parse_scheduled(value):
    lines = [line for line in value.strip().splitlines() if line.strip()]
    if not lines:
        raise ParseError("list-scheduled-messages: empty answer")
    if SCHEDULED_EMPTY.match(lines[0]):
        return frozenset()
    header = SCHEDULED_HEADER.match(lines[0])
    if not header:
        raise ParseError("list-scheduled-messages: unexpected format")
    recipients = []
    for line in lines[1:]:
        match = SCHEDULED_LINE.match(line)
        if match:
            recipients.append(match.group(1))
    if len(recipients) != int(header.group(1)):
        raise ParseError("list-scheduled-messages: count does not match the lines")
    return frozenset(recipients)


def parse_history(value, jid):
    return value.strip() != NO_MESSAGES.format(jid=jid)


def parse_send(value):
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        raw = None
    if isinstance(raw, dict):
        for key in ("message_id", "messageId", "id"):
            candidate = raw.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return SendResult(candidate.strip())
    for pattern in MESSAGE_ID:
        match = pattern.search(value)
        if match:
            return SendResult(match.group(1))
    raise ParseError("send-message: no message id in the answer")


class VoltClient:
    def __init__(self, api_key, instance_id, mcp=None):
        self.instance_id = instance_id
        self.mcp = mcp or McpClient(VOLT["url"], api_key, VOLT["protocol_version"], VOLT["timeout_s"])
        self.sends = 0

    def read(self, tool, arguments, parser):
        try:
            is_error, value = self.mcp.call(tool, arguments)
        except McpError as exc:
            raise VoltError(f"Volt {tool} failed: {exc}") from exc
        if is_error:
            raise VoltError(f"Volt {tool} refused the call")
        try:
            return parser(value)
        except ParseError as exc:
            raise VoltError(f"Volt {tool} answer did not match: {exc}") from exc

    def identity(self):
        return self.read(
            "get-own-identity",
            {"instance_id": self.instance_id, "reason": REASON},
            parse_identity,
        )

    def scheduled_recipients(self):
        return self.read("list-scheduled-messages", {"status": "all"}, parse_scheduled)

    def chats_matching(self, digits):
        found = []
        for page in range(VOLT["max_chat_pages"]):
            chats = self.read("list-chats", {
                "query": digits,
                "include_archived": True,
                "include_last_message": False,
                "limit": VOLT["chat_page_size"],
                "page": page,
                "reason": REASON,
            }, parse_chats)
            found.extend(chats)
            if len(chats) < VOLT["chat_page_size"]:
                return tuple(found)
        raise VoltError("Volt list-chats did not end within the page limit")

    def has_history(self, jid):
        return self.read(
            "get-chat-messages",
            {"chat_jid": jid, "limit": 1, "reason": REASON},
            lambda value: parse_history(value, jid),
        )

    def send(self, digits, message):
        self.sends += 1
        try:
            is_error, value = self.mcp.call("send-message", {
                "to": digits,
                "message": message,
                "instance_id": self.instance_id,
                "reason": REASON,
            }, VOLT["send_timeout_s"])
        except (McpError, McpUncertain) as exc:
            raise VoltUncertain(f"Volt send-message result is unknown: {exc}") from exc
        if is_error:
            raise VoltUncertain("Volt send-message answered with an error; the message may or may not exist")
        try:
            return parse_send(value)
        except ParseError as exc:
            raise VoltUncertain(f"Volt send-message answer did not match: {exc}") from exc
