# Message Monitor gateway health lifecycle

Approved contract: `specs/notifications-and-messaging.md` §11.3.1,
AC-MSG-GH-001–007. Implemented and verified on 5 October 2026.

## Behavior and artifacts

Each API worker continues to own one gateway and one health-record UUID. Its
heartbeat now reports concrete interface IP addresses and the owning API port.
Concrete binds are used directly; wildcard binds enumerate live interfaces
using psutil. Multiple addresses remain visible with an ambiguity explanation.
Discovery failure does not prevent reporting listener health. Endpoint metadata
remains limited to the privilege-gated Monitor, not the public health endpoint.

`gateway_health.py` defines the two fixed time boundaries. Reports are fresh
through exactly 45 seconds. Older reports warn until they reach 24 hours, when
they cease contributing to Monitor counts and pages. Every worker snapshot
removes expired records. PostgreSQL rechecks the deletion predicate after a
concurrent row update, so a refreshed heartbeat survives cleanup. Heartbeat
upserts recreate a retired record if reporting resumes. Graceful shutdown still
removes only the worker's own record.

Gateway-specific warnings are rendered beside the affected gateway's endpoint,
UUID, and last report time. Their status travels with the existing bounded
gateway page (25 rows, at most 50), avoiding an unbounded alert list in the
overview. Operational failure alerts remain in the overview. Expired records
are excluded immediately on reads even before the next cleanup heartbeat.
There is no new frontend cache or additional page request: the overview,
gateway page, and producer page remain three concurrent reads with abandonment
and revision guards.

The canonical schema adds nullable `host_addresses inet[]` and `api_port`
columns, with a port-range constraint. Migration
`045_messaging_gateway_health_lifecycle.sql` adds exactly the same columns to
existing databases without backfilling old rows. Old metadata is shown as
unavailable until the next heartbeat or expiry. No environment variables were
added. The API and root dependency manifests add `psutil>=7,<8` for portable
network-interface discovery.

## Requirement traceability

| Requirement | Implementation | Verification |
| --- | --- | --- |
| GH-001: remove own record on graceful shutdown | `operations.Worker.stop` | `test_snapshot_retirement_recreation_and_own_shutdown`; two real API processes, graceful termination removes only one |
| GH-002: overdue after crash, retire at 24 hours | `gateway_health` predicates and cleanup; `monitor` filtering | `test_fixed_time_boundaries_and_retirement`; `test_two_live_gateways_separate_reports_and_process_exit` forcibly kills an API process and checks overdue/expiry |
| GH-003: distinct disconnected/overdue status and recovery | `HEALTH_STATUS_SQL`; Monitor rendering | Exact 45-second boundary; paged status recovery; `test_one_real_listener_failure_and_recovery_does_not_hide_other` interrupts one real PostgreSQL listener and restores it |
| GH-004: preserve other instances, no healthy-instance suppression or mode setting | Per-UUID upsert/shutdown and per-row status | Two live API gateways on separate ports; one interrupted listener alongside a healthy listener sharing its endpoint |
| GH-005: expiry, concurrent refresh protection, recreation | `retire_expired`; worker upsert | Exact 24-hour boundary; real row-lock interleaving in `test_cleanup_preserves_concurrent_heartbeat`; retired worker record recreated |
| GH-006: English/Arabic rendering and translation lifecycle | Six new manifest/artifact keys; generic per-entry seed provenance | Bilingual Monitor interaction tests and live browser fixture; guarded seeding, publication/export/import regressions |
| GH-007: runtime addresses, API port, UUID, timestamp and ambiguity | `endpoint_identity`; API gateway page; `gateway_identity` renderer | IPv4/IPv6/concrete/wildcard/down-interface/discovery-failure checks; two actual API reports; bilingual browser inspection |

## Verification results

Database tests were run only through `tools/test_messaging.py`. Every run
created unique fresh/upgrade disposable databases, initialized from the
canonical schema or migration chain, verified schema parity and preservation
of a populated pre-upgrade gateway row with null new columns, and dropped both
databases afterward. Creation and cleanup succeeded on all runs.

- Gateway lifecycle/network acceptance: seven tests passed in the final
  gateway run (26.29 seconds).
- Per-entry Arabic generation provenance: one additional test passed after
  correcting its column-name assertion (2.72 seconds).
