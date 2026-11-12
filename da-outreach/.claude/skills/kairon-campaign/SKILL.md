---
name: kairon-campaign
description: Encontrar el LinkedIn de cada persona, armar la lista del proyecto en Kairon, enriquecer y dejar la campaña en borrador. Usar después de investigar un DA.
---

# Kairon: lista, enrichment y campaña

Antes de la primera herramienta de cada trabajo, leer el playbook de Kairon que corresponda (`skill_list`, `skill_get`): las herramientas que arrancan un trabajo piden su `readReceipt`.

## Personas y lista
1. `search_people` por nombre y empresa. Con varios candidatos, elegir por headline y empresa; si hay duda, `inferred` con el motivo.
2. `list_create`: una lista por proyecto, `DA <número> - <proyecto> (<developer>)`. Leer antes `skill_get list-building` y `skill_get lists`.
3. `list_add` con las URLs de LinkedIn.
4. `lead_enrich` **de a una persona por llamada** (con varias juntas falló), pidiendo email y teléfono. Lo que no encuentra no cobra.
5. Guardar el `lead_id` de cada persona en la ficha (`kairon_lead_id`).
6. Una columna de la lista lleva el rol de cada persona (`list_set`): al developer y al planner no se les dice lo mismo.

## Campaña
- Una campaña por proyecto, con la lista del proyecto. Canales: LinkedIn y email. El teléfono se guarda y no se usa.
- El texto fijo lleva el contexto del proyecto: nombre, dirección, unidades y estado.
- Antes de sumar a alguien, chequear que no esté en otra campaña activa.
- Respetar exclusiones (`exclusion_list`).
- **`AUTO_PUBLISH=false`**: `campaign_create`, después `campaign_preview`, y avisar a Franco. No llamar a `campaign_publish` ni a `campaign_activate`.
- Guardar el id de la campaña en el Deal: `crm_set_deal_fields(deal_id, {kairon_campaign_id})`.
