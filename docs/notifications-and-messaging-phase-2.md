# Notifications and messaging — Phase 2 report

Specification: `specs/notifications-and-messaging.md`, approved revision 1.20.
Scope: §16.2, Complete human messaging. Verification date: 2 October 2026.

**Status: implementation and functional validation complete.** New Arabic
translations await the normal administrator review; two unrelated existing
terminology findings are recorded below.

## Implementation

Phase 2 adds the human messaging workspace beneath Records Management:
Inbox, Outbox, Drafts, and Compose. It includes bounded mailbox and recipient
pages, filters, current authorization checks, read receipts, structured resource
links, priorities, security levels, reply, Inbox/Outbox forwarding, and Outbox
follow-up. Relationships open earlier content without copying it into the new
subject or body or exposing other recipients' private delivery state.

Drafts are private, explicitly saved, version checked, recoverably discarded,
and restorable. Expired drafts appear in Recently deleted during their configured
restoration window. Sending revalidates current recipients, clearance, resources,
and source eligibility, atomically creates one message, and removes the draft.
Concurrent sends and identical retries return the same committed result.

Action-required messages show original and current effective deadlines,
independent recipient completion, and chronological amendment history. Completion
requires an explicit reply acknowledgment with the original sender in To.
Amendments append history and a localized notice to every original concrete
recipient in the same transaction. They preserve original content, serialize
concurrent changes, enforce future deadlines and fairness for completed actions,
and support withdrawal. Linked originals also support bounded history paging
under the same ancestry authorization as their content.

`database/migrations/034_messaging_human_workflows.sql` upgrades Phase 1 integrity
functions. Equivalent definitions are in the independent canonical schema.
Transactions now use serializable isolation with bounded whole-transaction retry
for send, draft conversion, completion, and amendment races. This supersedes the
Phase 1 report's description of repeatable-read isolation.

## Requirement traceability

Backend tests below are in `backend/services/api/tests/test_messaging_phase2.py`
unless identified as Phase 1. The UI is `frontend/webui/messaging_workspace.py`;
application navigation and shared selectors are in `frontend/webui/app.py`.

| Approved requirement | Implementation | Verification evidence |
| --- | --- | --- |
| Navigation, Inbox/Outbox privileges and ownership (§6, MSG-016) | App/capabilities integration; route and service ownership gates | `test_phase2_routes_deny_exchange_loss_and_foreign_objects`; Phase 1 system-only Inbox, clearance and ownership tests; live navigation |
| Shared bounded user/role/unit/security selectors (MSG-005A) | Existing `relationship_select` and `bind_remote_relationship_select`, with bounded messaging loaders and disabled explanations | Shared selector interaction and clearance-search regressions (including active role labels); existing relationship-search/security-selector suites; live remote recipient search |
| Compose, priorities, levels, safe content/resources (MSG-003–006, MSG-011–014) | Canonical send validation; native editor; structured link controls; visible invalid selections | Phase 1 content, expansion, lookup, clearance, resource batching and byte-limit tests; compose/resource interaction tests |
| Independent read state and receipts (MSG-009–010) | Owned read operation, immutable first-read time, bounded sender recipient detail | Phase 1 send/read/receipt tests; live read and completion checks |
| Reply, both forward sources, follow-up and ancestry access (MSG-007–008) | `relationships.py`; compose source floor; read-only backward traversal | `test_relationship_access_completion_and_branches`, `test_relationship_security_floor_and_draft_clearance_loss`; live blank reply form and linked controls |
| Private drafts and optimistic concurrency (MSG-016) | `drafts.py`, If-Match versions, atomic send and request receipt | `test_draft_privacy_version_and_atomic_send_retry`, `test_draft_empty_send_and_failed_send_preserve_version_and_children`, `test_concurrent_draft_updates_have_one_winner`, `test_concurrent_draft_send_retries_create_one_envelope`; live save/reload/discard/restore/send |
| Due boundaries, completion and recipient independence (MSG-015) | `actions.py`; effective status projection; explicit unchecked completion control | `test_completion_is_independent_and_requires_original_sender_in_to`, `test_status_boundaries_and_fair_extension`, `test_effective_filters_and_due_date_validation`; live completion refresh |
| Immutable amendments, fairness and withdrawal (MSG-023) | Append-only amendment service, original-audience notice fan-out, canonical integrity constraints | `test_amendments_original_audience_withdrawal_and_idempotency`, `test_late_completion_corrected_by_removal_without_changing_original`, `test_concurrent_amendments_are_ordered_and_retries_emit_one_notice`, `test_completion_withdrawal_race_never_commits_completion_after_withdrawal`, `test_amendment_failure_rolls_back_all_history_and_delivery`; live original/current/history verification |
| Frozen localized notices (MSG-021, MSG-023) | Enabled-language variants from published translations with English fallback | `test_amendment_notice_freezes_published_localization_and_original_reason` |
| Loading, empty, restricted, validation, conflict and failure states (§16.2) | Stable list chrome, localized state/error rendering, version conflicts, per-selection validation | API negative/concurrency tests; English/Arabic empty-state tests; live validation and expired-session clearing |
| Freshness, abandonment and no tenant downloads (§16.2, WebUI performance contract) | 25-row pages; no message cache; per-view/form revision and identity guards; app cancels abandoned reads; mutation refresh | `test_abandoned_refresh_cannot_render_into_another_page`, repeated navigation/refresh interaction tests, live save/send/completion/amendment refresh |
| Persistence and schema upgrades | PostgreSQL storage; migration 034; canonical schema | Fresh/upgrade `pg_dump` parity and existing-data preservation; Phase 1 independent-process durability test; live page reload |
| Translation completeness and artifact integrity | 99 messaging keys plus 6 privilege name/description keys, sorted EN/AR artifacts | Catalogue checker; `test_messaging_translation_artifact_valid_and_curated_items_preserved`; live LTR/RTL |

