import type { FetchLike } from "../src/crm/client.js";

/** CRM falso en memoria que imita las rutas REST usadas (formas tomadas de los contratos de trycompai/crm). */
export function fakeCrm() {
	let seq = 0;
	const id = (prefix: string) => `${prefix}_${++seq}`;
	const db = { companies: [] as any[], contacts: [] as any[], deals: [] as any[], activities: [] as any[], fields: [] as any[], links: [] as any[] };
	const calls: string[] = [];
	const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "content-type": "application/json" } });
	const fieldArray = (entity: string, values: Record<string, unknown>) => db.fields.filter((f) => f.entity === entity).map((f) => ({ ...f, value: values[f.key] ?? null }));
	const fetcher: FetchLike = async (input, init) => {
		const url = new URL(input);
		const method = init?.method ?? "GET";
		const path = url.pathname.replace(/^\/rest/, "");
		const body = init?.body ? JSON.parse(String(init.body)) : {};
		calls.push(`${method} ${path}`);
		if ((init?.headers as Record<string, string>)["x-api-key"] !== "crm_test") return json({ message: "unauthorized" }, 401);
		const m = (re: RegExp) => path.match(re);
		let x: RegExpMatchArray | null;
		if (method === "GET" && path === "/fields") return json(db.fields.filter((f) => f.entity === url.searchParams.get("entity")));
		if (method === "POST" && path === "/fields") { const f = { id: id("fld"), entity: body.entity, key: body.label.toLowerCase().replace(/[^a-z0-9]+/g, "_"), label: body.label, type: body.type, agentFilled: body.agentFilled }; db.fields.push(f); return json(f); }
		for (const entity of ["companies", "contacts", "deals"] as const) {
			if (method === "POST" && path === `/${entity}/search`) {
				const q = String(body.q ?? "").toLowerCase();
				// Como el CRM real: q busca texto en columnas básicas, no en campos custom.
				const rows = db[entity].filter((r) => !q || [r.name, r.domain, r.firstName, r.lastName, r.email].some((v) => String(v ?? "").toLowerCase().includes(q)));
				return json({ rows: rows.map((r) => ({ ...r, fields: {} })), total: rows.length, facetCounts: {} });
			}
			if (method === "POST" && path === `/${entity}`) { const r = { id: id(entity.slice(0, 3)), ...body, fieldValues: {} }; db[entity].push(r); return json(r); }
			if ((x = m(new RegExp(`^/${entity}/([^/]+)$`)))) {
				const r = db[entity].find((item) => item.id === x![1]);
				if (!r) return json({ message: "not found" }, 404);
				if (method === "PATCH") { const { fields, ...rest } = body.data; Object.assign(r, rest); Object.assign(r.fieldValues, fields ?? {}); }
				const entityName = entity === "deals" ? "DEAL" : entity === "contacts" ? "CONTACT" : "COMPANY";
				const out: any = { ...r, fields: fieldArray(entityName, r.fieldValues) };
				if (entity === "deals") { out.stage = r.stage ?? "QUALIFIED_TO_BUY"; out.company = db.companies.find((c) => c.id === r.companyId); out.contacts = db.links.filter((l) => l.dealId === r.id).map((l) => ({ ...db.contacts.find((c) => c.id === l.contactId), role: l.role ?? null })); }
				return json(out);
			}
		}
		if (method === "PATCH" && (x = m(/^\/deals\/([^/]+)\/stage$/))) { const d = db.deals.find((item) => item.id === x![1]); d.stage = body.stage; d.closedReason = body.closedReason ?? null; return json(d); }
		if (method === "POST" && (x = m(/^\/deals\/([^/]+)\/contacts$/))) { if (db.links.some((l) => l.dealId === x![1] && l.contactId === body.contactId)) return json({ message: "conflict" }, 409); db.links.push({ dealId: x[1], contactId: body.contactId, role: body.role }); return json({ ok: true }); }
		if (method === "POST" && path === "/activities") { const a = { id: id("act"), ...body }; db.activities.push(a); return json(a); }
		if (method === "GET" && path === "/activities") { const dealId = url.searchParams.get("dealId"); const contactId = url.searchParams.get("contactId"); return json({ items: db.activities.filter((a) => (!dealId || a.dealId === dealId) && (!contactId || a.contactId === contactId)), nextCursor: null }); }
		return json({ message: `no route ${method} ${path}` }, 404);
	};
	return { db, calls, fetcher };
}

export const MARRONE = {
	da: "A006971478",
	council: "Brisbane City Council",
	project: "Marrone",
	address: "37-39 Browning St, South Brisbane QLD 4101",
	units: 97,
	decision: { status: "Approved", date: "2026-11-02" },
	da_url: "https://developmenti.brisbane.qld.gov.au/Home/FilterDirect?filters=DANumber%3DA006971478",
	companies: [
		{ name: "Dalcott", role: "developer", domain: "dalcott.com.au", linkedin: "https://www.linkedin.com/company/dalcott/", confidence: "inferred", why: "same address, 97 units and architect on dalcott.com.au/projects/marrone", source: "https://www.dalcott.com.au/projects/marrone" },
		{ name: "Mewing Planning Consultants", role: "planner", confidence: "inferred", why: "headline de LinkedIn de Second Planner" },
	],
	people: [
		{ first_name: "Sample", last_name: "Person", company: "Dalcott", title: "Managing Director", role_on_deal: "Developer – decision maker", linkedin: "https://www.linkedin.com/in/sample-person", email: null, phone: null, kairon_lead_id: "lead_sample0000000000000000001", confidence: "confirmed", source: "https://www.dalcott.com.au/about" },
		{ first_name: "Second", last_name: "Planner", company: "Mewing Planning Consultants", title: "Associate Director", role_on_deal: "Planner", linkedin: "https://www.linkedin.com/in/second-planner", kairon_lead_id: "lead_sample0000000000000000002", confidence: "inferred", why: "rol en el DA inferido por su cargo" },
	],
	whos_who: "Dalcott desarrolla; Mewing es el planner.",
} as const;
