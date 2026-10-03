# Notifications and messaging — Phase 5 report

Specification: `specs/notifications-and-messaging.md`, approved revision 1.20.
Scope: §16.5, records, retention, monitoring, and production hardening.

Status: implementation and functional verification complete, verified 3 October
2026. Deployment to persistent environments remains an operator step.

## Implementation

Human messages can be preserved through the existing record draft and commit
workflow. The draft takes its initial title and date from the selected message,
uses the highest included security level as its minimum, and retains ordinary
record-create, destination, role, closure, numbering, and clearance controls.
The selected message is component 1; earlier ancestors follow in deterministic
chronological order. A final provenance PDF and immutable structured mappings
are committed with the record and all components in one transaction. System
notifications, tests, and amendment notices are ineligible.

Generated PDFs contain immutable headers, sanitized body, safe resource
references, original action fields, amendment history, and effective action
state. They exclude recipients' delivery/read state. Changa is subset embedded;
the renderer has no network access and independently validates PDF/A-2u and
PDF/UA-1 before any authoritative commit. Failed authorization, generation,
staging, promotion, provenance, or final commit leaves no partial record.
Committed records are independent of source-message purge. Later amendments
never rewrite an earlier capture.

Expiry warnings remain passive mailbox indicators. Early personal deletion of
human messages requires that user's committed capture with a still-existing
record; system/test notifications and amendment notices have no capture gate.
Inbox and Outbox have Recently deleted views with restoration deadlines.
Restoration after expiry and repeated delete/restore cycles never extend the
original deadline. Restoration before expiry returns to ordinary expiry.

Cleanup discovers complete undirected conversation groups, including branches
and amendment notices. It locks the group, rechecks membership and every expiry
and mailbox deadline, then deletes all dependent messaging content atomically.
It leaves no envelope or delivery tombstones. Stable request receipts retain
purged-result evidence; captured record provenance retains historical IDs.
Unsent message drafts and record capture drafts do not pin a conversation.
Expired ancestors remain readable through an authorized active/restorable
linked root, subject to current clearance, but cannot become new send sources.
Ancestry authorization transfers only its aggregate result and requested message
to Python, not every ancestor's body.

Each API instance runs a bounded lifecycle worker using ordinary pooled
connections. Candidate pages, identifier fetches, and draft batches are bounded;
a large group's atomicity is never sacrificed to meet a batch size. Concurrent
workers coordinate through row locks. Group lock and statement timeouts retain
failed groups for retry. Shutdown waits for the active cleanup transaction to
finish before closing the pool.

Monitor is separately protected by `messaging.monitor` in navigation and API
policy. It exposes content-free gateway health, emitted/received counts,
connections/reconnections, slow clients, catch-up/restriction counts, capture and
cleanup measurements, production/test metrics by producer, mailbox lifecycle
counts, and group cleanup observations. Failures and stale/disconnected listeners
raise alerts; audit navigation additionally requires `audit.view`. Producer and
gateway lists use bounded server pagination. No frontend cache was introduced;
view/identity guards discard abandoned responses.

## Requirement-to-implementation-to-test traceability

| Approved requirement | Implementation | Verification |
| --- | --- | --- |
| MSG-017 human-only capture and ordinary permissions | `messaging/capture.py`, record-draft routes in `main.py` | Real committed capture; amendment-notice rejection; record.create denial; account recheck; fixed component controls; security floor |
| Selected/ancestor order, filenames, provenance agreement | `capture.sources`, `filename`, `finalize_staging`, `persist` | Committed three-component capture, stored ordered mappings and PDF text matching capture/record/source IDs |
| PDF/A-2u, PDF/UA-1, Changa, tags, Unicode, links, determinism | `capture_pdf.py`, bundled licensed assets | Independent veraPDF profiles; Poppler font/text/tag/link checks; English/Arabic visual inspection |
| Atomic capture at all boundaries | Ordinary record transaction, PostgreSQL staging/promote, capture mappings | Renderer/validation, staging, finalization, promotion and provenance fault injection; zero partial authoritative rows |
| Capture limits and revalidation | `capture.sources`, `stage_messages`, `prepare`, subprocess deadlines | Ancestor/combined-byte limit tests; changed authorization; security floor; immutable component controls |
| Record independence and immutable earlier captures | Capture foreign-key handling and content storage | Record/components survive group purge; earlier PDF bytes unchanged after an amendment; record disposition preserves historical capture IDs |
| MSG-020 personal deletion and restoration boundaries | `retention.mailbox_change`, `deleted_listing`, `deleted_detail` | Own-capture gate, other user's capture denied, disposed record no longer qualifies, fixed repeated restoration deadline, expired deadline denied; live EN/AR workflow |
| Complete connected-group purge without message tombstones | `retention.purge_group`, migration 037 guards | Branched group waits for youngest member; amendment notice participates; dependent rows gone; transactional rollback; parallel workers |
| Retained ancestry remains authorized and read-only | `relationships.linked`, source validation | Expired ancestor readable from live descendant; cannot restore after deadline or use expired source for a send |
| Stable replay after purge and catch-up gaps | Purged-result receipt marker and durable mailbox sequence | Replayed send returns 410; catch-up skips purged deliveries while advancing cursor |
| Draft/capture independence and bounded cleanup | No source FK on capture drafts; existing draft snapshots; `cleanup_drafts`, worker | Message and capture drafts do not pin purged group; stale-source send/capture commit rejected; expired draft children removed; batch smaller than a whole group; capture/cleanup coordination; one group attempt per candidate page |
| §11.3 operational privacy, privileges, alerts | `operations.py`, `monitor.py`, `messaging_monitor.py` | Privilege-only Monitor account, no subjects/bodies/recipient labels, producer/test separation, failure resolution, cleanup metrics; live LTR/RTL and abandonment tests |
| §16.6 schema fidelity, regression, translation preservation | Canonical schema plus migration 037, policy registry, catalogue merge | Fresh/upgrade schema parity and data preservation; prior-phase/API/authorization suites; exact-key/hash/provenance validation |

