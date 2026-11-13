import { afterAll, beforeAll, describe, expect, it } from "bun:test";
import {
	DEFAULT_WORKSPACE_NAME,
	isInvitedEmail,
	WORKSPACE_ID,
} from "@crm/auth/organization";
import { db } from "@crm/db";
import { workspaceSlug } from "@crm/db/workspace";
import type { AgentTriggerService } from "../src/agent/agent-trigger.service";
import { inviteMemberInput } from "../src/workspace/workspace.contracts";
import { WorkspaceService } from "../src/workspace/workspace.service";

const suffix = crypto.randomUUID();
const adminId = `invite-admin-${suffix}`;
const plainId = `invite-plain-${suffix}`;
const joinedId = `invite-joined-${suffix}`;
const guest = `guest-${suffix}@example.test`;
const joinedEmail = `${joinedId}@example.test`;

const workspace = new WorkspaceService(db, {} as AgentTriggerService);

beforeAll(async () => {
	await db.organization.upsert({
		where: { id: WORKSPACE_ID },
		update: {},
		create: {
			id: WORKSPACE_ID,
			name: DEFAULT_WORKSPACE_NAME,
			slug: workspaceSlug(DEFAULT_WORKSPACE_NAME),
			createdAt: new Date(),
		},
	});
	await db.user.createMany({
		data: [
			{ id: adminId, name: "Invite Admin", email: `${adminId}@example.test` },
			{ id: plainId, name: "Invite Plain", email: `${plainId}@example.test` },
			{ id: joinedId, name: "Invite Joined", email: joinedEmail },
		],
	});
	await db.member.createMany({
		data: [
			{
				id: `member-${adminId}`,
				organizationId: WORKSPACE_ID,
				userId: adminId,
				role: "admin",
				createdAt: new Date(),
			},
			{
				id: `member-${plainId}`,
				organizationId: WORKSPACE_ID,
				userId: plainId,
				role: "member",
				createdAt: new Date(),
			},
		],
	});
});

afterAll(async () => {
	await db.workspaceInvite.deleteMany({
		where: { email: { in: [guest, joinedEmail] } },
	});
	await db.member.deleteMany({
		where: { userId: { in: [adminId, plainId, joinedId] } },
	});
	await db.user.deleteMany({
		where: { id: { in: [adminId, plainId, joinedId] } },
	});
});

describe("adding a member by email", () => {
	it("lets an admin invite an address, stored in lower case", async () => {
		const invite = await workspace.invite(
			adminId,
			inviteMemberInput.parse({ email: ` ${guest.toUpperCase()} ` }),
		);

		expect(invite.email).toBe(guest);
		expect(await isInvitedEmail(`  ${guest.toUpperCase()} `)).toBe(true);
		expect(await isInvitedEmail(`nobody-${suffix}@example.test`)).toBe(false);
	});

	it("keeps one invite when the same address is added twice", async () => {
		await workspace.invite(adminId, { email: guest });

		expect(await db.workspaceInvite.count({ where: { email: guest } })).toBe(1);
	});

	it("lists the invite as pending", async () => {
		const invites = await workspace.invites();

		expect(invites.map((invite) => invite.email)).toContain(guest);
	});

	it("refuses a plain member", async () => {
		await expect(
			workspace.invite(plainId, { email: `other-${suffix}@example.test` }),
		).rejects.toThrow("Only an owner or an admin can add members.");
	});

	it("refuses somebody who is already a member", async () => {
		await expect(
			workspace.invite(adminId, { email: `${plainId}@example.test` }),
		).rejects.toThrow("is already a member.");
	});

	it("stops listing an invite once that person has joined", async () => {
		await db.workspaceInvite.create({ data: { email: joinedEmail } });
		await db.member.create({
			data: {
				id: `member-${joinedId}`,
				organizationId: WORKSPACE_ID,
				userId: joinedId,
				role: "member",
				createdAt: new Date(),
			},
		});

		const invites = await workspace.invites();

		expect(invites.map((invite) => invite.email)).not.toContain(joinedEmail);
	});

	it("removes an invite, and the address can no longer sign in", async () => {
		const [invite] = (await workspace.invites()).filter(
			(row) => row.email === guest,
		);

		await workspace.revokeInvite(adminId, { inviteId: invite?.id ?? "" });

		expect(await isInvitedEmail(guest)).toBe(false);
		await expect(
			workspace.revokeInvite(adminId, { inviteId: invite?.id ?? "" }),
		).rejects.toThrow("That invite does not exist any more.");
	});
});
