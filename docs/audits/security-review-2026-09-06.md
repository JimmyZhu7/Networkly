# Networkly security and privacy review, 6 September 2026

Scope: workstream 4 of the pre-payment beta launch preparation. Reviewed at
commit `38b38c6` ("Checkpoint the 6 September handoff as a revision"), which is
the tip of `codex/coverage-ui-refurbishment`. The diff under review is
`main..HEAD`: 506 files, 19983 insertions.

This is a source and configuration review with focused local test runs. It is
not a penetration test, a legal review, or a completed third-party security
assessment, and nothing in it should be quoted as one. No provider was called,
no key was rotated, no production data was read, and no environment value is
printed anywhere below.

Every finding names a file and a line. Where the fix landed inside this
workstream's file ownership it was made and is marked FIXED. Where it did not,
the finding carries a proposed patch and is marked FOR THE OWNER.

Interpreter for every command below:
`/Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python`, run from the
worktree root with `DJANGO_SETTINGS_MODULE=coverage_web.settings.local`.

---

## Verdict

**No launch blocker was found in the security posture itself.** The
authorization model is the strongest part of this codebase: `PrivateModel`'s
manager (`coverage_web/coverage_web/tenancy.py:66`) raises on an unscoped
tenant query, so a cross-tenant read is a loud runtime error rather than a
silent leak, and every one of the 33 `get_object_or_404` call sites on tenant
data is `for_user`-scoped.

Three things should be settled before the beta opens. None is a vulnerability;
two are honesty gaps and one is an availability risk on the public feed.

| | Item | Severity | Owner |
|---|---|---|---|
| B1 | Privacy page described AI mail classification as Scan Now only, while ordinary sync already sends subjects and snippets to Anthropic | High for a Google restricted-scope submission | FIXED here |
| B2 | Two processors missing from the published provider list: the avatar object store, and the shared cache holding sign-in counters keyed by email | High for the same reason | FIXED here |
| B3 | `Firm.logo_url` calls `.url` on a storage that refuses non-avatar keys; a firm with a DB logo and no generated static PNG returns 400 on the public Opportunities feed | Medium, availability, data-dependent | FOR THE OWNER (`directory/`) |

---

## 1. Authentication and authorization

### Proof

Full census of the resolved URLconf, view by view, cross-checked against each
callback's decorators and each queryset's tenant scoping. Encoded as a
permanent test rather than left as a document:

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/core/tests/test_route_auth_coverage.py -q
    # 114 passed

### Result

116 first-party routes plus django-allauth's own mount. 94 view functions carry
`@login_required`; four carry `@staff_member_required` (`ops.views.health_cron`
`ops/views.py:41`, `ops.views.health_gmail` `ops/views.py:80`,
`analytics.views.dashboard` `analytics/views.py:181`, and Django's admin at
`coverage_web/coverage_web/urls.py:26`). Both `/ops/health/*` endpoints are
correctly staff-gated, which matters because `health_gmail` returns other
users' `user_email` and `gmail_address` at `ops/views.py:117`.

The private media route is registered at `coverage_web/coverage_web/urls.py:80`
and enforces ownership in the body rather than by decorator, deliberately:
`core/media.py:11` requires an authenticated, active, undeleted user whose own
`avatar.name` equals the requested path. `@login_required` would be strictly
weaker there, since it would admit any signed-in user to any other user's key.

Object-level ownership: every `all_objects` use in the view layer carries an
explicit `user=request.user`. The two genuine cross-tenant reads
(`accounts/views.py:1189` and `:1196`, push-endpoint uniqueness) are guarded at
`accounts/views.py:1191`, which 409s when the endpoint belongs to another
account.

### 1.1 The posture has no backstop — FIXED

`settings/base.py:252-297` contains no login-enforcing middleware. Authentication
is therefore one hundred percent per-view decorator, and a view added without
one is public, looks exactly like a view that is public on purpose, and nothing
notices. That is a working design; what it lacked was a control.

Added `coverage_web/core/tests/test_route_auth_coverage.py`. It walks the
resolver, reads each first-party callback's own decorator lines, and requires
either a gate or an entry in one of two declared lists (`PUBLIC`, for routes
that answer anonymous callers on purpose; `GATED_IN_BODY`, for the media route).
Adding a public route is still a one-line change. It stops being a silent one.

