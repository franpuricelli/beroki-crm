const SECOND_MS = 1000;

export const DA_OUTREACH = {
	server: { name: "da-outreach-crm", version: "0.2.0" },
	crm: {
		restPath: "/rest",
		timeoutMs: 20 * SECOND_MS,
		pageSize: 100,
		maxPages: 5,
		detailLookups: 40,
		roleMaxLength: 80,
	},
	developmenti: {
		origin: "https://developmenti.brisbane.qld.gov.au",
		timeoutMs: 25 * SECOND_MS,
		maxChars: 60_000,
	},
	token: { minLength: 16 },
} as const;

export const DEAL_STAGES = [
	"DEMO_BOOKED",
	"QUALIFIED_TO_BUY",
	"DECISION_MAKER_BOUGHT_IN",
	"CONTRACT_SENT",
	"CLOSED_WON",
	"CLOSED_LOST",
	"UNQUALIFIED_TO_BUY",
] as const;

export const REQUIRED_FIELDS = [
	{ entity: "CONTACT", key: "kairon_lead_id", type: "TEXT" },
	{ entity: "CONTACT", key: "real_company", type: "TEXT" },
	{ entity: "CONTACT", key: "project_da", type: "TEXT" },
	{ entity: "DEAL", key: "da_number", type: "TEXT" },
	{ entity: "DEAL", key: "address", type: "TEXT" },
	{ entity: "DEAL", key: "decision", type: "TEXT" },
	{ entity: "DEAL", key: "units", type: "NUMBER" },
	{ entity: "DEAL", key: "da_record", type: "URL" },
	{ entity: "DEAL", key: "kairon_list", type: "URL" },
	{ entity: "DEAL", key: "companies_involved", type: "LONG_TEXT" },
	{ entity: "DEAL", key: "whos_who", type: "LONG_TEXT" },
	{ entity: "DEAL", key: "kairon_campaign_id", type: "TEXT" },
	{ entity: "DEAL", key: "next_step", type: "LONG_TEXT" },
] as const;
