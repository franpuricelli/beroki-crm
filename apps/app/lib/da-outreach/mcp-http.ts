import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { DA_OUTREACH } from "./config";
import { Crm, CrmError, type FetchLike } from "./crm-client";
import { buildServer } from "./mcp-server";
import { crmUsers } from "./schemas";

type Options = {
	apiUrl: string;
	token: string;
	fetcher?: FetchLike;
};

const UNAUTHORIZED = 401;
const FORBIDDEN = 403;

function plain(message: string, status: number): Response {
	return new Response(message, { status });
}

async function resolveOwner(
	probe: Crm,
	requested: string | null,
): Promise<string | Response> {
	let users: { id: string }[];

	try {
		users = await probe.read(crmUsers, "GET", "/users");
	} catch (error) {
		if (
			error instanceof CrmError &&
			(error.status === UNAUTHORIZED || error.status === FORBIDDEN)
		) {
			return plain("unauthorized", UNAUTHORIZED);
		}

		return plain("The CRM API is not reachable.", 502);
	}

	if (requested) {
		return users.some((user) => user.id === requested)
			? requested
			: plain("The owner in the URL is not a user of this CRM.", 400);
	}

	const [only, ...others] = users;

	if (!only || others.length > 0) {
		return plain(
			"This CRM has more than one user. Add ?owner=<user id> to the URL.",
			400,
		);
	}

	return only.id;
}

export async function handleMcp(
	request: Request,
	options: Options,
): Promise<Response> {
	if (request.method !== "POST") {
		return new Response("method not allowed", {
			status: 405,
			headers: { allow: "POST" },
		});
	}

	if (options.token.length < DA_OUTREACH.token.minLength) {
		return plain("unauthorized", UNAUTHORIZED);
	}

	const base = `${options.apiUrl.replace(/\/+$/, "")}${DA_OUTREACH.crm.restPath}`;
	const fetcher = options.fetcher ?? fetch;
	const owner = await resolveOwner(
		new Crm(base, options.token, "", fetcher),
		new URL(request.url).searchParams.get("owner"),
	);

	if (owner instanceof Response) return owner;

	const transport = new WebStandardStreamableHTTPServerTransport({
		sessionIdGenerator: undefined,
		enableJsonResponse: true,
	});
	const server = buildServer(
		new Crm(base, options.token, owner, fetcher),
		fetcher,
	);

	await server.connect(transport);

	return transport.handleRequest(request);
}