- Existing Phase 3 network/reconnection tests and operational producer-failure
  regression passed in an earlier combined run: 13 tests total, including the
  first six gateway tests (53.08 seconds).
- Existing Arabic artifact coverage, guarded source-copy seeding, and artifact
  export/import round-trip tests: three passed.
- Focused frontend Monitor interaction tests: three passed, covering both
  languages, repeated navigation, exactly three bounded reads per load,
  refresh after health change, and abandoned background responses.
- Translation Inspector regression: 13 passed when run independently.
- Catalogue source discovery, exact active-key coverage/order, all placeholder
  and nonblank checks, artifact hashes, preservation of all pre-existing Arabic
  items/provenance, Python compilation, and `git diff --check`: passed.

Two real API subprocesses reported healthy listeners separately at
`127.0.0.1:53012` (instance `1dbd4322-c2e2-49b9-ad03-bfe2d7ea7140`) and
`127.0.0.1:52993` (instance `ee8fd28a-3492-4d9f-b484-2676fb4f7732`). Both were
stopped and their disposable database was dropped after verification.

The in-app browser used the actual Monitor renderer with database-free fixture
responses. English/LTR and Arabic/RTL were inspected, including IPv6 endpoint
notation, address ambiguity, old-row fallback, and overdue-warning removal
after a resumed heartbeat and refresh. Returning to the other language retained
the appropriate labels. Computed direction was checked on the owning Monitor
container; English had no horizontal document overflow. The owned preview
process and browser tab were closed.

Screenshots and the reproducible preview source are under
`docs/verification/gateway-health/`. From the repository root:

```sh
PYTHONPATH=. frontend/webui/.venv/bin/python docs/verification/gateway-health/preview.py
```

Open `http://127.0.0.1:18091/en` or `/ar`. This preview uses fixtures, not a
persistent database or the real API. Its simulated endpoints are not the
actual subprocess endpoints reported above.

## Translation handoff and pre-existing check failures

`messages.en.json` and `messages.ar.generated.json` each gained exactly six
keys: `messaging.monitor.address_ambiguous`, `endpoint_unavailable`,
`gateway_endpoint`, `instance_id`, `last_report`, and `overdue` (all under the
`messaging.monitor` prefix). No keys were changed or removed. No administrator
export was promoted, and every prior Arabic item and its provenance remain
unchanged. The English manifest and Arabic items remain lexicographically
aligned. New Arabic values are generated drafts requiring human review before
publication. Their batch provenance is stored per entry; the generic seed
utility now respects that metadata in a mixed administrator/generated artifact.

The six new keys pass the strict terminology and unexplained-Latin checks.
The full legacy generator validator still rejects nine unchanged curated keys
(Vital Record wording, the approved artifact's `Re:` prefix, and the hold-removal
aggregation wording). Those existing translations were preserved, not replaced
to satisfy a machine checker. This full-artifact quality issue remains for
curated review; full strict terminology validation is not claimed to pass.

The broader existing Phase 5 interaction file also has three unrelated failures:
the English/Arabic Recently Deleted tests look for an obsolete Open control,
and the capture-button test uses an obsolete interaction assumption. All three
were reproduced using the original checked-in test file, independently of the
new Monitor tests. The focused Monitor tests pass. Combining the Inspector's
global-slot test with NiceGUI user-plugin tests also requires separate fixture
isolation; its independent suite passes.

## Deployment

Persistent databases have not been migrated by this verification work. Apply
migration 045 before restarting the API with the new code. Install updated API
dependencies through the existing runtime setup, then restart the API and WebUI.
There is no endpoint backfill, mode setting, or advertised-IP setting. Seed the
six Arabic drafts through the existing explicit translation seed workflow, then
review and publish them through Translation Administration. Until publication,
the existing localization policy uses English fallback for the new keys.

## Monitor audit shortcut follow-up

The Monitor's authorized audit-history button previously passed `audit-trail`
to the generic entity collection handler, which raised `KeyError` because Audit
Trail is a dedicated page rather than an `ENTITIES` collection. It now uses the
same navigation guard as the sidebar and opens `select_audit_trail` with the
initial entity-type filter `system_notification`. This is the existing entity
type used for messaging administration and notification test-send audit events;
the fix does not introduce new audit events or claim a complete human-message
send history.

