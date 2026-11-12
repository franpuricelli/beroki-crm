import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import { DA_OUTREACH } from "./config";
import type { Crm, FetchLike } from "./crm-client";
import * as ops from "./crm-ops";
import {
	fieldValuesInput,
	personInput,
	projectInput,
	stageInput,
} from "./schemas";

type ToolResult = {
	isError?: boolean;
	content: { type: "text"; text: string }[];
};

async function answer(run: () => Promise<unknown>): Promise<ToolResult> {
	try {
		const result = await run();

		return {
			content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
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

async function developmenti(
	fetcher: FetchLike,
	input: {
		method: "GET" | "POST";
		path: string;
		body?: string;
		content_type?: string;
	},
) {
	const { origin, timeoutMs, maxChars } = DA_OUTREACH.developmenti;
	const url = new URL(input.path, origin);

	if (url.origin !== origin) {
		throw new Error("Only developmenti.brisbane.qld.gov.au is allowed.");
	}

	const response = await fetcher(url.toString(), {
		method: input.method,
		headers: {
			accept: "application/json, text/html;q=0.9",
			...(input.body
				? { "content-type": input.content_type ?? "application/json" }
				: {}),
		},
		body: input.method === "POST" ? (input.body ?? "") : undefined,
		signal: AbortSignal.timeout(timeoutMs),
	});
	const type = response.headers.get("content-type") ?? "";

	if (!/json|text|xml/.test(type)) {
		return {
			status: response.status,
			content_type: type,
			note: "Binary content is not returned.",
		};
	}

	const text = await response.text();

	return {
		status: response.status,
		content_type: type,
		truncated: text.length > maxChars,
		text: text.slice(0, maxChars),
	};
}

export function buildServer(crm: Crm, fetcher: FetchLike = fetch): McpServer {
	const server = new McpServer(DA_OUTREACH.server);

	server.registerTool(
		"crm_ensure_fields",
		{
			description:
				"Creates the custom CONTACT and DEAL fields the DA flow needs, with agentFilled=false. Idempotent.",
			inputSchema: {},
		},
		() => answer(() => ops.ensureFields(crm)),
	);

	server.registerTool(
		"crm_find_contact",
		{
			description:
				"Finds a contact by kairon_lead_id, LinkedIn URL or email. last_name narrows the search. Returns null when there is none.",
			inputSchema: {
				kairon_lead_id: z.string().optional(),
				linkedin_url: z.string().optional(),
				email: z.string().optional(),
				last_name: z.string().optional(),
			},
		},
		(args) => answer(() => ops.findContact(crm, args)),
	);

	server.registerTool(
		"crm_get_contact",
		{
			description:
				"A contact with its custom fields (kairon_lead_id, real_company, project_da) and the deals it is on.",
			inputSchema: { id: z.string().min(1) },
		},
		(args) => answer(() => ops.getContact(crm, args.id)),
	);

	server.registerTool(
		"crm_find_deal",
		{
			description:
				"Finds the deal of a DA by its da_number. Returns null when there is none. Call it before creating.",
			inputSchema: { da_number: z.string().min(1) },
		},
		(args) => answer(() => ops.findDealByDa(crm, args.da_number)),
	);

	server.registerTool(
		"crm_get_deal",
		{
			description:
				"A deal with its custom fields (whos_who, companies_involved, next_step, kairon_campaign_id), contacts and roles.",
			inputSchema: { id: z.string().min(1) },
		},
		(args) => answer(() => ops.getDeal(crm, args.id)),
	);

	server.registerTool(
		"crm_list_da_deals",
		{
			description:
				"Lists the deals that are DA projects (they have da_number), with fields and contacts.",
			inputSchema: {},
		},
		() => answer(() => ops.listDaDeals(crm)),
	);

	server.registerTool(
		"crm_upsert_project",
		{
			description:
				"Idempotent load of one DA project: companies, the deal, contacts under the developer company with real_company, custom fields, and the research sheet as a note.",
			inputSchema: {
				project: projectInput,
				ficha_md: z.string().optional(),
				kairon_list_url: z.string().optional(),
				kairon_campaign_id: z.string().optional(),
			},
		},
		(args) => answer(() => ops.upsertProject(crm, args)),
	);

	server.registerTool(
		"crm_add_contact_to_deal",
		{
			description:
				"Creates or reuses a contact under the deal's company, with real_company, and attaches it to the deal with its role.",
			inputSchema: { deal_id: z.string().min(1), person: personInput },
		},
		(args) =>
			answer(() => ops.addContactToDeal(crm, args.deal_id, args.person)),
	);

	server.registerTool(
		"crm_set_deal_fields",
		{
			description:
				"Sets custom fields on a deal, for example kairon_campaign_id, next_step or kairon_list.",
			inputSchema: { deal_id: z.string().min(1), fields: fieldValuesInput },
		},
		(args) => answer(() => ops.setDealFields(crm, args.deal_id, args.fields)),
	);

	server.registerTool(
		"crm_list_activities",
		{
			description: "The latest activities of a deal or a contact.",
			inputSchema: {
				deal_id: z.string().optional(),
				contact_id: z.string().optional(),
			},
		},
		(args) =>
			answer(() =>
				ops.listActivities(crm, {
					dealId: args.deal_id,
					contactId: args.contact_id,
				}),
			),
	);

	server.registerTool(
		"crm_log_activity",
		{
			description:
				"Logs an activity. Use EMAIL for a reply that came by email and NOTE for LinkedIn or a plain note.",
			inputSchema: {
				type: z.enum(["NOTE", "CALL", "EMAIL", "MEETING"]),
				subject: z.string().optional(),
				body: z.string().optional(),
				contact_id: z.string().optional(),
				deal_id: z.string().optional(),
				company_id: z.string().optional(),
				occurred_at: z.string().optional(),
			},
		},
		(args) =>
			answer(() =>
				ops.logActivity(crm, {
					type: args.type,
					subject: args.subject,
					body: args.body,
					contactId: args.contact_id,
					dealId: args.deal_id,
					companyId: args.company_id,
					occurredAt: args.occurred_at,
				}),
			),
	);

	server.registerTool(
		"crm_create_task",
		{
			description: "Creates a task with a due date (ISO 8601).",
			inputSchema: {
				subject: z.string().min(1),
				due_at: z.string(),
				body: z.string().optional(),
				deal_id: z.string().optional(),
				contact_id: z.string().optional(),
			},
		},
		(args) =>
			answer(() =>
				ops.logActivity(crm, {
					type: "TASK",
					subject: args.subject,
					body: args.body,
					dueAt: args.due_at,
					dealId: args.deal_id,
					contactId: args.contact_id,
				}),
			),
	);

	server.registerTool(
		"crm_set_stage",
		{
			description:
				"Moves a deal to a stage. Give closed_reason with CLOSED_LOST.",
			inputSchema: {
				deal_id: z.string().min(1),
				stage: stageInput,
				closed_reason: z.string().optional(),
			},
		},
		(args) =>
			answer(() =>
				ops.setStage(crm, args.deal_id, args.stage, args.closed_reason),
			),
	);

	server.registerTool(
		"developmenti_request",
		{
			description:
				"One HTTP request to Brisbane Development.i, that host only. Returns status and text (JSON or HTML). PDFs are not returned.",
			inputSchema: {
				method: z.enum(["GET", "POST"]),
				path: z.string().startsWith("/"),
				body: z.string().optional(),
				content_type: z.string().optional(),
			},
		},
		(args) => answer(() => developmenti(fetcher, args)),
	);

	return server;
}
