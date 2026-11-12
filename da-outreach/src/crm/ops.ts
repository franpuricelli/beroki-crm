import { Crm, CrmError } from "./client.js";


export type ProjectCompany = {
	name: string;
	role: string;
	domain?: string | null;
	linkedin?: string | null;
	website?: string | null;
	confidence: "confirmed" | "inferred";
	why?: string | null;
	source?: string | null;
};

export type ProjectPerson = {
	first_name: string;
	last_name?: string | null;
	company: string;
	title?: string | null;
	role_on_deal?: string | null;
	linkedin?: string | null;
	email?: string | null;
	phone?: string | null;
	kairon_lead_id?: string | null;
	confidence?: "confirmed" | "inferred";
	why?: string | null;
	source?: string | null;
};

export type Project = {
	da: string;
	council?: string;
	project: string;
	address: string;
	units?: number | null;
	decision?: { status: string; date?: string | null };
	da_url?: string | null;
	companies: ProjectCompany[];
	people: ProjectPerson[];
	whos_who?: string;
};

type Row = Record<string, unknown> & { id: string };
type List = { rows: Row[]; total: number };

export const REQUIRED_FIELDS: { entity: "CONTACT" | "DEAL"; key: string; type: string }[] = [
	{ entity: "CONTACT", key: "kairon_lead_id", type: "TEXT" },
	{ entity: "CONTACT", key: "real_company", type: "TEXT" },
	{ entity: "CONTACT", key: "project_da", type: "TEXT" },
	{ entity: "DEAL", key: "da_number", type: "TEXT" },
	{ entity: "DEAL", key: "address", type: "TEXT" },
	{ entity: "DEAL", key: "decision", type: "TEXT" },
	{ entity: "DEAL", key: "units", type: "NUMBER" },
	{ entity: "DEAL", key: "da_record", type: "URL" },
	{ entity: "DEAL", key: "kairon_list", type: "URL" },
	{ entity: "DEAL", key: "companies_involved", type: "LONG_TEXT" },
	{ entity: "DEAL", key: "whos_who", type: "LONG_TEXT" },
	{ entity: "DEAL", key: "kairon_campaign_id", type: "TEXT" },
	{ entity: "DEAL", key: "next_step", type: "LONG_TEXT" },
];


const norm = (value: unknown) => String(value ?? "").trim().toLowerCase();

