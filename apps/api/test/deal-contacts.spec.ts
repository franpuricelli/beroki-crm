import { afterAll, beforeAll, describe, expect, it } from "bun:test";
import { db } from "@crm/db";
import type { AgentTriggerService } from "../src/agent/agent-trigger.service";
import { ActivityStampService } from "../src/crm/activity-stamp.service";
import { ConversionService } from "../src/currency/conversion.service";
import { DealsService } from "../src/deals/deals.service";
import { FieldsService } from "../src/fields/fields.service";
import { withDiscardedCrmEvents } from "./agent-trigger.stub";

const suffix = process.env.TEST_RUN_ID ?? "deal-contacts-spec";
const userId = `user-${suffix}`;
const domain = `dealpeople-${suffix}.test`;
const otherDomain = `elsewhere-${suffix}.test`;

const agent = {
	withCrmEvents: withDiscardedCrmEvents,
} as unknown as AgentTriggerService;

const deals = new DealsService(
	db,
	agent,
	new ActivityStampService(db),
	new ConversionService(db),
	new FieldsService(db, { fieldBackfill: async () => undefined } as never),
);

let companyId: string;
let dealId: string;
let championId: string;
let colleagueId: string;
let outsiderId: string;

async function clean() {
	await db.deal.deleteMany({ where: { company: { domain } } });
	await db.contact.deleteMany({
		where: { company: { domain: { in: [domain, otherDomain] } } },
	});
	await db.company.deleteMany({
		where: { domain: { in: [domain, otherDomain] } },
	});
	await db.user.deleteMany({ where: { id: userId } });
}

beforeAll(async () => {
	await clean();

	await db.user.create({
		data: {
			id: userId,
			name: "Deal Rep",
			email: `${userId}@example.test`,
			emailVerified: true,
		},
	});

	const company = await db.company.create({
		data: { name: `People Co ${suffix}`, domain },
		select: { id: true },
	});
	companyId = company.id;

	const other = await db.company.create({
		data: { name: `Other Co ${suffix}`, domain: otherDomain },
		select: { id: true },
	});

	const champion = await db.contact.create({
		data: { firstName: "Ada", lastName: "Champion", companyId },
		select: { id: true },
	});
	championId = champion.id;

	const colleague = await db.contact.create({
		data: { firstName: "Beau", lastName: "Colleague", companyId },
		select: { id: true },
	});
	colleagueId = colleague.id;

	const outsider = await db.contact.create({
		data: { firstName: "Cass", lastName: "Outsider", companyId: other.id },
		select: { id: true },
	});
	outsiderId = outsider.id;

	const deal = await deals.create({
		name: `Renewal ${suffix}`,
		companyId,
		ownerId: userId,
	});
	dealId = deal.id;
});

afterAll(clean);

describe("bringing a contact onto a deal", () => {
	it("offers the people at the deal's company first, then everybody else", async () => {
		const options = await deals.contactOptions(dealId);
		const ids = options.map((option) => option.id);

		expect(ids).toContain(championId);
		expect(ids).toContain(colleagueId);
		expect(ids).toContain(outsiderId);
		expect(ids.indexOf(outsiderId)).toBeGreaterThan(ids.indexOf(championId));
		expect(ids.indexOf(outsiderId)).toBeGreaterThan(ids.indexOf(colleagueId));
	});

	it("narrows the options to a search across people and companies", async () => {
		const byName = await deals.contactOptions(dealId, "Outsider");
		expect(byName.map((option) => option.id)).toEqual([outsiderId]);

		const byCompany = await deals.contactOptions(dealId, `Other Co ${suffix}`);
		expect(byCompany.map((option) => option.id)).toEqual([outsiderId]);
		expect(byCompany[0]?.company?.name).toBe(`Other Co ${suffix}`);
	});

	it("attaches with a role and reads back on the deal", async () => {
		await deals.attachContact({
			dealId,
			contactId: championId,
			role: "Champion",
		});

		const deal = await deals.byId(dealId);

		expect(deal.contacts).toHaveLength(1);
		expect(deal.contacts[0]?.id).toBe(championId);
		expect(deal.contacts[0]?.role).toBe("Champion");
	});

	it("stops offering somebody already on it", async () => {
		const options = await deals.contactOptions(dealId);

		expect(options.map((option) => option.id)).not.toContain(championId);
	});

	it("attaching twice keeps the role it already has", async () => {
		await deals.attachContact({ dealId, contactId: championId });

		const deal = await deals.byId(dealId);

		expect(deal.contacts).toHaveLength(1);
		expect(deal.contacts[0]?.role).toBe("Champion");
	});

	it("attaches somebody who works somewhere else, and keeps the deal's main company", async () => {
		await deals.attachContact({
			dealId,
			contactId: outsiderId,
			role: "Partner",
		});

		const deal = await deals.byId(dealId);
		const outsider = deal.contacts.find((contact) => contact.id === outsiderId);

		expect(deal.company.id).toBe(companyId);
		expect(outsider?.role).toBe("Partner");
		expect(outsider?.company?.name).toBe(`Other Co ${suffix}`);

		await deals.detachContact({ dealId, contactId: outsiderId });
	});

	it("refuses a contact that does not exist", async () => {
		await expect(
			deals.attachContact({ dealId, contactId: "missing-contact" }),
		).rejects.toThrow("No contact with id missing-contact.");
	});

	it("blanks a role rather than storing an empty string", async () => {
		await deals.setContactRole({ dealId, contactId: championId, role: "  " });

		const deal = await deals.byId(dealId);

		expect(deal.contacts[0]?.role).toBeNull();
	});

	it("will not set a role on somebody who is not on the deal", async () => {
		await expect(
			deals.setContactRole({
				dealId,
				contactId: colleagueId,
				role: "Blocker",
			}),
		).rejects.toThrow("That contact is not on this deal.");
	});

	it("takes them off again, leaving the contact in the CRM", async () => {
		await deals.detachContact({ dealId, contactId: championId });

		const deal = await deals.byId(dealId);

		expect(deal.contacts).toHaveLength(0);
		expect(await db.contact.count({ where: { id: championId } })).toBe(1);
	});

	it("says so when they were never on it", async () => {
		await expect(
			deals.detachContact({ dealId, contactId: championId }),
		).rejects.toThrow("That contact is not on this deal.");
	});
});
