import { describe, expect, test } from "bun:test";
import type { FetchLike } from "../lib/da-outreach/crm-client";
import { handleMcp } from "../lib/da-outreach/mcp-http";

type Row = Record<string, string | number | boolean | null>;

type Stored = { id: string; values: Row; fields: Row };

const API_KEY = "crm_test_key_0000000000";
const API_URL = "https://crm-api.test";

const PROJECT = {
	da: "A000000001",
	council: "Brisbane City Council",
	project: "Sample Tower",
	address: "1 Sample St, South Brisbane QLD 4101",
	units: 97,
	decision: { status: "Approved", date: "2026-11-02" },
	da_url: "https://developmenti.brisbane.qld.gov.au/x",
	companies: [
		{
			name: "Sampleco",
			role: "developer",
			domain: "sampleco.test",
			confidence: "inferred",
			why: "same address on the developer site",
		},
		{ name: "Planning Partners", role: "planner", confidence: "confirmed" },
	],
	people: [
		{
			first_name: "Sample",
			last_name: "Person",
			company: "Sampleco",
			title: "Managing Director",
			role_on_deal: "Developer – decision maker",
			linkedin: "https://www.linkedin.com/in/sample-person",
			kairon_lead_id: "lead_sample0000000000000000001",
			confidence: "confirmed",
		},
		{
			first_name: "Second",
			last_name: "Planner",
			company: "Planning Partners",
			role_on_deal: "Planner",
			kairon_lead_id: "lead_sample0000000000000000002",
			confidence: "confirmed",
		},
	],
	whos_who: "Sampleco develops. Planning Partners is the planner.",
};

