import { z } from "zod";
import { DA_OUTREACH, DEAL_STAGES } from "./config";

const fieldValue = z.union([z.string(), z.number(), z.boolean(), z.null()]);
const fieldRecord = z.record(z.string(), fieldValue);
const fieldArray = z.array(z.object({ key: z.string(), value: fieldValue }));

export const crmUsers = z.array(
	z.object({ id: z.string(), name: z.string(), email: z.string() }),
);

export const crmFieldDefinitions = z.array(z.object({ key: z.string() }));

export const crmCreated = z.object({ id: z.string() });

export const crmCompanyList = z.object({
	rows: z.array(
		z.object({
			id: z.string(),
			name: z.string(),
			domain: z.string().nullable(),
		}),
	),
	total: z.number(),
});

export const crmContactList = z.object({
	rows: z.array(
		z.object({
			id: z.string(),
			firstName: z.string(),
			lastName: z.string().nullable(),
			email: z.string().nullable(),
			fields: fieldRecord,
		}),
	),
	total: z.number(),
});

export const crmContactDetail = z.object({
	id: z.string(),
	firstName: z.string(),
	lastName: z.string().nullable(),
	email: z.string().nullable(),
	phone: z.string().nullable(),
	title: z.string().nullable(),
	linkedinUrl: z.string().nullable(),
	company: z.object({ id: z.string(), name: z.string() }).nullable(),
	fields: fieldArray,
	deals: z.array(z.object({ id: z.string(), name: z.string() })),
});

export const crmDealList = z.object({
	rows: z.array(
		z.object({ id: z.string(), name: z.string(), fields: fieldRecord }),
	),
	total: z.number(),
});

export const crmDealDetail = z.object({
	id: z.string(),
	name: z.string(),
	description: z.string().nullable(),
	stage: z.string(),
	closedReason: z.string().nullable(),
	company: z.object({
		id: z.string(),
		name: z.string(),
		domain: z.string().nullable(),
	}),
	fields: fieldArray,
	contacts: z.array(
		z.object({
			id: z.string(),
			firstName: z.string(),
			lastName: z.string().nullable(),
			email: z.string().nullable(),
			title: z.string().nullable(),
			role: z.string().nullable(),
		}),
	),
});

export const crmTimeline = z.object({
	entries: z.array(
		z.object({
			id: z.string(),
			type: z.string(),
			subject: z.string().nullable(),
			body: z.string().nullable(),
			occurredAt: z.string().nullable(),
			dueAt: z.string().nullable(),
		}),
	),
});

const confidence = z.enum(["confirmed", "inferred"]);

export const personInput = z.object({
	first_name: z.string().min(1),
	last_name: z.string().nullish(),
	company: z.string().min(1),
	title: z.string().nullish(),
	role_on_deal: z.string().max(DA_OUTREACH.crm.roleMaxLength).nullish(),
	linkedin: z.string().nullish(),
	email: z.string().nullish(),
	phone: z.string().nullish(),
	kairon_lead_id: z.string().nullish(),
	confidence: confidence.optional(),
	why: z.string().nullish(),
	source: z.string().nullish(),
});

const companyInput = z.object({
	name: z.string().min(1),
	role: z.string().min(1),
	domain: z.string().nullish(),
	linkedin: z.string().nullish(),
	website: z.string().nullish(),
	confidence,
	why: z.string().nullish(),
	source: z.string().nullish(),
});

export const projectInput = z.object({
	da: z.string().min(1),
	council: z.string().optional(),
	project: z.string().min(1),
	address: z.string().min(1),
	units: z.number().nullish(),
	decision: z
		.object({ status: z.string(), date: z.string().nullish() })
		.optional(),
	da_url: z.string().nullish(),
	companies: z.array(companyInput).min(1),
	people: z.array(personInput),
	whos_who: z.string().optional(),
});

export const stageInput = z.enum(DEAL_STAGES);

export const fieldValuesInput = z.record(z.string(), fieldValue);

export type PersonInput = z.infer<typeof personInput>;
export type CompanyInput = z.infer<typeof companyInput>;
export type ProjectInput = z.infer<typeof projectInput>;
export type FieldValues = z.infer<typeof fieldValuesInput>;