Source inspection rather than object introspection is deliberate:
`login_required` returns a `functools.wraps` closure that copies `__module__`,
`__name__` and `__doc__`, so a wrapped and an unwrapped view are nearly
indistinguishable as objects, and the parts that differ are Django internals a
version bump may reshape.

### 1.2 `university_search` is anonymous and unthrottled — FOR THE OWNER

`coverage_web/accounts/urls.py:30` binds `accounts.views.university_search`
(`coverage_web/accounts/views.py:1315`), which carries only `@require_GET`.
`accounts/urls.py:7-10` states the contract this breaks in its own words:
"Everything is login-required except the two legal pages and the digest
unsubscribe link."

It leaks nothing. It serves a bundled `accounts/data/universities.json`
(`accounts/views.py:1306`) and reads no tenant data. But it is the only
anonymous scanning endpoint in the app without the per-IP burst guard that both
`core.views.search` (`core/views.py:165`) and `billing.views.waitlist_join`
(`billing/views.py:107`) carry, and it does an O(10k) Python scan per call.

Proposed patch, `coverage_web/accounts/views.py`:

```python
+from core.views import _search_throttled   # the shared per-IP guard
+
 @require_GET
 def university_search(request) -> HttpResponse:
+    if _search_throttled(request):
+        return HttpResponse(status=429)
```

Recorded in `test_route_auth_coverage.py`'s `PUBLIC` dict with this finding's
number, so the test states today's truth instead of failing on a known item.

### 1.3 `calendar_ics` compares its bearer token with a plain filter — NOTED

`coverage_web/crm/calendar_views.py:823` looks the user up with
`filter(calendar_token=token)`. Not constant time. The token is server-generated
and rotatable (`calendar_views.py:701`), the comparison happens inside Postgres
across a network hop, and the code documents the trade at `calendar_views.py:704`.
No change recommended; recorded because it is the one route where a leaked path
component discloses a full read-only calendar.

---

## 2. Invitation enforcement

### Proof

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/accounts/tests/test_beta_admission.py -q
    # 27 passed

### Result

No gap found. All three allauth hooks check admission
(`accounts/adapter.py:385` `pre_social_login`, `:395` `is_open_for_signup`,
`:401` `save_user`), and the local path is closed twice over: the account
adapter's `is_open_for_signup` returns False while the beta is on
(`adapter.py:321`) and its `save_user` hard-denies unless the request carries
`_beta_google_signup` (`adapter.py:326`), a flag set only inside the social
adapter's `claim_invitation` closure (`adapter.py:410`).

`_verified_google_email` (`adapter.py:358`) requires provider `google`, a
provider-asserted `email_verified`, membership in the *verified*
`sociallogin.email_addresses` set, agreement with `sociallogin.user.email`, and
agreement with `form.cleaned_data["email"]` when a signup form is present. That
last clause is what stops a signup form substituting somebody else's invited
address.

Concurrency is real, not asserted: `beta.registry_lock` (`accounts/beta.py:166`)
takes `pg_advisory_xact_lock` and refuses to run outside PostgreSQL, and
`test_simultaneous_last_seat_reservations_are_serialized`
(`test_beta_admission.py:323`) races two threads on the last seat through the
live test connection and asserts exactly one wins.

Deleted seats stay consumed through a `pre_delete` receiver on `User`
(`accounts/models.py:396`) rather than through the deletion view, so admin and
queryset deletions are covered too. `BetaInvitation.delete` raises outright
(`accounts/models.py:390`).

---

## 3. CSRF

### Proof

    grep -rn "csrf_exempt" --include='*.py' coverage_web/ | grep -v '/tests/'
    # coverage_web/billing/views.py:20, :70   (the only two hits, one import)

### Result

`CsrfViewMiddleware` is installed (`settings/base.py:275`), and there is exactly
one exemption in the repo: the Stripe webhook, where a session token is
meaningless and the HMAC is the authentication. It verifies before it acts
(`billing/views.py:88` into `stripe_gateway.py:184`
`stripe.Webhook.construct_event`) and 400s on an unconfigured deploy
(`billing/views.py:84`) rather than 500ing or accepting an unsigned body.

