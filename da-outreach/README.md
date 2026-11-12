# da-outreach

See `CLAUDE.md` for the design and the rules.

## Where the MCP lives

The CRM MCP is part of the CRM app: `apps/app/app/api/da-outreach/mcp/[token]/route.ts`, with its code in `apps/app/lib/da-outreach`.

Connector URL: `https://beroki-crm.vercel.app/api/da-outreach/mcp/<CRM_API_KEY>`

- The token is a CRM API key. The CRM checks it on every request.
- No environment variable is needed.
- A CRM with more than one user needs `?owner=<user id>` at the end of the URL.
- The URL is a secret. To revoke it, delete that API key in the CRM.

## First run

1. Add the connector in Claude.
2. Run `crm_ensure_fields`.
3. Run one DA end to end by hand.
4. Create the two scheduled tasks with the prompts in `automations/`.

## Webhook receiver (optional, not deployed)

`api/kairon/webhook.ts` and `src/receiver` hold the Kairon webhook receiver. It needs its own deploy, a KV and the API trigger token of the reply task. The hourly sweep works without it.

`npm install`, `npm run typecheck`, `npm test` cover the receiver and the schemas.
