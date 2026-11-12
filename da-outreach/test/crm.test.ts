import assert from "node:assert/strict";
import { test } from "node:test";
import { Crm } from "../src/crm/client.js";
import * as ops from "../src/crm/ops.js";
import { handleMcp } from "../src/mcp/http.js";
import { fakeCrm, MARRONE } from "./helpers.js";

const TOKEN = "t".repeat(32);
const setup = () => {
	const fake = fakeCrm();
	return { ...fake, crm: new Crm("https://crm.test/rest", "crm_test", "owner_1", fake.fetcher) };
};

test("ensureFields crea los 13 campos una sola vez, con agentFilled=false", async () => {
	const { crm, db } = setup();
	const first = await ops.ensureFields(crm);
	assert.equal(first.created.length, 13);
	assert.ok(db.fields.every((field) => field.agentFilled === false));
	assert.deepEqual(db.fields.filter((f) => f.entity === "DEAL").map((f) => f.key).slice(-2), ["kairon_campaign_id", "next_step"]);
	const second = await ops.ensureFields(crm);
	assert.equal(second.created.length, 0);
	assert.equal(db.fields.length, 13);
});

test("upsertProject es idempotente y respeta el modelo (contactos bajo el developer, real_company)", async () => {
	const { crm, db } = setup();
	await ops.ensureFields(crm);
	const input = { project: MARRONE as never, ficha_md: "# Marrone", kairon_list_url: "https://app.heykairon.com/lists/leads/x" };
	const first = await ops.upsertProject(crm, input);
	assert.equal(first.deal.created, true);
	const second = await ops.upsertProject(crm, input);
	assert.equal(second.deal.created, false);
	assert.equal(second.deal.id, first.deal.id);
	assert.deepEqual([db.companies.length, db.deals.length, db.contacts.length, db.links.length], [2, 1, 2, 2]);
	assert.equal(db.activities.filter((a) => a.subject === "Research DA A006971478").length, 1);
	const dalcott = db.companies.find((c) => c.name === "Dalcott");
	assert.ok(db.contacts.every((c) => c.companyId === dalcott.id), "todos bajo la empresa del developer");
	const frances = db.contacts.find((c) => c.firstName === "Second");
	assert.equal(frances.fieldValues.real_company, "Mewing Planning Consultants");
	assert.equal(frances.fieldValues.project_da, "A006971478");
	assert.equal(frances.email, undefined, "no se inventan emails");
	const deal = await ops.getDeal(crm, first.deal.id);
	assert.equal(deal.fields.da_number, "A006971478");
	assert.equal(deal.fields.units, 97);
	assert.equal(deal.fields.decision, "Approved 2026-11-02");
	assert.equal(deal.contacts.find((c) => c.name === "Sample Person")?.role, "Developer – decision maker");
});

test("findContact encuentra por kairon_lead_id aunque la búsqueda no filtre por campos", async () => {
	const { crm } = setup();
	await ops.ensureFields(crm);
	await ops.upsertProject(crm, { project: MARRONE as never });
	const byLead = await ops.findContact(crm, { kairon_lead_id: "lead_sample0000000000000000001" });
	assert.equal(byLead?.matched_by, "kairon_lead_id");
	const byUrl = await ops.findContact(crm, { linkedin_url: "http://linkedin.com/in/Sample-Person/", last_name: "Person" });
	assert.equal(byUrl?.id, byLead?.id);
	assert.equal(await ops.findContact(crm, { kairon_lead_id: "lead_nope" }), null);
});

async function rpc(fake: ReturnType<typeof setup>, method: string, params: unknown, token = TOKEN) {
	const request = new Request(`https://x.test/api/mcp/${token}`, {
		method: "POST",
		headers: { "content-type": "application/json", accept: "application/json, text/event-stream" },
		body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
	});
	return handleMcp(request, { crm: () => fake.crm, accessToken: TOKEN });
}

test("MCP: rechaza sin token, lista herramientas y ejecuta el flujo de una respuesta", async () => {
	const fake = setup();
	assert.equal((await rpc(fake, "tools/list", {}, "wrong".repeat(8))).status, 401);

	const init = await rpc(fake, "initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "test", version: "0" } });
	assert.equal(init.status, 200);
	assert.equal(((await init.json()) as any).result.serverInfo.name, "da-outreach-crm");

	const list = (await (await rpc(fake, "tools/list", {})).json()) as any;
	const names = list.result.tools.map((tool: any) => tool.name);
	for (const name of ["crm_ensure_fields", "crm_find_contact", "crm_find_deal", "crm_get_deal", "crm_upsert_project", "crm_add_contact_to_deal", "crm_log_activity", "crm_create_task", "crm_set_stage", "crm_set_deal_fields", "developmenti_request"]) assert.ok(names.includes(name), name);

	const call = async (name: string, args: unknown) => {
		const body = (await (await rpc(fake, "tools/call", { name, arguments: args })).json()) as any;
		assert.equal(body.result.isError, undefined, body.result.content?.[0]?.text);
		return JSON.parse(body.result.content[0].text);
	};
	await call("crm_ensure_fields", {});
	const loaded = await call("crm_upsert_project", { project: MARRONE });
	const dealId = loaded.deal.id;
	await call("crm_set_deal_fields", { deal_id: dealId, fields: { kairon_campaign_id: "camp_1" } });
	const added = await call("crm_add_contact_to_deal", { deal_id: dealId, person: { first_name: "Ana", last_name: "Ruiz", company: "Dalcott", role_on_deal: "Development manager" } });
	assert.equal(added.attached, true);
	await call("crm_log_activity", { type: "NOTE", subject: "Respuesta LinkedIn", body: "msg_1", deal_id: dealId });
	await call("crm_create_task", { subject: "Seguimiento", due_at: "2026-11-20", deal_id: dealId });
	await call("crm_set_stage", { deal_id: dealId, stage: "CLOSED_LOST", closed_reason: "No interesado" });
	const deal = await call("crm_get_deal", { id: dealId });
	assert.equal(deal.stage, "CLOSED_LOST");
	assert.equal(deal.fields.kairon_campaign_id, "camp_1");
	assert.equal(deal.contacts.length, 3);
	assert.equal(fake.db.activities.find((a) => a.type === "TASK")?.dueAt, "2026-11-20");

	const bad = (await (await rpc(fake, "tools/call", { name: "developmenti_request", arguments: { method: "GET", path: "//evil.test/x" } })).json()) as any;
	assert.equal(bad.result.isError, true);
});