Browser-side state changes are covered on both shapes. Every `hx-post` is either
inside a `<form>` carrying `{% csrf_token %}` or under an ancestor with
`hx-headers='{"X-CSRFToken": ...}'` (`crm/_contact_live.html:129`, `:159`;
`crm/week.html:130`, `:136`; `directory/_results.html:115`). The five raw
`fetch(..., {method: "POST"})` calls either set the header explicitly
(`base.html:1206`, `crm/contact_list.html:1175`, `accounts/settings.html:1028`,
`static/js/push-subscribe.js:32`) or post a `FormData` built from a form that
contains the token (`assistant/chat.html:2244` into `:2179`).

### 3.1 The webhook reflects internal error text to an unauthenticated caller — FOR THE OWNER

`coverage_web/billing/views.py:89`:

```python
    except stripe_gateway.StripeGatewayError as exc:
        return HttpResponseBadRequest(str(exc))
```

The message is built at `stripe_gateway.py:188` as
`f"invalid Stripe webhook payload/signature: {exc}"`, so the Stripe SDK's own
exception text is returned as `text/html` to anyone who can POST to the
endpoint. Today's SDK messages are constant strings, which is why this is Low
and not Medium — but it is a fragile assumption, and it contradicts the
discipline the same file applies four lines earlier at `billing/views.py:64`,
where a provider error is logged as `type(exc).__name__` precisely because
"provider errors may contain request or account details."

Proposed patch:

```python
     except stripe_gateway.StripeGatewayError as exc:
-        return HttpResponseBadRequest(str(exc))
+        # Stripe's retry logic only needs the 4xx. The reason is ours.
+        logger.warning("Stripe webhook rejected: %s", type(exc).__name__)
+        return HttpResponseBadRequest("Rejected.")
```

---

## 4. Uploads

### Proof

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/core/tests/test_private_media.py \
      coverage_web/core/tests/test_private_storage.py \
      coverage_web/core/tests/test_media_serving.py -q
    # 45 passed

### Result

No gap found, and this is the part of the codebase that reads as if it were
written by someone who has seen an upload go wrong.

`ProfileForm.clean_avatar` (`accounts/forms.py:448`) enforces an 8 MB ceiling
before it hands anything to the decoder, applies EXIF orientation and then drops
the block (`ImageOps.exif_transpose` at `:484`, so GPS coordinates in a phone
photo do not ride along with the profile picture), centre-crops to 512px, and
re-encodes through Pillow. The stored bytes are ones Pillow wrote. The type
comes from the decode, not the extension and not the `Content-Type` header — the
`accept="image/*"` attribute is commented in the source as a picker hint rather
than a control (`forms.py:302`). The filename is `uuid4().hex` (`forms.py:510`),
never the uploaded name, so it is neither attacker-controlled nor guessable, and
two users uploading `profile.jpg` cannot collide or probe for each other.

Serving is ownership-checked at `core/media.py:11` and the path is validated
independently at `core/storage.py:507`, which rejects backslashes, NULs, any
name outside `avatars/`, any path whose `PurePosixPath` round-trip differs from
the input, any `.`/`..` component, and any extension outside jpg/jpeg/png. The
response carries `Cache-Control: private, no-store` and `X-Content-Type-Options:
nosniff` (`media.py:27`).

Noted, not a finding: Pillow's default decompression-bomb ceiling
(`MAX_IMAGE_PIXELS`) is the only bound on the raster a valid 8 MB PNG can expand
to inside `ImageOps.fit`. In scope terms this is resource exhaustion, which this
review does not report.

---

## 5. Exports

### Proof

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/accounts/tests/test_export.py -q
    # 22 passed

Plus a mechanical sweep of every builder for an unscoped query:

    python3 -c "…"   # regex walk of accounts/services.py, 35 *_csv builders

### Result

No gap found. All 35 export builders are `for_user`-scoped. The one query that
is not is `fit_scores_csv`'s `Firm.objects.filter(id__in=firm_ids)`
(`accounts/services.py:1144`), a name lookup against shared-directory data whose
ids came from the caller's own fit scores.

Nothing is written to disk: `export_zip` (`accounts/services.py:1456`) builds
the archive in a `BytesIO` and hands it straight to the response, so the
"world-readable file" question does not arise. No token or secret is exported:
`gmail_connection_csv` (`:1262`) and `gcal_connection_csv` (`:1273`) return the
address and status columns only, and `push_subscriptions_csv` (`:1284`) returns
the user agent and creation time, not the subscription keys.

