# CRM MCP endpoint — rules for AI agents

An MCP server for this CRM. An agent connects to it and reads and writes CRM records.

## Files

- `apps/app/app/api/crm-mcp/[token]/route.ts` — the route. It hands the request to `handleCrmMcp`.
- `apps/app/lib/crm-mcp.ts` — the server and all its tools.

## URL and auth

`https://<app host>/api/crm-mcp/<CRM API key>`

- The token in the path is a CRM API key (Settings → API keys).
- The endpoint sends it to the API as `x-api-key`. The API does the auth.
- The endpoint stores nothing and needs no environment variable.
- The URL is a secret. To revoke it, delete that API key.
- The route sits under `/api`, which `proxy.ts` skips, so no session cookie is needed.

## How it works

- Streamable HTTP, stateless: one server per request, JSON responses, `POST` only.
- Each tool is one call to the REST bridge at `${API_URL}/rest`.
- A tool returns the API's JSON as text. An API error comes back as a tool error with the status.
- An invalid key still connects. The first tool call returns `CRM 401`.

## Tools

| Tool | REST call |
| --- | --- |
| `crm_search` | `POST /{companies\|contacts\|deals}/search` |
| `crm_get` | `GET /{entity}/{id}` |
| `crm_create` | `POST /{entity}` |
| `crm_update` | `PATCH /{entity}/{id}` with `{ data }` |
| `crm_link_contact_to_deal` | `POST /deals/{dealId}/contacts` |
| `crm_set_deal_stage` | `PATCH /deals/{id}/stage` |
| `crm_list_activities` | `GET /activities` |
| `crm_create_activity` | `POST /activities` |
| `crm_list_fields` | `GET /fields` |
| `crm_create_field` | `POST /fields` |
| `crm_list_users` | `GET /users` |

Facts an agent needs:

- `POST` on a record does not take `linkedinUrl` or custom fields. Set them with `crm_update`.
- Custom fields go in `data.fields`, as a map of field key to value.
- `q` in a search matches one word. The `fields` filter of a search does not match custom field values.
- A deal has one main company. A contact on a deal can work at any company.
- A deal has two text columns. `description` is the short summary at the top of the overview. `findings` is the full text of everything found about the deal.

## Rules for changes

- Keep it generic. A tool maps to one REST call. No workflow logic and no knowledge of any automation that uses it.
- No change to `apps/api` for this endpoint. A new capability is a new REST route there first, then a thin tool here.
- Add a tool with `server.registerTool` in `crm-mcp.ts`. Use snake_case inputs and map them to the API's camelCase.
- Tunable values go in the `CRM_MCP` object at the top of `crm-mcp.ts`.
