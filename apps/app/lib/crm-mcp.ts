import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { z } from "zod";

const SECOND_MS = 1000;

const CRM_MCP = {
	server: { name: "crm", version: "0.1.0" },
	restPath: "/rest",
	timeoutMs: 20 * SECOND_MS,
	pageSize: 25,
} as const;

const record = z.enum(["companies", "contacts", "deals"]);
const fieldEntity = z.enum(["COMPANY", "CONTACT", "DEAL"]);
const data = z.record(z.string(), z.unknown());

type Method = "GET" | "POST" | "PATCH";

type ToolResult = {
	isError?: boolean;
	content: { type: "text"; text: string }[];
};

function defined(input: Record<string, unknown>): Record<string, unknown> {
	return Object.fromEntries(
		Object.entries(input).filter(([, value]) => value !== undefined),
	);
}

function buildServer(apiUrl: string, apiKey: string): McpServer {
	const base = `${apiUrl.replace(/\/+$/, "")}${CRM_MCP.restPath}`;
	const server = new McpServer(CRM_MCP.server);

	async function call(
		method: Method,
		path: string,
		options: {
			body?: unknown;
			query?: Record<string, string | undefined>;
		} = {},
	): Promise<ToolResult> {
		const url = new URL(base + path);

		for (const [key, value] of Object.entries(options.query ?? {})) {
			if (value !== undefined) url.searchParams.set(key, value);
		}

		try {
			const response = await fetch(url, {
				method,
				headers: {
					"x-api-key": apiKey,
					accept: "application/json",
					...(options.body === undefined
						? {}
						: { "content-type": "application/json" }),
				},
				body:
					options.body === undefined ? undefined : JSON.stringify(options.body),
				signal: AbortSignal.timeout(CRM_MCP.timeoutMs),
			});
			const text = await response.text();

			return {
				isError: !response.ok,
				content: [
					{
						type: "text",
						text: response.ok ? text : `CRM ${response.status}: ${text}`,
					},
				],
			};
		} catch (error) {
			return {
				isError: true,
				content: [
					{
						type: "text",
						text: error instanceof Error ? error.message : String(error),
					},
				],
			};
		}
	}

	server.registerTool(
		"crm_search",
		{
			description:
				"Searches companies, contacts or deals. q matches one word of text.",
			inputSchema: {
				entity: record,
				q: z.string().default(""),
				page: z.number().int().min(1).default(1),
			},
		},
		({ entity, q, page }) =>
			call("POST", `/${entity}/search`, {
				body: { q, page, pageSize: CRM_MCP.pageSize },
			}),
	);

	server.registerTool(
		"crm_get",
		{
			description:
				"One company, contact or deal by id, with its custom fields. A deal includes its contacts and their roles.",
			inputSchema: { entity: record, id: z.string().min(1) },
		},
		({ entity, id }) => call("GET", `/${entity}/${id}`),
	);

	server.registerTool(
		"crm_create",
		{
			description:
				"Creates a company (name, domain, ownerId), a contact (firstName, lastName, email, phone, title, companyId, ownerId) or a deal (name, companyId, ownerId). Custom fields and linkedinUrl are set with crm_update.",
			inputSchema: { entity: record, data },
		},
		({ entity, data }) => call("POST", `/${entity}`, { body: data }),
	);

	server.registerTool(
		"crm_update",
		{
			description:
				"Updates a company, contact or deal. data takes the record's columns and fields, a map of custom field key to value. On a deal, description is the short summary at the top of its overview and findings is the full text of everything found about it.",
			inputSchema: { entity: record, id: z.string().min(1), data },
		},
		({ entity, id, data }) =>
			call("PATCH", `/${entity}/${id}`, { body: { data } }),
	);

	server.registerTool(
		"crm_link_contact_to_deal",
		{
			description:
				"Puts a contact on a deal with a role. The contact can work at any company. The deal keeps its own main company.",
			inputSchema: {
				deal_id: z.string().min(1),
				contact_id: z.string().min(1),
				role: z.string().optional(),
			},
		},
		({ deal_id, contact_id, role }) =>
			call("POST", `/deals/${deal_id}/contacts`, {
				body: defined({ contactId: contact_id, role }),
			}),
	);

	server.registerTool(
		"crm_set_deal_stage",
		{
			description:
				"Moves a deal to a stage: TO_CONTACT, CONTACTED, INTERESTED, DEMO_BOOKED, QUALIFIED_TO_BUY, CONTRACT_SENT, CLOSED_WON, CLOSED_LOST or UNQUALIFIED_TO_BUY.",
			inputSchema: {
				deal_id: z.string().min(1),
				stage: z.string().min(1),
				closed_reason: z.string().optional(),
			},
		},
		({ deal_id, stage, closed_reason }) =>
			call("PATCH", `/deals/${deal_id}/stage`, {
				body: defined({ stage, closedReason: closed_reason }),
			}),
	);

	server.registerTool(
		"crm_list_activities",
		{
			description: "The timeline of a company, a contact or a deal.",
			inputSchema: {
				company_id: z.string().optional(),
				contact_id: z.string().optional(),
				deal_id: z.string().optional(),
			},
		},
		({ company_id, contact_id, deal_id }) =>
			call("GET", "/activities", {
				query: {
					companyId: company_id,
					contactId: contact_id,
					dealId: deal_id,
				},
			}),
	);

	server.registerTool(
		"crm_create_activity",
		{
			description:
				"Logs a NOTE, CALL, EMAIL, MEETING or TASK on a company, a contact or a deal. A TASK needs a subject. Dates are ISO 8601.",
			inputSchema: {
				type: z.enum(["NOTE", "CALL", "EMAIL", "MEETING", "TASK"]),
				subject: z.string().optional(),
				body: z.string().optional(),
				occurred_at: z.string().optional(),
				due_at: z.string().optional(),
				company_id: z.string().optional(),
				contact_id: z.string().optional(),
				deal_id: z.string().optional(),
			},
		},
		(input) =>
			call("POST", "/activities", {
				body: defined({
					type: input.type,
					subject: input.subject,
					body: input.body,
					occurredAt: input.occurred_at,
					dueAt: input.due_at,
					companyId: input.company_id,
					contactId: input.contact_id,
					dealId: input.deal_id,
				}),
			}),
	);

	server.registerTool(
		"crm_list_fields",
		{
			description:
				"The custom fields defined for companies, contacts or deals.",
			inputSchema: { entity: fieldEntity },
		},
		({ entity }) => call("GET", "/fields", { query: { entity } }),
	);

	server.registerTool(
		"crm_create_field",
		{
			description:
				"Defines a custom field. type is TEXT, LONG_TEXT, NUMBER, DATE, CHECKBOX, URL, EMAIL or PHONE. The key comes from the label.",
			inputSchema: {
				entity: fieldEntity,
				label: z.string().min(1),
				type: z.string().min(1),
				agent_filled: z.boolean().default(false),
			},
		},
		({ entity, label, type, agent_filled }) =>
			call("POST", "/fields", {
				body: { entity, label, type, agentFilled: agent_filled },
			}),
	);

	server.registerTool(
		"crm_list_users",
		{
			description: "The users of this CRM. Use an id as ownerId.",
			inputSchema: {},
		},
		() => call("GET", "/users"),
	);

	return server;
}

export async function handleCrmMcp(
	request: Request,
	options: { apiUrl: string; apiKey: string },
): Promise<Response> {
	if (request.method !== "POST") {
		return new Response("method not allowed", {
			status: 405,
			headers: { allow: "POST" },
		});
	}

	const transport = new WebStandardStreamableHTTPServerTransport({
		sessionIdGenerator: undefined,
		enableJsonResponse: true,
	});

	await buildServer(options.apiUrl, options.apiKey).connect(transport);

	return transport.handleRequest(request);
}
