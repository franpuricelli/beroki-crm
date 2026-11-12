---
name: da-research
description: Investigar un DA aprobado de Brisbane (developer, planner, personas) y armar la ficha estándar del proyecto. Usar al procesar un DA nuevo.
---

# Investigar un DA

Time box: unos 15 minutos por DA. Salida: `projects/<DA>.md` con el bloque de `schemas/project.schema.json` al inicio.

## Descubrir DAs nuevos
- Fuente: Development.i de Brisbane, decisión "Approved", fecha de decisión dentro de los últimos 4 días.
- Criterios: Material Change of Use, multiple dwelling, 20 unidades o más.
- **El listado por fecha de decisión no está verificado.** Probar primero con `developmenti_request`; si no devuelve un listado usable, abrir https://developmenti.brisbane.qld.gov.au en un browser y filtrar ahí. Anotar en el resumen qué camino funcionó.
- Saltear los DAs que ya están en el CRM: `crm_find_deal(da_number)`.

## Orden de investigación
1. **Búsqueda web por dirección o proyecto** (lo que más rindió): `theurbandeveloper <calle> <calle cruzada>`, `"<dirección>" developer`, `"<proyecto>" developer`.
2. **Listings** (máx. 2 min): apartments.com.au y realestate.com.au.
3. **Documentos de Development.i**:
   - Lista: `POST /DocumentSearch/GetResult?searchText=&datefile=&applicationId=<DA>&isSubCategory=false`
   - Descarga: `GET /DocumentSearch/downloadFile?fileId=<documentId>&fileName=<fileName>&flag=false&fileType=pdf`
   - Leer solo DA Form 1, owner's consent, decision notice y cartas del planner. Los consents suelen ser escaneos: hace falta un browser para renderizar la página y leer la imagen (`developmenti_request` no devuelve PDF).
4. **ABN Lookup**: por ACN y, aparte, `"<nombre> Unit Trust"`.
5. **Noticias**: The Urban Developer.
6. **Web y LinkedIn del developer**: directores y development managers.

## Reglas
- Cada dato va `confirmed` o `inferred` (con `why`) y con su URL en `source`.
- No comprar extractos de ASIC. No adivinar emails: si no hay, `null`.
- Si no se identifica al developer en el time box, no cargar el DA: listarlo en el resumen como "sin developer".
