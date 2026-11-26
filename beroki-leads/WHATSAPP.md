# Hourly first WhatsApp to DA contacts

`.github/workflows/da-whatsapp.yml` runs `beroki-leads/whatsapp/` at minute 17 of every hour. It sends one first WhatsApp, through Volt, to at most 15 DA contacts, Monday to Friday, 09:00 to 17:00 in the contact's local time (AU and US). The agent in `apps/agent` writes each message (`docs/agent.md`). It does not touch the daily "Outreach DAs AU+US" task or the Kairon campaigns.

## Turn it on

1. Create the GitHub environment `da-whatsapp`, deployable from the default branch only. Add the secrets and variables in `.env.example` (DA WhatsApp section).
2. Deploy the agent with the same `DA_WHATSAPP_DRAFT_SECRET`.
3. Run the workflow by hand in `dry-run` and read the summary.
4. Set the repository variable `DA_WHATSAPP_SEND_ENABLED=true`. To pause, set it to anything else and cancel the active run.

The schedule exists only once the workflow file is on the default branch.

## One run

1. A scheduled run stops at once when no AU or US zone is in hours. Otherwise Volt's default instance must be the configured instance and number, because the chat reads use the default. Kairon's people and company exclusions are read; an entry the job cannot evaluate stops the run: a person with no LinkedIn profile and no full name once normalized, or with a slug or LinkedIn URL that is not a valid profile or that disagree, a company with no name and no domain, or a company that covers past employees. Then the reservation ledger is read: `state.json` on the branch `da-whatsapp-state`, written through the GitHub API with the job's `GITHUB_TOKEN`. One open entry, or a ledger the job cannot read, stops a send run before anything else. The first send run creates the branch and the file. The ledger does not depend on CRM records, so deleting a deal or a contact does not clear a pause.
2. Every DA deal in `TO_CONTACT` or `CONTACTED` (with `da_number`, and channel `DA Automation` when set) and each linked contact is read.
3. A contact is skipped when: it is archived or `no_contactar`; the phone is missing, ambiguous, invalid, not an AU mobile or US number, shared, or the company's; another deal of the person is further on, or the company has a deal in `INTERESTED` or later; a note says hold, wrong number or unsubscribe, or mentions WhatsApp; this job already sent to it or holds an open reservation; Kairon excludes the person or the company; it is outside hours in any possible zone of the phone's country (or in the contact's `timezone` field); Volt has a chat, a message or a scheduled message for the number.
4. Contacts are taken newest deal first. When more than 80 wait for the Volt check, each hour starts at a different point of the list, so every contact is reached. The agent gets the first name, the confirmed role on the deal, the project name, the dwellings, the approval and `DA_WHATSAPP_SERVICES`. A review, an agent error or a missing fact skips the contact. Three agent errors in a row stop the run.
5. To send: check the hour, add the reservation to the ledger, write a `reserved` note on the contact, confirm it and that this contact has no other open or accepted reservation, read the contact, the deal and both sets of notes again (archive, stage, `no_contactar`, phone, hold, wrong number or unsubscribe), work out the zone again from the fresh contact, check the hour, Volt and the hour again, call `send-message` once, write an `accepted` note with the Volt message ID, the UTC time and the text, and remove the entry from the ledger. A send run stops at `DA_WHATSAPP_BATCH_SIZE` messages accepted by Volt, so a contact skipped at the last check does not use the batch; it drafts at most three times the batch.

A dry run drafts up to the batch and never reserves or sends. Its summary has totals only.

## When something fails

- An uncertain Volt result keeps the reservation, writes `uncertain`, stops the run and fails it. Nothing is retried.
- A CRM failure before the reservation sends nothing. After Volt accepted, the reservation stays open.
- An open reservation stops every later send run before Volt is called, and the run fails until someone reconciles it: open the Volt chat, add a note on the contact with `da-whatsapp: accepted` (the message is there) or `da-whatsapp: released` (it is not), plus the same `reservation:` line, then delete that entry from `state.json` on the `da-whatsapp-state` branch.

Not verified yet: a real `send-message` answer (without a message ID the send ends `uncertain`), the shape of Kairon's REST answers, and the first real drafts. Start with `DA_WHATSAPP_BATCH_SIZE=1`.
