export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export class CrmError extends Error {
	constructor(
		readonly status: number,
		readonly method: string,
		readonly path: string,
		readonly detail: string,
	) {
		super(`CRM ${method} ${path} -> ${status}: ${detail.slice(0, 400)}`);
	}
}

/** Thin client for the trycompai/crm REST bridge (`/rest`, header `x-api-key`). */
export class Crm {
	constructor(
		private readonly base: string,
		private readonly apiKey: string,
		readonly ownerId: string,
		private readonly fetcher: FetchLike = fetch,
	) {}

	async request<T = unknown>(
		method: "GET" | "POST" | "PATCH" | "DELETE",
		path: string,
		options: { body?: unknown; query?: Record<string, string | number | undefined> } = {},
	): Promise<T> {
		const url = new URL(this.base.replace(/\/+$/, "") + path);
		for (const [key, value] of Object.entries(options.query ?? {})) {
			if (value !== undefined) url.searchParams.set(key, String(value));
		}
		const response = await this.fetcher(url.toString(), {
			method,
			headers: {
				"x-api-key": this.apiKey,
				accept: "application/json",
				...(options.body === undefined ? {} : { "content-type": "application/json" }),
			},
			body: options.body === undefined ? undefined : JSON.stringify(options.body),
			signal: AbortSignal.timeout(20_000),
		});
		const text = await response.text();
		if (!response.ok) throw new CrmError(response.status, method, path, text);
		return (text ? JSON.parse(text) : null) as T;
	}
}

export function crmFromEnv(env: NodeJS.ProcessEnv = process.env): Crm {
	const { CRM_API, CRM_API_KEY, CRM_OWNER_ID } = env;
	if (!CRM_API || !CRM_API_KEY || !CRM_OWNER_ID) {
		throw new Error("Faltan CRM_API, CRM_API_KEY o CRM_OWNER_ID en el entorno.");
	}
	return new Crm(CRM_API, CRM_API_KEY, CRM_OWNER_ID);
}
