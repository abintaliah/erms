# Message resource selection — implementation and verification

Approved revisions: 3 October 2026. Compose opens the shared **Add resources**
dialog directly. It uses `POST /api/v1/full-text-search`, with **All** as the
default resource-kind filter and **Aggregations** and **Records** as alternatives.
There is one search box. Numbers, titles, descriptions and indexed record
component contents use the existing full-text index; component hits select the
owning record. There is no separate number field or full-text switch.

Opening the dialog, editing text, changing the filter, and blank queries cause
no search request. Search or Enter explicitly submits a nonblank query. Requests
use a 25-item limit and opaque server cursors. New criteria reset pagination;
selections, keyed by resource kind and ID, survive paging and new searches.
Revision and active-view guards discard abandoned responses. There is no new
cache: state belongs to one dialog and results are fetched fresh on submission.

Each result places a checkbox alongside a linked title, followed by its type
and number, then its description when present. The authorized search response
includes description and security-level ID, avoiding per-result lookups.
A record/document or aggregation/folder icon identifies every result. Its title
opens `resource_inspector.py` above the picker, leaving Compose and picker state
intact. It fetches authorized metadata and selected relationship IDs afresh,
without a cache, and renders only metadata plus the existing authorized digital
content Preview button for records. No resource action panel or component
section is rendered. The preview viewer opens above metadata; closing each
layer returns to the layer underneath. Denied targets display an error.
Metadata uses two columns, a full-width description, and a single column on
narrow screens. Existing translation keys are reused; this revision adds no
new keys or Arabic drafts. The previous separate-tab navigation has been removed.

The caller rechecks every selected resource concurrently before inserting any
resource attachments in a separate panel below the authored body. Errors, revoked access, changed levels, and limit failures insert
nothing. Confirmation is disabled for empty/over-limit selections, and selection
controls are disabled during recheck. Closing or abandoning compose prevents
insertion. Final send still validates permissions and levels transactionally.

## Layout evidence

Browser inspection found the old `full-width` dialog property forced the outer
card to 1232px at a 1280px viewport, overriding its maximum-width class. Removing
that property and setting a scoped responsive card width produces 616px at the
same viewport. The standard default 560px cap cannot express half-width sizing.
The card retains readable width on smaller screens and fits narrow viewports.

Native NiceGUI grids align the checkbox and text column, metadata, and actions.
Inspection of the Arabic flex-row version found `direction: rtl` together with
`flex-direction: row-reverse`, which put the checkbox on the left. A native grid
resolves this without a direction-specific CSS override. The only custom sizing
is scoped to the dialog card; native scroll-area and grid components handle the
remaining layout. Final English and Arabic previews were inspected at 1280px
and 390px viewports (616px and 342px cards respectively), with no horizontal
overflow. All preview processes were shut down after inspection.

## Requirement traceability

| Requirement | Implementation | Verification |
| --- | --- | --- |
| AC-MSG-008F: dialog, paging, retained selection, cancel | `resource_picker.py`; compose `add_resources` | Picker paging/filter/search retention, cancel, limit and composer roundtrip tests |
| AC-MSG-008G: combined authorized full-text search, component hits identify records | `ApiClient.full_text_search`; existing backend `global_search_rows` | Query payload/no-preload tests; full-text phase 3 grammar, attribution, ACL and cursor tests |
| AC-MSG-008H: bounded, explained, all-or-nothing insertion | Picker confirmation and compose `attach`; final-send validation | Composer batch-recheck and eligibility tests; abandoned-result tests |
| AC-MSG-008I: reject direct component links; preserve capture | ResourceLink model and contract kinds; schema and migration 040 | Earlier messaging API rejection, schema parity and veraPDF capture tests |
| Explicit search, All default, descriptions and compact layout | Shared picker and authorized global-search projection | Interaction tests; English/Arabic browser inspection and responsive sizing |
| Details inspection without losing picker state | Title button; `resource_inspector`; existing authorized preview viewer | Overlay close/selection-retention tests; metadata, preview authorization, denied-target and abandonment tests |

## Verification

The revised picker has 20 passing frontend interaction checks, six passing
metadata-overlay checks, and eight passing focused backend/translation
checks. The backend run used two uniquely named disposable databases; canonical
and migrated schemas matched and both databases were dropped. No tests used demo.
Catalogue reference/stale-key, coverage, hash, placeholder and terminology checks
passed. Browser previews use the real shared picker and Wathiq stylesheet with
bounded fixtures; they do not substitute for an authenticated production smoke test.

The previous implementation also passed 88 distinct messaging, full-text and
translation checks, including capture validation with veraPDF. This revision
changes selection/search presentation and the additive search projection, not
the message-storage or capture contracts.

## Deployment and translations

Demo already has migration 040; this revision needs no new migration. Restart
API and WebUI to load the new search projection, metadata overlay, and picker.

The English manifest and canonical Arabic artifact were merged by key. Added
`resource_picker.prompt`; removed unused `resource_picker.full_text` and
`resource_picker.number`. All remaining wording/provenance was preserved, with
no administrator export promoted. Demo catalogue synchronization stored the new
Arabic draft, preserved all 2926 existing protected translation rows, and
published nothing. All 2884 active keys have Arabic text: 2874 published and
10 drafts awaiting review, including the new prompt. Database-only administrator
wording remains in the database until an export is deliberately promoted.

The metadata-overlay revision reuses existing catalogue keys without changing
English or Arabic artifacts. It was checked with stacked Compose/picker/details
dialogs: closing Preview and details preserved the query, scroll position,
selected record and unsaved Compose data. The metadata grid has two columns
on desktop and one without horizontal overflow at 390px. Parallel metadata
formatting retains the originating client locale; Arabic yes/no is tested.

Both the picker selection list and Compose's attached-resources list now use
native NiceGUI scroll areas capped at 168px. Empty lists collapse; one or two
items use less height. Counts and confirmation actions remain outside the scroll
areas, and all removal controls remain reachable by scrolling. No translation
keys or database changes are required.

Scroll verification: the Arabic picker with six selections remained capped at
168px, and real Compose with twelve attachments had a 168px scroll viewport
for 460px of content. Removing the last item updated the count and resource attachments in a separate panel below the authored body.
The run also exposed the editor shrinking to 160px while its 347px content
overflowed onto controls. The editor now uses its supported height property
(12rem) and disables flex shrinking; its content scrolls internally. Twenty
picker/composer interaction tests and the catalogue check passed.


### Message presentation (3 October 2026)

Compose and reading views separate attachments from authored text. Existing internal resource markers are hidden; new attachments add no titles to the editor. Resource rows use type icons, aligned titles and removal controls, with bounded scrolling. Outbox summaries show localized recipient names with ellipsis and a full-name tooltip. Reading views resolve translated sender and recipient names with stored-name fallback and show security code, localized name and numeric level. Stored send-time snapshots remain unchanged.

Verification for this revision: 27 UI interaction tests passed, plus 38 messaging/API/localization checks on newly created disposable databases. Fresh-schema/upgrade parity passed; both databases were dropped. Browser fixtures verified English and Arabic Compose, Outbox recipient summaries, and the separate message resource panel. One new key, `messaging.field.resources`, has an Arabic draft (`الموارد`); existing translation wording and provenance are preserved.
