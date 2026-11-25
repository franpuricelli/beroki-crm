# Hourly first WhatsApp to DA contacts

A GitHub Actions job sends one first WhatsApp message, through Volt, to a small batch of DA contacts every hour. The agent in `apps/agent` writes each message for its contact; there is no fixed text and no template. It sends only Monday to Friday, 09:00 to 17:00 in the contact's local time, in Australia and the US. The code is `beroki-leads/whatsapp/`. The workflow is `.github/workflows/da-whatsapp.yml`.

It is separate from the daily "Outreach DAs AU+US" task in `AUTOMATION.md`. It does not change that task, the Kairon campaigns or their limits. Kairon does not send this message.

## Before you turn it on

**WhatsApp requires opt-in.** A mobile number in the CRM is not consent. A contact that is not on an exclusion list did not consent. Before you set the switch, confirm that every contact who can enter the job already gave permission for WhatsApp, and that new contacts will too. The job does not check consent and there is no opt-in field. If consent is not resolved, keep the job off.

1. Create the GitHub environment `da-whatsapp` (Settings → Environments). Set its deployment branches to the default branch only.
2. Add the secrets `CRM_API_KEY`, `VOLT_API_KEY`, `KAIRON_API_KEY` and `DA_WHATSAPP_DRAFT_SECRET`.
3. Add the variables `CRM_API_URL`, `AGENT_URL`, `DA_WHATSAPP_SERVICES`, `DA_WHATSAPP_VOLT_INSTANCE_ID`, `DA_WHATSAPP_SENDER` and, if not 3, `DA_WHATSAPP_BATCH_SIZE`. `.env.example` says what each one is.
4. Set the same `DA_WHATSAPP_DRAFT_SECRET` on the agent's deployment, and deploy the agent with the `/internal/crm/whatsapp-draft` route. Without it the route answers `503` and the job sends nothing.
5. Leave `DA_WHATSAPP_SEND_ENABLED` unset. Run the workflow by hand from the default branch in `dry-run`. Read the totals, the exclusion reasons, the draft results and the Volt identity result.
6. Only with Franco's explicit approval, set `DA_WHATSAPP_SEND_ENABLED` to `true`. The next run at minute 17 sends. Set it as a **repository** variable (Settings → Secrets and variables → Actions → Variables), not in the environment: the scheduled job reads it before it enters the environment, and an environment variable is not visible there.

The schedule works only when the workflow file is on the default branch (`release`).

**Pause:** set `DA_WHATSAPP_SEND_ENABLED` to anything but `true`, then cancel the active run. Do not delete reservations.

## One run

1. **Volt identity.** `get-own-identity` must answer the configured instance, `connected`, and the configured number. Otherwise the run stops.
2. **Kairon exclusions.** People and companies, through the REST API. A failure or an answer in an unknown shape stops the run.
3. **CRM.** Every page of deals that are not archived and are in `TO_CONTACT` or `CONTACTED`. A deal needs `da_number`. When `channel` is set, it must be `DA Automation`. For each deal: its detail, its notes, each linked contact, the contact's notes and the companies.
4. **Exclusions,** in this order. The first one that applies is the reason.
   - The contact is not linked to the deal on both sides, or is archived.
   - `no_contactar`, or a flag field from `WHATSAPP["crm"]["flag_fields"]` on the contact or the deal.
   - The phone: missing, ambiguous (no `+` or `00`, two numbers, an extension), invalid, not AU or US, an AU number that is not a mobile, shared by two contacts, or the company phone. `+1` counts as the US only when the area code is a US one.
   - Another deal of the person is past `CONTACTED`. A company of the person or the deal has a deal in `INTERESTED`, `DEMO_BOOKED`, `QUALIFIED_TO_BUY`, `CONTRACT_SENT` or `CLOSED_WON`.
   - A note on the contact, or on the deal (about this contact or about nobody), says hold, wrong number or unsubscribe. The patterns are in `WHATSAPP["marks"]`.
   - A note mentions WhatsApp. On the deal, a WhatsApp note about nobody blocks every contact of that deal.
   - The contact has a sent message or an open reservation from this job.
   - Kairon: the person by LinkedIn slug or name; the company by name or domain. A company entry with `matchPastEmployees` blocks every contact, because the CRM cannot show past employers. A company entry with only a LinkedIn page blocks every contact, because it cannot be compared.
   - The zone. With a verified IANA zone in the contact field `timezone`, the job uses it; a zone outside the phone's country is a conflict. Without one, the job uses every zone of the phone's country and sends only when all of them are in hours. The project's location and a mobile prefix are never evidence of a zone.
   - Volt: a scheduled message to the number (any status), a chat with the number (archived included), a chat that matches the number with another identity, or any message in the chat. A scheduled recipient that is not a phone JID blocks every contact, because it cannot be compared.
