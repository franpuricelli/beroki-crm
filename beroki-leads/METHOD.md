# Method per project: developer, people and contacts

Goal: one lead file per project, maximising **named people at the developer** with LinkedIn, work email and phone. SPV applicant, owner, developer, JV partner, builder and planner are different roles. This procedure combines Wickham/Marrone and the contributed run of 1–12 November 2026; it does not imply a new search or an executed enrichment.

## 1. Triage and file

- Confirm DA, address, decision, date and **type**: new approval, s81 minor change, s82 change or extension. Changes and extensions **count if the project has ≥10 dwellings**; record the original application/relationship and do not add versions up as independent supply.
- Fewer than ten dwellings: **only a row in the small-projects list**, with no deep research and no people. If only an increase is recorded, do not assume it is the total: mark the total as pending. The old Gold Coast lead files under ten are historical exceptions.
- Prioritise the decision notice for permanent dwellings, separating short-term. Record differences: Lotus, 76 multiple dwelling versus 132 including short-term in the press; Railway, 20 versus 32 in the listing. An information request does not prove approval; if the notice is missing, identify an alternative source and its limit.

## 2. Find the brand and partners

1. **Listings first, two minutes at most in total:** address/variants on realestate.com.au and apartments.com.au, preferably through a search engine. If it is already selling, the marketing name leads to the developer: Marrone → Dalcott. If it is empty, unclaimed or blocked, move to the next source; do not complete truncated phone numbers.
2. Search the address/name on **brisbanedevelopment.com.au**, **yourneighbourhood.com.au**, **apartments.com.au/news**, **`/builders/<company>`** pages and **The Urban Developer**: they give the brand, JV partners and architect. For Keylin + Mackwell, capture **both partners**, not only the SPV.
3. Cross-check **address + architect + units + date** against the developer's site. Dalcott/Marrone matches on 37–39 Browning, DAH and 97 dwellings: the Culkoa–Dalcott link is **inferred**, not legal equivalence. Keylin's usual CoStruct does not prove a contract on Lotus; Carbone/Amado is inferred from the address and 51 dwellings.
4. Separate the historical group from the current one. Wickham: **unresolved** Tribune Properties/NKM Holding, attributed to an earlier application, versus TKM Capital/Asher Capital in a July 2026 news item. Do not replace attributions or treat an old one as current.

## 3. Find people at the developer

- Open **About / Meet the team** on their own site: founders, directors, managing director and development managers. Record full name, title, company, source and date; verify LinkedIn, avoiding namesakes.
- **ZoomInfo** org charts surface development managers: mark the association **inferred**, like Ben Johnson. An email on the right domain does not confirm the title or assignment to the DA. Initials AS/MZ/GT/JS are not identities: they go to **Not loaded**.
- **Reuse people** from recurring developers: Louis Cheung and Ben Johnson across several Keylin projects. Check they are current, keep the provenance and do not duplicate contacts, enrichment or cost; reuse does not prove assignment to the project.
- In a JV, look for at least one person from **each partner**. Names with no unambiguous LinkedIn, incomplete titles or conflicting identity are kept in Not loaded with the reason.

## 4. Documents and registry

- Development.i: decision notice; **DA Form 1**, Applicant Letter/emails for the planner's contact and email/mobile; **owner's consent** for the owner/signatory. If it is a scan, **read the rendered pages**: Wickham did and got a director; Thorn skipped it and ended with zero developer people. Do not claim a read from empty text.
- If the applicant is not the owner, the consent may not identify the SPV director: this happened with Culkoa. Go back to brand/partners/team, without turning the owner into the developer.
- **ABN Lookup by ACN**, then exact name, Unit Trust and owner separately. Record ABN/ACN, GST, dates and state/postcode. NSW 2099 on Culkoa pointed to Northern Beaches/Sydney, **inferred**, not proof of head office/group. ABN start is not incorporation; a trust's ABN is not automatically the company's. W & R had a candidate trust with no proven trustee; Culkoa Unit Trust returned no results per the report.
- **Planner as fallback** to ask for an introduction, not an automatic substitute for finding the developer. Do not load an official or consultant as the developer's decision-maker.