## Verification evidence

Completed test runs (overlapping suites are reported separately):

- Final Phase 5 backend suite: **19 passed** in 65.62 seconds.
- Phase 5, Phase 2, ordinary records API, and content authorization regression
  run: **104 passed** in 193.61 seconds. The final Phase 5 run additionally
  verified the subsequent amendment PDF and record-disposition coverage.
- Phase 3 regression suite: **6 passed** in 43.67 seconds.
- Final frontend interaction, workspace, administration, live messaging, API
  client, and capability suites: **86 passed** in 6.53 seconds.
- Fresh/upgrade schema parity, catalogue coverage/order/provenance/hash checks,
  Python compilation, and `git diff --check`: passed.
- Independent PDF/A-2u and PDF/UA-1 validation: passed for representative
  English/Arabic PDFs and all four extracted committed-capture PDFs, including
  amendment history. Font embedding, Unicode extraction, links, tags,
  deterministic output, and rendered appearance were verified.

Backend Phase 5 cases are in
`backend/services/api/tests/test_messaging_phase5.py`; frontend Phase 5 cases
are in `frontend/webui/interaction/tests/test_messaging_phase5.py`.
There are no unresolved functional test failures. An earlier fixture failure
was corrected to use the account deactivation timestamp rather than writing a
generated status column; the final suite verifies that account recheck.

Automated conformance reports, font and link reports, representative English and
Arabic PDFs, and renderings are under `docs/verification/messaging-phase-5`.
The `committed` subdirectory contains PDFs extracted from a real disposable
record capture, including its final provenance. These are synthetic test data.
Live browser verification created ordinary records from English and Arabic
capture flows, verified component order/provenance, exercised deletion and
restoration, and inspected Monitor with repeated navigation. RTL had no
horizontal document overflow at the 1280-pixel verification viewport.
Screenshots include the [Arabic capture editor](verification/messaging-phase-5/capture-editor-ar.jpg),
[committed Arabic record](verification/messaging-phase-5/record-ar.jpg), and
[English Monitor](verification/messaging-phase-5/monitor-en.jpg).
The [catalogue change manifest](verification/messaging-phase-5/catalogue-changes.json)
records new keys and preservation checks.

All database runs use `tools/test_messaging.py`: unique disposable fresh and
upgrade databases, canonical initialization, schema parity, isolated fixtures,
and cleanup. Every test and browser-preview database was successfully dropped,
and preview servers were stopped. No development or other persistent database
was migrated or tested.

## Deployment and remaining review

Apply migration 037 to an existing Phase 4 deployment. Install WeasyPrint native
runtime dependencies and the independent veraPDF CLI/Java runtime; configure
`MESSAGING_PDF_VALIDATOR`. Capture fails closed if validation is unavailable.
The deployment guide documents timeouts, limits, worker behavior, Monitor
interpretation, and the unchanged PostgreSQL connection-sizing calculation.

The English manifest and Arabic canonical artifact add 95 Phase 5 keys. All
2,778 Phase 4 Arabic entries, including their wording and provenance, are
unchanged. No administrator export was promoted. New Arabic values are generated
drafts requiring normal administrator review/publication. Two previously
reported curated terminology findings remain unchanged. Existing Starlette/
AnyIO deprecation warnings are unrelated to this phase.

Raising configured capture limits, unusually large connected groups, and a
production concurrency target require deployment-specific capacity testing;
acceptance evidence covers configured boundaries and atomic behavior, not a
claim of unlimited throughput.
