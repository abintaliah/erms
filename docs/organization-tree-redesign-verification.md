# Organization tree redesign — 29 September 2026

The approved mockup replaces the full Browse page's tree/summary split with a
full-width tree. Node names open the existing organization-unit, role, and user
detail pages. No schema, API route, authorization privilege, detail-page field,
or detail-page action changed.

## Requirement traceability

| Approved requirement | Implementation | Verification |
| --- | --- | --- |
| Tree-centered Browse page | One full-width tree in `show_organization_structure`; summary container exists only in selector dialogs | Live desktop and 714px layout inspection; presentation assertion |
| Node click opens existing details | Native name buttons invoke the existing detail callbacks; separate disclosure buttons only expand | Three destination interaction tests; live unit, role and user navigation |
| Details unchanged | No edits to `select_organization_unit_details`, `select_role_details`, or `select_user_details` | Each function's full source compared byte-for-byte with HEAD |
| Preserve return context | Existing navigation history and Back actions; saved expansion, page counts, selected assignment, query, filters and scroll | Branch/root paging and return tests; live repeated Back navigation |
| Translated entities and Arabic UI | Existing localized API responses, message keys, and direction helper | Arabic names for all three node types; Arabic search with two occurrences of one user; live Arabic user destination |
| Correct chevrons | `tree_expander_icon`, native Material icons, `aria-expanded`; removed old CSS mirror | LTR/RTL interaction tests and live computed transform `none` |
| Preserve permissions | Existing `can_open_organization_detail` gates name/search buttons and destination dispatch | Browse-only interaction test; capability suite |
| Preserve selectors | Compact tree/summary, eligibility and Select confirmation retained | Selector interaction and existing selector/paging assertions |
| Freshness and abandonment | Fresh page/branch reads on return; refresh invalidates instance snapshots; stale search/branch results ignored | Refresh/return renamed-data tests; abandoned-request test |

## Data lifetime and requests

Tree snapshots stay within one invocation of the authenticated page or selector.
Branches use existing `(type, ID)` keys and the current assignment-validity
filter. They are invalidated on refresh, validity change, and page recreation.
Only UI context and loaded-row counts persist in signed-in user storage, not
entity rows or translations. Existing sign-out clearing and locale reload apply.
Branch requests are coalesced while pending; independent expanded branches
restore concurrently within the API client's concurrency limit. Failed branch
requests are not cached, and an abandoned page cannot render or persist them.

Roots use 25 visible rows plus look-ahead. Unit and role branches retain their
existing bounded endpoints, offsets and Load more controls. Returning restores
only previously loaded pages under expanded branches. The full-page browser
no longer requests entity summaries when a node is selected or restored; only
the destination detail page obtains its own metadata. Selector summaries remain.

## RTL findings and NiceGUI-first correction

The existing tree uses a grid with logical indentation, which already places
nodes correctly under RTL. Native NiceGUI buttons and labels provide focus,
keyboard activation, full accessible names and direction-aware text. Directional
icons are selected through the same helper used elsewhere in the application;
the obsolete CSS icon mirror was removed to avoid double mirroring.

Live inspection found the toolbar had effective `direction: rtl` plus
`flex-direction: row-reverse` from the global application rule. That placed the
search field on the left. NiceGUI Row exposes wrapping/alignment but no direction
setting. The existing application language/direction setting was retained. As in
the classification workspace, a narrowly scoped override restores ordinary row
order for `.nicegui-row` and button contents inside this full-page browser only.
No global RTL rule or detail-page layout was changed. At 714px in both English and Arabic, document
width equals viewport width and tree rows have equal client/scroll widths.

## Verification results

- Organization browse API suite: **6 passed**, using a uniquely named disposable
  PostgreSQL database initialized from `database/schema.sql` alone.
- NiceGUI interaction suite: **32 passed**, including **12** organization tree
  tests. No database is used by these tests.
- Final organization interaction, saved-audience paging and capability checks:
  **25 passed** after the final navigation guard change.
- Broader focused frontend run: **150 passed, 4 failed**. All four failures were
  reproduced against HEAD source: classification height source assertion, brand
  RTL source assertion, navigation-section visibility source assertion, and
  drawer-collapse source assertion. They are unrelated to this redesign.