5. **Draft,** for each contact that passed every check. The job sends the agent the CRM first name, the person's role on the deal, the project name, the verified facts and `DA_WHATSAPP_SERVICES`. It never sends a phone number, a chat or the DA number. `docs/agent.md` describes the agent's side.
   - The role must be on the deal link and must not say inferred, unconfirmed, unknown or probable. Otherwise the contact is skipped (`draft_role_unconfirmed`).
   - The project is the deal name without its DA number and postcode. The facts are the dwellings (`units`) and `Planning status: Approved` (`decision`). Without a project or a fact the contact is skipped (`draft_missing_facts`).
   - The agent answers `draft` or `review`. A review, an agent error, or a draft that fails the job's own check (length, link, email, placeholder, no greeting by name, not exactly one question, the DA number, a number not in the context) skips the contact. There is no fallback text. Three agent errors in a row stop the run.
6. **Send,** at most the batch size, in deal creation order:
   1. Check the window again.
   2. Write the reservation note to the CRM. If it fails, stop. Nothing is sent.
   3. Read the contact's notes again. The new reservation must be the only open one.
   4. Read Volt again: scheduled messages and the chat.
   5. Check the window again.
   6. Call `send-message` once, with the number (country code, no `+`), the drafted message and the configured instance.
   7. Write the `accepted` note with the Volt message ID, the UTC send time and the text that was sent.

A contact appears once, however many DA deals it is on. A dry run does the same reads and drafts up to the batch size, then stops before step 6. It never reserves, writes, schedules or sends; a guard refuses any write. Its summary has totals and reasons only: no names, phones, drafts or chat text.

## The record in the CRM

Every step is a NOTE on the contact and the deal. The first line of the body is the state:

```
da-whatsapp: reserved
reservation: r_<id>
contact: <CRM contact id>
deal: <CRM deal id>
at: <UTC time>
```

| State | Meaning |
| --- | --- |
| `reserved` | Written before Volt is called. It blocks the contact until another state closes it. |
| `accepted` | Volt accepted the message and gave its ID. The note also holds `sent-at` and, after a blank line, the text sent. This is not a delivery receipt. The contact never gets this message again. |
| `uncertain` | Volt timed out, answered an error, or gave no message ID. The message may exist. |
| `not-sent` | The job stopped before Volt and says why. It closes the reservation. |
| `released` | Written by a person after reconciliation. It closes the reservation. |

## When something fails

- **CRM fails before the reservation:** the run stops and sends nothing.
- **Volt is uncertain:** the job does not retry. It keeps the reservation, writes `uncertain` if it can, stops the run, and the run fails. Every later run lists the reservation as an alert and fails until somebody reconciles it.
- **CRM fails after Volt accepted:** the reservation stays open, the run stops and fails. The Volt chat now holds the message, so the contact stays blocked.

To reconcile: open the Volt chat with the number. If the message is there, add a note on the contact with the body `da-whatsapp: accepted` with the same `reservation:` line. If it is not, add a note on the contact with `da-whatsapp: released` and the same `reservation:` line. Only then can the contact enter a batch again.

## Exit codes

`0` clean. `1` stopped, or configuration error, and nothing is pending. `2` an alert needs reconciliation.

## Run it locally

```
cd beroki-leads
pip install -r whatsapp/requirements.txt
python -m whatsapp.run --mode dry-run
```

A local run cannot send: send mode needs GitHub Actions and the default branch.

## Not verified yet

- The text of a successful `send-message` answer. The job needs a message ID in it; without one, the first send ends `uncertain` and the run stops.
- The shape of Kairon's `GET /api/exclusion/people` and `/companies` answers. The OpenAPI document gives no schema. A shape the parser does not know stops the run.
- How the team records hold, wrong number and unsubscribe in the CRM. Only `no_contactar` exists as a field. The job reads the note patterns above.
- That a runner reaches the CRM, Volt, Kairon and the agent with the environment's keys. The first manual dry run proves it.
- What the configured model writes. A dry run does not show drafts. Start with `DA_WHATSAPP_BATCH_SIZE=1` and read the text in the first `accepted` notes in the CRM.
