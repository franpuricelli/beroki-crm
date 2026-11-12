import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";
import type { Crm, FetchLike } from "../crm/client.js";
import * as ops from "../crm/ops.js";

const DEVELOPMENTI = "https://developmenti.brisbane.qld.gov.au";
const STAGES = ["DEMO_BOOKED", "QUALIFIED_TO_BUY", "DECISION_MAKER_BOUGHT_IN", "CONTRACT_SENT", "CLOSED_WON", "CLOSED_LOST", "UNQUALIFIED_TO_BUY"] as const;

const confidence = z.enum(["confirmed", "inferred"]);
const person = z.object({
	first_name: z.string().min(1),
	last_name: z.string().nullish(),
	company: z.string().min(1).describe("Empresa donde trabaja de verdad (va a real_company)"),
	title: z.string().nullish(),
	role_on_deal: z.string().max(80).nullish(),
	linkedin: z.string().nullish(),
	email: z.string().nullish(),
	phone: z.string().nullish(),
	kairon_lead_id: z.string().nullish(),
	confidence: confidence.optional(),
	why: z.string().nullish(),
	source: z.string().nullish(),
});
const project = z.object({
	da: z.string().min(1),
	council: z.string().optional(),
	project: z.string().min(1),
	address: z.string().min(1),
	units: z.number().nullish(),
	decision: z.object({ status: z.string(), date: z.string().nullish() }).optional(),
	da_url: z.string().nullish(),
	companies: z.array(z.object({
		name: z.string().min(1),
		role: z.string().min(1),
		domain: z.string().nullish(),
		linkedin: z.string().nullish(),
		website: z.string().nullish(),
		confidence,
		why: z.string().nullish(),
		source: z.string().nullish(),
	})).min(1),
	people: z.array(person),
	whos_who: z.string().optional(),
});

