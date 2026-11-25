import itertools
import json

import requests

from .parsing import ParseError, flag, items, obj, text


class McpError(RuntimeError):
    pass


class McpUncertain(McpError):
    pass


def parse_rpc_body(response):
    kind = response.headers.get("Content-Type", "")
    if kind.startswith("text/event-stream"):
        messages = []
        for block in response.text.split("\n\n"):
            data = [line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")]
            if data:
                messages.append(json.loads("\n".join(data)))
        return messages
    return [response.json()]


def parse_tool_result(raw):
    raw = obj(raw, "tool result")
    is_error = raw.get("isError", False)
    flag(is_error, "tool result.isError")
    parts = []
    for index, part in enumerate(items(raw.get("content"), "tool result.content")):
        part = obj(part, f"tool result.content[{index}]")
        if part.get("type") == "text":
            parts.append(text(part.get("text"), f"tool result.content[{index}].text"))
    return is_error, "\n".join(parts)


class McpClient:
    def __init__(self, url, token, protocol_version, timeout_s, session=None):
        self.url = url
        self.protocol_version = protocol_version
        self.timeout_s = timeout_s
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        })
        self.ids = itertools.count(1)
        self.ready = False

    def post(self, payload, timeout_s):
        try:
            response = self.session.post(self.url, json=payload, timeout=(10, timeout_s))
        except requests.RequestException as exc:
            raise McpUncertain(f"MCP request failed: {type(exc).__name__}") from exc
        if response.status_code >= 400:
            raise McpError(f"MCP answered HTTP {response.status_code}")
        session_id = response.headers.get("Mcp-Session-Id")
        if session_id:
            self.session.headers["Mcp-Session-Id"] = session_id
        return response

    def rpc(self, method, params, timeout_s=None):
        request_id = next(self.ids)
        response = self.post(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
            timeout_s or self.timeout_s,
        )
        try:
            messages = parse_rpc_body(response)
        except (ValueError, json.JSONDecodeError) as exc:
            raise McpUncertain("MCP answered a body that is not JSON-RPC") from exc
        for message in messages:
            if isinstance(message, dict) and message.get("id") == request_id:
                if "error" in message:
                    raise McpError(f"MCP {method} error: {str(message['error'])[:200]}")
                return message.get("result")
        raise McpUncertain(f"MCP {method} answered without a result")

    def initialize(self):
        if self.ready:
            return
        self.rpc("initialize", {
            "protocolVersion": self.protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "beroki-da-whatsapp", "version": "1.0"},
        })
        self.session.headers["MCP-Protocol-Version"] = self.protocol_version
        self.post({"jsonrpc": "2.0", "method": "notifications/initialized"}, self.timeout_s)
        self.ready = True

    def call(self, name, arguments, timeout_s=None):
        self.initialize()
        result = self.rpc("tools/call", {"name": name, "arguments": arguments}, timeout_s)
        try:
            return parse_tool_result(result)
        except ParseError as exc:
            raise McpUncertain(f"MCP {name} result did not match: {exc}") from exc
