# Advanced Search implementation traceability

**Specification:** `specs/advanced-search.md`, approved revision 1.0  
**Current delivery phase:** Phase 4 — record component metadata criteria

| Requirement | Planned phase | Implementation evidence | Verification evidence | Status | Notes |
| --- | --- | --- | --- | --- | --- |
| §§7.1–7.2 ownership, versioned definition, direct role/unit audiences and relational integrity | 1 | `database/schema.sql`; migration `018_add_advanced_search_phase1.sql` | `test_saved_searches.py`; canonical/migration disposable-database checks | verified | One owner; separate role/unit grant tables; direct units only |
| §§7.3, 8.1 creator/administrator update authority and audience authority | 1 | `backend/services/api/saved_searches.py` | ownership, audience and negative authorization API tests | verified | Owner update does not depend on retaining save; audience update does |
| §8.1 delete matrix | 1 | saved-search delete route and capabilities | owner/non-owner privilege matrix and dependency tests | verified | Non-owner requires delete plus administrator |
| §8.2 approved built-in profile grants | 1 | canonical schema, migration 018, `security/catalogue-seed.json` | catalogue and database privilege tests | verified | Manager and Officer intentionally differ by administrator privilege |
| §8.3 server-computed capabilities and reasons | 1 | saved-search serializer/capability evaluation | API capability tests | verified | Client state is non-authoritative |
| §§9.1–9.3, 9.5–9.6 list/create/read/update/delete/admin APIs | 1 | `backend/services/api/saved_searches.py`; router registration; policy registry | API tests and policy inventory | verified | CRUD and administration contract |
| §4 canonical, versioned, bounded definition validation | 1 | `SavedSearchDefinition`; `canonicalize_search_request` | grammar boundary/API tests | verified | Reuses the resource search validator without executing results |
| §11 immutable governed change history | 1 | saved-search history and reason triggers; API event metadata | history tests | verified | Execution history is Phase 2 and remains non-governed |
| §12 lifecycle and optimistic concurrency | 1 | FK/lifecycle-aware audience SQL; `If-Match`; DB version trigger | lifecycle and stale-write tests | verified | Ineffective grants remain stored |
| §13 lookup indexes | 1 | canonical schema and migration indexes | schema and migration initialization checks | verified | No result execution in Phase 1 |
| AS-01 navigation visibility and ordering | 2 | `frontend/webui/app.py`; `frontend/webui/capabilities.py` | capability unit tests and live browser DOM/visual inspection | verified | Advanced Search is above Aggregations and requires either supported view privilege |
| AS-02–AS-05 recursive controlled builder | 2 | typed builder helpers and Advanced Search workspace in `frontend/webui/app.py` | `test_advanced_search_builder.py`; live builder interaction | verified | Existing JSON grammar only; client guards 50 leaves/five levels; target change confirms reset |
| AS-06 pageable result cards | 2 | Advanced Search execution/result renderer in `frontend/webui/app.py` | live desktop and 390px responsive browser inspection; empty-state execution | verified | Uses Wathiq cards, not `ui.table`; First/Previous/Next/Last preserve builder state |
| AS-07 authorized results, snippets, component preview and freshness | 2–4 | existing governed `search_rows`; matched-component attribution enriched with authorized preview metadata while retaining safe snippets; preview action reusing `preview_record_components`; index-freshness response | search authorization coverage plus 178 frontend tests including match-only rendering and governed-viewer wiring | verified | Only attributed matching components render; unmatched record components are never added; unsupported/unavailable matches show a disabled preview icon |
| AS-09, AS-22 saved execution freshness and cap | 2 | `POST /api/v1/saved-searches/{id}/execute` | `test_execute_saved_search_uses_fresh_results_and_enforces_stored_cap`; disposable DB run | verified | Runtime may override only page size, offset and authorized debug; stored cap cannot be raised |
| AS-18 page states and accessibility | 2–3 | validation summary, loading spinner, empty/error/partial-index presentations, labelled groups and controls; saved-search dialogs and read-only presentation | helper tests; live keyboard-semantic DOM and desktop visual inspection | verified | Existing logical-layout and responsive conventions are preserved by the Phase 3 controls |
| AS-08, AS-10–AS-13, AS-15–AS-17, AS-19 | 1 | governed saved-search model, APIs, audience rules, policy catalogue and canonical/migration SQL | 36 focused API/security tests plus schema/migration verification | verified | Fresh disposable schema and migration databases were both dropped successfully |
| AS-14 optimistic concurrency UX | 3 | `If-Match` client methods; stale update/delete handling and latest-version reload dialog | API concurrency tests; client header unit test | verified | Winning stored definition is preserved and the client offers an explicit reload |
| §§5.2, 5.4, 5.5, 10 task-first and durable saved-search workspace UX | 3–4 | Desktop Criteria/Saved Search two-column workspace with responsive stacking; workspace-owned category metadata and independent suggestion list; explicit Update saved search action; search-first open dialog; durable workspace snapshot in `frontend/webui/app.py` | 178 frontend tests; arbitrary-category restore, category-authority/commit/update, workspace-layout, deferred-discard-confirmation, and drill-down restoration regression checks | verified | Restored categories are no longer passed as invalid values to an empty hidden select; arbitrary saved category text such as `General` survives save and Back/breadcrumb restoration |
| §9.6 administration filters | 3 | bounded owner, target, audience, name, category, maximum-results and update-date filters in API and UI | focused API filter test; live administration listing inspection | verified | Administrative discovery does not grant execute capability or reveal results |
| §4.3 and AS-23 component catalogue and result contract | 4 | controlled public-to-column catalogue and Records-only compiler path in `backend/services/api/search.py` | all-eight-field typed-operator tests; aggregation/sort/internal-field rejection; saved execution test | verified | Uses ordinary comparison leaves; component fields are filters only and result rows remain records |
| §4.3 and AS-24 same-component Boolean semantics | 4 | authorization-aware correlated component scope in `_compile_expression` | false cross-component trap, nested component-only `or`, independent `or`, complete negation, mixed record/component and record-only-alternative DB tests | verified | One authorized component satisfies predicates within an `and` scope without changing ordinary Boolean meaning when a record-only alternative succeeds |
| §4.3 and AS-25 security, bounds and performance | 4 | bound values, controlled identifiers, existing depth/leaf/operator validation, component sort exclusion, `digital_components_record_id_idx` correlation | hidden-component, injection/internal-field, limit, response-contract and forced-index query-plan tests | verified | Authorization is evaluated inside the correlated existence test before matching/counting |
| §5.3 and AS-26 component builder UX | 4 | grouped Record/Digital component field labels, typed and clearable controls, contextual same-component help, chip-rendered controlled content-status catalogue, sort exclusion and RTL logical-edge CSS in `frontend/webui/app.py` | 176 frontend tests including contextual-help, chip-rendering and controlled-selector regression checks | verified | Component guidance appears only when a component field is present; builder exposes no joins, quantifiers, SQL, component table names or component full-text operation |
| §5.3 governed relationship pickers | 4 | card-style searchable relationship options; classification and organization-unit Browse actions; classification-scheme-to-aggregation hierarchy browser in `frontend/webui/app.py` | 176 frontend tests including hierarchy-path regression checks | verified | Medium has a controlled selector; aggregation selection drills through governed classification and aggregation nodes; selected values remain IDs and can be cleared |

