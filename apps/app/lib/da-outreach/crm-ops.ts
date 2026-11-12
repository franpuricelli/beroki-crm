import { DA_OUTREACH, REQUIRED_FIELDS } from "./config";
import { type Crm, CrmError } from "./crm-client";
import {
	type CompanyInput,
	crmCompanyList,
	crmContactDetail,
	crmContactList,
	crmCreated,
	crmDealDetail,
	crmDealList,
	crmFieldDefinitions,
	crmTimeline,
	type FieldValues,
	type PersonInput,
	type ProjectInput,
} from "./schemas";

type FieldValue = string | number | boolean | null;

type ContactQuery = {
	kairon_lead_id?: string | null;
	linkedin_url?: string | null;
	email?: string | null;
	last_name?: string | null;
};

type ContactFacts = {
	email: string | null;
	linkedinUrl: string | null;
	fields: Record<string, FieldValue>;
};

type ActivityInput = {
	type: "NOTE" | "CALL" | "EMAIL" | "MEETING" | "TASK";
	subject?: string;
	body?: string;
	contactId?: string;
	dealId?: string;
	companyId?: string;
	occurredAt?: string;
	dueAt?: string;
};

const CONFLICT = 409;

function norm(value: FieldValue | undefined): string {
	return String(value ?? "")
		.trim()
		.toLowerCase();
}