export function buildServer(crm: Crm, fetcher: FetchLike = fetch): McpServer {
	const server = new McpServer({ name: "da-outreach-crm", version: "0.1.0" });
	const tool = <Shape extends z.ZodRawShape>(
		name: string,
		description: string,
		inputSchema: Shape,
		run: (args: z.infer<z.ZodObject<Shape>>) => Promise<unknown>,
	) =>
		server.registerTool(name, { description, inputSchema }, (async (args: unknown) => {
			try {
				const result = await run(args as z.infer<z.ZodObject<Shape>>);
				return { content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }] };
			} catch (error) {
				return { isError: true, content: [{ type: "text" as const, text: error instanceof Error ? error.message : String(error) }] };
			}
		}) as never);

	tool("crm_ensure_fields", "Crea en el CRM los campos propios que falten (CONTACT y DEAL), con agentFilled=false. Idempotente.", {}, () => ops.ensureFields(crm));

	tool("crm_find_contact", "Busca un contacto por kairon_lead_id, LinkedIn o email (con apellido como pista de búsqueda). Devuelve null si no existe.", {
		kairon_lead_id: z.string().optional(),
		linkedin_url: z.string().optional(),
		email: z.string().optional(),
		last_name: z.string().optional(),
	}, (args) => ops.findContact(crm, args));

	tool("crm_find_deal", "Busca el Deal de un DA por número (campo da_number o nombre). Devuelve null si no existe. Usar antes de crear.", { da_number: z.string().min(1) }, (args) => ops.findDealByDa(crm, args.da_number));

	tool("crm_get_deal", "Deal con campos (whos_who, companies_involved, next_step, kairon_campaign_id...), contactos y roles.", { id: z.string().min(1) }, (args) => ops.getDeal(crm, args.id));

	tool("crm_list_da_deals", "Lista los Deals que son proyectos de DA (tienen da_number), con sus campos y contactos.", {}, () => ops.listDaDeals(crm));

	tool("crm_upsert_project", "Carga idempotente de un proyecto (formato estándar 6.1): empresas, Deal, contactos bajo la empresa del developer con real_company, campos y la ficha como nota.", {
		project,
		ficha_md: z.string().optional().describe("Ficha .md completa; se guarda una sola vez como nota 'Research DA <número>'"),
		kairon_list_url: z.string().optional(),
		kairon_campaign_id: z.string().optional(),
	}, (args) => ops.upsertProject(crm, args as never));

	tool("crm_add_contact_to_deal", "Crea (o reutiliza) un contacto bajo la empresa del Deal, con real_company, y lo suma al Deal con su rol.", { deal_id: z.string().min(1), person }, (args) => ops.addContactToDeal(crm, args.deal_id, args.person as never));

	tool("crm_set_deal_fields", "Actualiza campos propios del Deal (p. ej. kairon_campaign_id, next_step, kairon_list).", {
		deal_id: z.string().min(1),
		fields: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])),
	}, async (args) => {
		await crm.request("PATCH", `/deals/${args.deal_id}`, { body: { data: { fields: args.fields } } });
		return { ok: true };
	});

	tool("crm_list_activities", "Últimas Activities de un Deal o de un contacto.", {
		deal_id: z.string().optional(),
		contact_id: z.string().optional(),
		limit: z.number().int().min(1).max(100).optional(),
	}, (args) => ops.listActivities(crm, { dealId: args.deal_id, contactId: args.contact_id, limit: args.limit }));

	tool("crm_log_activity", "Registra una Activity. EMAIL si la respuesta llegó por email; NOTE si fue por LinkedIn o es una nota.", {
		type: z.enum(["NOTE", "CALL", "EMAIL", "MEETING"]),
		subject: z.string().optional(),
		body: z.string().optional(),
		contact_id: z.string().optional(),
		deal_id: z.string().optional(),
		company_id: z.string().optional(),
		occurred_at: z.string().optional().describe("ISO 8601"),
	}, (args) => ops.logActivity(crm, { type: args.type, subject: args.subject, body: args.body, contactId: args.contact_id, dealId: args.deal_id, companyId: args.company_id, occurredAt: args.occurred_at }));

	tool("crm_create_task", "Crea una tarea (Activity TASK) con vencimiento.", {
		subject: z.string().min(1),
		due_at: z.string().describe("ISO 8601"),
		body: z.string().optional(),
		deal_id: z.string().optional(),
		contact_id: z.string().optional(),
	}, (args) => ops.logActivity(crm, { type: "TASK", subject: args.subject, body: args.body, dueAt: args.due_at, dealId: args.deal_id, contactId: args.contact_id }));

	tool("crm_set_stage", "Cambia el stage del Deal. closed_reason es obligatorio en la práctica para CLOSED_LOST.", {
		deal_id: z.string().min(1),
		stage: z.enum(STAGES),
		closed_reason: z.string().optional(),
	}, async (args) => {
		await crm.request("PATCH", `/deals/${args.deal_id}/stage`, { body: { stage: args.stage, ...(args.closed_reason ? { closedReason: args.closed_reason } : {}) } });
		return { ok: true, stage: args.stage };
	});

	tool("developmenti_request", "Pedido HTTP a Development.i de Brisbane (solo ese host). Devuelve status y texto (JSON/HTML, hasta 60 kB). Los PDF no se devuelven: abrirlos con un browser.", {
		method: z.enum(["GET", "POST"]),
		path: z.string().startsWith("/").describe("Ruta con query, p. ej. /DocumentSearch/GetResult?searchText=&datefile=&applicationId=A006971478&isSubCategory=false"),
		body: z.string().optional(),
		content_type: z.string().optional(),
	}, async (args) => {
		const url = new URL(args.path, DEVELOPMENTI);
		if (url.origin !== DEVELOPMENTI) throw new Error("Solo se permite developmenti.brisbane.qld.gov.au");
		const response = await fetcher(url.toString(), {
			method: args.method,
			headers: { accept: "application/json, text/html;q=0.9", ...(args.body ? { "content-type": args.content_type ?? "application/json" } : {}) },
			body: args.method === "POST" ? (args.body ?? "") : undefined,
			signal: AbortSignal.timeout(25_000),
		});
		const type = response.headers.get("content-type") ?? "";
		if (!/json|text|xml/.test(type)) return { status: response.status, content_type: type, note: "Contenido binario: no se devuelve." };
		const text = await response.text();
		return { status: response.status, content_type: type, truncated: text.length > 60_000, text: text.slice(0, 60_000) };
	});

	return server;
}
