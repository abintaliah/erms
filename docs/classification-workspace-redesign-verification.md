# Classification workspace redesign — 29 September 2026

The user-approved tree and dedicated-details design replaces specification
section 14's former four-panel layout. No schema, retention semantics, entity
permissions or backend endpoints changed.

## Requirement traceability

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Central scheme-rooted tree; distinguish reused codes | `classification_workspace.py`: scheme roots, contextual search and scheme/ancestor identity on details | Live English/Arabic tree; independent paging interaction test |
| Clicking the node opens details; separate expansion only | `node_link`, `select_scheme`, `focus_classification` | Node navigation interaction test; live scheme and terminal details |
| Plus creates under its matching node | `create_classification`, existing `open_editor` with locked scheme/parent | Creation-context interaction test; terminals have no child action |
| Inactive schemes/nodes remain distinguishable | Muted scheme background and node text; direct, parent and scheme badges | Inactive-ancestor interaction test; live seeded inactive scheme/branch/descendants in English and Arabic |
| Existing fields, lifecycle, deletion and history | Dedicated identity/metadata/action cards; existing editor/history callbacks, version and reason headers, deletion explanations | 12 classification API tests; detail interaction tests and live metadata inspection |
| Retention timeline and provenance | Shared `retention_timeline.py`, used by aggregation and classification details | Direct/inherited retention interaction test; live three-stage timeline in English/Arabic; existing presentation tests updated to shared renderer |
| Ascending classification codes; bounded paging/search | Existing server code order; 25 visible rows plus look-ahead per branch and scheme; scoped four-field search | Independent branch/scheme paging and scoped-search interaction tests; API regression tests |
| Freshness and abandoned work | Instance revision guard, per-branch pending guard, search revision, fresh details/return reads | Abandoned-response and changed-metadata interaction tests; repeated live tree/details navigation |
| Arabic and RTL | Canonical catalogue merge, direction-aware expanders, logical indentation, shared timeline | Catalogue validation; live Arabic details/tree and narrow-width inspection |

Scheme roots retain their existing sort choices, defaulting to code ascending.
Filtered scheme searches use the existing search endpoint and code order.
Search result totals and empty-scheme guidance are retained. Classification
siblings always use code ascending, independent of the scheme-root sort choice.

## Data lifetime and layout

Snapshots belong to one workspace instance within one authenticated page and
language. Children are keyed by `(scheme_id, parent_id)`, paths by classification
ID. Refresh, return and mutation invalidate these snapshots. Only IDs, expansion,
loaded-page counts, sort and search preferences survive workspace recreation;
sign-out clears them. A restored search scheme is fetched by ID. Failed reads
are not cached; existing tree content remains available during refresh, and
initial/detail failures have retry and return controls. Independent reads use
the API client's bounded concurrency. New selections invalidate late responses.

Live RTL inspection found `direction: rtl` together with the application's global
`.row { flex-direction: row-reverse }`, reversing the new rows twice. NiceGUI's
`Row` supports wrapping and alignment but has no direction option. The existing
application direction setting and logical indentation were retained; a scoped
`.classification-workspace` override makes rows and button contents use normal
flex order under RTL. The existing shared timeline CSS already orders stages
correctly. No global RTL rule was changed. Material hierarchy glyphs also mirror in RTL.
Node buttons now use standard NiceGUI rows/icons/labels with a 12px logical gap,
retaining codes while ellipsizing only titles and exposing full-title tooltips.
Title/code spans use `dir=auto` so English entity names truncate at their own
text end even inside the Arabic interface. Live measurements at 714px showed
no document overflow, a 12px gap, ellipsis on a 339px title containing 412px of
text, and mirrored scheme/branch/terminal glyphs.

The scheme and classification detail pages reuse the Aggregation command grid
and categorized action-card presentation. Metadata/hierarchy, lifecycle and audit
commands retain their prior behavior and permissions. Back navigation remains in
the summary. Live desktop inspection confirmed the action panel on the right in
English and left in Arabic; the Arabic terminal retained its three-stage retention
timeline and had no child-creation action. At 714px the summary and controls
stacked, with document width equal to viewport width. Two additional interaction
tests cover panel grouping and back-link placement for both detail types.

## Automated checks

