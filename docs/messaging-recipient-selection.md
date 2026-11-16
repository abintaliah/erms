# Message recipient selection

Implemented the user-approved composer revision on 3 October 2026 under
MSG-005A in `specs/notifications-and-messaging.md`.

To and Cc are always-visible shared multiple selectors. Selecting a result adds
a removable chip directly, without a recipient-kind dropdown or Add button.
Each field has its own shared organizational browser action for users with the
existing `organization.browse` privilege. Its new general `all` selection mode
accepts units, roles and users, with normal lazy branch pagination. Messaging
checks eligibility before accepting a browsed entity and revalidates at send.

Search starts at two non-whitespace characters with the shared 200 ms debounce.
Three independent requests run concurrently, each bounded to 25 results, using
the existing recipient endpoints. They match canonical names/descriptions,
names/descriptions in enabled supported languages, and user email addresses.
The displayed name follows the current language with canonical fallback.
Results identify the entity type. Queries can be refined for additional matches.
The composite option identity keeps overlapping user/role/unit IDs distinct;
the send and draft contracts still use the original kind and target ID.

No new cache exists. Search options belong to the open composer and retain only
current results and selected identities. Restored selections are freshly resolved
by exact ID. Shared revision/active guards discard stale and abandoned searches.
Security changes revalidate selections and clear unselected options. Existing
expansion, To precedence, limits and send-time authorization remain unchanged.

## NiceGUI and RTL findings

The standard multiple `ui.select` re-filters options by their displayed label
on updates. Live Arabic description search proved that it removed valid server
matches. The installed NiceGUI Select constructor exposes no switch to disable
this filtering. `RemoteSelect` therefore preserves the standard Python Select
API and uses QSelect's public filtering callback to render the already-filtered
server page. It is a shared component selected through `relationship_select`'s
`remote` option, not a separate messaging selector implementation.

Live testing also showed a retained multi-select popup intercepting clicks on
the other field. The shared multiple selector clears its search buffer and
closes the popup after selection through QSelect's public methods; NiceGUI has
no corresponding setters. Keyboard navigation and chips remain native.

The application's global RTL row reversal double-reversed the native RTL field
rows and placed chips on the left. Computed styles confirmed `direction: rtl`
and `flex-direction: row-reverse`. A narrowly scoped override for remote
relationship selects restores normal row direction inside these controls.
The final browser measurements were `row`/`rtl` in Arabic and `row`/`ltr` in
English. Other selectors retain their existing presentation.

## Verification

- 17 existing Phase 2 API regressions passed in disposable PostgreSQL databases.
- The new database acceptance test passed for English/Arabic/French name and
  description matching, user email, localized display, bounded responses,
  eligibility and suspended-user exclusion. Two test-fixture setup omissions
  (localization audit reason and required timezone) were corrected before it passed.
- 34 focused NiceGUI interaction tests passed, including the new separate
  To/Cc search/removal, shared browsing, all three organizational entity types,
  existing tree consumers and security-level selectors.
- One additional abandoned recipient-search test verifies that its three
  pending bounded reads cannot update a departed composer.
- 16 shared relationship-search tests passed in their normal separate test
  process. Mixing these tests into the interaction-plugin process caused
  NiceGUI slot-context failures; their standalone run passes.
- Live browser: mixed search; direct user/unit selection; unit → role → user
  browsing into Cc; save/reopen draft; renamed/translatable entity freshness;
  Arabic description and email matching; Arabic search in English; repeated
  navigation; closed selection popups; and LTR/RTL layouts.
- Python compilation, catalogue/stale-key checks and `git diff --check` passed.
- Existing Starlette/AnyIO deprecation warnings remain unrelated to this change.

Screenshots: `verification/producer-names/compose-recipients-en.png` and
`verification/producer-names/compose-recipients-ar.png`.

## Translation and deployment handoff

Two keys were added to the English catalogue and merged into the canonical
Arabic artifact: `messaging.action.browse_recipients` and
`messaging.help.recipient_search`. No existing wording/provenance was replaced,
no keys were removed, and no administrator export was promoted. The two new
Arabic values are generated drafts requiring human review/publication through
the normal catalogue workflow. Exact coverage/order (2,877 keys), nonblank,
placeholder, terminology, provenance for the added values, and artifact hash
checks passed. Existing artifact entries retain their original provenance,
including legacy entries using the artifact-level metadata.