CSV formula injection is already closed twice over, which is worth recording
because it is the failure most export code has: `_csv` (`accounts/services.py:783`)
writes through defusedcsv, and `_neutralise_tab_or_cr_lead` closes the leading
tab/CR gap defusedcsv leaves.

---

## 6. Account deletion, checked against the page

### Proof

Rather than reading the list, enumerated every concrete `PrivateModel` subclass
at runtime and diffed it against `accounts.services._DELETE_ORDER`:

    python /private/tmp/.../delcheck.py
    # 31 concrete PrivateModel subclasses; 31 in _DELETE_ORDER
    # every one OK

### Result

The deletion path is complete and the page is accurate about the database, with
one exception, below.

`delete_user_and_data` (`accounts/services.py:1554`) revokes both Google grants
first and outside the transaction (`google_revoke.revoke_all_for_user`, which
never raises), deletes all 31 tenant tables in child-before-parent order with
`.for_user(user)`, deletes the user row, and removes the avatar from storage on
commit. The beta seat is anonymised by the `pre_delete` receiver
(`accounts/models.py:396`), which clears the address and the account link and
retains the SHA-256 fingerprint plus the two dates — exactly what the Retention
section says it retains. Uploaded CSVs are parsed rows, not files: `Import`
(`analytics/models.py:95`) has no FileField, and the only FileFields in the app
are `User.avatar` and `Firm.logo`.

### 6.1 Sessions on other devices outlive the account — FOR THE OWNER

`accounts/views.py:1072` calls `logout(request)`, which flushes the *requesting*
session only. `SESSION_ENGINE` is unset, so sessions are DB-backed, and
`django_session` has no foreign key for `user.delete()` to cascade. There is
also no `clearsessions` job anywhere in the repo or in `render.yaml`, so expired
rows are never purged either.

The rows are harmless in the sense that matters: the account they name is gone,
so they authenticate nobody. But `services.sign_out_other_sessions`
(`accounts/services.py:70`) already exists, already does exactly this, and is
simply not called from the deletion path.

Proposed patch, `coverage_web/accounts/services.py::delete_user_and_data`:

```python
     google_revoke.revoke_all_for_user(user)
+    # Every device, not just the one asking. `logout(request)` in the view
+    # flushes the caller's session; these rows have no FK to cascade from.
+    sign_out_other_sessions(user)
```

and a `clearsessions` entry alongside the other crons in `render.yaml`.

Per the workstream rule, the page was corrected to match the code rather than
the reverse. The Retention section now says plainly that sessions on other
devices are not removed at that moment, that they stop working immediately, and
that they carry no readable personal information. If the patch above lands, that
sentence should come back out.

---

## 7. Token and secret handling

### Proof

    git log -p main..HEAD > branch.patch          # 3.4 MB
    grep -nE '^\+' branch.patch | grep -inE 'sk-ant-…|sk_live_|whsec_|AKIA…|
      GOCSPX-…|BEGIN .* PRIVATE KEY|eyJ….….…|re_…|hc-ping\.com/…|<uuid>'

### Result

**No secret is committed on this branch.** Eight matches, every one a test
fixture with a self-describing value. Naming the files only, per the rule:

- `coverage_web/billing/tests/test_stripe_gateway.py` (three)
- `coverage_web/ops/tests/test_deploy_preflight_beta.py` (two)
- `coverage_web/assistant/tests/test_agent.py` (one, plus the assertion that it
  does *not* appear in a log line)
- `coverage_web/core/tests/test_migrate_avatar_storage.py` (one UUID filename)
- `coverage_web/capture/tests/test_gmail_history_recovery.py` (one message id)

`docs/liam-safe-draft-2026-08-29.md` is absent from the tree and has never been
committed on any ref (`git log --all --diff-filter=A` returns nothing). `.env`
has never been committed on any ref. `.gitignore:42` covers it, and the
symlink created for this review is confirmed ignored by `git check-ignore -v`.

`deploy_preflight` cannot print a value by construction, which is a nicer
property than "does not": its `Check` class has `__slots__ = ("level", "keys",
"message")` and its docstring says there is nowhere in the class to put a value
(`ops/management/commands/deploy_preflight.py:99`). Confirmed by reading every
`stdout.write` in the command.

Refresh tokens are Fernet-encrypted under a `MultiFernet` ring. Not touched, not
rotated, per instruction.

### 7.1 A heartbeat URL can reach the logs — FOR THE OWNER

`coverage_web/ops/tracking.py:89`:

