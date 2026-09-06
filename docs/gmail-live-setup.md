# Gmail Live Setup

Updated 2026-09-06 against the implementation and the Google documentation linked below.
The previous guide recorded a successful local setup on 2026-09-02. That historical
record does not verify the current deployment, OAuth publishing status, credentials,
or worker health. Check each environment independently.

## 1. Choose Polling or Pub/Sub

Polling is the path configured in `render.yaml`. It uses the mailbox's OAuth grant
and requires no Pub/Sub resources or Application Default Credentials (ADC).

| Requirement | `gmail_poll` | `gmail_pubsub_listen` |
|---|---|---|
| Gmail API and per-user OAuth grant | Required | Required |
| Gmail Live client ID, client secret, token-encryption key | Required | Required |
| Pub/Sub topic and pull subscription | Not needed | Required |
| ADC with subscription access | Not needed | Required |
| Mailbox watch renewal | Not needed | Required |
| Trigger | Poll interval, configured as 120 seconds | Gmail notification |

Both paths call the same history reader and classification pipeline. Automatic
live syncing is Pro-only; connecting Gmail, the free historical scan, and
user-requested Scan Now are available on either plan. Scan Now's optional AI
classification is metered separately.

Pub/Sub notifications can be delayed or dropped. Keep periodic history polling as
a fallback if you deploy the listener. [Google push guidance](https://developers.google.com/workspace/gmail/api/guides/push)

## 2. Enable the API and Configure the Client

In Google Cloud Console, select the project and enable **Gmail API**. Enable
**Cloud Pub/Sub API** only if choosing the listener.

Create a **Web application** OAuth client for Gmail Live. The app uses separate
credentials and consent requests for Gmail access and Google sign-in; do not
replace the login client with the Gmail client or add Gmail scopes to login.
OAuth publishing and verification settings belong to the Cloud project: creating
another client in the same project does not create an independent consent screen.

Register the exact callback URLs needed by each environment:

- Local: `http://localhost:8000/capture/gmail/callback/`
- Deployed: `https://<your-domain>/capture/gmail/callback/`

Store the client ID and secret in the deployment's secret configuration. Avoid
printing existing credentials into logs or pasting them into support messages.

## 3. Configure Consent and Public Release Requirements

For an app serving users outside one managed Workspace organization, configure
an External audience. Request only
`https://www.googleapis.com/auth/gmail.readonly` for this feature. Add designated
testers while the app is in Testing, and verify that the consent screen identifies
the actual product and links to its public privacy policy.

`gmail.readonly` is a **restricted** scope. Google specifies restricted-scope
verification and a security assessment when restricted data is stored on or
transmitted through servers. Determine the applicable requirements and any
exceptions for the intended deployment before public release. A test-user count
alone does not establish an exemption, and publishing status is separate from
verification approval. [Google Gmail scope requirements](https://developers.google.com/workspace/gmail/api/auth/scopes)

For an External app in **Testing**, refresh tokens expire after seven days unless
only basic identity scopes are requested. Gmail access does not qualify for that
exception, including when the account belongs to the founder. The publishing
status restriction is documented; actual project status and continued refresh
operation must be verified in Google Cloud. Moving to production does not itself
prove verification approval or guarantee that a token will never be revoked.
[Google token expiry rules](https://developers.google.com/identity/protocols/oauth2#expiration)

Do not test token expiry by changing `GmailConnection.connected_at`: Google owns
the token lifetime. The current connect flow updates that field on successful
consent; changing a local timestamp cannot age the Google-issued token. Verify
continued refresh using real elapsed time and test accounts. Keep a reconnect
procedure for revoked grants, password changes and administrator restrictions.

Before inviting users, review the actual deployed privacy policy, legal entity
and contact details, Limited Use disclosures, and data sent to AI providers. Do
not rely on this guide's former assertions that the policy was either ready or
still a draft; inspect the current page and obtain the necessary review.

## 4. Configure Secrets

Required for web, polling and historical workers:

```text
GMAIL_LIVE_CLIENT_ID=<Gmail OAuth client ID>
GMAIL_LIVE_CLIENT_SECRET=<Gmail OAuth client secret>
GMAIL_LIVE_TOKEN_KEY=<Fernet key>
```

Generate the Fernet key once with the project's installed cryptography library,
store it securely, and use the same key configuration on every process accessing
these tokens. Changing it without a migration makes existing grants unreadable.

`gmail_live.is_configured()` checks these three values only. Neither Pub/Sub
setting is required to show Connect Gmail or run polling/backfill. Configuration
presence is not proof that the values are valid or that Google accepted a grant.

The worker handling queued Scan Now requests also needs `ANTHROPIC_API_KEY` for
ambiguous-thread AI classification. Without it, the deterministic scan runs and
the AI stage is skipped. Failed provider requests are reported separately and
are not charged as completed classifications.

### Key Rotation

`GMAIL_LIVE_TOKEN_KEY` accepts comma-separated keys, newest first. New tokens are
encrypted with the first; older keys remain available for decryption.

1. Put `<new>,<old>` on every affected process and restart them.
2. Run `python manage.py rotate_gmail_tokens --check` to inspect Gmail rows.
3. Run `python manage.py rotate_gmail_tokens` to re-encrypt those rows, then check again.
4. Retire an old key only after every token encrypted with it has been migrated.

The current rotation command covers `GmailConnection` rows only. Google Calendar
shares this key configuration but stores its tokens separately. If Calendar is
in use, a clean Gmail check alone does **not** establish that the old key can be
removed; retain it until Calendar tokens have also been migrated or reconnected.

## 5. Optional Pub/Sub Setup

Skip this section for a polling-only deployment.

Create a topic in the project and grant **Pub/Sub Publisher** to
`gmail-api-push@system.gserviceaccount.com`. Create a **Pull** subscription on that
topic and give the listener ADC with subscriber permissions. Use an approved
credential mechanism for the deployment rather than assuming a downloaded
service-account key is permitted by the organization.

Configure:

```text
GMAIL_LIVE_PUBSUB_TOPIC=projects/<project>/topics/<topic>
GMAIL_LIVE_PUBSUB_SUBSCRIPTION=projects/<project>/subscriptions/<subscription>
```

The listener requires the subscription and ADC. Registering a watch requires the
topic. A topic permission error is a deployment problem and does not revoke an
otherwise valid mailbox grant. Follow [Google's topic and watch setup](https://developers.google.com/workspace/gmail/api/guides/push).

## 6. Connect and Run the Workers

Connect a designated account from Settings and confirm the page reports an active
grant. If Google invalidates the grant during setup, reconnect before expecting
historical or ongoing sync to work.

Run commands from the Django application directory in the project's configured
runtime, or use the equivalent commands already declared in `render.yaml`:

| Process | Purpose | Current deployment cadence |
|---|---|---|
| `python manage.py gmail_poll --interval 120` | Keep Pro mailboxes current | Long-running worker |
| `python manage.py gmail_backfill` | Consume historical/recovery and Scan Now queues | Every five minutes |
| `python manage.py gmail_watch_renew` | Renew Pro Pub/Sub watches | Daily; needed only with Pub/Sub |
| `python manage.py gmail_pubsub_listen` | Consume Pub/Sub notifications | Optional long-running worker |

A single `gmail_poll` invocation without `--interval` runs one pass. The polling
and backfill commands support `--dry-run`: they read Google and report without
writing application data. These remain real authenticated Google requests.

Watch renewal preserves the last processed history checkpoint. When Gmail
rejects an expired checkpoint, the application atomically anchors ongoing sync
and queues the existing **free deterministic backfill**. Pending, failed or
running backfills keep their existing state; recovery never queues a paid rescan.
The historical worker must actually run for this recovery to complete.

Monitor worker health, connection status, history advancement, pending/failed
queue age and per-run results. A successful no-op tick proves the worker ran;
it does not prove that a particular mailbox refreshed or that a queued scan
completed. Verify a designated account through connect, scan, retry and reconnect
before treating the deployment as ready.

## 7. Coverage and Recovery Limits

The deterministic pipeline records supported sent mail, replies, bounces and
structured calendar evidence against existing contacts. Eligible unmatched mail
can create reviewable contact or application suggestions; the scan does not
silently turn every sender into a contact. Ambiguous prose is not proof that a
meeting happened. Scan Now may use capped, grounded AI classification for
otherwise unresolved threads when configured and credits permit.

Historical recovery uses the existing bounded scan: 365 days for contacts with
no touches; otherwise a seven-day overlap from the last touch, capped at 90 days.
The historical worker additionally scans up to 500 recent sent/bounce messages
across 180 days to support discovery. These bounds and deterministic classification
mean recovery is not a guarantee to reconstruct every message from an arbitrarily
long outage. Messages outside that scope need separately reviewed recovery.

Google Calendar is a separate optional read-only grant and sync job. Do not add
its scope to Gmail requests. Its enabled flag, API/consent setup and worker must
be verified separately before advertising Calendar sync.
