# da-outreach

Ver `CLAUDE.md` para el diseño y las reglas. Esto es el paso a paso para prenderlo.

## 1. Deploy (Vercel)
1. Importar este repo en Vercel (framework: Other).
2. Environment Variables: `CRM_API`, `CRM_API_KEY`, `CRM_OWNER_ID`, `MCP_ACCESS_TOKEN` (`openssl rand -hex 32`).
3. Deploy.

## 2. Conector en Claude
Agregar un conector MCP personalizado con la URL `https://<proyecto>.vercel.app/api/mcp/<MCP_ACCESS_TOKEN>`.

Esa URL es un secreto: quien la tenga puede escribir en el CRM. Para rotarla, cambiar `MCP_ACCESS_TOKEN` y volver a desplegar.

## 3. Primera corrida
1. `crm_ensure_fields` (crea `kairon_campaign_id`, `next_step` y los que falten).
2. Prueba de punta a punta con un DA nuevo, a mano.
3. Recién después, crear las dos tareas programadas con los prompts de `automations/`.

## 4. Tiempo real (opcional)
El barrido cada hora alcanza para empezar. Para tiempo real:
1. En la tarea del agente de respuestas, agregar un trigger por API y generar el token (se muestra una vez).
2. En Vercel: `ROUTINE_FIRE_URL`, `ROUTINE_FIRE_TOKEN`, `KAIRON_WEBHOOK_SECRET` y un KV (Upstash: `KV_REST_API_URL`, `KV_REST_API_TOKEN`).
3. En Kairon, apuntar el webhook a `https://<proyecto>.vercel.app/kairon/webhook` y probar con `webhook_test`.

Si se registra un endpoint nuevo en Kairon, el secreto cambia: se muestra una sola vez.

## Sin verificar todavía
- Las llamadas al CRM real (las pruebas usan un CRM falso con las formas de los contratos de trycompai/crm).
- El deploy en Vercel.
- Que Development.i responda a pedidos desde Vercel, y el endpoint para listar DAs por fecha de decisión.