```python
    except requests.RequestException:
        logger.exception("healthcheck ping failed for job %r", name)
```

The format string is innocent — it interpolates the job name — but
`logger.exception` emits the traceback, and a `requests.RequestException`'s own
message embeds the full request URL (`Max retries exceeded with url:
/<ping-uuid>`). The healthchecks.io ping UUID *is* the credential.
`settings/base.py:941` says so in as many words: "a bare, unauthenticated ping
endpoint (anyone who has it can ping 'success' for that check), so it belongs in
the deploy environment, not source control, same reasoning as every other
secret-shaped value on this page." A DNS blip on any of the ten cron jobs writes
one into Render's log stream.

Sentry is not exposed: `scrub_sentry_event` replaces every exception value with
`[Filtered]` (`core/monitoring.py:39`) and pops `logentry` and `message`. The
plaintext log stream is.

Proposed patch:

```python
     except requests.RequestException:
-        logger.exception("healthcheck ping failed for job %r", name)
+        # NOT logger.exception, and not %s of the exception either: a
+        # requests error carries the full URL, and the ping UUID is the
+        # credential (settings/base.py's HEALTHCHECK_URL_* comment).
+        logger.warning("healthcheck ping failed for job %r", name)
```

Checked for the same shape elsewhere and did not find it.
`capture/google_revoke.py:70` logs `%s` of a `RequestException`, but that call
is a POST to the constant `https://oauth2.googleapis.com/revoke` with the token
in the body, so the message carries the endpoint and nothing else — which is
what that module's docstring claims at `google_revoke.py:30`, and the claim
holds.

### 7.2 A contact's email address is logged at WARNING — NOTED

`coverage_web/crm/region_enrich.py:290` and `:293` log `%r` of a contact's
address on an API error. Not a secret, and the privacy page's "we do not put
email bodies in our logs" is about bodies, so nothing is contradicted. Recorded
because it is third-party personal data in a log stream, and the cheapest fix is
to log the contact's primary key instead.

---

## 8. Logging and Sentry scrubbing

### Proof

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/core/tests/test_sentry_privacy_settings.py -q
    # 3 passed

That suite parses `settings/production.py`'s actual `if SENTRY_DSN:` block out
of the AST and executes it against a mock `sentry_sdk`, so it asserts on the
shipped configuration rather than on a copy of it.

### Result

Verified, and the docs' claims hold. `send_default_pii=False`,
`include_local_variables=False`, `max_request_body_size="never"`,
`traces_sample_rate=0.0`, `enable_logs=False`, `before_send=scrub_sentry_event`
— all asserted by name at `test_sentry_privacy_settings.py:35-41`.

The scrubber (`core/monitoring.py:12`) pops `breadcrumbs`, `user`, `extra`,
`message` and `logentry`; strips request `headers`, `cookies`, `data`,
`query_string` and `env`; reduces the URL to scheme, authority and path, which
drops both the query string and any `user:pass@` in it; and replaces every
exception `value` with `[Filtered]` while keeping the type and the stack frames.
A denylist of credential names would not be enough here and the module says why:
provider exception messages can contain mailbox content.

No user email can reach breadcrumbs or tags: `user` is popped wholesale, and
breadcrumbs with it.

---

## 9. Third-party data flows, checked against the page

Every outbound destination in the codebase that can carry user data, and whether
the published policy names it.

