# Automation: multifamily DA leads → CRM → Kairon

Spec for the automation. Read it together with `CONTEXT.md` (sources and rules), `METHOD.md` (research per project) and `LEAD-TEMPLATE.md` (lead file).

## How to run it
- **Code:** `franpuricelli/beroki-crm`, folder `beroki-leads/` (`pipeline/` and these .md files). The repo is the only copy of the code. Do not edit a local copy: change the repo and pull.
- **Data:** `db/` (approvals database, run logs, state) and `leads/` (lead files) live in the data folder on Franco's Mac, `/Users/francopuricelli/beroki-leads`. They are never committed to this repo.
- **Clone:** the repo is cloned inside the data folder, at `/Users/francopuricelli/beroki-leads/beroki-crm`, so the scheduled tasks can read it. The code folder is `beroki-crm/beroki-leads`.
- Requirements: Python 3.10+ and `pip install -r pipeline/requirements.txt`.
- Run, from the code folder: `git pull`, then `python -m pipeline.run --db-dir /Users/francopuricelli/beroki-leads/db` (incremental) or add `--since YYYY-MM-DD`; `--sources brisbane goldcoast ...` runs only some sources. Without `--db-dir` the pipeline writes a new empty database inside the clone.
- The council sources do not answer from Claude's cloud network. The pipeline runs on the Mac: `launchd` runs `scripts/job1.sh` in the data folder every day at 08:00 Buenos Aires. If the Mac is asleep, `launchd` runs it on wake.
- Victoria (`vicministerial`) needs Chrome open with remote debugging (`--remote-debugging-port=9222`) and Node + Playwright. If that is not available, skip the source with `--sources`.
- The Claude scheduled tasks ("Outreach DAs AU+US – Job 1" daily, "– Job 2" Mondays 09:00) read what the pipeline left and follow this spec, `CONTEXT.md`, `METHOD.md` and `LEAD-TEMPLATE.md` from the clone.
- MCPs Claude needs: Beroki CRM (the URL carries the token: treat it as a password, never write it in a file) and Kairon.

## Job 1 — Daily 08:00 America/Argentina/Buenos_Aires: new approvals
1. `python -m pipeline.run` (incremental: last decision date − 14 days per council). If an adapter fails, continue with the others and report the error.
2. Upsert into `db/approvals.csv` by `(council, application_number)`, keeping `first_seen`. Recalculate `db/frequency.csv`.
3. Filter the new rows (`first_seen` = today) that are multifamily residential, have a verified Approved decision (or an issued permit in the US) and ≥10 permanent dwellings. Exclude short-term-only, retirement only if so decided, commercial, and existing buildings with no new construction.
4. For each new project, create the minimal lead file (triage: DA, address, decision, date, type new/s81/s82/extension, units, applicant, link) with `status_lead: nuevo`.
5. Summary: number of new projects per council, top by units, and adapter errors. Do not write to the CRM or Kairon.

## Job 2 — Weekly (Monday 09:00 BA): contact research and loading
For each lead file with `status_lead: nuevo` and ≥10 dwellings (budget: about USD 0.30–1.20 per project, weekly cap to be defined):
1. Research per `METHOD.md`: real developer vs SPV, JV partners and **at least 5 named people**. If you cannot reach 5, document what was searched. Never guess emails. Do not buy ASIC extracts.
2. **CRM (Beroki):** `crm_search` before creating. One company (the developer; if unknown, the applicant entity, not marked as developer), the contacts (fields `kairon_lead_id`, `real_company`, `project_da`) and one deal per project ("<name or address> – DA <number>", with `da_number`, `address`, `units`, `decision`, `da_record` and `kairon_list`; owner Franco Puricelli). Link each contact to the deal with their role (max 80 characters). Reuse existing contacts.
3. **Kairon:**
   - One list per project with the contacts that have LinkedIn. Kairon does not load contacts without LinkedIn: those stay only in the CRM.
   - Enrichment of **emails only**, never mobiles (USD 0.02 per email). Skip people who already have an email. Write the emails found to the CRM with the note "source: Kairon".
   - Before loading, check whether the lead is already in another active or paused campaign. If so, remove it from that one and keep it in the project campaign, which is more specific.
   - One campaign per project, with no ICP filter (`icpId: null`), priority 0.
