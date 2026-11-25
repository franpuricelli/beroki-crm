const SECOND_MS = 1_000;

export const WHATSAPP_DRAFT = {
	model: {
		maxOutputTokens: 600,
		timeoutMs: 45 * SECOND_MS,
	},
	message: {
		maxChars: 320,
		maxSentences: 3,
		questions: 1,
		sender: "Franco",
		brand: "Beroki",
	},
	forbidden: [
		{
			label: "a link",
			pattern:
				/https?:\/\/|\bwww\.|\b[a-z0-9-]+\.(com|net|org|io|au|co|app|dev)\b/i,
		},
		{ label: "an email address", pattern: /@/ },
		{
			label: "a price",
			pattern: /[$€£%]|\b(usd|aud|price|pricing|quote|discount|cost|costs)\b/i,
		},
		{
			label: "a promise",
			pattern:
				/\b(guarantee[ds]?|for free|free of charge|no cost|promise[ds]?)\b/i,
		},
		{
			label: "an attachment",
			pattern: /\b(attach(ed|ment|ments|ing)?|enclosed|pdf)\b/i,
		},
		{ label: "a placeholder", pattern: /[[\]{}<>]/ },
		{ label: "a line break", pattern: /\n/ },
	],
} as const;