The selected filter is visible and editable, is applied on the first search,
and is retained across pagination. It is preserved even when the filter-options
endpoint currently has no matching event type. The ordinary sidebar entry calls
the page without an initial filter and remains unfiltered. `audit.view` gating
is unchanged. No catalogue entries or user-facing wording changed in this fix.

Six EN/AR interaction cases execute the actual application callback, navigation
guard, and audit-page handler with fixture API responses. They verify first-read
scope, pagination, default sidebar behavior, read cancellation, denied navigation
guards, and hidden controls without authorization. Together with the three
Monitor regressions, **nine tests passed**. Compilation, catalogue discovery,
and `git diff --check` passed. No database-backed suite was used for this fix.

The in-app browser also verified the button and selected filter in both English
and Arabic using the actual handlers with database-free fixtures. Evidence is
`docs/verification/gateway-health/audit-shortcut-en.png` and
`audit-shortcut-ar.png`; `audit_preview.py` reproduces the fixture on port 18092.
The owned preview process and tab were closed. Restart the WebUI if it is still
running the earlier code; no further database migration is needed.

## Immediate listener-state reporting

Listener connection, disconnection, and reconnection now notify the lifecycle
worker to publish health immediately, retaining the 15-second periodic heartbeat.
The worker consumes the notification before taking its snapshot, so a transition
during a report triggers a subsequent report rather than being lost. Shutdown
continues to remove only the owning worker's record. The Monitor retains its
existing explicit refresh behavior; a view opened before connection can briefly
show the initial disconnected state, but the database no longer waits for the
next periodic heartbeat to reflect connection.

Verification extends AC-MSG-GH-003 with real listener connection, disconnection,
and reconnection reports within five seconds, without manual snapshots, while
another listener remains healthy. A separate regression verifies transitions
during a snapshot are retained and the worker does not spin. All nine gateway
health tests passed; fresh/upgrade schema parity and data preservation passed,
and both uniquely named disposable databases were dropped. No schema,
configuration, or translation artifact changes are required for this fix.

## Approved At-a-glance Monitor presentation

Implemented the user's selected mockup in `frontend/webui/messaging_monitor.py`
and recorded its presentation contract in notifications specification §11.3.
All data continues to come from the existing three concurrent reads. Summary
cards and the health ring use complete gateway overview counts, not the current
25-row page. Attention is the number of unhealthy reports plus operational
alerts, with a visible breakdown, rather than a distinct-incident count.

The responsive NiceGUI grid presents identified gateway rows and operational
counters alongside a health ring, active/restorable Inbox and Outbox breakdowns,
and producer emission bars. Instance IDs and every existing secondary metric
remain in expandable diagnostics. Overdue counters are labeled as last-reported
values. Producer bars are explicitly a comparison of loaded producers; loading
another bounded producer page recomputes their common scale. Empty states do
not invent healthy percentages, and unresolved producer failures remain visible.

Refresh retains the preceding usable snapshot during loading and read failure,
disables overlapping refresh actions, and preserves disclosure state. Disclosure
state is limited to the current page and keyed by section, instance ID, or
producer code; it stores only expansion booleans and is discarded on navigation.
No operational cache, new API contract, table, configuration, migration, or
database-backed test was added. The authorized filtered audit shortcut is
unchanged.

### Traceability and verification

| Approved presentation requirement | Implementation and evidence |
| --- | --- |
| Complete summary counts and health ring | Existing overview aggregates; interaction test with ten total instances but one loaded row |
| Retention and producer visualization | Native NiceGUI progress components; tests verify active/restorable ratios and producer rescaling after paging |
| Preserve bounded diagnostics | Independent 25-row cursor requests; all prior fields retained under expansions |
| Non-destructive refresh | Delayed concurrent-read test and failed-read test preserve the previous snapshot; recovery updates the ring |
| Page abandonment and authorization | Existing abandonment regression and six audit authorization/navigation cases pass |
| EN/LTR and AR/RTL | Parametrized interactions plus browser verification of actual renderer with the application's exact stylesheet at 1280px and 360px |

