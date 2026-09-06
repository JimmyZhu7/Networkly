# Element and copy audit — September 2026

Scope: all 96 project-owned templates, their shared primitives, and visible form/action messages. This extends the shell and primary-widget passes. Third-party Django admin and user-authored or source-quoted content are outside the redesign.

Direction: a clear recruiting workspace. Keep the existing cool white/slate/blue identity. Every element must disclose its purpose and result; local motion acknowledges interaction. Small controls use readable text, semantic states, native keyboard behavior and touch targets.

## Product vocabulary

| Concept | Wording |
|---|---|
| Open a mail composer | Draft email |
| Record an already sent message | Log sent / Log sent email |
| Record any contact event | Log interaction |
| Record an incoming reply | Log reply |
| Stop routine outreach | Pause outreach |
| Restore routine outreach | Resume outreach |
| Finished personal application | Finished (separate from a closed posting) |
| Contact progression | Relationship: New, Replied, Had a chat, Advocate |
| Unknown posting deadline | Deadline not listed |
| AI conversation destination | Assistant |

## Element coverage

Reviewed families: navigation and account links; search/palette; buttons and icon actions; labels, hints, errors, number steppers, native/enhanced selects; checkbox/radio/segmented choices; badges, counts and evidence labels; disclosures; toasts and undo; confirmation dialogs; role drawers; contact timelines and relationship stages; score axes; archived, paused and hidden-contact collections; Today proposal/mail-fact/application/debrief lanes; calendar cells/events/forms; profile photo, affiliations and school-email chips; target-firm tier controls; outreach goal/schedule; onboarding steps/previews; assistant draft/message/folder/memory controls; pricing/FAQ/comparison table; public/auth/error/legal pages; transactional emails; staff activity tables.

Existing accurate labels, source evidence, privacy obligations and legal placeholders are retained where rewriting would change meaning. Native controls keep their submitted values. Stored notes and quoted evidence are never rewritten.

## Template ledger

