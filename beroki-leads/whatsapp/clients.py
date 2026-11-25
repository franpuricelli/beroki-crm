import itertools
import json
import re

import requests

from .config import WHATSAPP

TIMEOUT = WHATSAPP["timeout_s"]


class ServiceError(RuntimeError):
    pass


class Uncertain(ServiceError):
    pass


def fields_of(raw):
    values = {}
    for field in raw:
        value = field.get("value")
        if field.get("type") == "SELECT":
            value = next((o["label"] for o in field.get("options", []) if o["id"] == value), value)
        values[field["key"]] = value
    return values


def company_of(raw):
    return {"id": raw["id"], "name": raw["name"], "domain": raw.get("domain")} if raw else None


class Crm:
    def __init__(self, base_url, key, writable):
        self.base = base_url.rstrip("/") + "/rest"
        self.session = requests.Session()
        self.session.headers["x-api-key"] = key
        self.writable = writable

    def call(self, method, path, shape, **kwargs):
        try:
            response = self.session.request(method, self.base + path, timeout=TIMEOUT["crm"], **kwargs)
        except requests.RequestException as exc:
            raise ServiceError(f"CRM {method} failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise ServiceError(f"CRM {method} {path.split('/')[1]} answered {response.status_code}")
        try:
            return shape(response.json())
        except (ValueError, KeyError, TypeError, StopIteration) as exc:
            raise ServiceError(f"CRM {path.split('/')[1]} answer did not match") from exc

    def deal_ids(self):
        ids = {}
        for page in range(1, WHATSAPP["max_pages"] + 1):
            body = {"page": page, "pageSize": WHATSAPP["page_size"], "stage": list(WHATSAPP["stages"]), "archived": False}
            rows, total = self.call("POST", "/deals/search", lambda r: (r["rows"], int(r["total"])), json=body)
            for row in rows:
                ids.setdefault(row["id"], row["createdAt"])
            if not rows or page * WHATSAPP["page_size"] >= total:
                return sorted(ids, key=lambda deal_id: (ids[deal_id], deal_id))
        raise ServiceError("CRM deal search did not end within the page limit")

    def deal(self, deal_id):
        return self.call("GET", f"/deals/{deal_id}", lambda r: {
            "id": r["id"], "name": r["name"], "stage": r["stage"], "archived": r["archivedAt"] is not None,
            "company": company_of(r["company"]), "fields": fields_of(r["fields"]),
            "roles": {c["id"]: c.get("role") for c in r["contacts"]},
        })

    def contact(self, contact_id):
        return self.call("GET", f"/contacts/{contact_id}", lambda r: {
            "id": r["id"], "first_name": r["firstName"], "last_name": r.get("lastName"), "email": r.get("email"),
            "phone": r.get("phone"), "linkedin": r.get("linkedinUrl"), "archived": r["archivedAt"] is not None,
            "company": company_of(r.get("company")), "fields": fields_of(r["fields"]),
            "deal_stages": {d["id"]: d["stage"] for d in r["deals"]},
        })

    def company(self, company_id):
        return self.call("GET", f"/companies/{company_id}", lambda r: {
            "phone": r.get("phone"), "stages": [d["stage"] for d in r["deals"]],
        })

    def notes(self, anchor, anchor_id):
        notes, cursor = [], None
        for _ in range(WHATSAPP["max_pages"]):
            params = {anchor: anchor_id, "filter": "all", **({"cursor": cursor} if cursor else {})}
            entries, cursor = self.call("GET", "/activities", lambda r: (r["entries"], r["nextCursor"]), params=params)
            notes += [{"text": f"{e.get('subject') or ''}\n{e.get('body') or ''}", "body": e.get("body") or "",
                       "contact": (e.get("contact") or {}).get("id")} for e in entries]
            if not cursor:
                return notes
        raise ServiceError("CRM history did not end within the page limit")

    def add_note(self, contact_id, deal_id, subject, body, at):
        if not self.writable:
            raise ServiceError("a dry run tried to write to the CRM")
        payload = {"type": "NOTE", "subject": subject, "body": body, "occurredAt": at, "contactId": contact_id, "dealId": deal_id}
        return self.call("POST", "/activities", lambda r: r["id"], json=payload)


class Volt:
    def __init__(self, key, instance, can_send):
        self.instance = instance
        self.can_send = can_send
        self.session = requests.Session()
        self.session.headers.update({"Authorization": "Bearer " + key, "Accept": "application/json, text/event-stream"})
        self.ids = itertools.count(1)
        self.ready = False

    def rpc(self, method, params, timeout):
        request_id = next(self.ids)
        try:
            response = self.session.post(WHATSAPP["volt_url"], json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, timeout=(TIMEOUT["connect"], timeout))
        except requests.RequestException as exc:
            raise Uncertain(f"Volt {method} failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise ServiceError(f"Volt answered HTTP {response.status_code}")
        if response.headers.get("Mcp-Session-Id"):
            self.session.headers["Mcp-Session-Id"] = response.headers["Mcp-Session-Id"]
        lines = [line[5:].strip() for line in response.text.splitlines() if line.startswith("data:")]
        try:
            messages = [json.loads(line) for line in lines] or [response.json()]
        except ValueError as exc:
            raise Uncertain(f"Volt {method} answered something that is not JSON-RPC") from exc
        reply = next((m for m in messages if m.get("id") == request_id), None)
        if reply is None or "error" in reply:
            raise Uncertain(f"Volt {method} gave no result")
        return reply["result"]

    def tool(self, name, arguments, timeout=TIMEOUT["volt"]):
        if not self.ready:
            self.rpc("initialize", {"protocolVersion": WHATSAPP["mcp_protocol"], "capabilities": {}, "clientInfo": {"name": "beroki-da-whatsapp", "version": "1"}}, TIMEOUT["volt"])
            self.session.headers["MCP-Protocol-Version"] = WHATSAPP["mcp_protocol"]
            self.session.post(WHATSAPP["volt_url"], json={"jsonrpc": "2.0", "method": "notifications/initialized"}, timeout=TIMEOUT["volt"])
            self.ready = True
        result = self.rpc("tools/call", {"name": name, "arguments": {**arguments, "reason": "Hourly DA WhatsApp job."}}, timeout)
        text = "\n".join(part.get("text", "") for part in result.get("content", []) if part.get("type") == "text")
        if result.get("isError"):
            raise ServiceError(f"Volt {name} refused the call")
        return text

    def identity(self):
        text = self.tool("get-own-identity", {"instance_id": self.instance})
        found = [re.search(pattern, text, re.MULTILINE) for pattern in (r"^Instance:.*\(([^()\s]+)\)\s*$", r"^Status:\s*(\S+)", r"^JID:\s*(\d+)@s\.whatsapp\.net")]
        if not all(found):
            raise ServiceError("Volt identity has an unknown format")
        instance, status, number = (match.group(1) for match in found)
        return instance, status.lower(), number

    def scheduled(self):
        lines = [line for line in self.tool("list-scheduled-messages", {"status": "all"}).strip().splitlines() if line.strip()]
        if lines and re.match(r"^no\b.*\bscheduled messages?\b", lines[0], re.IGNORECASE):
            return set()
        header = re.match(r"^(\d+) scheduled message\(s\):$", lines[0].strip()) if lines else None
        jids = [m.group(1) for m in (re.match(r"^\S+ · \S+ · \S+ → ([^\s:]+@[^\s:]+):", line) for line in lines[1:]) if m]
        if not header or len(jids) != int(header.group(1)):
            raise ServiceError("Volt scheduled messages have an unknown format")
        return set(jids)

    def chats(self, digits):
        found, size = [], WHATSAPP["volt_chats"]["page_size"]
        for page in range(WHATSAPP["volt_chats"]["max_pages"]):
            try:
                chats = json.loads(self.tool("list-chats", {"query": digits, "include_archived": True, "include_last_message": False, "limit": size, "page": page}))["chats"]
            except (ValueError, KeyError, TypeError) as exc:
                raise ServiceError("Volt chats have an unknown format") from exc
            found += [(c["jid"], bool(c["is_group"])) for c in chats]
            if len(chats) < size:
                return found
        raise ServiceError("Volt chats did not end within the page limit")

    def has_history(self, jid):
        return self.tool("get-chat-messages", {"chat_jid": jid, "limit": 1}).strip() != f"No messages found in chat {jid}."

    def send(self, digits, message):
        if not self.can_send:
            raise ServiceError("a dry run tried to send")
        try:
            text = self.tool("send-message", {"to": digits, "message": message, "instance_id": self.instance}, TIMEOUT["volt_send"])
        except ServiceError as exc:
            raise Uncertain(f"Volt send-message result is unknown: {exc}") from exc
        match = re.search(r"\bmessage[ _-]?id\b[\"']?\s*[:=]\s*[\"']?([A-Za-z0-9_.:-]{6,})", text, re.IGNORECASE)
        if not match:
            raise Uncertain("Volt send-message gave no message ID")
        return match.group(1)


class Kairon:
    def __init__(self, key):
        self.session = requests.Session()
        self.session.headers["x-api-key"] = key

    def entries(self, facet):
        try:
            response = self.session.get(f"{WHATSAPP['kairon_url']}/api/exclusion/{facet}", timeout=TIMEOUT["kairon"])
            raw = response.json() if response.status_code < 400 else None
        except (requests.RequestException, ValueError) as exc:
            raise ServiceError(f"Kairon {facet} exclusions failed") from exc
        if isinstance(raw, dict) and not any(raw.get(k) for k in ("nextCursor", "next", "hasMore")):
            raw = next((raw[k] for k in (facet, "items", "data", "results") if isinstance(raw.get(k), list)), None)
        if not isinstance(raw, list) or not all(isinstance(entry, dict) for entry in raw):
            raise ServiceError(f"Kairon {facet} exclusions have an unknown format")
        return raw


class Agent:
    def __init__(self, base_url, secret):
        self.url = base_url.rstrip("/") + WHATSAPP["draft_path"]
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer " + secret

    def draft(self, payload):
        try:
            response = self.session.post(self.url, json=payload, timeout=TIMEOUT["agent"])
            reply = response.json() if response.status_code < 400 else {}
        except (requests.RequestException, ValueError) as exc:
            raise ServiceError(f"agent draft failed: {type(exc).__name__}") from exc
        if reply.get("status") == "draft" and isinstance(reply.get("message"), str) and reply["message"].strip():
            return reply["message"].strip()
        if reply.get("status") == "review":
            return None
        raise ServiceError("agent draft answer did not match")