| Destination | User data sent | Trigger | On the page? |
|---|---|---|---|
| Anthropic — advisor (`assistant/agent.py:855`, `tools.py:1083`) | profile, contact names, firms, roles, notes, interactions, **Gmail subject lines**; `has_email` bool, never the address | user | now yes (subjects added) |
| Anthropic — daily brief (`assistant/brief.py:963`) | contact and firm names, queue lines | user | yes |
| Anthropic — Autopilot (`capture/autopilot.py:453`) | `PERSON: {name} <{email}>`, firm, evidence, subject; 200 rows/run | user-started worker | yes, correctly including the address |
| Anthropic — Scan Now (`capture/gmail_residue.py:193`) | subject + snippet, ≤100 threads | user | yes |
| Anthropic — **ordinary sync** (`capture/appmail.py:636`, `capture/mailfacts.py:675` via `directory/ai_extract.py:521`, `:623`) | subject + snippet | **background worker** | **was missing; now yes** |
| Anthropic — contact summary / coffee-chat brief (`crm/ai_summary.py:176`, `crm/ai_brief.py:201`) | contact name, firm, role, angle, notes | user | yes |
| Google — sign-in (`settings/base.py:567`) | identity only | user | yes |
| Google — Gmail read (`capture/gmail_live.py:976`) | OAuth token | worker | yes |
| Google — **Gmail search** (`capture/gmail_live.py:2255`) | **a contact's email address as a query term** | worker | **was missing; now yes** |
| Google — Calendar (`capture/gcal_live.py:451`) | OAuth token | worker | yes |
| Google — revoke (`capture/google_revoke.py:64`) | refresh token, in the body | user | yes |
| Push relay (`accounts/push.py:136`) | firm name and role title, **AES128GCM-encrypted to the subscription**; relay sees only the endpoint and the operator's VAPID `sub` | cron | yes |
| SMTP / Resend (`crm/management/commands/send_weekly_digest.py:165`) | recipient address and full digest body | cron and user | yes |
| Sentry (`settings/production.py:148`) | scrubbed technical data only | on error | yes |
| **Object store, S3 API** (`core/storage.py:579`, `production.py:131`) | **the profile picture** | user | **was missing; now yes** |
| **Shared cache / Redis** (`settings/base.py:521`) | **the email address typed at sign-in, as a rate-limit key** | user | **was missing; now yes** |
| Stripe (`billing/stripe_gateway.py:153`) | `user_id` and pack key only; no name, no address | user | not listed — see below |
| healthchecks.io (`ops/tracking.py:88`) | none, a bare GET | cron | correctly absent |
| Job boards / ATS (`coverage_connectors/http.py:102`) | none; fixed UA, no cookies, no per-user params | cron | correctly absent |
| LinkedIn (`crm/sourcing.py:296`) | none; a link the browser follows, no server request | user | correctly absent |

Stripe is the one omission left standing, deliberately. It is off in beta
(`is_configured()` requires both keys, `stripe_gateway.py:112`), and even when
on, the only thing Networkly sends is an opaque internal id — the payer's card
and email go to Stripe's own hosted page, under Stripe's own policy. **If Stripe
is ever enabled, the provider list needs a payment-processor bullet before the
first checkout.**

### 9.1 The page said Scan Now when the code says every sync — FIXED

`capture/gmail.py:1261` calls `appmail.consider_finding` and `:1322` calls
`mailfacts.consider_finding`, neither passing `allow_ai`, and both default it to
`True` (`appmail.py:552`, `mailfacts.py:611`). So a subject and Gmail snippet go
to Anthropic during ordinary background sync whenever the deterministic rules
come up empty. The page framed that transfer as something that happens only when
the student presses Scan Now.

This is the finding with the most consequence outside the codebase. The
verification dossier's own instruction is
`docs/google-verification-preparation-2026-09-06.md:44`: "Do not describe
Networkly as keeping all Google data exclusively within its database or as never
sharing Google-derived data with an AI provider." A restricted-scope reviewer who
compares the deployed policy against the running code would find the narrower
claim.

Rewritten to name both paths. Guarded by
`test_ai_classification_is_not_described_as_scan_now_only`.

### 9.2 Two processors were missing from the provider list — FIXED

Avatars leave Render entirely once `MEDIA_S3_*` is set, and the shared cache
holds allauth's and axes' counters keyed by the address typed at sign-in. The
page named Render alone, so a reader would reasonably conclude their photo sits
where their database rows sit. Two bullets added, each describing what the
provider actually holds.

### 9.3 The advisor sends mail subject lines — FIXED

`assistant/tools.py:1094` puts `recent_subjects` — real Gmail subject lines,
three per contact, 120 characters each — into the advisor's contact payload. The
bullet listed CRM fields only, so Google-derived data was reaching Anthropic
through a route the page did not name.

The same bullet's claim that contact **email addresses** are excluded is
correct and was left alone: `tools.py:1094` sends `"has_email": bool(...)`, and
`tools.py:158` documents the exclusion. The page's asymmetry between the advisor
and Autopilot mirrors the code's asymmetry exactly, which is the right outcome
even though the two modules disagree with each other.

### 9.4 Contact addresses travel to Google — FIXED

`capture/gmail_live.py:2255` builds `(from:{email} OR to:{email})` queries.
Every read of the mailbox is also a write of a third party's address into
Google's query log. The page described the flow one way round only.

