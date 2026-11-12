import { timingSafeEqual } from "node:crypto";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import type { Crm, FetchLike } from "../crm/client.js";
import { buildServer } from "./server.js";

function sameToken(given: string, expected: string): boolean {
	const a = Buffer.from(given);
	const b = Buffer.from(expected);
	return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Endpoint MCP sin estado (una instancia por pedido, apta para serverless).
 * Acceso: el token va como último segmento de la URL (/api/mcp/<token>) o como Bearer.
 */
export async function handleMcp(request: Request, deps: { crm: () => Crm; accessToken: string | undefined; fetcher?: FetchLike }): Promise<Response> {
	if (!deps.accessToken || deps.accessToken.length < 24) return new Response("MCP_ACCESS_TOKEN no configurado", { status: 503 });
	const fromPath = decodeURIComponent(new URL(request.url).pathname.split("/").filter(Boolean).pop() ?? "");
	const fromHeader = (request.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
	if (!sameToken(fromPath, deps.accessToken) && !sameToken(fromHeader, deps.accessToken)) return new Response("unauthorized", { status: 401 });
	if (request.method !== "POST") return new Response("method not allowed", { status: 405, headers: { allow: "POST" } });

	const transport = new WebStandardStreamableHTTPServerTransport({ sessionIdGenerator: undefined, enableJsonResponse: true });
	const server = buildServer(deps.crm(), deps.fetcher);
	await server.connect(transport);
	return transport.handleRequest(request);
}
