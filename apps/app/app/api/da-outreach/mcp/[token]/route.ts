import { handleMcp } from "@/lib/da-outreach/mcp-http";
import { API_URL } from "@/lib/env";

type Context = { params: Promise<{ token: string }> };

async function handler(
	request: Request,
	{ params }: Context,
): Promise<Response> {
	const { token } = await params;

	return handleMcp(request, { apiUrl: API_URL, token });
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