4. Update the lead file (CRM/Kairon section with the deal, list and campaign IDs and the status) and set `status_lead: en_campaña`. Save the changes.

## Sequence of each campaign (copy the structure of Wickham `camp_01m795vrdneh78rcxj2rxewvzx`)
- English, `{{firstName}}`. Steps: E1 → 1 day → LinkedIn invitation (L1) → wait 1 day.
  - **If accepted:** 2 h → L2 with `Beroki_Portfolio.pdf` → E2 → L3 → E3 → M4 → E4 → M5 → E5, 1 day between each.
  - **If not accepted:** E2 → visit profile → E3 → like latest post → E4 → follow profile → E5 → visit profile → wait 14 days and withdraw the invitation.
  - **Late acceptance:** L2 with the portfolio and resume the emails.
- Sending window: Monday to Friday, 09:00–17:00 Australia/Brisbane.
- E1, subject: `Congrats on the <project> approval!`. Body: "Congrats on the <project> approval." + one real fact from the lead file (units, storeys, type) + "We'd like to handle the visualisation for the project: exteriors, interiors and the launch imagery. We're doing that for Niecon's Reflections on the Broadwater right now." + closing question. Signature "Franco\nBeroki (by Render a House)". No DA number, no postcode.
- If the contact is a third party (planner, architect or consultant): ask for an introduction ("Who at <developer> handles the visuals?").
- **L1 (invitation with note) always has a CTA**, ≤200 characters. E.g.: "Hi {{firstName}}! Congrats on the <project> approval. Could I send you a few renders from similar projects?"
- M4: "would a 15 minute call this week work…". M5 and E5: friendly close.

## Senders
- LinkedIn Franco `chan_01m1er9jhffk4bzj4n90sgnf7g`: 30 invitations/day, shared across all his campaigns in priority order. He keeps the 19 Brisbane DA campaigns; their limits and sequences were not changed. Campaigns with no priority can be left with no quota behind the prioritised ones.
- LinkedIn Sebastián `chan_01m7b6gznzesp8pgryxf3nxggt`: **20 invitations/day for the account**, configured and verified on 2026-11-13 UTC. Only sender of the 11 new active campaigns (9 GC + Marrone + The Isles; 27 people, no runs before the change), with a seat limit of 20/day per campaign, priority 0 and window Monday–Friday 09–17 Brisbane. Assignment is by whole campaign, not rotation inside a campaign. These 11 are published v2, **LinkedIn-only**, with no email and no invitation note: acceptance → 2 h → L2 (congratulation, project fact, CTA and Beroki_Portfolio.pdf, Sebastián's voice/signature) → 1 day → L3 → 1 day → M4 → 1 day → M5. No acceptance: visit/like/follow and waits → final wait 14 days with withdrawal; late acceptance → 2 h → L2. The 9 empty DA campaigns stay in draft, unchanged.
- Reactivation keeps its senders David + Sebastián, priority 3 and an effective limit of 5 per seat; it was not modified. Its invitations from Sebastián share the account maximum of 20 with the 11 DA campaigns (priority 0); its existing runs keep consuming actions. This is not 20 invitations per campaign, and there are no 5 extra invitations reserved for Reactivation.
- Connected mailboxes: `franco@renderahouse.org`, `fran@renderahouse.org` and `david@renderahouse.org`, 30/day each, unchanged. `sp@renderahouse.org` and `sebastian@renderahouse.org` were **not connected** at the last readback: do not send email from the 11 campaigns and do not reintroduce email steps automatically. Connecting them, and any cost, warm-up and reactivation of the channel, need separate approval; later target 30/day per mailbox and signature "Sebastián
Beroki (by Render a House)".
- Each lead keeps the same sender for the whole sequence.

## Guardrails
- Activate campaigns only if the user authorised it for that batch (so far yes for the DAs). Never enrich mobiles unless asked. Do not create paid items (ASIC, extra seats).
- No duplicates: search the CRM and Kairon before creating.
- Always separate `confirmed` from `inferred`. Do not assume a planner or architect is the developer.
- Report for each run: new projects, people, how many with email/phone/LinkedIn, campaigns created/activated, Kairon spend and errors.

## Job 3 (optional) — Daily: campaign monitoring
Read the DA campaigns: sent, scheduled, replies, and active campaigns with 0 capacity. If a lead replied, move the deal to the matching stage in the CRM and notify.
