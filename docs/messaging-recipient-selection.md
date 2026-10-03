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