## 5. Enrichment and lead file

- With identity/company/LinkedIn reviewed, **attempt Kairon enrichment** of work email and phone. Emails come from enrichment or explicit publication, **never guessed**. Provenance per field: a confirmed title does not independently validate the enriched contact.
- Cheap reference from run 1: **USD 0.72 for 7 people**, not a guaranteed rate. Reuse current results. With no access/result, note pending/failed; do not invent an attempt.
- Use the per-project template: Address, Decision/type, Units/source, Project, DA link, Companies, People, Not loaded, CRM/Kairon, Sources and Notes/follow-up. Company: role, confidence, source and website on one line. Person: LinkedIn/email/phone/confidence.
- Record the exact IDs of **list, campaign and deal**, even if the list holds only one partner. "No list/campaign" is not an invented ID. Preserve **draft**; writing a local lead file does not run enrichment or publish/send campaigns.

## 6. Checklist before closing

- [ ] **At least 5 contacts (named people) per project ≥10 dwellings.** Priority: developer/JV partners (directors, founders, development/project managers, sales) → DA planner → architect → builder → other DA consultants. Each with a real role and company; if you cannot reach 5 after exhausting the sources, document what was searched.
- [ ] At least **one developer person with LinkedIn**; cover both JV partners. If missing, mark pending, do not fake success.
- [ ] **Enrichment attempted** or block/pending documented; provenance, result and cost.
- [ ] Type/date/outcome and units with a source; **conflicts noted**, without mixing versions, short-term or historical/current partners.
- [ ] Roles separated, exclusions justified, sources/confidence per fact, exact IDs and campaigns not sending.

## 7. Totals and costs per run

Report projects reviewed/eligible/loaded, **unique** people and appearances per project, how many with email, phone and both, lists/campaigns, cost and pending items. Do not double-count Keylin or add research and enrichment together without saying so.

**Declared totals of run 1:** 236 DAs decided, 14 approved with multiple dwelling; Marrone was already in the CRM. 7 projects loaded, 5 with a draft list/campaign; **7 unique people, 6 with email, 3 with phone**, enrichment **USD 0.72**; nothing published/sent. The rows indicate that the 3 with phone also have email; this reading is distinct from the declared totals. These are not operations performed by this repo.

Earlier reference from the user: **~USD 1.16 per project in their own session** for research, separate from enrichment. Wickham times are retrospective and overlapping: documents ~4 min, ABN 1–2, news ~1, LinkedIn/companies 1–2, consultants ~1, Apartments ~1, Realestate ~2; writing/validation on top. Not a timing or a guaranteed budget.

## Access and limits

- Brisbane: POST `/DocumentSearch/GetResult?applicationId=...`; observed download `downloadFile?fileId=...&fileName=...&flag=false&fileType=pdf`. Historical patterns, not a universal guarantee.
- If curl fails, use Chrome/CDP where available, without bypassing CAPTCHA/authentication. Browning: DDG "anomaly", Bing via curl irrelevant, Google in Chrome useful. Wickham: Realestate empty; Apartments with no developer/marketer/display suite and an outdated status; Nettleton 403 via requests, text readable through another retrieval. An access failure does not prove non-existence.
- Do not buy ASIC, guess contacts or reconstruct masked data; do not attribute rental agents/namesakes to the project. A snippet is not an article read; ABR does not prove the full ownership chain. **confirmed** for what is published; **inferred** with a reason for connections. Keep sources/dates; links, not PDFs.

## Base reports

- `/home/ubuntu/attachments/1fb09941-b4cb-4540-b3bb-a4ca33a86f42/pasted-1794536553611.txt` (run 1, transcript with no live re-validation).
- `/home/ubuntu/au_da/enrich/A007062453.md` (Wickham).
- `/home/ubuntu/attachments/07bf6493-229c-4373-a6d1-7e41a4302766/A006971478.md` (Marrone).
- `/home/ubuntu/gc_docs/findings.md` (Gold Coast; equivalent of the previously requested path `/home/ubuntu/au_da/gc_docs/findings.md`).