- Classification API: **12 passed**, using a newly created disposable PostgreSQL
  database initialized from `database/schema.sql` alone.
- NiceGUI interaction suite: **9 passed**. Run separately because NiceGUI's user
  plugin resets process-global UI state:
  `DATABASE_URL='' frontend/webui/.venv/bin/python -m pytest frontend/webui/interaction/tests -q -o asyncio_mode=auto`
- Focused classification/shared-retention presentation checks: **14 passed**.
- Full existing frontend suite: **354 passed, 5 failed**. All five failures also
  occur against an untouched HEAD snapshot: advanced-search stale-role assertion,
  brand RTL CSS assertion, empty navigation sections, organization selector
  confirmation, and security-level selector assertion. The isolated baseline
  additionally had a timezone-default assertion failure because it had no local
  `.env`; this was not a redesign regression.
- Python compilation and `git diff --check` passed.
- Live validation service logs contained no errors or tracebacks.

## Translation handoff

Both `messages.en.json` and canonical `messages.ar.generated.json` changed.
There was no promotion of a new administrator export. All **2,557 retained Arabic
entries**, including wording and provenance, remain byte-for-byte equivalent as
JSON values. Six new keys were added under `classification_browser`:
`add_child`, `add_root`, `back_to_tree`, `retry`, `toggle_branch`, `toggle_scheme`.
Five additional keys under `classification_details.actions` provide the scheme,
classification, metadata, lifecycle and audit headings. All eleven Arabic values
are generated drafts requiring human review/publication.

The six live browser drafts were initially English source copies. They have now
been corrected to Arabic using guarded, audited updates; the five new action
headings were synchronized and populated too. Existing reviewed or published
translations were protected. These eleven live drafts were not published by this
work; publication remains in Translation Administration.
They were published only in the disposable validation database for RTL testing.
Normal deployment must use the existing catalogue synchronization/review workflow.

Eleven unused keys from the removed panel/selection presentation were removed.
The reference checker confirms no remaining application references. English and
Arabic now have **2,568 identical active keys**, in identical sorted order.
Catalogue SHA256, nonblank text, placeholders, disallowed markup, quality flags,
source candidates and approved terminology checks passed. Existing artifact
export metadata and all retained per-entry provenance were preserved.

Removed keys:

- `webui.render_scheme_list.label.counts_loading_1ffb90cd`
- `webui.render_scheme_list.text.no_description_7f023195`
- `webui.render_workspace_right.label.its_information_will_appear_here_bc4769c5`
- `webui.render_workspace_right.label.its_metadata_and_effective_retention_rule_f231c468`
- `webui.render_workspace_right.label.select_a_classification_192337f3`
- `webui.render_workspace_right.label.select_a_classification_scheme_825fcd9e`
- `webui.render_workspace_right.label.select_a_scheme_to_browse_its_classificati_afdd23e3`
- `webui.render_workspace_right.tooltip.select_a_branch_classification_before_addi_b9ec1645`
- `webui.render_workspace_right.tooltip.terminal_classifications_cannot_contain_ch_80c2bf31`
- `webui.select_classification_workspace.label.classification_schemes_6020e95d`
- `webui.select_classification_workspace.text.classification_schemes_79225ac9`

## Database safety

The development database was backed up before source changes to
`database/local-backups/before-classification-redesign-20260929T081644Z.dump`.
The custom-format archive was readable by `pg_restore --list` (912 entries).
SHA256: `4488b693b87f372971e68b5e06167ecad3ccc9b97c5bb484846d5d55dc494fec`.
All test data, preference changes and Arabic test publication were confined to
uniquely named disposable databases; no test suite used the development database.

Cleanup confirmed: both `erms_test_classification_b5bb219a2f58` and
`erms_test_classification_7d2f86c45dca` were dropped after stopping their API/UI
processes. Final English and Arabic checks at 714px both had document width equal
to viewport width; long titles used ellipsis with a 12px icon gap. English glyphs
remained unmirrored and Arabic scheme, branch and terminal glyphs were mirrored.

Follow-up panel validation also cleanly stopped its services and dropped
`erms_test_classification_fa1f453da7dd`. Its classification API suite passed all
12 tests; the updated interaction suite passed all 9 tests.
