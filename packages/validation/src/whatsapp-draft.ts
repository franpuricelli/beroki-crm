import { z } from "zod";

export const WHATSAPP_DRAFT_LIMITS = {
	name: 60,
	line: 120,
	project: 160,
	list: 8,
	message: 400,
	reason: 300,
} as const;

const L = WHATSAPP_DRAFT_LIMITS;
const line = (max: number) => z.string().trim().min(1).max(max);

export const whatsappDraftRequest = z.object({
	firstName: line(L.name),
	role: line(L.line),
	project: line(L.project),
	contactCompany: line(L.line).nullable(),
	developer: line(L.line),
	facts: z.array(line(L.project)).min(1).max(L.list),
	services: z.array(line(L.line)).min(1).max(L.list),
});

export type WhatsappDraftRequest = z.infer<typeof whatsappDraftRequest>;

export const whatsappDraftReply = z.discriminatedUnion("status", [
	z.object({ status: z.literal("draft"), message: line(L.message) }),
	z.object({ status: z.literal("review"), reason: line(L.reason) }),
]);

export type WhatsappDraftReply = z.infer<typeof whatsappDraftReply>;