- Python compilation and `git diff --check` passed.
- Live English: unit, role and user destinations, separate expansion, repeated
  Back navigation. Live Arabic: translated tree/search data, multiple assignment
  occurrences, existing user details, chevrons and responsive geometry.

## Translation handoff

No translation artifacts changed and no administrator export was promoted.
**Zero keys added, changed or removed.** All **2,621** Arabic entries, including
text and provenance, remain unchanged. Disclosure controls use the existing
entity label plus native expanded-state accessibility instead of introducing a
new translated instruction. The existing Retry key is reused for initial errors.

Catalogue references/stale-key checks, identical sorted active-key coverage,
artifact hash, placeholders, blanks, markup and quality flags pass. The approved
terminology checker reports two pre-existing values in the unchanged artifact:
`classification_transfer.error.checksum_mismatch` and
`classification_transfer.retention_rule`. These unrelated curated values were
not replaced as part of organization work; they remain for translation review.

## Disposable database lifecycle

Early preview setup attempts encountered fixture constraints (generated status
and lifecycle timestamps). Each affected disposable database was dropped by the
runner's `finally` cleanup. The successful preview used server-time lifecycle
fixtures, translated sample entities and more than 25 child units. No tests,
fixture changes, preferences or translation publication touched a persistent
ERMS database.

Cleanup confirmed: preview API/UI processes stopped and
`erms_test_organization_e090884c296d` was dropped. The three earlier fixture
attempts also reported successful database drops. Service logs contained no
errors or tracebacks. Final organization presentation/selector checks passed
**6 tests** after the last source change.

## Sibling sorting follow-up

Implemented specification section 5.1: natural code ordering for roots, child
units and roles; all units before roles across pages; localized, language-aware
user ordering before pagination; stable entity/assignment ID tie-breakers.
Migration 029 adds the ICU numeric collation for existing databases. The
canonical schema includes the same definition independently.

Verification passed: **8 API tests** and **14 organization interaction tests**.
The new API cases cover natural root/branch ordering, role deferral, independent
offsets, selectors, English/Arabic ordering, regional-language fallback,
canonical-name fallback and duplicate-name ties. New LTR/RTL interaction cases
verify that roles appear after the final unit page and offsets remain correct.
Existing interaction cases verify fresh reads on return, search navigation and
abandoned-request handling. No layout or detail-page code changed in this
sorting follow-up; no additional live-browser visual inspection was performed.
Translation artifacts and keys remain unchanged.

The first API run found a duplicate-name fixture error, corrected before the
successful run. Both disposable databases
`erms_test_organization_b6b7f3d55376` and
`erms_test_organization_462bd53a11e0` were dropped successfully. A migration
smoke test removed the new collation from the disposable schema, applied
migration 029 and verified `U-2 < U-10` under its collation. The initial sandbox
connection attempt was denied before any database was created; the authorized
retry used only these disposable databases. No persistent database was migrated.

## Identity-detail header RTL correction

A separately approved follow-up corrects the Organization Unit, Role and User
headers. Live Arabic inspection found inherited `direction: rtl` combined with
`flex-direction: row-reverse` from the legacy global `.row` rule: the unit icon
was at x=420 while Back was at x=965 in a 1440px viewport. All three Back buttons
also hard-coded `arrow_back`.

The fix uses supported NiceGUI `ui.grid(columns="auto minmax(0, 1fr) auto")`
for the icon/avatar, identity text and Back control. Grid follows document
direction without the legacy flex-row reversal. NiceGUI Row exposes wrapping
and alignment but no direction setting. The existing button configuration uses
`icon-right=arrow_forward` in Arabic, matching the application's current button
content direction, and the normal `arrow_back` icon in English. No new CSS
overrides or translation keys are required. Existing callbacks, metadata,
permissions and management actions are unchanged.

Live checks cover all three pages in English and Arabic at 1440px and 714px:
identity icons/avatars lead the name, Back is on the opposite edge, its arrow
points right in Arabic and left in English, and document width does not overflow.
The Arabic unit header now places its icon at x=1004 and Back at x=420.

Targeted presentation checks passed **8 tests**. Live Back clicks returned users
and roles to their lists and the organization unit to Browse. Preview API checks
also passed **8 tests** before seeding. The disposable database
`erms_test_organization_8eb49af17d16` was used for the preview only.
Preview processes stopped and disposable database cleanup confirmed successful.
