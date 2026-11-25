import { z } from "zod";

export const WHATSAPP_DRAFT_LIMITS = {
	firstName: 60,
	role: 120,
	project: 160,
	company: 120,
	fact: 160,
	facts: 8,
	service: 120,
	services: 8,
	message: 400,
	reason: 300,
} as const;

const line = (max: number) => z.string().trim().min(1).max(max);

export const whatsappDraftRequest = z.object({
	firstName: line(WHATSAPP_DRAFT_LIMITS.firstName),
	role: line(WHATSAPP_DRAFT_LIMITS.role),
	project: line(WHATSAPP_DRAFT_LIMITS.project),
	contactCompany: line(WHATSAPP_DRAFT_LIMITS.company).nullable(),
	developer: line(WHATSAPP_DRAFT_LIMITS.company),
	facts: z
		.array(line(WHATSAPP_DRAFT_LIMITS.fact))
		.min(1)
		.max(WHATSAPP_DRAFT_LIMITS.facts),
	services: z
		.array(line(WHATSAPP_DRAFT_LIMITS.service))
		.min(1)
		.max(WHATSAPP_DRAFT_LIMITS.services),
});

export type WhatsappDraftRequest = z.infer<typeof whatsappDraftRequest>;

export const whatsappDraftReply = z.discriminatedUnion("status", [
	z.object({
		status: z.literal("draft"),
		message: line(WHATSAPP_DRAFT_LIMITS.message),
	}),
	z.object({
		status: z.literal("review"),
		reason: line(WHATSAPP_DRAFT_LIMITS.reason),
	}),
]);

export type WhatsappDraftReply = z.infer<typeof whatsappDraftReply>;