## Automated results

- **72 passed**: messaging kernel, Phase 2 workflows, global privilege enforcement,
  and policy inventory in one combined disposable-database run.
- **1 passed** in an additional focused disposable run after extending linked
  amendment-history authorization. It also verifies denial without an owned root
  and denial of an unrelated branch. A further focused run passed translation
  artifact validation after adding the explicit active lifecycle label.
- **11 passed**: messaging NiceGUI interaction tests and existing shared security
  selector regression tests.
- **24 passed**: existing relationship-search and capability unit tests.
- Canonical fresh schema and populated predecessor upgraded through 033 and 034
  produce identical schema dumps; predecessor data is preserved.
- Catalogue references, active-key coverage, ordering, placeholder/blank/import
  validity, provenance preservation, and catalogue hash passed. `git diff --check`
  passed.

Commands (run frontend unit and interaction suites as separate processes):

```sh
backend/services/api/.venv/bin/python tools/test_messaging.py \
  backend/services/api/tests/test_messaging.py \
  backend/services/api/tests/test_messaging_phase2.py \
  backend/services/api/tests/test_global_privilege_enforcement.py \
  backend/services/api/tests/test_policy_inventory.py
frontend/webui/.venv/bin/python -m pytest -q --asyncio-mode=auto \
  frontend/webui/interaction/tests/test_messaging_workspace.py \
  frontend/webui/interaction/tests/test_security_level_selector.py
frontend/webui/.venv/bin/python -m pytest -q \
  frontend/webui/tests/test_relationship_search.py \
  frontend/webui/tests/test_capabilities.py
frontend/webui/.venv/bin/python frontend/webui/scripts/check_i18n_catalogue.py
```

`tools/test_messaging.py` creates unique disposable fresh and upgrade databases,
initializes them, points every fixture at the fresh database, and drops both in
`finally`. `--preview` starts isolated API/WebUI processes with disposable fixture
accounts; stopping it shuts those processes down before dropping the databases.
No persistent ERMS database is used for tests or browser verification. All
preview processes were stopped and every disposable database was removed
successfully.

## Live browser verification

The in-app browser used the isolated API on 18001 and WebUI on 18081. Verified
English LTR and Arabic RTL, shared recipient lookup, blank relationship compose
fields, explicit completion and locked original-sender To selection, independent
completion refresh, original/current amendment state and history, draft save and
reload, discard/restore, and conversion to an Outbox message. Navigation between
mailboxes fetches current data. An expired session removed protected content and
the open compose dialog rather than leaving private fields visible.

The list/card presentation was compared with the existing organization-unit
workspace. Standard NiceGUI components and the established Wathiq blue/bordered
presentation are reused; no raw table or messaging-specific RTL CSS was added.

Saved browser evidence: [LTR message](verification/messaging-phase-2/ltr-sent-draft.png)
and [RTL message](verification/messaging-phase-2/rtl-sent-draft.png). The RTL view
reported `direction: rtl` with equal viewport and document scroll widths.

## Translation review and remaining boundaries

Every pre-existing Arabic item, including its provenance, is unchanged. The 105
new Arabic entries are generated drafts marked `review_required=true`; an
administrator must review/publish them through the existing translation workflow.
Browser QA published fixture copies only inside the disposable database.

The full approved-terminology checker still reports **two pre-existing findings**:
`classification_transfer.error.checksum_mismatch` (Checksum) and
`classification_transfer.retention_rule` (Retention Rule). These are unrelated
curated translations and were preserved. There are no terminology findings for
new messaging keys. Two existing Starlette test-client deprecation warnings also
remain; they do not fail the test suite.

This phase is not a production-release approval. Phase 3 supplies real-time
signals, reconnect reconciliation and live toasts. Phase 4 supplies system
producer/administration workflows. Phase 5 supplies record capture, sent-message
delete/restore, scheduled lifecycle processing, whole-connected-group purge,
monitoring and production hardening. The agreed no-tombstone, whole-group retention
rule remains intact.

For an existing database at 033, apply migration 034; new databases use
`database/schema.sql` alone, followed by separate seeds. No persistent database
migration or production deployment was performed during this work.