| Template | Treatment |
|---|---|
| `404.html` | Element and copy review; existing literal copy retained |
| `500.html` | Copy and element review; literal copy revised |
| `_icon.html` | Reviewed and retained SVG primitives; existing brand retained pending logo selection |
| `_logo.html` | Reviewed and retained SVG primitives; existing brand retained pending logo selection |
| `_nav_icon.html` | Reviewed and retained SVG primitives; existing brand retained pending logo selection |
| `_pagehead.html` | Element and copy review; existing literal copy retained |
| `account/_account_page.html` | Shared styles reviewed; elements.css supplies updated component treatment |
| `account/_auth_providers.html` | Element and copy review; existing literal copy retained |
| `account/_auth_styles.html` | Shared styles reviewed; elements.css supplies updated component treatment |
| `account/email.html` | Copy and element review; literal copy revised |
| `account/email_change.html` | Copy and element review; literal copy revised |
| `account/login.html` | Copy and element review; literal copy revised |
| `account/logout.html` | Copy and element review; literal copy revised |
| `account/password_change.html` | Copy and element review; literal copy revised |
| `account/password_reset.html` | Element and copy review; existing literal copy retained |
| `account/password_reset_done.html` | Copy and element review; literal copy revised |
| `account/password_reset_from_key.html` | Copy and element review; literal copy revised |
| `account/password_reset_from_key_done.html` | Copy and element review; literal copy revised |
| `account/password_set.html` | Copy and element review; literal copy revised |
| `account/signup.html` | Copy and element review; literal copy revised |
| `accounts/_firm_list.html` | Element and copy review; existing literal copy retained |
| `accounts/_onboarding_preview.html` | Copy and element review; literal copy revised |
| `accounts/_profile_form.html` | Copy and element review; literal copy revised |
| `accounts/_welcome_head.html` | Element and copy review; existing literal copy retained |
| `accounts/_work_auth_matrix.html` | Copy and element review; literal copy revised |
| `accounts/delete.html` | Copy and element review; literal copy revised |
| `accounts/emails/trial_ended.html` | Copy and element review; literal copy revised |
| `accounts/emails/trial_ended.txt` | Copy and element review; literal copy revised |
| `accounts/export.html` | Copy and element review; literal copy revised |
| `accounts/import.html` | Copy and element review; literal copy revised |
| `accounts/onboarding.html` | Copy and element review; literal copy revised |
| `accounts/settings.html` | Copy and element review; literal copy revised |
| `accounts/signout_all.html` | Copy and element review; literal copy revised |
| `accounts/unsubscribe.html` | Copy and element review; literal copy revised |
| `analytics/dashboard.html` | Copy and element review; literal copy revised |
| `assistant/_draft_card.html` | Element and copy review; existing literal copy retained |
| `assistant/_draft_chip.html` | Copy and element review; literal copy revised |
| `assistant/_history.html` | Copy and element review; literal copy revised |
| `assistant/_history_row.html` | Element and copy review; existing literal copy retained |
| `assistant/_memories.html` | Copy and element review; literal copy revised |
| `assistant/_message.html` | Element and copy review; existing literal copy retained |
| `assistant/_thread.html` | Copy and element review; literal copy revised |
| `assistant/chat.html` | Copy and element review; literal copy revised |
| `base.html` | Copy and element review; literal copy revised |
| `core/_waitlist_form.html` | Element and copy review; existing literal copy retained |
| `core/home.html` | Copy and element review; literal copy revised |
| `core/pricing.html` | Copy and element review; literal copy revised |
| `crm/_act_card.html` | Copy and element review; literal copy revised |
| `crm/_application_lane.html` | Element and copy review; existing literal copy retained |
| `crm/_calendar_day.html` | Copy and element review; literal copy revised |
| `crm/_calendar_event.html` | Element and copy review; existing literal copy retained |
| `crm/_calendar_week.html` | Element and copy review; existing literal copy retained |
| `crm/_cockpit.html` | Copy and element review; literal copy revised |
| `crm/_contact_ai_brief.html` | Element and copy review; existing literal copy retained |
| `crm/_contact_ai_summary.html` | Copy and element review; literal copy revised |
| `crm/_contact_live.html` | Copy and element review; literal copy revised |
| `crm/_contact_search.html` | Copy and element review; literal copy revised |
| `crm/_daily_brief.html` | Copy and element review; literal copy revised |
| `crm/_seed_lane.html` | Element and copy review; existing literal copy retained |
| `crm/_styles.html` | Shared styles reviewed; elements.css supplies updated component treatment |
| `crm/autopilot_log.html` | Copy and element review; literal copy revised |
| `crm/calendar.html` | Copy and element review; literal copy revised |
| `crm/contact_archived.html` | Copy and element review; literal copy revised |
| `crm/contact_campaign_hidden.html` | Copy and element review; literal copy revised |
| `crm/contact_detail.html` | Element and copy review; existing literal copy retained |
| `crm/contact_form.html` | Copy and element review; literal copy revised |
| `crm/contact_list.html` | Copy and element review; literal copy revised |
| `crm/contact_parked.html` | Copy and element review; literal copy revised |
| `crm/contact_unrelated.html` | Copy and element review; literal copy revised |
| `crm/debrief.html` | Copy and element review; literal copy revised |
| `crm/emails/weekly_digest.html` | Copy and element review; literal copy revised |
| `crm/emails/weekly_digest.txt` | Element and copy review; existing literal copy retained |
| `crm/week.html` | Element and copy review; existing literal copy retained |
| `directory/_apps_body.html` | Copy and element review; literal copy revised |
| `directory/_card.html` | Copy and element review; literal copy revised |
| `directory/_columns.html` | Element and copy review; existing literal copy retained |
| `directory/_cycle_band.html` | Element and copy review; existing literal copy retained |
| `directory/_drawer.html` | Element and copy review; existing literal copy retained |
| `directory/_facet_options.html` | Element and copy review; existing literal copy retained |
| `directory/_filter_counts.html` | Element and copy review; existing literal copy retained |
| `directory/_pickcol.html` | Copy and element review; literal copy revised |
| `directory/_recommend_bar.html` | Copy and element review; literal copy revised |
| `directory/_results.html` | Copy and element review; literal copy revised |
| `directory/_role_drawer.html` | Copy and element review; literal copy revised |
| `directory/_role_people.html` | Copy and element review; literal copy revised |
| `directory/_rolecard.html` | Copy and element review; literal copy revised |
| `directory/_rolecard_dismissed.html` | Copy and element review; literal copy revised |
| `directory/_styles.html` | Shared styles reviewed; elements.css supplies updated component treatment |
| `directory/_timeline.html` | Copy and element review; literal copy revised |
| `directory/_track_control.html` | Copy and element review; literal copy revised |
| `directory/firm_detail.html` | Copy and element review; literal copy revised |
| `directory/my_applications.html` | Copy and element review; literal copy revised |
| `directory/opportunities.html` | Copy and element review; literal copy revised |
| `legal/privacy.html` | Copy and element review; literal copy revised |
| `legal/terms.html` | Copy and element review; literal copy revised |
| `socialaccount/connections.html` | Copy and element review; literal copy revised |

## Validation evidence

Local evidence is stored under `.impeccable/review/elements/` (ignored): `final-pass.json` for 76 route/width checks, `functional-checks.json` for real demo CRUD/navigation, `confirmation-checks.json` for final rendering/onboarding and the 640px viewport equivalent to 200% desktop zoom, and final desktop/phone captures. Extra component tests intercept POST requests. External Gmail, paid AI and payment providers are not contacted by visual tests.

The independent Astra review identified seven material fixes: paused-contact recovery, domain keys in status classes, pricing claims, onboarding/recovery copy, redundant public headings, equal work-authorization options, and phone schedule timing. All seven were scored resolved in the follow-up verdict (`ship`, scoped to that correction batch).

The correction batch was recaptured at 1440, 390 and 640 pixels: 19 page/width checks returned 200 with no horizontal overflow or JavaScript errors. Work-authorization options measured equal heights at each width; schedule values remained visible. Earlier verification covered 11 real demo workflow groups, five read-only interaction groups, and 28 confirmation checks. These are sampled rendered states, not a claim that every conditional state or external integration was exercised.

Final regression evidence: the complete suite ran 11,252 tests: 11,226 passed, 13 skipped (opt-in live connector smoke tests), and 13 failed on superseded presentation expectations or a now-unused public style. Those expectations were reconciled with the rendered behavior; CSS-comment matches were excluded from visible-copy assertions, and the dead rule was removed. All 401 tests across the affected files and added regression guards then passed. Django system checks and compilation of all 96 templates passed. No unresolved test failure remains; this result combines the full run with the targeted confirmation run, rather than claiming a second full-suite run.

No external Gmail, AI, or payment transaction was performed. Live provider behavior remains outside this pass’s verification.