No database migration is required. API and WebUI processes need the updated
code; normal catalogue synchronization supplies the two definitions. This task
used only disposable databases and did not publish translations into `demo`.

## Follow-up: code search, activation and due-date guidance

Recipient lookup also matches role/unit `code` and user `external_id`, the
existing user identifier field. The search guidance was updated in English and
its generated Arabic draft only; all other catalogue values remain unchanged.
The prior generated Arabic text is recorded as superseded. No keys were added
or removed and no administrator export was promoted.

The reported email failure coincided with the local API still running from
06:06, before the recipient SQL changes at 06:26; the WebUI had reloaded while
the API had not. A fresh disposable browser session searching only
`recipient@messages.test` (with no selected recipients) returned Message
Recipient. Evidence: `verification/producer-names/recipient-email-search.png`.
The API must be restarted to activate Python route changes when reload is off.

The due-date help now shares the date field's visibility condition. Both are
hidden unless Action required is selected. English and Arabic interaction
checks cover initial hidden state, show and hide again; live browser checks
confirmed the same behavior.

Verification: 12 composer interaction tests and the extended multilingual/code/
email database test passed. All disposable databases were dropped. Catalogue
checks and diff whitespace checks passed. The changed Arabic search guidance
remains a generated draft for review/publication.

Activation completed: the original local stack had already stopped before the
planned restart. Its detached launcher failed the readiness check; running the
same launcher in a managed terminal succeeded. The API, WebUI and configured
indexer workers are ready with the updated code (API health returned HTTP 200).

### Recipient option subtitles (3 October 2026)

The To/Cc result name no longer includes eligibility guidance. The shared
remote select carries the guidance as option metadata and renders it below the
name using its existing Quasar option slot and caption labels. NiceGUI's
standard string option mapping does not carry secondary labels, so the existing
RemoteSelect adapter reattaches metadata by stable ID whenever NiceGUI rebuilds
its ordinal options. No custom layout CSS was added. User options also display
their email, returned by the same bounded recipient endpoint; role and unit
options return no email. Eligibility checks and disabled-option behavior are
unchanged. Metadata is scoped to each control and pruned to its current options,
including retained selections; subsequent searches replace returned metadata.

Verification: 12 composer interaction tests passed, including selection
retention, disabled options, email/subtitle metadata surviving updates, search
abandonment, and English/Arabic behavior. The API multilingual search test now
checks email output for both searched and individually resolved users. That test
and two catalogue validation tests passed against disposable databases; both
fresh and upgrade databases were dropped afterward. The catalogue reference
validator passed. No translation keys, wording, artifacts, or provenance were
changed; no new translation review is required.

A temporary database-free browser preview verified the source component in
English and Arabic. With the existing Wathiq stylesheet, Arabic names, guidance,
and emails aligned right; emails retained left-to-right character order. The
preview was stopped after inspection. The user's running stack was not restarted.

## Reply, Cc action semantics and mailbox filtering (3 October 2026)

Reply to a human message starts with its original sender selected in To. Saved
reply drafts preserve their chosen recipients. The sender remains mandatory in
To only when the reply acknowledges action completion.

Actions belong to To deliveries. Cc is informational, with no action status or
completion prompt. API validation and migration 041's database constraint reject
Cc completion acknowledgments. Cc deliveries retain their independent read
receipts and can send ordinary replies. Outstanding/Late Outbox filtering checks
only incomplete To deliveries; To precedence remains in force for overlapping
selectors.

Inbox and Outbox use one bounded remote Recipient filter for users, roles and
units, with the existing organization browser when permitted. Searches begin
at two characters and fetch at most 25 results per type concurrently. Selected
IDs are resolved individually. Filters match stored To/Cc selector identity,
not current role/unit expansion. Lookup uses `purpose=filter` so the current
user can be found and current sending eligibility does not limit historical
message searches. No cache is added: selected values and options live only in
the current mailbox view; shared revision and active guards abandon stale
responses. Search refreshes the server page from its first cursor; clearing
removes the paired filter parameters.

Existing English and Arabic keys are reused; no catalogue text or provenance
is changed by this revision.

Verification: 25 UI interaction tests and 40 messaging API tests passed. Fresh
schema/upgrade parity passed, and every disposable database was dropped.
English Outbox and Arabic Inbox/Reply were inspected in a database-free browser
preview; the preview was stopped. Migration 041 was applied to demo after the
tests, preserving existing message data. Prior function DDL was saved in
`/tmp/demo-message-completion-before-041.sql`.

