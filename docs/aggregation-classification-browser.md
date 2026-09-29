# Aggregation classification browser

The Aggregations page's Browse classification tab now uses a single 720px-high,
full-width scrollable tree. Aggregation and record title buttons call
`open_aggregation` and `show_record_details` directly. Those existing functions
perform their own authorized detail reads, avoiding the former pre-navigation
GET and the summary's retention/location requests. Classification titles toggle
branches. Native buttons provide keyboard access; chevrons have entity-title
accessible names and `aria-expanded` state.

The selector toolbar and tree heading use standard NiceGUI grids. Tree title
buttons use NiceGUI's supported `align` setting for the current direction.
Live Arabic inspection showed that fixed `align=left` placed labels away from
their icons; `align=right` corrects that without adding CSS overrides. Existing
scoped RTL row handling remains responsible for tree disclosure placement.
Record nodes use the primary-blue outlined `description` icon at the tree's
standard compact icon size, matching the aggregation and classification icon
treatment.

The destination detail headers use standard NiceGUI grids rather than rows.
This avoids the application's RTL row reversal applying a second visual flip:
in Arabic the entity icon is beside the title on the right, while Favourite,
Preview where available, and Back sit on the left. The Arabic Back control uses
NiceGUI's `icon-right` property with `arrow_forward`, so the arrow points toward
the previous page and remains correctly spaced after the label. English keeps
the left-pointing `arrow_back` before the label. No custom CSS was required.

## State and request lifetime

`state['aggregation_browse']` belongs to the authenticated browser page. Keys
identify the scheme/owner type, owner ID and child collection; each collection
retains its own filter, cursor and loaded rows. It is not shared across identities
or pages, and sign-out clears it. There is no new shared cache.

On return, the browser refetches previously loaded collections and enough cursor
pages to restore their loaded lengths. It renders fresh rows, then restores tree
and page scroll. Independent collections reload concurrently through the API
client's existing request limit. A page-invocation token, current resource/mode,
container lifetime and collection request version reject abandoned responses.
Overlapping clicks cannot open multiple details. Failed branch reads retain the
existing bounded retry/error treatment. Refresh retains its existing scheme-reset
behavior. Language reinitialization obtains data in the new language.

## Translation lifecycle

No keys were added and no wording was changed. Twelve now-unreferenced
`webui.render_detail_content.*` keys were removed from the English manifest and
canonical Arabic artifact. The artifact catalogue hash was updated. All 2,609
retained Arabic entries are byte-for-byte equivalent as parsed rows, including
administrator wording and provenance. No administrator export was promoted.
Normal message synchronization deprecates absent database definitions without
removing translation/event history. No persistent database was changed.

## Verification

The four new interaction cases cover direct navigation, separate chevrons in
both directions, paginated return/freshness and abandoned requests. The complete
interaction suite passed 38 tests. Existing presentation checks for tree RTL,
continuation anchors and retained detail-page styling pass.

A disposable PostgreSQL database initialized from `database/schema.sql` supplied
28 aggregations and a record for live checks; the API browse suite passed 8 tests.
The live browser verified both existing detail destinations, direction-aware
header controls, and Back restoring expanded paths. UI checks include desktop
English/Arabic and narrow layouts.

Final checks: 134 entity tests pass; four unrelated source-assertion failures
also reproduce against HEAD (classification workspace height, application shell,
empty navigation sections and login-session/security layout). Running interaction
and entity suites in one process additionally exposes a NiceGUI uploader slot
fixture conflict; the standalone entity run has only the four baseline failures.

Catalogue reference/stale-key, sorted coverage, placeholder/blank/markup,
provenance and artifact-hash checks pass for all 2,609 active keys. The terminology
checker retains two pre-existing curated Arabic issues:
`classification_transfer.error.checksum_mismatch` and
`classification_transfer.retention_rule`. These unchanged entries remain for
translation review and were not overwritten.

Live computed-style and dimension checks passed at desktop and 714px in both
languages (714px document width; 298px tree width and scroll width). The detail
metadata and action callbacks remain unchanged; only their header layout and
direction-aware Back icon properties changed. Reloading an
aggregation-detail URL directly exposed an existing hidden-content-card issue;
normal tree-to-detail and Back navigation both rendered correctly. This unrelated
detail-page reload issue was not changed by the browser redesign.

Preview services stopped; disposable database
`erms_test_organization_9d3f6ec9d8cb` was successfully dropped. No migration is
required for this frontend change.