---

## 10. Production security headers

### Proof

Booted `coverage_web.settings.production` with dummy env (`DJANGO_SECRET_KEY`,
`DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, empty `SENTRY_DSN` and
`REDIS_URL`) and read the headers off a real response through Django's test
client.

### Result

All present and correct.

```
Strict-Transport-Security: max-age=604800; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: same-origin
Cross-Origin-Opener-Policy: same-origin
Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=()
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-…';
  style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self';
  connect-src 'self'; object-src 'none'; base-uri 'self';
  form-action 'self' https://accounts.google.com; frame-ancestors 'none'
```

`SECURE_HSTS_PRELOAD` is False, which is the honest setting at a seven-day
max-age and is argued at length at `settings/production.py:76-94`: the `preload`
token is a claim about meeting hstspreload.org's one-year bar, not a request, and
it is a one-way door.

CSP is real rather than report-only, with a nonce for scripts and no
`unsafe-inline` on `script-src`. `style-src` keeps `unsafe-inline`; that is a
known limitation of nonces over `style` attributes and is documented at
`settings/base.py:332`.

---

## 11. Rate limiting and lockout

### Result

Correct on both the cache and the counter, and for the reason that matters:
neither is allowed to be quietly worthless.

`settings/base.py:520` switches `CACHES` to `RedisCache` when `REDIS_URL` is
set and LocMemCache otherwise, and `AXES_HANDLER` (`base.py:655`) switches on
the same condition — cache handler only when there is a real shared cache,
database handler otherwise. The alternative, which this block exists to avoid, is
the cache handler over LocMemCache under `gunicorn --workers 3`: three
independent allowances, all reset on every deploy.

`AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]` (`base.py:621`) is the
combination, not either alone, so knowing a staff address cannot be used to lock
the founder out of his own admin. `AXES_USERNAME_FORM_FIELD = "username"`
(`base.py:632`) is load-bearing and the comment records how it was found: Django's
admin form posts a field literally named `username`, so on the default (the
model's `USERNAME_FIELD`, which is `email` here) axes recorded a null username
and the pair collapsed to IP alone.

Axes is scoped to the admin site through both `AXES_ONLY_ADMIN_SITE` and
`AXES_WHITELIST_CALLABLE` (`core/axes_scope.py`), because the first is consulted
in `is_allowed` and not in `user_login_failed`. allauth counts its own form.

`settings/local.py:15` pins LocMemCache and `:22` pins the database handler for
development, and `:27` empties `HEALTHCHECK_URLS` so a local `.env` holding
production heartbeat credentials cannot keep a suspended production check alive.

---

## Cross-cutting: the Firm logo will 400 the public feed

Not a security finding. Recorded here because it was found during this review
and it is the only thing in this report that can take a page down.

`directory/models.py:147`:

```python
        return self.logo.url if self.logo else ""
