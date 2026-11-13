import { Inject } from "@nestjs/common";
import {
	Ctx,
	Input,
	Mutation,
	Query,
	Router,
	UseMiddlewares,
} from "nestjs-trpc";
import type { z } from "zod";
import type { AuthedTrpcContext } from "../trpc/context.types";
import { AuthMiddleware } from "../trpc/middlewares/auth.middleware";
import { restMeta } from "../trpc/openapi";
import {
	inviteMemberInput,
	memberListInput,
	memberListOutput,
	revokeInviteInput,
	revokeInviteOutput,
	setMemberRoleInput,
	updateWorkspaceInput,
	workspaceInviteListOutput,
	workspaceInviteOutput,
	workspaceMemberOutput,
	workspaceOutput,
} from "./workspace.contracts";
import { WorkspaceService } from "./workspace.service";

@Router({ alias: "workspace" })
@UseMiddlewares(AuthMiddleware)
export class WorkspaceRouter {
	constructor(
		@Inject(WorkspaceService) private readonly workspace: WorkspaceService,
	) {}

	@Query({
		output: workspaceOutput,
		meta: restMeta("GET", "/workspace", ["Workspace"]),
	})
	async get(@Ctx() ctx: AuthedTrpcContext) {
		return this.workspace.get(ctx.user.id);
	}

	@Query({
		input: memberListInput,
		output: memberListOutput,
		meta: restMeta("POST", "/workspace/members/search", ["Workspace"]),
	})
	async members(
		@Ctx() ctx: AuthedTrpcContext,
		@Input() input: z.infer<typeof memberListInput>,
	) {
		return this.workspace.members(ctx.user.id, input);
	}

	@Mutation({
		input: updateWorkspaceInput,
		output: workspaceOutput,
		meta: restMeta("PATCH", "/workspace", ["Workspace"]),
	})
	async update(
		@Ctx() ctx: AuthedTrpcContext,
		@Input() input: z.infer<typeof updateWorkspaceInput>,
	) {
		return this.workspace.update(ctx.user.id, input);
	}

	@Mutation({
		input: setMemberRoleInput,
		output: workspaceMemberOutput,
		meta: restMeta("PATCH", "/workspace/members/{memberId}/role", [
			"Workspace",
		]),
	})
	async setMemberRole(
		@Ctx() ctx: AuthedTrpcContext,
		@Input() input: z.infer<typeof setMemberRoleInput>,
	) {
		return this.workspace.setMemberRole(ctx.user.id, input);
	}

	@Query({
		output: workspaceInviteListOutput,
		meta: restMeta("GET", "/workspace/invites", ["Workspace"]),
	})
	async invites() {
		return this.workspace.invites();
	}

	@Mutation({
		input: inviteMemberInput,
		output: workspaceInviteOutput,
		meta: restMeta("POST", "/workspace/invites", ["Workspace"]),
	})
	async invite(
		@Ctx() ctx: AuthedTrpcContext,
		@Input() input: z.infer<typeof inviteMemberInput>,
	) {
		return this.workspace.invite(ctx.user.id, input);
	}

	@Mutation({
		input: revokeInviteInput,
		output: revokeInviteOutput,
		meta: restMeta("DELETE", "/workspace/invites/{inviteId}", ["Workspace"]),
	})
	async revokeInvite(
		@Ctx() ctx: AuthedTrpcContext,
		@Input() input: z.infer<typeof revokeInviteInput>,
	) {
		return this.workspace.revokeInvite(ctx.user.id, input);
	}
}
