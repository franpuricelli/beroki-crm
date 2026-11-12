---
name: crm-load
description: Cargar o actualizar un proyecto de DA en el CRM con las herramientas crm_* del MCP. Usar después de armar la ficha estándar.
---

# Cargar en el CRM

Siempre por el MCP (`crm_*`). No armar requests a mano.

1. `crm_find_deal(da_number)`: si existe, se actualiza; no se duplica.
2. `crm_upsert_project(project, ficha_md, kairon_list_url)`: hace toda la carga, idempotente:
   - empresas (busca por dominio o nombre antes de crear);
   - Deal `<Proyecto> – DA <número>` con `companyId` = developer;
   - contactos bajo la empresa del developer, con `kairon_lead_id`, `real_company` y `project_da`;
   - rol de cada contacto en el Deal (`role_on_deal`, máx. 80 caracteres);
   - campos `da_number`, `address`, `decision`, `units`, `da_record`, `kairon_list`, `companies_involved`, `whos_who`;
   - la ficha como nota `Research DA <número>` (una sola vez).
3. Cuando exista la campaña: `crm_set_deal_fields(deal_id, {kairon_campaign_id})`.

Si una herramienta devuelve que falta un campo, correr `crm_ensure_fields` una vez y reintentar.

Persona nueva más adelante (por ejemplo, una derivación): `crm_add_contact_to_deal(deal_id, person)`.