```

`Firm.logo` is an `ImageField(upload_to="firm-logos/")` (`directory/models.py:108`)
on the *default* storage, which in production is now `PrivateMediaStorage`
(`settings/production.py:131`). `PrivateMediaStorage.url` calls
`avatar_content_type(name)` (`core/storage.py:552`), which raises
`SuspiciousFileOperation` for any key not under `avatars/`. Django turns a
`SuspiciousOperation` into a 400.

`directory/views.py:2994` and `:3900` read `o.firm.logo_url` while rendering the
public Opportunities feed. `logo_url` tries the generated static PNG first, so
the blast radius is exactly: any firm that has a row-level `logo` and no
`static/img/firm-logos/<slug>.png`. `fetch_firm_logos` still writes to the field
(`fetch_firm_logos.py:519`), and `audit_firm_logos.py:50` reads `firm.logo.path`,
which S3 storage does not implement at all.

Whether this is live or latent depends on the production `firms` table, which
this review did not query. Confirm before deploy. The narrow fix that keeps the
monogram fallback doing its job:

```python
-        return self.logo.url if self.logo else ""
+        if not self.logo:
+            return ""
+        try:
+            return self.logo.url
+        except (SuspiciousFileOperation, NotImplementedError):
+            # Firm marks are shared-zone public assets; the private avatar
+            # storage has no route for them, and the monogram is the
+            # documented final fallback. Never a 400 on the public feed.
+            return ""
```

The longer fix is to give firm logos their own storage alias rather than sharing
the private default. That is a `directory/` decision, not this workstream's.

---

## What was checked and found clean

Recorded so a re-review does not spend the time twice.

- **No new XSS.** No `mark_safe`, `format_html`, `|safe`, `json_script` or
  `{% autoescape off %}` is added anywhere in `main..HEAD`.
  `core/templatetags/textstyle.py` returns plain `str`. The streaming chat client
  escapes before it layers markup (`assistant/chat.html`).
- **No SQL injection.** Every added `cursor.execute` is a parameterised advisory
  lock (`accounts/beta.py:172`, `assistant/locks.py:41`). No `RawSQL`, no
  `.extra(`, no f-string SQL in application code.
- **No unsafe deserialization or shell.** No `pickle`, `yaml.load`, `eval` or
  `exec` in production code. `core/management/commands/backup_db.py` uses
  `subprocess.run` with an argv list and no `shell=True`, layering `PGPASSWORD`
  onto a copy of `os.environ`.
- **SSRF is narrower than it was.** `accounts/push.py:62` adds a scheme and host
  allowlist for push endpoints, dot-anchored so `notify.windows.com.attacker.test`
  fails. `media_storage_config` (`core/storage.py:534`) refuses a non-HTTPS S3
  endpoint or one carrying credentials, a query or a fragment.
- **OAuth `state` is verified.** `secrets.token_urlsafe(24)`, compared against a
  session-popped value, under separate session keys for Gmail and Calendar, so
  two concurrent flows cannot clobber each other.
- **The assistant cannot be talked into a settings write.**
  `assistant/confirmation.py` derives authority only from stored, tenant-scoped
  `ChatMessage` rows and rejects same-turn self-approval, so a mailbox or an
  attachment is not an instruction channel.
- **A latent attribute-injection pattern, not exploitable today.**
  `assistant/chat.html:1569`'s `escapeHtml` does not escape quotes, and its output
  lands in double-quoted attributes in `chipMarkup()`. Safe only because
  `channel` and `kind` are enum-validated server-side in `assistant/drafts.py`.
  Worth tightening if either ever becomes free text.

---

## Files changed by this review

- `coverage_web/templates/legal/privacy.html` — five factual corrections
  (findings 6.1, 9.1, 9.2, 9.3, 9.4) and a revision note recording the call
  site behind each. All six placeholders preserved: `[LEGAL ENTITY NAME]`,
  `[REGISTERED ADDRESS]`, `[PRIVACY CONTACT EMAIL]`, `[JURISDICTION]`,
  `[HOSTING REGION]`, `[BACKUP RETENTION PERIOD]`. The DRAFT banner stays.
- `coverage_web/accounts/tests/test_privacy_disclosures.py` — six guards, one
  per corrected claim, each naming the call site it traces to.
- `coverage_web/core/tests/test_route_auth_coverage.py` — new; the URLconf
  backstop from finding 1.1.

Combined run:

    /Users/zhujimmy/Claude/Projects/Coverage/.venv/bin/python -m pytest \
      coverage_web/accounts/tests/test_privacy_disclosures.py \
      coverage_web/core/tests/test_route_auth_coverage.py \
      coverage_web/core/tests/test_sentry_privacy_settings.py \
      coverage_web/core/tests/test_private_media.py \
      coverage_web/core/tests/test_private_storage.py \
      coverage_web/core/tests/test_media_serving.py \
      coverage_web/accounts/tests/test_beta_admission.py \
      coverage_web/accounts/tests/test_security.py \
      coverage_web/accounts/tests/test_export.py \
      coverage_web/accounts/tests/test_delete_receipt.py \
      coverage_web/capture/tests/test_google_revoke.py -q
    # 296 passed

## Open items for their owners

1. `accounts/views.py:1315` — throttle `university_search` (1.2).
2. `accounts/services.py:1554` — call `sign_out_other_sessions` in the deletion
   path; add a `clearsessions` cron (6.1).
3. `ops/tracking.py:89` — `logger.warning`, not `logger.exception` (7.1).
4. `billing/views.py:89` — stop reflecting provider error text (3.1).
5. `directory/models.py:147` — guard `logo_url` before the feed 400s.
6. `crm/region_enrich.py:290` — log the contact pk, not the address (7.2).
7. If Stripe is ever enabled, add the payment-processor bullet to the provider
   list before the first checkout (9).