| Approved behavior | Implementation | Verification |
| --- | --- | --- |
| MSG-007 Reply prefill | Compose source initialization | `test_reply_prefills_sender_and_cc_has_no_completion_prompt` |
| MSG-010H/I, informational Cc | Derived statuses, completion validation, database constraint 041, Outstanding filter | `test_cc_is_informational_and_cannot_complete_or_keep_action_outstanding` |
| Unified mailbox recipient filter | Inbox/Outbox paired server filters, remote mixed selector, existing browser callback | `test_inbox_and_outbox_recipient_selector_filter`, `test_mailbox_recipient_filter_search_browse_and_clear` |

## Reply subject and completion guidance revision

MSG-007/AC-MSG-005 now prefill new reply subjects with the conventional `Re: `
prefix followed by the original subject exactly, in every language. The subject
is editable, and opening an existing reply draft preserves its saved subject.
Priority remains Normal for new replies; the original security level remains
the initial level, with its existing server-enforced floor. The body stays blank.
The completion guidance explains that checking the completion control informs
the original sender through the reply. Linked-message guidance refers explicitly
to the earlier body, so it no longer conflicts with subject prefilling.

Catalogue changes in `messages.en.json` and `messages.ar.generated.json`:
`messaging.help.completion` and `messaging.help.linked` were revised;
`messaging.reply.subject_prefix` was added. Existing unrelated wording and
provenance were preserved. No administrator export was promoted. Updated
machine drafts record provenance and known superseded values; the Arabic
completion and linked-body guidance require human review/publication. Explicit
demo synchronization stored the prefix and corrected the two approved guidance
keys, preserving 2926 unrelated translation rows.

Verification: 22 UI tests passed, including new replies in English/Arabic,
editable subject persistence, and preservation on opening a saved reply. Two
catalogue tests passed on disposable databases, which were dropped. All 2886
English/Arabic keys passed exact coverage, nonblank, placeholder, quality-flag,
ordering and hash checks. English and Arabic browser fixtures verified the
subject and completion guidance; the temporary preview was stopped.

## Mailbox panels and capture runtime — 4 October 2026

The approved mailbox reading-panel rule is implemented in
`frontend/webui/messaging_workspace.py`: native responsive NiceGUI grid, whole
row mouse/keyboard activation, independent list/detail request revisions,
preserved listing page, local read-badge updates and selected-row highlighting.
Restricted entries retain their non-disclosing presentation. Changing deleted
mailbox mode or deleting/restoring an item clears stale details. Drafts retain
their existing compose workflow. No new cache or translation key is introduced.

`test_mailbox_row_keeps_page_and_discards_stale_detail` covers both mailbox
types in English and Arabic, pagination preservation and out-of-order responses.
The existing reply tests activate the row directly. Browser checks confirm
LTR/RTL desktop panel order and single-column layout at a 391-pixel viewport;
native grid configuration avoids an inline column count that overrides
responsive classes.

The local capture error was caused by the validator not being on PATH and no
`MESSAGING_PDF_VALIDATOR` setting. The verified veraPDF 1.30.2 runtime now resides
in ignored `.local-tools/verapdf`; `.env` specifies its absolute executable.
English/Arabic real PDF generation passes both independent compliance profiles.
The fail-closed validator and capture transaction contract remain unchanged.

### Drafts editing panel extension

Drafts now share the approved mailbox split layout and mouse/keyboard row
activation. The existing compose form renders directly in the adjacent panel.
Saving refreshes the same listing page while retaining edited controls; cancel,
send and discard/restore close the editing panel. Independent detail revisions
prevent an older draft fetch or form validation from replacing a newer selection.
No translation keys or database changes are required. The reply-draft test
verifies inline editing and saved content;
`test_draft_panel_switch_save_and_cancel_keep_listing` verifies switching,
stale fetch abandonment, save pagination and cancellation in English/Arabic.
Native grid browser checks confirm LTR/RTL order.

### Earlier linked message dialog

The approved 4 October rule is implemented by `open_linked` and the shared
message renderer in `messaging_workspace.py`. Dialog requests have an independent
revision and owning-message guard; Close invalidates pending results. Nested
links and Back retain the original root envelope for access checks. The reading
pane, selection and pagination are untouched. Existing permitted linked-message
controls and resource inspection remain available. No cache is introduced.