All four approved Advanced Search phases are complete.

## Matched-component result presentation

Advanced Search record cards treat component rows as search attribution rather
than as a list of every component attached to the record. Only components
identified by the executed criteria as matches may be rendered. Their safe
highlighted snippets remain visible, and their preview icons invoke the
existing governed component viewer. Authorized component metadata may enrich
those matched rows to determine previewability, but must never introduce an
unmatched component into the result card. A preview request independently
rechecks the caller's current component permissions.

## Phase 1 exit reconciliation

On 25 September 2026, the focused API/security suite completed with **33
passed**. A fresh uniquely named database initialized from `database/schema.sql`
and a separate uniquely named pre-Phase-1 database upgraded through migration
018 both passed verification. Cleanup was checked after the run; no disposable
Advanced Search database remained. No unexplained Phase 1 requirement omission
or implementation behavior was identified.

## Phase 2 exit reconciliation

On 25 September 2026, **35 focused API/security tests** passed against a newly
created disposable canonical-schema database, and the separate pre-Phase-1
database upgraded through migration 018 also passed and was dropped. The
complete frontend unit suite completed with **164 passed**. Live browser verification
confirmed navigation order, labelled controls and groups, client validation,
an executed empty state, responsive layout at 390 pixels, and no browser console
warnings or errors. Phase 3 retains saved-search management experiences and the
final expanded authorization, performance, security, and Arabic/RTL matrix.

## Phase 3 exit reconciliation

On 25 September 2026, **36 focused API/security tests** passed against a newly
created disposable canonical-schema database. The separate pre-Phase-1 database
upgraded through migration 018 also passed, and both databases were dropped by
the test harness. The complete frontend suite completed with **166 passed**.
Live browser verification covered structural-invalid action disabling, private
creation, owner context, accessible discovery, the separate administration
listing, and the unsaved-navigation guard. The browser-rendered workspace used
the established Wathiq cards and controls; no raw table was introduced.

## Phase 4 exit reconciliation

On 25 September 2026, **54 focused API/security/component-search tests** passed
against a newly created disposable canonical-schema database. The separate
pre-Phase-1 database upgraded through migration 018 also passed; both databases
were dropped by the harness. The complete frontend suite completed with **168
passed**. Live browser verification confirmed the separate Record and Digital
component labels, all eight component choices, contextual same-component help,
component-field exclusion from sorting, keyboard-semantic controls, and record
result empty-state behavior. RTL logical-edge rules cover the added indentation,
group boundary and trailing status alignment. No schema or migration change was
required because Phase 4 extends the version-1 controlled query compiler only.