function fakeCrm(userIds = ["user_1"]) {
	let sequence = 0;
	const nextId = (prefix: string) => `${prefix}_${++sequence}`;
	const tables: Record<string, Stored[]> = {
		companies: [],
		contacts: [],
		deals: [],
		activities: [],
	};
	const definitions: { entity: string; key: string; agentFilled: boolean }[] =
		[];
	const links: { dealId: string; contactId: string; role: string | null }[] =
		[];
	const json = (data: unknown, status = 200) =>
		new Response(JSON.stringify(data), {
			status,
			headers: { "content-type": "application/json" },
		});
	const fieldArray = (entity: string, fields: Row) =>
		definitions
			.filter((definition) => definition.entity === entity)
			.map((definition) => ({
				key: definition.key,
				value: fields[definition.key] ?? null,
			}));
	const find = (table: string, id: string) =>
		tables[table]?.find((item) => item.id === id);
	const text = (stored: Stored, key: string) =>
		typeof stored.values[key] === "string" ? stored.values[key] : null;
	const contactView = (contact: Stored) => ({
		id: contact.id,
		firstName: text(contact, "firstName") ?? "",
		lastName: text(contact, "lastName"),
		email: text(contact, "email"),
		phone: text(contact, "phone"),
		title: text(contact, "title"),
		linkedinUrl: text(contact, "linkedinUrl"),
	});
	const companyView = (id: string | null) => {
		const company = id ? find("companies", id) : undefined;

		return company
			? {
					id: company.id,
					name: text(company, "name") ?? "",
					domain: text(company, "domain"),
				}
			: null;
	};

	const fetcher: FetchLike = async (input, init) => {
		const url = new URL(input);
		const method = init?.method ?? "GET";
		const path = url.pathname.replace(/^\/rest/, "");
		const headers = new Headers(init?.headers);
		const body = init?.body ? JSON.parse(String(init.body)) : {};

		if (headers.get("x-api-key") !== API_KEY) {
			return json({ message: "unauthorized" }, 401);
		}

		if (method === "GET" && path === "/users") {
			return json(
				userIds.map((id) => ({
					id,
					name: "Owner",
					email: "owner@crm.test",
					image: null,
				})),
			);
		}

		if (method === "GET" && path === "/fields") {
			return json(
				definitions.filter(
					(definition) => definition.entity === url.searchParams.get("entity"),
				),
			);
		}

		if (method === "POST" && path === "/fields") {
			definitions.push({
				entity: body.entity,
				key: body.label,
				agentFilled: body.agentFilled,
			});

			return json({ key: body.label });
		}

		if (method === "POST" && path === "/activities") {
			const activity = { id: nextId("act"), values: body, fields: {} };
			tables.activities?.push(activity);

			return json({ id: activity.id });
		}

		if (method === "GET" && path === "/activities") {
			const dealId = url.searchParams.get("dealId");
			const contactId = url.searchParams.get("contactId");

			return json({
				entries: (tables.activities ?? [])
					.filter(
						(activity) =>
							(!dealId || activity.values.dealId === dealId) &&
							(!contactId || activity.values.contactId === contactId),
					)
					.map((activity) => ({
						id: activity.id,
						type: text(activity, "type") ?? "NOTE",
						subject: text(activity, "subject"),
						body: text(activity, "body"),
						occurredAt: text(activity, "occurredAt"),
						dueAt: text(activity, "dueAt"),
					})),
				nextCursor: null,
			});
		}

		const stage = path.match(/^\/deals\/([^/]+)\/stage$/);

		if (method === "PATCH" && stage?.[1]) {
			const deal = find("deals", stage[1]);

			if (deal) {
				deal.values.stage = body.stage;
				deal.values.closedReason = body.closedReason ?? null;
			}

			return json({ id: stage[1] });
		}

		const attach = path.match(/^\/deals\/([^/]+)\/contacts$/);

		if (method === "POST" && attach?.[1]) {
			links.push({
				dealId: attach[1],
				contactId: body.contactId,
				role: body.role ?? null,
			});

			return json({ ok: true });
		}

		for (const table of ["companies", "contacts", "deals"]) {
			const rows = tables[table] ?? [];

			if (method === "POST" && path === `/${table}/search`) {
				const q = String(body.q ?? "").toLowerCase();
				const hits = rows.filter(
					(row) =>
						!q ||
						Object.values(row.values).some((value) =>
							String(value ?? "")
								.toLowerCase()
								.includes(q),
						),
				);

				return json({
					rows: hits.map((row) => ({
						...(table === "contacts"
							? contactView(row)
							: {
									id: row.id,
									name: text(row, "name") ?? "",
									domain: text(row, "domain"),
								}),
						fields: {},
					})),
					total: hits.length,
				});
			}

			if (method === "POST" && path === `/${table}`) {
				const created = { id: nextId(table), values: body, fields: {} };
				rows.push(created);

				return json({ id: created.id });
			}

			const one = path.match(new RegExp(`^/${table}/([^/]+)$`));

			if (!one?.[1]) continue;

			const record = find(table, one[1]);

			if (!record) return json({ message: "not found" }, 404);

			if (method === "PATCH") {
				const { fields, ...rest } = body.data;
				Object.assign(record.values, rest);
				Object.assign(record.fields, fields ?? {});

				return json({ id: record.id });
			}

			if (table === "contacts") {
				return json({
					...contactView(record),
					company: companyView(text(record, "companyId")),
					fields: fieldArray("CONTACT", record.fields),
					deals: links
						.filter((link) => link.contactId === record.id)
						.map((link) => ({
							id: link.dealId,
							name: text(find("deals", link.dealId) ?? record, "name") ?? "",
						})),
				});
			}

			if (table === "deals") {
				return json({
					id: record.id,
					name: text(record, "name") ?? "",
					description: text(record, "description"),
					stage: text(record, "stage") ?? "QUALIFIED_TO_BUY",
					closedReason: text(record, "closedReason"),
					company: companyView(text(record, "companyId")),
					fields: fieldArray("DEAL", record.fields),
					contacts: links
						.filter((link) => link.dealId === record.id)
						.map((link) => {
							const contact = find("contacts", link.contactId);

							return contact
								? { ...contactView(contact), role: link.role }
								: null;
						})
						.filter(Boolean),
				});
			}
		}

		return json({ message: `no route ${method} ${path}` }, 404);
	};

	return { tables, definitions, links, fetcher };
}

function rpc(
	fake: ReturnType<typeof fakeCrm>,
	method: string,
	params: unknown,
	token = API_KEY,
	search = "",
) {
	return handleMcp(
		new Request(`https://crm.test/api/da-outreach/mcp/${token}${search}`, {
			method: "POST",
			headers: {
				"content-type": "application/json",
				accept: "application/json, text/event-stream",
			},
			body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
		}),
		{ apiUrl: API_URL, token, fetcher: fake.fetcher },
	);
}

async function call(
	fake: ReturnType<typeof fakeCrm>,
	name: string,
	args: unknown,
) {
	const response = await rpc(fake, "tools/call", { name, arguments: args });
	const body = await response.json();

	expect(body.result.isError).toBeUndefined();

	return JSON.parse(body.result.content[0].text);
}