**12 Monitor/audit interaction tests passed**, including three new overview
cases. **76 localization/API-client tests passed**. A preexisting source-boundary
assertion was updated for the audit handler's already-added optional filter
argument. Compilation, catalogue reference/stale-key checks, and
`git diff --check` passed. Source text discovery reports no untranslated Monitor
candidates. Initial navigation and Refresh each retain three concurrent requests;
each Load more action adds one bounded request. Browser console reported no
errors or warnings. Owned fixture server and browser tab were stopped/closed.

Browser inspection first exposed that a minimal fixture inherited NiceGUI's
LTR body defaults despite an RTL html style. The fixture now applies Wathiq's
actual shared stylesheet and supported html direction props. The Monitor reuses
the existing `messaging-workspace` native-row treatment documented in design
language §19.1, correcting the application's legacy global row reversal without
introducing a new CSS override. Numeric connected/total ratios explicitly use
native `dir=ltr`; value labels use `dir=auto` where appropriate. Verified RTL
grid/row direction and no horizontal page overflow in both directions at 360px.

Reproduce the database-free fixture with:

```sh
PYTHONPATH=. frontend/webui/.venv/bin/python docs/verification/gateway-health/overview_preview.py
```

Open `/en` or `/ar` on port 18095. Fixture controls demonstrate recovery, empty
data, and failed reads; the displayed operational values are illustrative.
Rendered evidence: `overview-en.png`, `overview-ar.png`, and
`overview-en-summary.png` in `docs/verification/gateway-health`.

### Translation handoff

Added **17** contextual `messaging.monitor` definitions and Arabic review drafts
in the English manifest and canonical Arabic artifact; no existing key was
changed or removed. All **2,901** existing Arabic items, including wording and
provenance, were preserved exactly against the artifact immediately preceding
this change. No administrator export was promoted. English and Arabic active
keys/order, placeholders, nonblank text, markup, hash, and provenance checks
pass; every new draft passes terminology and Latin-token validation.

The strict whole-artifact draft validator still reports **ten unchanged legacy
curated findings**, identical before and after this change. They were not
overwritten. Exact findings, hashes, and added keys are recorded in
`overview-catalogue-validation.json`. New Arabic drafts require the existing
explicit seed, review, and publication workflow; runtime English fallback applies
until publication. Restart the WebUI to load the new layout and the API to
synchronize its new English definitions through the existing guarded path.

## Operational counter subtitles

The user requested localizable, plain-language subtitles beneath every
operational counter. All 21 instrumented metrics now have muted descriptions
in summary counters, expanded operational counters, producer emission displays,
unresolved producer indicators, and producer diagnostics. Descriptions follow
the existing measurements: recipient deliveries rather than unique messages,
average durations in seconds, repeated group examination, and test inclusion
or exclusion where applicable. No measurement or API behavior changed.

Added 21 English definitions under `messaging.monitor.description.*` and 21
Arabic generated drafts with per-item provenance. All 2,918 preceding Arabic
items were preserved exactly; no administrator export was promoted, and no
existing definition or translation was changed or removed. New drafts pass
terminology/Latin validation and catalogue coverage/order/hash/provenance checks.
The same ten legacy curated strict-validator findings remain unchanged; see
`counter-subtitles-catalogue.json` for exact keys and evidence.

The existing explicit seed utility synchronized definitions and seeded drafts
into both user-used databases. `demo`: stored 44 previously source-copy entries,
including all 21 new subtitles, with 2,938 protected translation rows unchanged.
`demo3`: stored 46 previously source-copy entries, including all 21 new subtitles,
with 2,936 protected rows unchanged. Both runs reported zero failures, zero
legacy wording corrections, and zero awaiting-generation entries. New subtitles
are `generated` / `draft`, with no published text, ready for human review and
publication through Translation Administration. Previously pending generated
artifact entries were seeded by the same generic workflow as well.

Two new EN/AR interaction cases verify subtitle coverage against the backend's
actual 21-metric declaration (read as source; no database imports), their
presence in both operational and producer diagnostics, and muted styling.
The full focused Monitor/audit set passes. Browser verification of the actual
renderer confirms 12px muted text, readable wrapping, expanded diagnostics,
and no page overflow at 1280px and 360px in English/LTR and Arabic/RTL.
Screenshots: `counter-subtitles-en.png`, `counter-subtitles-ar.png`, and the
focused `counter-subtitles-summary.png`. The fixture process and tab were closed.
Restart the WebUI to load the subtitles. No migration is required.
