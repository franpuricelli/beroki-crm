import { crmFromEnv } from "../../src/crm/client.js";
import { handleMcp } from "../../src/mcp/http.js";

const handler = (request: Request) => handleMcp(request, { crm: () => crmFromEnv(), accessToken: process.env.MCP_ACCESS_TOKEN });
export const POST = handler;
export const GET = handler;
export const DELETE = handler;
