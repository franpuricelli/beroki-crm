import type { z } from "zod";
import { DA_OUTREACH } from "./config";

export type FetchLike = (
	input: string,
	init?: RequestInit,
) => Promise<Response>;

type Method = "GET" | "POST" | "PATCH";

type RequestOptions = {
	body?: unknown;
	query?: Record<string, string | undefined>;
};

export class CrmError extends Error {
	constructor(
		readonly status: number,
		method: string,
		path: string,
		detail: string,
	) {
		super(`CRM ${method} ${path} -> ${status}: ${detail.slice(0, 400)}`);
	}
}

export class Crm {
	constructor(
		private readonly base: string,
		private readonly apiKey: string,
		readonly ownerId: string,
		private readonly fetcher: FetchLike = fetch,
	) {}

	async send(method: Method, path: string, options: RequestOptions = {}) {
		const url = new URL(this.base.replace(/\/+$/, "") + path);

		for (const [key, value] of Object.entries(options.query ?? {})) {
			if (value !== undefined) url.searchParams.set(key, value);
		}

		const response = await this.fetcher(url.toString(), {
			method,
			headers: {
				"x-api-key": this.apiKey,
				accept: "application/json",
				...(options.body === undefined
					? {}
					: { "content-type": "application/json" }),
			},
			body:
				options.body === undefined ? undefined : JSON.stringify(options.body),
			signal: AbortSignal.timeout(DA_OUTREACH.crm.timeoutMs),
		});
		const text = await response.text();

		if (!response.ok) {
			throw new CrmError(response.status, method, path, text);
		}

		return text;
	}

	async read<Schema extends z.ZodType>(
		schema: Schema,
		method: Method,
		path: string,
		options: RequestOptions = {},
	): Promise<z.infer<Schema>> {
		const text = await this.send(method, path, options);
		const parsed = schema.safeParse(JSON.parse(text));

		if (!parsed.success) {
			throw new Error(
				`CRM ${method} ${path} returned an unexpected shape: ${parsed.error.message.slice(0, 400)}`,
			);
		}

		return parsed.data;
	}
}
