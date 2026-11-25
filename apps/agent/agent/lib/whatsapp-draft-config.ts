const SECOND_MS = 1_000;

export const WHATSAPP_DRAFT = {
	model: { maxOutputTokens: 600, timeoutMs: 45 * SECOND_MS },
	message: { maxChars: 320 },
	forbidden:
		/https?:\/\/|\bwww\.|@|[$€£%[\]{}<>\n]|\b[a-z0-9-]+\.(com|net|org|io|au|co)\b|\b(usd|aud|price|pricing|quote|discount|costs?|guarantee[ds]?|for free|free of charge|promise[ds]?|attach\w*|enclosed|pdf)\b/i,
} as const;
