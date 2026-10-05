# Classification export auditing and Audit Trail actor filtering

Verified 5 October 2026 against classification transfer IE-14 / AT-15 and
security specification section 18.1. Code, migrations and draft artifacts are
implemented; generated Arabic wording remains subject to human review and
publication. API/WebUI processes must reload the changed code/catalogue.

## Requirement traceability

| Requirement | Implementation | Verification |
| --- | --- | --- |
| One successful export event per JSON/CSV/Word request | `backend/services/api/scheme_transfer/routes.py::export_scheme` | `test_successful_export_history` parameterized for JSON, CSV, English/Arabic/French Word; normal request source, actor ID/name/email, occurrence, request/correlation IDs, scheme snapshot, format, export ID and Word language |
| Package/event identity and source preservation | Read-only repeatable-read generation followed by separate context-configured audit transaction | JSON/CSV manifest export ID equals event metadata; scheme, classifications and retention-rule rows remain equal; full transfer snapshot/authorization/roundtrip regressions passed |
| Audit before successful response; generation is not browser saving | Audit connection commits before constructing the successful download response | `test_failed_generation_and_validation_are_not_exports`; `test_history_commit_failure_prevents_success` uses an initially deferred constraint trigger: error response and no committed EXPORT event |
| Existing export privilege; existing authorized history | Existing `classifications.administer` dependency and Audit Trail | `test_only_administer_privilege`, anonymous transfer denial and authorized EXPORT retrieval; no new privilege or page |
| Readable immutable export identity | `app.py::event_entity_identity` prefers export metadata scheme snapshot | `test_export_identity_prefers_export_snapshot_to_renamed_current_entity`: original code/title retained after rename/deletion |
| Name/email literal partial search; historical identity | Actor-name/email OR using existing server `contains_ci`; trim input; no directory reads | `test_actor_search_snapshots_literal_and_authorization`: case folding, name/email, literal `%_`, null snapshots, duplicate names, actual account rename and deletion, paged counts |
| Compose every filter, reset first page, clear/preserve navigation preset | `app.py::select_audit_trail`; existing paginated search | English/Arabic `test_monitor_audit_button_routes_to_dedicated_page_with_navigation_guard`: all existing filters AND actor OR; whitespace trimming; pagination reset; clearing filters; Monitor preset and unfiltered sidebar |
| No protected actor matching/disclosure | `authorized_event_history` CASE expressions mask ID/name/email; canonical schema and migration 046 | Hidden historical resource does not match actor name/email or contribute to matching counts; authorized result retains redacted envelope with null actor fields; upgrade definition equals canonical definition |
| Repeated navigation, abandoned reads, identity/language isolation | Per-client page/request revisions; no new cache | Existing navigation guard tests plus delayed old search released after opening another audit page: old result never rendered; EN/AR tests and live fixture |
| Responsive LTR/RTL and normal Wathiq controls | Standard NiceGUI inputs/selects/buttons/grid; actor spans two columns at wider breakpoints | Actual application page extracted into database-free fixture, exact application stylesheet; live English/Arabic apply/reset; widths 360, 740 and 1280 without horizontal overflow; effective control/body direction correct; no browser warnings/errors |

## Runs and database isolation

The initial focused backend run had one assertion error: the commit failure was
translated by the API into an error response, rather than propagating an
exception to TestClient. The test was corrected to assert the actual public
behavior and rolled-back history.

`backend/services/api/.venv/bin/python tools/test_scheme_transfer.py`:
118 passed. Disposable databases
`erms_transfer_test_79150c25f33e4be2_source` and
`erms_transfer_test_385f1e8ffaaa41d5_destination` were created from the standalone
canonical schema and dropped successfully.

After strengthening unchanged-retention-rule and actual renamed/deleted-account
assertions, nine focused new backend cases passed; 109 unrelated cases were
deselected. Both additional databases
`erms_transfer_test_dd5f78a1573d4c5c_source` and
`erms_transfer_test_fab9b87dcf284539_destination` were dropped successfully.
The initial focused run's disposable databases were also dropped after failure.
No tests used `demo`, `demo3`, or another persistent ERMS database.

Final frontend command:

```sh
frontend/webui/.venv/bin/python -m pytest \
  frontend/webui/interaction/tests/test_messaging_monitor_navigation.py \
  frontend/webui/tests/test_locale_services.py \
  frontend/webui/tests/test_export_audit_labels.py --asyncio-mode=auto -q
```

