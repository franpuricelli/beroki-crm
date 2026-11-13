import { handleCrmMcp } from "@/lib/crm-mcp";
import { API_URL } from "@/lib/env";

type Context = { params: Promise<{ token: string }> };

async function handler(
	request: Request,
	{ params }: Context,
): Promise<Response> {
	const { token } = await params;

	return handleCrmMcp(request, { apiUrl: API_URL, apiKey: token });
}

export const GET = handler;
export const POST = handler;
export const DELETE = handler;
