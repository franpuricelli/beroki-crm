# Context: multifamily development leads pipeline (AU + US)

Self-contained document so another agent can pick up the work. Status as of 13 Nov 2026.

## Goal
A database of large multifamily residential projects (apartments, multiple dwellings, residential flat buildings, shop-top housing, build-to-rent, mixed-use with dwellings), preferably **≥10 units**, approved in Australia and the US. For each project: detect the approval, identify the **real developer** behind the entity (SPV) that lodges the DA, and get **people with contact details** (LinkedIn, email, phone). One `.md` lead file per project, later loaded into the internal CRM (Beroki CRM) and into Kairon campaigns.

## Quality rules (non-negotiable)
- `Decided`/`Determined` is **not** `Approved`. Mark Approved only if the source or the decision notice says so. If it cannot be verified: `Determined (unverified)`.
- Every fact has a source and a confidence: `confirmed` (published) or `inferred` (with the reason).
- **Never guess emails.** Only published ones or ones from enrichment (Kairon).
- Do not invent developers, directors or corporate links. Do not buy ASIC extracts.
- **At least 5 named people per project ≥10 dwellings.** Priority: developer/JV partners (directors, founders, development/project managers, sales) → DA planner → architect → builder → other DA consultants. If you cannot reach 5 after exhausting the sources, document what was searched. People reused from other DAs are marked `inferred`.
- In joint ventures, at least one person from each partner.
- The planner is a fallback contact to ask for an introduction; do not confuse them with the developer.
- s81/s82/extensions count if the project has ≥10 dwellings, but they are not new independent supply.
- <10 units: only a row in a "small projects" table, with no people research.
- Exclude: short-term-only, commercial, recreational, existing buildings with no new construction.
- Do not create campaigns that send, and do not send messages, without explicit authorisation.

## Approval sources (pipeline)
Code: `pipeline/` (Python 3.10+, `requests`, `pypdf`, `fonttools`). Database: `db/approvals.csv` (1,128 rows) and `db/frequency.csv`. Upsert by `(council, application_number)`, keeps `first_seen`. Run: `python -m pipeline.run` (incremental: last decision date − 14 days) or `--since YYYY-MM-DD`.

| Region | Source | Notes |
|---|---|---|
| Brisbane | Development.i `https://developmenti.brisbane.qld.gov.au/` | Docs: POST `/DocumentSearch/GetResult?applicationId=...`. Almost daily. |
| Gold Coast | Development.i `https://developmenti.goldcoast.qld.gov.au/`; docs `integrations.goldcoast.qld.gov.au/pdonline/ViewDocs.aspx?id=` | curl usually times out on docs: use Chrome. |
| Sunshine Coast | ArcGIS `https://geopublic.scc.qld.gov.au/arcgis/rest/services/PlanningCadastre/Applications_SCRC/MapServer/1` | Decision `DevPermit`/`Approved`/`#APPROVED`. Units from the description. |
| Logan | ArcGIS `https://services5.arcgis.com/ZUCWDRj8F77Xo351/arcgis/rest/services/Logan_City_Decided_Development_Applications/FeatureServer/0` | Includes applicant and an explicit decision. |
| Moreton Bay | ArcGIS `https://services-ap1.arcgis.com/152ojN3Ts9H3cdtl/ArcGIS/rest/services/MyStreet/FeatureServer/0` | No address or applicant: must be enriched from the tracker. |
| Ipswich, ACT, Casey (VIC) | existing adapters | |
| NSW (whole state) | NSW Planning Portal API | Only "Determined": outcome unverified. Canterbury-Bankstown publishes quarterly PDFs with Approved/Refused. |
| VIC ministerial / DFP | `https://www.planning.vic.gov.au/planning-approvals/ministerial-permits-register` | JSON only from the browser (Chrome with CDP + Node). |
| Miami-Dade | ArcGIS `https://services.arcgis.com/8Pc9XBTAsYuxx9Ny/arcgis/rest/services/miamidade_permit_data/FeatureServer/0/query` | Filter: BLDG/MBLD, NEW, "5 UNITS OR MORE - RESIDENTIAL", StructureUnits ≥10. Includes owner, architect, contractor with phone. Group by folio. |
| City of Miami | ArcGIS `https://services1.arcgis.com/CvuPhqcTQpZPT9qY/arcgis/rest/services/Building_Permits_Since_2014/FeatureServer/0/query` | No units: proxy is new multifamily construction, permit B001, ≥USD 1M. Deduplicate with Miami-Dade by folio. |
| Austin | Socrata `https://data.austintexas.gov/resource/3syk-w9eu.json` | New C-105 permits, housing_units ≥10, group by master permit. Site plans (`mavg-96ck`) have no units, not enabled. |

In the US these are **issued building permits** (later than a DA). The date is that of the last permit issued.