function normLinkedin(url: string | null | undefined): string {
	return norm(url)
		.replace(/^https?:\/\//, "")
		.replace(/^www\./, "")
		.replace(/[?#].*$/, "")
		.replace(/\/+$/, "");
}

function byKey(
	fields: { key: string; value: FieldValue }[],
): Record<string, FieldValue> {
	return Object.fromEntries(fields.map((field) => [field.key, field.value]));
}

function present<Value>(
	input: Record<string, Value | null | undefined>,
): Record<string, Value> {
	const out: Record<string, Value> = {};

	for (const [key, value] of Object.entries(input)) {
		if (value !== undefined && value !== null && value !== "") out[key] = value;
	}

	return out;
}

function longestWord(text: string): string {
	return (
		text.split(/[^\p{L}\p{N}.@-]+/u).sort((a, b) => b.length - a.length)[0] ??
		""
	);
}

function searchBody(q: string, page = 1) {
	return { q, page, pageSize: DA_OUTREACH.crm.pageSize };
}

export async function ensureFields(crm: Crm) {
	const created: string[] = [];
	const existing: string[] = [];

	for (const entity of ["CONTACT", "DEAL"] as const) {
		const current = await crm.read(crmFieldDefinitions, "GET", "/fields", {
			query: { entity },
		});
		const keys = new Set(current.map((field) => field.key));

		for (const field of REQUIRED_FIELDS) {
			if (field.entity !== entity) continue;

			if (keys.has(field.key)) {
				existing.push(`${entity}.${field.key}`);
				continue;
			}

			await crm.send("POST", "/fields", {
				body: {
					entity,
					label: field.key,
					type: field.type,
					agentFilled: false,
				},
			});
			created.push(`${entity}.${field.key}`);
		}
	}

	return { created, existing };
}

async function findCompany(crm: Crm, company: CompanyInput) {
	const queries = [company.domain, longestWord(company.name)].filter(
		(query): query is string => Boolean(query),
	);

	for (const q of queries) {
		const { rows } = await crm.read(
			crmCompanyList,
			"POST",
			"/companies/search",
			{ body: searchBody(q) },
		);
		const hit = rows.find(
			(row) =>
				(company.domain && norm(row.domain) === norm(company.domain)) ||
				norm(row.name) === norm(company.name),
		);

		if (hit) return hit;
	}

	return null;
}

async function upsertCompany(crm: Crm, company: CompanyInput) {
	const found = await findCompany(crm, company);
	const row =
		found ??
		(await crm.read(crmCreated, "POST", "/companies", {
			body: present({
				name: company.name,
				domain: company.domain,
				ownerId: crm.ownerId,
			}),
		}));
	const data = present({
		website:
			company.website ?? (company.domain ? `https://${company.domain}` : null),
		linkedinUrl: company.linkedin,
	});

	if (Object.keys(data).length > 0) {
		await crm.send("PATCH", `/companies/${row.id}`, { body: { data } });
	}

	return { id: row.id, name: company.name, created: !found };
}

function matchContact(
	contact: ContactFacts,
	query: ContactQuery,
): string | null {
	if (
		query.kairon_lead_id &&
		norm(contact.fields.kairon_lead_id) === norm(query.kairon_lead_id)
	) {
		return "kairon_lead_id";
	}

	if (
		query.linkedin_url &&
		contact.linkedinUrl &&
		normLinkedin(contact.linkedinUrl) === normLinkedin(query.linkedin_url)
	) {
		return "linkedin_url";
	}

	if (query.email && norm(contact.email) === norm(query.email)) return "email";

	return null;
}

async function contactCandidates(crm: Crm, query: ContactQuery) {
	const ids = new Map<string, ContactFacts>();
	const queries = [
		query.email,
		query.last_name ? longestWord(query.last_name) : null,
	].filter((item): item is string => Boolean(item));
	const collect = async (q: string, page: number) => {
		const result = await crm.read(crmContactList, "POST", "/contacts/search", {
			body: searchBody(q, page),
		});

		for (const row of result.rows) {
			ids.set(row.id, {
				email: row.email,
				linkedinUrl: null,
				fields: row.fields,
			});
		}

		return result.total;
	};

	if (queries.length > 0) {
		for (const q of queries) await collect(q, 1);

		return ids;
	}

	for (let page = 1; page <= DA_OUTREACH.crm.maxPages; page++) {
		const total = await collect("", page);

		if (page * DA_OUTREACH.crm.pageSize >= total) break;
	}

	return ids;
}

export async function getContact(crm: Crm, id: string) {
	const contact = await crm.read(crmContactDetail, "GET", `/contacts/${id}`);

	return {
		id: contact.id,
		name: `${contact.firstName} ${contact.lastName ?? ""}`.trim(),
		email: contact.email,
		phone: contact.phone,
		title: contact.title,
		linkedinUrl: contact.linkedinUrl,
		company: contact.company,
		fields: byKey(contact.fields),
		deals: contact.deals,
	};
}

export async function findContact(crm: Crm, query: ContactQuery) {
	const candidates = await contactCandidates(crm, query);

	for (const [id, facts] of candidates) {
		const matchedBy = matchContact(facts, query);

		if (matchedBy)
			return { matched_by: matchedBy, ...(await getContact(crm, id)) };
	}

	const ids = [...candidates.keys()].slice(0, DA_OUTREACH.crm.detailLookups);

	for (const id of ids) {
		const contact = await getContact(crm, id);
		const matchedBy = matchContact(contact, query);

		if (matchedBy) return { matched_by: matchedBy, ...contact };
	}

	return null;
}

async function upsertContact(
	crm: Crm,
	person: PersonInput,
	companyId: string,
	da: string | null,
) {
	const found = await findContact(crm, {
		kairon_lead_id: person.kairon_lead_id,
		linkedin_url: person.linkedin,
		email: person.email,
		last_name: person.last_name,
	});
	const id =
		found?.id ??
		(
			await crm.read(crmCreated, "POST", "/contacts", {
				body: present({
					firstName: person.first_name,
					lastName: person.last_name,
					title: person.title,
					email: person.email,
					phone: person.phone,
					companyId,
					ownerId: crm.ownerId,
				}),
			})
		).id;
	const fields: FieldValues = present({
		kairon_lead_id: person.kairon_lead_id,
		real_company: person.company,
		project_da: da,
	});

	await crm.send("PATCH", `/contacts/${id}`, {
		body: {
			data: {
				...present({
					linkedinUrl: person.linkedin,
					email: found ? person.email : null,
					phone: found ? person.phone : null,
				}),
				fields,
			},
		},
	});

	return {
		id,
		name: `${person.first_name} ${person.last_name ?? ""}`.trim(),
		created: !found,
	};
}

export async function getDeal(crm: Crm, id: string) {
	const deal = await crm.read(crmDealDetail, "GET", `/deals/${id}`);

	return {
		id: deal.id,
		name: deal.name,
		stage: deal.stage,
		description: deal.description,
		closedReason: deal.closedReason,
		company: deal.company,
		fields: byKey(deal.fields),
		contacts: deal.contacts.map((contact) => ({
			id: contact.id,
			name: `${contact.firstName} ${contact.lastName ?? ""}`.trim(),
			email: contact.email,
			title: contact.title,
			role: contact.role,
		})),
	};
}

export async function findDealByDa(crm: Crm, da: string) {
	const { rows } = await crm.read(crmDealList, "POST", "/deals/search", {
		body: searchBody(da),
	});

	for (const row of rows) {
		const deal = await getDeal(crm, row.id);

		if (norm(deal.fields.da_number) === norm(da)) return deal;
	}

	return null;
}

export async function listDaDeals(crm: Crm) {
	const deals = [];

	for (let page = 1; page <= DA_OUTREACH.crm.maxPages; page++) {
		const { rows, total } = await crm.read(
			crmDealList,
			"POST",
			"/deals/search",
			{ body: searchBody("", page) },
		);

		for (const row of rows) {
			if (!row.fields.da_number && !/\bDA\b/.test(row.name)) continue;

			const deal = await getDeal(crm, row.id);

			if (deal.fields.da_number) deals.push(deal);
		}

		if (page * DA_OUTREACH.crm.pageSize >= total) break;
	}

	return deals;
}

async function attachContact(
	crm: Crm,
	dealId: string,
	contactId: string,
	role: string | null | undefined,
) {
	const deal = await getDeal(crm, dealId);

	if (deal.contacts.some((contact) => contact.id === contactId)) {
		return { attached: false };
	}

	try {
		await crm.send("POST", `/deals/${dealId}/contacts`, {
			body: present({ contactId, role }),
		});
	} catch (error) {
		if (error instanceof CrmError && error.status === CONFLICT) {
			return { attached: false };
		}

		throw error;
	}

	return { attached: true };
}

export async function addContactToDeal(
	crm: Crm,
	dealId: string,
	person: PersonInput,
) {
	const deal = await getDeal(crm, dealId);
	const da = deal.fields.da_number;
	const contact = await upsertContact(
		crm,
		person,
		deal.company.id,
		typeof da === "string" ? da : null,
	);
	const link = await attachContact(
		crm,
		dealId,
		contact.id,
		person.role_on_deal,
	);

	return { ...contact, ...link };
}

export async function listActivities(
	crm: Crm,
	where: { dealId?: string; contactId?: string },
) {
	const { entries } = await crm.read(crmTimeline, "GET", "/activities", {
		query: { dealId: where.dealId, contactId: where.contactId },
	});

	return entries;
}

export async function logActivity(crm: Crm, input: ActivityInput) {
	const { id } = await crm.read(crmCreated, "POST", "/activities", {
		body: present(input),
	});

	return { id };
}

export async function setDealFields(
	crm: Crm,
	dealId: string,
	fields: FieldValues,
) {
	await crm.send("PATCH", `/deals/${dealId}`, { body: { data: { fields } } });

	return { ok: true };
}

export async function setStage(
	crm: Crm,
	dealId: string,
	stage: string,
	closedReason: string | undefined,
) {
	await crm.send("PATCH", `/deals/${dealId}/stage`, {
		body: present({ stage, closedReason }),
	});

	return { ok: true, stage };
}

function companiesInvolved(project: ProjectInput): string {
	return project.companies
		.map((company) => {
			const reason = company.why ? `: ${company.why}` : "";
			const source = company.source ? ` ${company.source}` : "";

			return `${company.name} — ${company.role} (${company.confidence}${reason})${source}`;
		})
		.join("\n");
}

export async function upsertProject(
	crm: Crm,
	input: {
		project: ProjectInput;
		ficha_md?: string;
		kairon_list_url?: string;
		kairon_campaign_id?: string;
	},
) {
	const { project } = input;
	const developer =
		project.companies.find((company) => norm(company.role) === "developer") ??
		project.companies[0];

	if (!developer) throw new Error("The project needs a developer company.");

	const companies = [];

	for (const company of project.companies) {
		companies.push({
			...(await upsertCompany(crm, company)),
			role: company.role,
		});
	}

	const developerId = companies.find(
		(company) => company.name === developer.name,
	)?.id;

	if (!developerId) throw new Error("The developer company was not saved.");

	const existing = await findDealByDa(crm, project.da);
	const dealId =
		existing?.id ??
		(
			await crm.read(crmCreated, "POST", "/deals", {
				body: {
					name: `${project.project} – DA ${project.da}`,
					companyId: developerId,
					ownerId: crm.ownerId,
				},
			})
		).id;
	const units = project.units ? ` — ${project.units} units` : "";
	const fields: FieldValues = present({
		da_number: project.da,
		address: project.address,
		decision: project.decision
			? [project.decision.status, project.decision.date]
					.filter(Boolean)
					.join(" ")
			: null,
		units: project.units,
		da_record: project.da_url,
		kairon_list: input.kairon_list_url,
		kairon_campaign_id: input.kairon_campaign_id,
		companies_involved: companiesInvolved(project),
		whos_who: project.whos_who,
	});

	await crm.send("PATCH", `/deals/${dealId}`, {
		body: {
			data: {
				description: `${project.project} — ${project.address}${units}`,
				fields,
			},
		},
	});

	const contacts = [];

	for (const person of project.people) {
		const contact = await upsertContact(crm, person, developerId, project.da);
		const link = await attachContact(
			crm,
			dealId,
			contact.id,
			person.role_on_deal,
		);

		contacts.push({ ...contact, ...link });
	}

	const subject = `Research DA ${project.da}`;
	let noteCreated = false;

	if (input.ficha_md) {
		const activities = await listActivities(crm, { dealId });

		if (!activities.some((activity) => activity.subject === subject)) {
			await logActivity(crm, {
				type: "NOTE",
				subject,
				body: input.ficha_md,
				dealId,
			});
			noteCreated = true;
		}
	}

	return {
		deal: { id: dealId, created: !existing },
		companies,
		contacts,
		note_created: noteCreated,
	};
}