`test_earlier_dialog_preserves_latest_and_navigates_back` verifies both English
and Arabic, nested links, Back, original root access and Close. All 30 workspace
tests passed; the RTL browser preview verified the same navigation.
Catalogue coverage, sorting, placeholders, blanks, new-key provenance and hash
checks passed for 2,887 keys. The new `messaging.linked.title` heading has English
and Arabic definitions; existing artifact wording/provenance is preserved.
Demo synchronization added one Arabic draft and preserved 2,929 existing
translation rows. The new heading requires administrator review/publication.
No administrator export was promoted. The preview was stopped after verification.

### Capture destination and resource layout corrections

The record editor now retains the capture’s Digital default before a parent is
selected and allows clearing the aggregation selection. Its remote loader makes
no collection request for fewer than two characters, then requests at most 25
results from aggregation search with `record_creation=true`. Capture additionally
uses `digital_only=true`. The same destination predicate filters paged browse
branches before cursor pagination. Existing visibility, record.create, add-record
permission/governance, effective owner-unit role, ancestor closure and medium
rules are reused; commit-time checks remain authoritative. Changing selection
or abandoning the capture prevents stale destination/role results from applying.
No client cache is introduced.

Tests exercise the real medium and bounded-search callbacks, captured title/date/
security defaults, ancestor closure, owner-unit role and ACL eligibility.
All 34 UI checks and all 21 phase-5 API checks passed across the regression run
and corrected-fixture reruns. Each API run used new disposable databases; all
were dropped.

Browser inspection found the previous popup’s effective width was 560px due to
the dialog’s standard maximum, despite a 960px utility class. The native card
size now specifies 672px capped by viewport width. Resource rows use native
NiceGUI grids: the shared RTL row-reverse rule had doubled the direction reversal
and placed icons incorrectly. Grid avoids that rule with no custom CSS fallback.
Measured width and icon positions were verified in English and Arabic; the actual
record editor showed Digital and the sent instant in the working timezone.

The shared component storage label now uses `components.field.storage_backend`,
English “Storage backend” and Arabic “محرك التخزين”. It labels the existing
backend value and does not change storage behavior. The old dashboard key remains
used by its dashboard chart. Catalogue checks passed for 2,888 active keys;
existing translation wording/provenance was preserved. Demo received one new
Arabic draft and retained 2,930 existing translation rows. Human review/publication
is still required; no administrator export was promoted. All previews stopped.

### Login notification checkpoint and immutable Digital capture

The repeated-login toast originated from session-token-hashed sessionStorage
keys: every login reset the checkpoint. `mailbox_cursor_key` now isolates a
numeric localStorage checkpoint by API URL and user ID, retaining it across
logins and language changes. No message content or credentials are stored.
Each bounded reconciliation page updates the checkpoint; synchronous BigInt
comparison prevents another tab from regressing it. Logout stops adapters and
dismisses notifications, while retaining this metadata. Browser clearing
invalidates it; unavailable browser storage retains existing REST/in-page
recovery. Only the current authenticated legacy session can supply a migration
checkpoint. A browser with no saved checkpoint can show one initial catch-up
summary before the new durable checkpoint exists.

The singular normal-message summary uses `messaging.live.summary_one`. Its
English/Arabic definitions were added without changing curated plural wording.
`test_checkpoint_survives_new_login_and_isolates_api_and_user` verifies no
repeated summary on a new login, notification of a genuinely new delivery and
account/API isolation. Existing abandonment, reconnect and duplicate-hint tests
remain passing.

Capture controls now expose only Digital, disabled regardless of the selected
parent medium. PATCH and commit independently enforce Digital; ordinary record
creation retains its permitted medium choices. The new API error uses
`messaging.capture.error.message_capture_medium_fixed_digital`, including the
existing Arabic term “هجين” for Mixed. Its corrected initial machine wording is
recorded in superseded_translations; protected administrator text was preserved.
The real PDF capture integration test rejects Mixed/Physical/null updates and
still commits successfully. All disposable databases were dropped.

42 UI/live regression checks passed, plus the added ordinary-medium regression
(13 targeted live/control checks passed). Browser verification confirmed the
actual Digital field is disabled with a Mixed parent. Catalogue checks passed
for 2,890 keys. Two new Arabic drafts were seeded in demo; existing translation
rows stayed unchanged except the explicitly corrected new machine draft.
Both new drafts require administrator review/publication. No administrator export
was promoted. Database-free previews and their browser tabs were closed.
