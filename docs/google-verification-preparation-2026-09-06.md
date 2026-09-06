# Networkly Google verification preparation

Prepared 6 September 2026 from the current working tree and official Google guidance. This is a submission dossier, not evidence of submission, approval, legal review, or a completed security assessment. Legal placeholders remain intentionally unresolved. Do not paste this entire internal document into Google's form; use the copy sections after completing the gates below.

## Review path and beta limits

Google documents exceptions for personal use by a few people known personally to the developer, development/testing/staging, and qualifying internal organizational use. Its help page describes personal use as fewer than 100 users. A commercial invitation beta with a 100-person application limit does not, by that number alone, establish that it meets one of these exceptions. All apps remain subject to Google's user-data policy. [Exceptions](https://support.google.com/cloud/answer/13464323?hl=en), [production guidance](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification).

The unverified-app cap is 100 new Google users in total, not a renewable monthly allowance or an approval. The application invitation count and Google's count measure different things. Publishing an External project “In production” does not verify its scopes. An External project in Testing normally has seven-day refresh tokens when it requests Gmail access. [User cap](https://support.google.com/cloud/answer/7454865?hl=en), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

`gmail.readonly` is restricted. Networkly processes Gmail on its server and retains derived records and excerpts, so it cannot claim a device-only/no-server security-assessment exception. Budget for restricted-scope review and the applicable annual assessment unless Google confirms an exception for this deployment. Assessment tier, assessor, price, and approval remain unresolved. [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes), [security assessment](https://support.google.com/cloud/answer/13465431?hl=en).

## Actual scopes and flow inventory

| Feature | Requested scopes | Current callback path | Evidence |
|---|---|---|---|
| Google sign-in | `openid`, `email`, `profile` | `/accounts/google/login/callback/` | `coverage_web/coverage_web/settings/base.py`, allauth routes |
| Connect Gmail | `https://www.googleapis.com/auth/gmail.readonly` | `/capture/gmail/callback/` | `capture/gmail_live.py`, `capture/urls.py` |
| Connect Calendar | `https://www.googleapis.com/auth/calendar.readonly` | `/capture/calendar/callback/` | `capture/gcal_live.py`, `capture/urls.py` |

Prepend the owner-confirmed production HTTPS origin to each callback. These are separate consent flows. Project-level branding, verification and revocation behavior must not be described as isolated merely because clients or local connection records differ. Capture each active client in the final demonstration.

**Calendar least-privilege decision:** the current implementation calls `calendars.get(primary)` and `events.list/get`. It reads primary-calendar identity for connection/recovery and event details for the schedule. Google now documents narrower `calendar.calendars.readonly` and `calendar.events.readonly` scopes. Before submission, compare that pair with the current broad read-only scope and either migrate and validate the flow or document why the current scope is necessary. Do not claim `calendar.readonly` is the only possible read-only choice. No scope change is made by this dossier. [Calendar scope inventory](https://developers.google.com/workspace/calendar/api/auth).

## Copy for review forms

### Product description

Networkly helps users organize their recruiting contacts, applications, interactions, and schedule in a private workspace. Users can connect Gmail to identify recruiting activity and connect Google Calendar to view their primary calendar in Networkly. Both connections are optional. Google sign-in requests identity information separately and does not grant mailbox or calendar access.

### Gmail scope justification

Networkly uses Gmail read-only access to identify recruiting interactions, replies, delivery failures, and calendar evidence in a mailbox the user chooses to connect. The server retrieves messages, processes their bodies and calendar attachments, and stores structured recruiting records with limited evidence excerpts for the user to review. Message-body access is needed to interpret delivery reports and calendar evidence; header-only metadata access would not provide this content. Networkly does not request permission to send, modify, or delete Gmail messages.

### Calendar scope justification, subject to the decision above

Networkly uses read-only Calendar access to display the user's primary-calendar events in their recruiting schedule. It reads primary-calendar metadata to identify the connected calendar and validate recovery, and reads event titles, descriptions, locations, times, and identifiers to keep the local schedule current. It does not create, edit, delete, or RSVP to Google Calendar events. Free/busy access alone does not provide the event details shown to the user.

### Data handling explanation

Networkly stores encrypted connection tokens, mailbox or calendar identifiers, and sync markers. Gmail message bodies and calendar attachments are processed on the server. The sync retains structured results and limited excerpts rather than complete messages: interaction previews may contain up to 300 characters, and stored mail facts may include a supporting sentence of up to 500 characters.

When a user triggers an enabled AI feature, relevant information is sent to Anthropic. Scan Now can send subjects and preview snippets for unresolved Gmail threads. Autopilot can send pending contact names, email addresses, firm matches, snippet evidence, and stored mail facts for review. Assistant and briefing features can use relevant recruiting and schedule context. These transfers must remain disclosed in the deployed privacy policy. Do not describe Networkly as keeping all Google data exclusively within its database or as never sharing Google-derived data with an AI provider.

Users can disconnect integrations in Settings, export recruiting records, or delete their account. Disconnect removes the stored connection and stops subsequent syncing; the application attempts Google grant revocation. Existing imported recruiting records remain until separately removed or the account is deleted. Successful Google revocation may also invalidate another connection in the same Cloud project. Account deletion does not erase provider-held copies or hosting backups immediately. The privacy policy must disclose the actual backup-retention arrangement and the retained pseudonymous beta invitation fingerprint.

### Permitted-use classification

Describe the implemented function as a recruiting productivity application that organizes a user's email-derived interactions and schedule. Select an allowed application type only if Google's exact current option matches the implemented behavior. If uncertain, explain the workflow for Google's determination instead of asserting eligibility. Confirm Limited Use compliance for all derived-data uses, including the shared aggregate delivery statistics disclosed in the policy; a policy sentence is not an independent compliance finding.

## Demonstration recording storyboard

Use a designated demo account with synthetic recruiting mail and calendar events. Record in English with the app name and relevant browser address bars readable. Do not show passwords, tokens, client secrets, unrelated private mail, or real third-party contact data. The finished video must show live behavior on the submitted environment; mock screens and source inspection cannot replace it.

| Sequence | Screen and action | Evidence to capture |
|---|---|---|
| 1 | Open the public home page, then `/welcome/privacy/` and terms | Networkly identity, product purpose, working public links, final policy |
| 2 | Sign in with Google | Actual identity consent and sign-in completion; relevant client ID visible in the authorization URL |
| 3 | Open `/welcome/settings/`, choose Connect Gmail | Explain why mail access is optional; show complete Gmail consent, app name, requested permission, and client ID |
| 4 | Return to Settings and run the available scan | Connected account, queued/running/completed state; wait for a real worker result |
| 5 | Open the resulting recruiting records | A synthetic sent/reply interaction, a supported delivery/calendar finding, and any reviewable contact suggestion; show retained evidence without claiming exhaustive capture |
| 6 | If deployed, show Scan Now and Autopilot | User trigger, AI disclosure, completed result and review action; explain the actual information transferred |
| 7 | Connect Google Calendar separately | Full consent and client ID; return to connected state, then show a matching synthetic primary-calendar event in Networkly |
| 8 | Change that synthetic event in Google Calendar and wait for sync | Updated local event and read-only behavior; disclose if the worker result cannot be demonstrated |
| 9 | Disconnect a connection in Settings | Disconnected UI and stopped connection; explain retained records and project-wide revocation effect, reconnect the other grant if required |
| 10 | Open `/welcome/export/` and account deletion confirmation | Export contents and accurate deletion explanation; use a disposable account for any actual deletion demonstration |

Upload the completed video as Unlisted on YouTube and save its URL in the submission. Google's guidance requires the complete consent flow, app name/client ID, scope-enabled functionality, and coverage of multiple clients. [Demo requirements](https://support.google.com/cloud/answer/13464321?hl=en).

## Submission gates and owner inputs

- [ ] Confirm the final public HTTPS origin and domain ownership; supply Search Console ownership evidence for authorized domains. Do not substitute a guessed domain.
- [ ] Confirm legal operator, registered address, monitored privacy/support contact, jurisdiction, and actual backup-retention period. Preserve `[LEGAL ENTITY NAME]`, `[REGISTERED ADDRESS]`, `[PRIVACY CONTACT EMAIL]`, `[JURISDICTION]`, and `[BACKUP RETENTION PERIOD]` until supplied. Review the policy's age and breach-response commitments with the responsible owner/adviser.
- [ ] Publish the final policy and public home page with matching Networkly identity, product description, privacy and terms links. Read them back without authentication.
- [ ] Read current Cloud project, External audience, branding, active client IDs/callbacks, enabled APIs, scope declarations, verification status and remaining user cap directly from Console. Prior status notes are not current approval evidence.
- [ ] Resolve Calendar scope minimization and ensure the deployed requests match the declared scopes. Do not add write scopes or Gmail scopes to identity sign-in.
- [ ] Confirm the deployed data flows, retention, provider arrangements, Limited Use compliance and assessment scope. Confirm assessment requirements with Google; obtain the requested assessment/letter when applicable.
- [ ] Complete real Gmail and Calendar connection, scan/sync, disconnect/reconnect and recovery checks. Record outcomes, environment and date. No provider acceptance test was run for this document.
- [ ] Supply the finished unlisted demonstration URL and a safe reviewer access route through the invitation gate, with a designated account and any required plan access. Keep credentials out of this repository and use Google's approved review channel for access instructions.
- [ ] Review the exact Console submission fields and factual copy, then submit within the user's authorized scope. Record submission receipt/status and Google follow-up requests. Brand publication and data-access approval are separate milestones.

The existing policy template is a draft with unresolved owner fields. This document neither fills those fields nor authorizes statements that the service is verified, certified, legally reviewed, or approved for unrestricted public onboarding.

## Source-review record

Inspected `coverage_web/coverage_web/settings/base.py`, `coverage_web/coverage_web/urls.py`, `coverage_web/capture/urls.py`, `coverage_web/capture/gmail_live.py`, `coverage_web/capture/gmail_residue.py`, `coverage_web/capture/gcal_live.py`, `coverage_web/accounts/urls.py`, and `coverage_web/templates/legal/privacy.html`; cross-checked `docs/gmail-live-setup.md`. This is a bounded source/document review. No credentials were read, external submissions made, live database tests run, or legal-page files edited by this work.