export function normLinkedin(url: unknown): string {
	return norm(url)
		.replace(/^https?:\/\//, "")
		.replace(/^www\./, "")
		.replace(/[?#].*$/, "")
		.replace(/\/+$/, "");
}

export function fieldMap(record: Record<string, unknown> | null | undefined): Record<string, unknown> {
	const fields = record?.fields;
	if (Array.isArray(fields)) {
		return Object.fromEntries(
			fields.map((field) => [String((field as Row).key), (field as Row).value ?? null]),
		);
	}
	return fields && typeof fields === "object" ? (fields as Record<string, unknown>) : {};
}

function clean<T extends Record<string, unknown>>(input: T): Partial<T> {
	return Object.fromEntries(
		Object.entries(input).filter(([, value]) => value !== undefined && value !== null && value !== ""),
	) as Partial<T>;
}

function oneWord(text: string): string {
	return text.split(/[^\p{L}\p{N}.@-]+/u).sort((a, b) => b.length - a.length)[0] ?? "";
}

async function search(crm: Crm, entity: "companies" | "contacts" | "deals", q: string, page = 1) {
	return crm.request<List>("POST", `/${entity}/search`, { body: { q, page, pageSize: 100 } });
}


export async function ensureFields(crm: Crm) {
	const created: string[] = [];
	const existing: string[] = [];
	for (const entity of ["CONTACT", "DEAL"] as const) {
		const current = await crm.request<Row[]>("GET", "/fields", { query: { entity } });
		const keys = new Set(current.map((field) => String(field.key)));
		for (const field of REQUIRED_FIELDS.filter((item) => item.entity === entity)) {
			if (keys.has(field.key)) {
				existing.push(`${entity}.${field.key}`);
				continue;
			}
			await crm.request("POST", "/fields", {
				body: { entity, label: field.key, type: field.type, agentFilled: false },
			});
			created.push(`${entity}.${field.key}`);
		}
	}
	return { created, existing };
}


export async function findCompany(crm: Crm, company: { name: string; domain?: string | null }) {
	const queries = [company.domain, oneWord(company.name)].filter(Boolean) as string[];
	for (const q of queries) {
		const { rows } = await search(crm, "companies", q);
		const hit = rows.find(
			(row) =>
				(company.domain && norm(row.domain) === norm(company.domain)) ||
				norm(row.name) === norm(company.name),
		);
		if (hit) return hit;
	}
	return null;
}

export async function upsertCompany(crm: Crm, company: ProjectCompany) {
	const found = await findCompany(crm, company);
	const row =
		found ??
		(await crm.request<Row>("POST", "/companies", {
			body: clean({ name: company.name, domain: company.domain ?? undefined, ownerId: crm.ownerId }),
		}));
	const data = clean({
		website: company.website ?? (company.domain ? `https://${company.domain}` : undefined),
		linkedinUrl: company.linkedin ?? undefined,
	});
	if (Object.keys(data).length) await crm.request("PATCH", `/companies/${row.id}`, { body: { data } });
	return { id: row.id, name: company.name, created: !found };
}


export type ContactQuery = {
	kairon_lead_id?: string | null;
	linkedin_url?: string | null;
	email?: string | null;
	last_name?: string | null;
};

function matchContact(record: Record<string, unknown>, query: ContactQuery): string | null {
	const fields = fieldMap(record);
	if (query.kairon_lead_id && norm(fields.kairon_lead_id) === norm(query.kairon_lead_id)) return "kairon_lead_id";
	if (query.linkedin_url && record.linkedinUrl && normLinkedin(record.linkedinUrl) === normLinkedin(query.linkedin_url)) return "linkedin_url";
	if (query.email && norm(record.email) === norm(query.email)) return "email";
	return null;
}

export async function findContact(crm: Crm, query: ContactQuery) {
	const candidates = new Map<string, Row>();
	const queries = [query.email, query.last_name ? oneWord(query.last_name) : null].filter(Boolean) as string[];
	if (queries.length) {
		for (const q of queries) for (const row of (await search(crm, "contacts", q)).rows) candidates.set(row.id, row);
	} else {
		for (let page = 1; page <= 5; page++) {
			const { rows, total } = await search(crm, "contacts", "", page);
			for (const row of rows) candidates.set(row.id, row);
			if (page * 100 >= total) break;
		}
	}
	for (const row of candidates.values()) {
		const onRow = matchContact(row, query);
		if (onRow) return { id: row.id, matched_by: onRow, contact: row };
	}
	for (const row of [...candidates.values()].slice(0, 40)) {
		const detail = await crm.request<Row>("GET", `/contacts/${row.id}`);
		const onDetail = matchContact(detail, query);
		if (onDetail) return { id: row.id, matched_by: onDetail, contact: detail };
	}
	return null;
}

export async function upsertContact(crm: Crm, person: ProjectPerson, companyId: string, da?: string) {
	const found = await findContact(crm, {
		kairon_lead_id: person.kairon_lead_id,
		linkedin_url: person.linkedin,
		email: person.email,
		last_name: person.last_name,
	});
	const id =
		found?.id ??
		(
			await crm.request<Row>("POST", "/contacts", {
				body: clean({
					firstName: person.first_name,
					lastName: person.last_name ?? undefined,
					title: person.title ?? undefined,
					email: person.email ?? undefined,
					phone: person.phone ?? undefined,
					companyId,
					ownerId: crm.ownerId,
				}),
			})
		).id;
	const data = clean({
		linkedinUrl: person.linkedin ?? undefined,
		email: found ? (person.email ?? undefined) : undefined,
		phone: found ? (person.phone ?? undefined) : undefined,
		fields: clean({
			kairon_lead_id: person.kairon_lead_id ?? undefined,
			real_company: person.company,
			project_da: da,
		}),
	});
	await crm.request("PATCH", `/contacts/${id}`, { body: { data } });
	return { id, name: `${person.first_name} ${person.last_name ?? ""}`.trim(), created: !found };
}


export async function getDeal(crm: Crm, id: string) {
	const deal = await crm.request<Row>("GET", `/deals/${id}`);
	const company = deal.company as Row | undefined;
	return {
		id: deal.id,
		name: deal.name,
		stage: deal.stage,
		description: deal.description ?? null,
		closedReason: deal.closedReason ?? null,
		company: company ? { id: company.id, name: company.name, domain: company.domain ?? null } : null,
		fields: fieldMap(deal),
		contacts: ((deal.contacts as Row[]) ?? []).map((contact) => ({
			id: contact.id,
			name: `${contact.firstName ?? ""} ${contact.lastName ?? ""}`.trim(),
			email: contact.email ?? null,
			title: contact.title ?? null,
			role: contact.role ?? null,
		})),
	};
}

export async function findDealByDa(crm: Crm, da: string) {
	const { rows } = await search(crm, "deals", da);
	for (const row of rows) {
		if (norm(fieldMap(row).da_number) === norm(da) || norm(row.name).includes(norm(da))) return getDeal(crm, row.id);
		const detail = await getDeal(crm, row.id);
		if (norm(detail.fields.da_number) === norm(da)) return detail;
	}
	return null;
}

export async function listDaDeals(crm: Crm) {
	const out = [];
	for (let page = 1; page <= 5; page++) {
		const { rows, total } = await search(crm, "deals", "DA", page);
		for (const row of rows) {
			const detail = await getDeal(crm, row.id);
			if (detail.fields.da_number) out.push(detail);
		}
		if (page * 100 >= total) break;
	}
	return out;
}

export async function attachContact(crm: Crm, dealId: string, contactId: string, role?: string | null) {
	const deal = await getDeal(crm, dealId);
	if (deal.contacts.some((contact) => contact.id === contactId)) return { attached: false };
	try {
		await crm.request("POST", `/deals/${dealId}/contacts`, { body: clean({ contactId, role: role ?? undefined }) });
	} catch (error) {
		if (error instanceof CrmError && error.status === 409) return { attached: false };
		throw error;
	}
	return { attached: true };
}

export async function addContactToDeal(crm: Crm, dealId: string, person: ProjectPerson) {
	const deal = await getDeal(crm, dealId);
	if (!deal.company) throw new Error("El Deal no tiene empresa.");
	const contact = await upsertContact(crm, person, deal.company.id, String(deal.fields.da_number ?? ""));
	const link = await attachContact(crm, dealId, contact.id, person.role_on_deal);
	return { ...contact, ...link };
}


export async function listActivities(crm: Crm, where: { dealId?: string; contactId?: string; limit?: number }) {
	const result = await crm.request<Record<string, unknown>>("GET", "/activities", {
		query: { dealId: where.dealId, contactId: where.contactId, limit: where.limit ?? 30 },
	});
	const items = (result.items ?? result.rows ?? result.activities ?? []) as Row[];
	return items.map((item) => ({
		id: item.id,
		type: item.type,
		subject: item.subject ?? null,
		body: item.body ?? null,
		occurredAt: item.occurredAt ?? item.createdAt ?? null,
		dueAt: item.dueAt ?? null,
	}));
}

export async function logActivity(
	crm: Crm,
	input: { type: "NOTE" | "CALL" | "EMAIL" | "MEETING" | "TASK"; subject?: string; body?: string; contactId?: string; dealId?: string; companyId?: string; occurredAt?: string; dueAt?: string },
) {
	const row = await crm.request<Row>("POST", "/activities", { body: clean(input) });
	return { id: row.id };
}


export async function upsertProject(
	crm: Crm,
	input: { project: Project; ficha_md?: string; kairon_list_url?: string; kairon_campaign_id?: string },
) {
	const { project } = input;
	const developer = project.companies.find((company) => norm(company.role) === "developer") ?? project.companies[0];
	if (!developer) throw new Error("El proyecto no tiene empresas: hace falta al menos el developer.");

	const companies = [];
	for (const company of project.companies) companies.push({ ...(await upsertCompany(crm, company)), role: company.role });
	const developerId = companies.find((company) => company.name === developer.name)!.id;

	const existing = await findDealByDa(crm, project.da);
	const dealId =
		existing?.id ??
		(
			await crm.request<Row>("POST", "/deals", {
				body: { name: `${project.project} – DA ${project.da}`, companyId: developerId, ownerId: crm.ownerId },
			})
		).id;

	const involved = project.companies
		.map((company) => `${company.name} — ${company.role} (${company.confidence}${company.why ? `: ${company.why}` : ""})${company.source ? ` ${company.source}` : ""}`)
		.join("\n");
	await crm.request("PATCH", `/deals/${dealId}`, {
		body: {
			data: {
				description: `${project.project} — ${project.address}${project.units ? ` — ${project.units} unidades` : ""}`,
				fields: clean({
					da_number: project.da,
					address: project.address,
					decision: project.decision ? [project.decision.status, project.decision.date].filter(Boolean).join(" ") : undefined,
					units: project.units ?? undefined,
					da_record: project.da_url ?? undefined,
					kairon_list: input.kairon_list_url,
					kairon_campaign_id: input.kairon_campaign_id,
					companies_involved: involved,
					whos_who: project.whos_who,
				}),
			},
		},
	});

	const contacts = [];
	for (const person of project.people) {
		const contact = await upsertContact(crm, person, developerId, project.da);
		const link = await attachContact(crm, dealId, contact.id, person.role_on_deal);
		contacts.push({ ...contact, ...link });
	}

	let note: { id: string } | null = null;
	const subject = `Research DA ${project.da}`;
	if (input.ficha_md) {
		const already = (await listActivities(crm, { dealId, limit: 100 })).some((activity) => activity.subject === subject);
		if (!already) note = await logActivity(crm, { type: "NOTE", subject, body: input.ficha_md, dealId });
	}

	return { deal: { id: dealId, created: !existing }, companies, contacts, note_created: Boolean(note) };
}