28 passed. NiceGUI tests require asyncio auto mode for its asynchronous fixture.
Browser fixture: `audit_preview.py`, localhost port 18096; illustrative rows and
stubbed API only. The filter page and stylesheet are taken from actual `app.py`.
Saved evidence: `filters-en.png`, `filters-ar.png`. Temporary server and owned
browser tab were closed; viewport override was reset.

## Translation artifact and deployment

Four new keys, with no existing keys changed or removed:

- `audit.event.export`
- `audit.filter.actor_identity`
- `audit.filter.actor_identity_hint`
- `audit.filter.clear`

English and Arabic coverage/order agree at 2,943 active keys. All 2,939 existing
Arabic entries, including wording and provenance, are byte-equivalent as JSON
objects to the pre-change canonical artifact. The four new Arabic entries have
machine-generation provenance and require human review. No administrator export
was promoted and no translation was published. Catalogue SHA-256:
`415bbd06b9e77a7c371e579dea0eebb083c9816619c3e59c4bfb33f05c72c6ca`.

Source completeness/stale-key validation, coverage/order/hash, and new Arabic
blank/placeholder/terminology checks pass. The full strict Arabic quality check
still reports the same ten pre-existing findings as HEAD (vital-record and
aggregation terminology plus the curated `Re:` prefix); none is introduced by
this change. Existing curated values were preserved rather than regenerated.
These inherited findings require a separate administrator review.

Operational deployment, not tests: applied `046_audit_actor_redaction` to `demo`
and `demo3`. Ran the existing generic Arabic draft seeder for each: stored 4,
corrected 0, failed 0, awaiting generation 0. Read-back verified all four are
`generated` / `draft` with null `published_text`, and all 2,982 pre-existing
protected Arabic translation rows in each database remained exactly unchanged.


## Actor autocomplete, indexed queries and configurable cap

Approved extension: security specification §18.1 and the separately approved
Audit Trail setting in application-configuration §4.1. Implementation mapping:

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| Two-character, 200 ms, 25-identity historical suggestions | `audit_search.py`, `/event-history/actors`, `audit_actor_select.py` | `test_audit_search.py`, `test_audit_actor_select.py`; EN/AR screenshots |
| Renamed/deleted actors; exact ID selection; null-ID snapshots | Historical authorized witness queries, `actor_condition` | Deleted/renamed, nullable identity and shared snapshot tests |
| No hidden identities or authorization bypass | Raw candidates followed by authorized projection/witness checks; existing audit.view policy | Hidden actor, null/NOT/OR and route privilege tests |
| Cancellable requests, retained choices and navigation isolation | API client cancellable reads; page revision/task guards | API client, selector and Messages Monitor navigation tests |
| Configurable result cap, count limit+1, refinement notice | `.env`/`.env.example` `AUDIT_TRAIL_SEARCH_RESULT_LIMIT=1000`, `search.py`, page banner | Default/custom cap, shortened last page, beyond-cap rejection and invalid configuration tests; live preview |
| Efficient substring/identity ordering and upgrade parity | Canonical indexes, migration 047, conservative candidate predicate | 50,000-event EXPLAIN plans, migration parity and long snapshot tests |
| Localizable and RTL | Six new contextual keys; preserved canonical Arabic objects | Coverage/order/hash/quality checks, English/Arabic browser and interaction checks |

Final backend run: **130 passed** (two existing dependency deprecation warnings).
Created and dropped `erms_transfer_test_ecf28c72725c4785_source` and
`erms_transfer_test_ab218616f2af4a55_destination`. An earlier run had an overly
specific plan assertion: PostgreSQL selected the new actor identity index rather
than the timeline index. Corrected the assertion to accept either valid indexed
actor-ID plan; both earlier disposable databases were also dropped.

Frontend run: **87 passed**, covering selector, navigation, API client,
localization and export labels. No tests used persistent ERMS databases.

`query-plans.json` records the 50,000-event fixture: substring search about
24 ms and two-character suggestions about 70 ms. These local measurements are
not deployment-wide guarantees. Name/email trigram and actor-ID indexes are
used for selective searches. Counts stop after cap+1 authorized matches; the
API retrieves one page, not the entire capped collection.