**Stages.** Each row has `etapa` (`presentado`, `en_evaluacion`, `info_request`, `notificacion_publica`, `aprobado`, `rechazado`, `retirado`, `caducado`; in the US `permiso_en_revision` and `permiso_emitido`; NSW `determinado` because the outcome is unknown), `etapa_desde` and `historial_etapas` (`etapa:date;etapa:date`). A lodged DA and the same DA approved are one row: the key stays `(council, application_number)`. `decision` holds only the final decision and is empty while the DA is open. `--lodged-since` sets the lodgement window, and `--recheck` (plus every open row already in the database) re-queries open DAs each run. Lodged DAs come from Brisbane, Gold Coast and Sunshine Coast (Development.i); `plans_url` links an architectural plan, and a lodged DA without one is not a lead.

**Not covered:** Perth/WA (DAP outcomes are only in PDF minutes: `https://www.planning.wa.gov.au/development-assessment-panels/daps-agendas-and-minutes`), Melbourne councils (Melbourne, Yarra, Port Phillip, Stonnington, Monash: difficult or blocked portals), outcomes for NSW, SA, TAS and NT.

## Frequency (projects ≥10 units, last 12 months)
| Council | Projects | Check every |
|---|---|---|
| Brisbane | ~339 | 1 day |
| Miami-Dade | 103 | 1 day |
| Moreton Bay | 65 | 1 day |
| VIC ministerial/DFP | 66 | 2 days |
| Gold Coast | 57 | 5 days |
| Sunshine Coast | 35 | 3 days |
| Logan | 31 | 3 days |
| Austin | 26 | 4 days |
| City of Miami | 26 | 5 days |
| ACT | 36 | 7 days |
| Ipswich / Casey | 22 / 24 | ~12 days |
| NSW councils | 8–17 each | 2–4 weeks |

**Recommendation:** run the pipeline every day at 8:00 Buenos Aires (21:00 in Brisbane, after the business day closes in Australia and the US). Contact research is best done once a week, with all the new projects together.

## Method per project (efficient order, ~5–15 min, USD 0.30–1.20 per project)
1. **Triage:** confirm DA, address, decision (decision notice), date, type (new/s81/s82/extension) and permanent vs short-term units.
2. **Listings (max 2 min):** realestate.com.au and apartments.com.au by address or name. If the project is already selling, the marketing name leads to the developer (e.g. Marrone → Dalcott). realestate.com.au blocks automated browsers.
3. **Press and aggregators:** The Urban Developer, brisbanedevelopment.com.au, yourneighbourhood.com.au, apartments.com.au/news and `/builders/<company>`. They give the brand, the JV partners and the architect.
4. **Cross-check:** address + architect + units + date against the developer's website. If they match, the link is a strong `inferred`.
5. **DA documents:** DA Form 1 and letters (planner email and mobile), owner's consent (SPV director; if it is a scan, read the rendered pages) and decision notice.
6. **ABN Lookup** (abr.business.gov.au): search by ACN, by exact name, by "<name> Unit Trust" and by the owner. The ABN's state and postcode hint at where the developer is based.
7. **People:** the developer's About / Meet the team pages, LinkedIn and ZoomInfo org charts (development managers found there are `inferred`). Reuse people from recurring developers (e.g. Keylin).
8. **Enrichment with Kairon** (work email and phone). It only works on leads already loaded in the workspace, so a list must be created. Reference: about USD 0.10 per person and about USD 0.20 per mobile found. Search by company requires configuring the ICP (error `ICP_SEARCH_SCOPE_REQUIRED`).
9. **US:** use Sunbiz (`https://search.sunbiz.org/Inquiry/CorporationSearch/ByName`, browser only, free) to see the "Authorized Persons" of the owner LLC. The permits already include owner, contractor and architect.

## Lead file template (`leads/<STATE>/<council>/<DA>-<address>.md`)
Frontmatter: council, state, da, address, units, storeys, decision, date_decided, applicant_entity, developer, status_lead, last_updated.
Sections: Address · Decision · Units · Project · DA link · Companies (role, confidence, source, website) · People (table Name | Role | LinkedIn | Email | Phone | Confidence) · Not loaded · CRM/Kairon (list, campaign and deal IDs) · Sources · Notes/follow-up (empty).

## Internal CRM (Beroki CRM, MCP)
Entities: companies, contacts, deals. Tools: `crm_search`, `crm_create`, `crm_update`, `crm_link_contact_to_deal`, `crm_set_deal_stage`, `crm_create_activity`.
Custom fields: contacts `kairon_lead_id`, `real_company`, `project_da`; deals `da_number`, `address`, `units`, `decision`, `da_record`, `kairon_list`.
Convention: one deal per project ("<name or address> – DA <number>"), the developer as company, the people as contacts linked to the deal with their role. **Search before creating** to avoid duplicates.

## Current status (13 Nov 2026)
- CRM: 45 DA deals, 173 linked contacts (123 with email, 128 with LinkedIn, 35 with phone).
- Kairon: 40 DA campaigns: 30 active (19 Brisbane, 11 Gold Coast/Marrone/The Isles), 9 in draft with no LinkedIn contacts and 1 archived. 123 contacts in active campaigns.
- Messages: 14 emails sent and 16 scheduled. 0 LinkedIn invitations sent and 0 replies.
- New sources (QLD, VIC, Miami, Austin): approvals only, no contacts yet.
- Pending: Google Sheet, Perth, Melbourne councils and NSW outcomes.
- See `AUTOMATION.md` for the automation.