describe("DA outreach MCP endpoint", () => {
	test("rejects a token the CRM does not accept", async () => {
		const fake = fakeCrm();

		expect(
			(await rpc(fake, "tools/list", {}, "wrong_key_000000000000")).status,
		).toBe(401);
		expect((await rpc(fake, "tools/list", {}, "short")).status).toBe(401);
	});

	test("asks for an owner when the CRM has several users", async () => {
		const fake = fakeCrm(["user_1", "user_2"]);

		expect((await rpc(fake, "tools/list", {})).status).toBe(400);
		expect(
			(await rpc(fake, "tools/list", {}, API_KEY, "?owner=user_2")).status,
		).toBe(200);
		expect(
			(await rpc(fake, "tools/list", {}, API_KEY, "?owner=user_9")).status,
		).toBe(400);
	});

	test("lists the tools", async () => {
		const body = await (await rpc(fakeCrm(), "tools/list", {})).json();
		const names = body.result.tools.map((tool: { name: string }) => tool.name);

		expect(names).toContain("crm_upsert_project");
		expect(names).toContain("crm_get_contact");
		expect(names).toContain("developmenti_request");
		expect(names).toHaveLength(14);
	});

	test("creates the custom fields once", async () => {
		const fake = fakeCrm();
		const first = await call(fake, "crm_ensure_fields", {});
		const second = await call(fake, "crm_ensure_fields", {});

		expect(first.created).toHaveLength(13);
		expect(second.created).toHaveLength(0);
		expect(fake.definitions.every((field) => !field.agentFilled)).toBe(true);
	});

	test("loads a project idempotently under the developer company", async () => {
		const fake = fakeCrm();
		await call(fake, "crm_ensure_fields", {});
		const input = { project: PROJECT, ficha_md: "# Sample Tower" };
		const first = await call(fake, "crm_upsert_project", input);
		const second = await call(fake, "crm_upsert_project", input);

		expect(first.deal.created).toBe(true);
		expect(second.deal.created).toBe(false);
		expect(second.deal.id).toBe(first.deal.id);
		expect(fake.tables.companies).toHaveLength(2);
		expect(fake.tables.deals).toHaveLength(1);
		expect(fake.tables.contacts).toHaveLength(2);
		expect(fake.links).toHaveLength(2);
		expect(fake.tables.activities).toHaveLength(1);

		const developerId = first.companies[0].id;

		expect(
			fake.tables.contacts?.every(
				(contact) => contact.values.companyId === developerId,
			),
		).toBe(true);

		const deal = await call(fake, "crm_get_deal", { id: first.deal.id });

		expect(deal.fields.da_number).toBe("A000000001");
		expect(deal.fields.units).toBe(97);
		expect(deal.fields.decision).toBe("Approved 2026-11-02");
		expect(deal.contacts[0].role).toBe("Developer – decision maker");
	});

	test("handles a reply: find the contact, log, task, stage", async () => {
		const fake = fakeCrm();
		await call(fake, "crm_ensure_fields", {});
		const loaded = await call(fake, "crm_upsert_project", { project: PROJECT });
		const dealId = loaded.deal.id;
		const contact = await call(fake, "crm_find_contact", {
			kairon_lead_id: "lead_sample0000000000000000002",
		});

		expect(contact.matched_by).toBe("kairon_lead_id");
		expect(contact.fields.real_company).toBe("Planning Partners");
		expect(contact.deals[0].id).toBe(dealId);
		expect(
			await call(fake, "crm_find_contact", { kairon_lead_id: "lead_none" }),
		).toBeNull();

		await call(fake, "crm_set_deal_fields", {
			deal_id: dealId,
			fields: { kairon_campaign_id: "camp_1" },
		});
		const added = await call(fake, "crm_add_contact_to_deal", {
			deal_id: dealId,
			person: {
				first_name: "Third",
				last_name: "Manager",
				company: "Sampleco",
				role_on_deal: "Development manager",
			},
		});

		expect(added.attached).toBe(true);

		await call(fake, "crm_log_activity", {
			type: "NOTE",
			subject: "LinkedIn reply",
			body: "kairon_message_id: msg_1",
			deal_id: dealId,
			contact_id: contact.id,
		});
		await call(fake, "crm_create_task", {
			subject: "Follow up",
			due_at: "2026-11-20",
			deal_id: dealId,
		});
		await call(fake, "crm_set_stage", {
			deal_id: dealId,
			stage: "CLOSED_LOST",
			closed_reason: "Not interested",
		});

		const deal = await call(fake, "crm_get_deal", { id: dealId });
		const activities = await call(fake, "crm_list_activities", {
			contact_id: contact.id,
		});

		expect(deal.stage).toBe("CLOSED_LOST");
		expect(deal.fields.kairon_campaign_id).toBe("camp_1");
		expect(deal.contacts).toHaveLength(3);
		expect(activities[0].body).toContain("msg_1");
	});

	test("refuses a Development.i path that leaves the host", async () => {
		const response = await rpc(fakeCrm(), "tools/call", {
			name: "developmenti_request",
			arguments: { method: "GET", path: "//evil.test/x" },
		});
		const body = await response.json();

		expect(body.result.isError).toBe(true);
	});
});