Browser fixture uses the actual Audit Trail page and stylesheet with synthetic
API responses. English and Arabic historical suggestion dropdowns verified,
selection/Apply verified, configured refinement banner visible. At 360 px both
languages have scroll width equal to viewport width; body directions are LTR
and RTL respectively. No browser warnings/errors. Evidence:
`actor-autocomplete-en.png`, `actor-autocomplete-ar.png`. Preview server and
owned tab closed; viewport override reset.

Six further keys: `audit.filter.actor_suggestions_hint`,
`audit.filter.unnamed_actor`, `audit.filter.refine_actors`,
`audit.filter.no_actors`, `audit.filter.actors_failed`,
`audit.filter.results_capped`. Coverage now agrees at **2,949** keys, in identical
lexicographic order. All 2,939 HEAD Arabic objects and the four earlier added
objects were preserved. New drafts pass blank/placeholder/terminology/provenance
checks; full catalogue still has the same ten inherited curated findings.
Current catalogue SHA-256:
`6813f4d2bfc23d9e7fd8daecf3eac584798a2b18a6bc4b5159f355f56d02ced9`.

Operational deployment: migration **047** applied to **demo** and **demo3**.
Arabic seeder stored six generated drafts per database, corrected/failed/
awaiting generation all zero. All 2,986 pre-existing protected Arabic database
rows per database were unchanged. No translations were published. Restart API
and WebUI processes to activate the updated configuration and page code.


## Directory-only actor lookup correction (2026-10-05)

This correction supersedes the historical-suggestion behavior above, following
explicit user direction. Suggestions now query `users` only, after two characters,
returning at most 25 matches plus a has-more indication. No event-history query,
visibility function, historical fallback, or cache runs during autocomplete.
The existing audit.view endpoint permits the bounded directory lookup; current
names/emails are displayed. Unselected text remains unchanged when no match
exists, and Apply searches persisted audit name/email snapshots normally.
Deleted/renamed actors remain searchable through that Apply path. Event scopes
continue to constrain final audit results, not directory suggestions; legacy
scope query parameters remain accepted for API compatibility.

Read-only diagnosis on the reported database found 26 automated_process/API
translation-publication events dated September 29, with actor ID 6, the user's
email, and actor name `Codex — user-authorized translation publication`.
The previous deduplication sorted snapshots alphabetically and selected that
label. Its plan decorrelated the visibility witness into a global history scan;
lookup elapsed about 6.7 seconds. The new directory-only query returned the
current user's actual name in about 0.6 ms. This measures the database service
call only, excluding the 200 ms debounce, HTTP and UI rendering. No history rows
were changed. An intermediate latest-snapshot query was abandoned in favor of
the user's simpler approved design.

Implementation: `backend/services/api/audit_search.py`; specification §18.1;
updated database README. Backend tests verify current directory labels despite
conflicting automated audit snapshots, literal wildcard handling, no history
read in the suggestion SQL, no-match/deleted-user fallback through Apply, bounded
results, authorization and existing search cap/index behavior. Frontend selector,
navigation and API client checks: **65 passed**, including English/Arabic and
explicit retention of unselected no-match text. No UI keys or translations changed.

Final backend verification: **131 passed**, two existing dependency warnings.
Fresh disposable databases `erms_transfer_test_89a2ddcc65a4495f_source` and
`erms_transfer_test_78c2d1d0720b4fdf_destination` initialized from canonical schema
and dropped successfully. No persistent database tests or data corrections ran.
Restart the API to activate this code change; no new migration is required.

## Selection reopening correction

Reproduced the reported second popup in the actual Audit Trail live fixture:
selecting a server suggestion caused `changed()` to invoke
`updateInputValue('')`, whose default QSelect behavior invokes filtering again
and opens the popup. This was an input synchronization/filter pass, not a second
required user-selection step. Removed that input-clearing call from selection;
retain the native selected label and close with the supported `hidePopup`
method. Reset now uses `updateInputValue('', true)` (noFilter), and selected-label
input synchronization does not start a remote query. No CSS/component overrides
or user-visible text changes were introduced.

Nine selector/navigation interaction tests passed, including EN/AR and an added
assertion that selected-label synchronization makes no extra API call. Live
English and Arabic selection left the combo collapsed with its chosen label.
After the menu transition Arabic DOM inspection found `aria-expanded=false`
and zero `.q-menu` elements. No browser errors/warnings. Evidence:
`actor-selected-ar.png` (after closing transition). The preview server and owned
browser tab were closed. Restart WebUI for the revised handler.
