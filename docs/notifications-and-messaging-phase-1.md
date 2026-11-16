# Notifications and messaging — Phase 1 report

Specification: `specs/notifications-and-messaging.md`, approved revision 1.20.
Scope: §16.1, Durable messaging kernel. Verification date: 2 October 2026.

**Status: complete.** All Phase 1 validation gates passed. The previously reported
permission-catalogue policy/test mismatch has also been corrected and verified.

## Implementation

The backend can commit a human message and its entire recipient fan-out in one
PostgreSQL transaction, retrieve it from another process, and reconcile a
recipient's mailbox using a durable cursor. It does not depend on a WebSocket,
NiceGUI page, notification listener, or in-memory message store.

The canonical schema contains all 19 specified tables, using UUIDs only for the
specified external domain identities. Internal children and association rows
retain numeric, text, or composite keys. Migration 033 creates the equivalent
storage model in an existing database and records its migration version.

The send service uses a repeatable-read snapshot and transaction-level request
locks. It locks recipient mailboxes in ascending user-ID order, allocates
sequences transactionally, and retries a whole transaction after serialization
conflicts. A failed recipient insertion rolls back the envelope, all recipients,
mailbox increments, and request receipt. A concurrent retry returns the original
committed envelope and delivery identities. Reusing a key with different
canonical content conflicts. A retained receipt for an already-purged result
returns `message_result_purged` without creating a replacement.

Sent content and recipient snapshots cannot be updated, deleted, or extended
through ordinary writes after commit. Read timestamps can be set once. Deferred
constraints reject incomplete fan-out and invalid completion/amendment links.
Draft storage has owner and version guards. Capture provenance preserves its
snapshot IDs separately from nullable live references. Later workflow services
are not exposed merely because their tables exist.

Recipient validation uses the existing effective-role and global-privilege
predicates. Expansion excludes the sender, inactive/suspended users, expired
assignments, and users without sufficient clearance or exchange privilege. Units
include directly owned effective roles, not descendant units. Overlap produces
one delivery per user, with To taking precedence. Selector and recipient display
names are immutable snapshots.

Rich text is serialized through an explicit allowlist before storage. Script,
event handlers, embedded active content, unsafe URL schemes, raw internal
resource paths, and unregistered resource tokens cannot bypass validation.
Subjects are normalized to NFC and trimmed before the 255-character check.
The raw rich-text input is bounded at 131,072 UTF-8 bytes; sanitized content is
bounded at 65,536 bytes. Structured resource links retain opaque occurrence
tokens, not client-supplied resource labels. Resource names and availability are
resolved under current permissions and security levels.

Inbox, Outbox, details, read operations, and catch-up enforce ownership from the
authenticated principal. Loss of exchange privilege hides human messages;
insufficient message clearance produces a restricted placeholder without
protected metadata. Resource checks operate in batches for the bounded page.
A resource becoming inaccessible does not hide the rest of a readable message.
System-only Inbox access and selection of an existing Arabic variant are
verified without exposing a public system-send operation.

## API contract

All paths below start with `/api/v1/messages`. List endpoints default to 25
items and accept at most 50. They return `items`, `has_more`, and `next_cursor`.
There is no client-supplied mailbox owner ID.

| Operation | Endpoint | Contract |
| --- | --- | --- |
| Compose capabilities | `GET /capabilities` | Effective limits and selectable security levels; exchange privilege required |
| Recipient search | `GET /recipients/{kind}` | `user`, `role`, or `org_unit`; bounded `q`, `after`, `target_id`, and selected `security_level_id`; stable eligibility reasons |
| Recipient preview | `POST /recipients/validate` | Expanded count with `is_preview=true`; final send revalidates |
| Resource search/validation | `GET /resources/{kind}` | Authorized aggregation, record, or digital-component results; visible higher-level targets are disabled |
| Human send | `POST /send` | Required UUID `request_id`; subject/body, selectors, level, priority, action/due fields, receipt preference, and structured resource links; no sender impersonation fields |
| Inbox | `GET /inbox` | Descending send time and delivery UUID; opaque keyset cursor; read and priority filters |
| Delivery | `GET /inbox/{delivery_id}` | Owned copy, immutable headers, sanitized body, and currently authorized link state; does not mark read |
| Mark read | `POST /inbox/{delivery_id}/read` | Owned readable copy only; preserves first-read timestamp |
| Unread count | `GET /unread-count` | Durable count; includes restricted placeholders but excludes hidden human messages |
| Catch-up | `GET /catch-up` | Ascending mailbox sequence after numeric `after`; never skips an eligible row omitted by the limit; advances over gaps only to the snapshot's safe high-water mark |
| Outbox | `GET /outbox` | Sender-owned envelopes; keyset paging; subject, priority, level, action, sent-date, outstanding/late, and recipient-selector filters |
| Sent detail | `GET /outbox/{envelope_id}` | Sender-owned readable envelope |
| Recipient status | `GET /outbox/{envelope_id}/recipients` | Bounded concrete-recipient page; read timestamps only when requested |

A structured link is submitted as an anchor with
`href="wathiq-resource:<link_token>"`, accompanied by a matching `resource_links`
entry containing the UUID token, controlled kind, and target ID. Storage replaces
the anchor label with an opaque span. The response's `resource_links` array
supplies currently authorized presentation data. Frontends must render
unavailable links as non-clickable placeholders.

The send response contains the envelope UUID, all committed delivery IDs and
sequences within the configured fan-out bound, and `expanded_recipient_count`.
A preview count is never described as a committed result. Database exceptions
cannot return success before the transaction commits.

## Requirement traceability

Test names below refer to `backend/services/api/tests/test_messaging.py`.

| Phase 1 requirement | Implementation | Verification |
| --- | --- | --- |
| Complete schema, upgrade, hybrid IDs (§7, AC-MSG-069) | `database/schema.sql`, migration 033 | Fresh/upgrade schema dump parity; preserved pre-upgrade user; `test_storage_model_and_deferred_integrity` |
| Human attribution and no system impersonation (MSG-002, AC-MSG-001A) | `models.py`, `routes.py`, `service.py` | `test_sanitization_validation_and_sender_boundary` |
| To/Cc, overlap, fan-out (MSG-004–006) | `expand`, `selector_users`, `send` | `test_expansion_snapshot_and_privilege_revocation`, `test_send_read_receipts_and_pagination` |
| Direct units and effective membership (AC-MSG-003A–D) | Existing role/unit predicates reused in `service.py` | `test_expansion_excludes_descendants_inactive_and_expired_assignments`; suspended-user check in `test_lookup_preview_outbox_filters_and_read_timestamp` |
| Immutable content and historical names (MSG-013) | Database guards and snapshots | `test_database_immutability_and_restart_durability`, `test_expansion_snapshot_and_privilege_revocation` |
| Recipient-specific read state and requested receipts (MSG-009–010) | `reading.delivery`, `reading.receipts` | `test_send_read_receipts_and_pagination`, `test_lookup_preview_outbox_filters_and_read_timestamp` |
| Resource authorization and level checks (MSG-011) | Controlled resource queries and batched presentation | `test_resource_authorization_security_and_batching` |
| Sanitization and size limits (MSG-012, AC-MSG-009A–B) | `content.py`, strict request models | `test_sanitization_validation_and_sender_boundary`, `test_body_byte_limits_token_integrity_and_encoded_internal_urls` |
| Clearance and non-disclosing placeholders (MSG-014) | Send validation and read-time projection | `test_clearance_recheck_is_non_disclosing` |
| Exchange privilege and system-only Inbox (MSG-022) | Existing privilege predicates, policy dependencies and owner-scoped reads | `test_expansion_snapshot_and_privilege_revocation`, `test_system_only_inbox_and_language_variant` |
| Idempotency and all-or-nothing fan-out (§8) | Request locks, receipts, transactional mailbox allocation | `test_idempotency_concurrent_fanout_and_rollback`, `test_minimal_receipt_prevents_recreation_after_purge` |
| Stable cursor and committed-only visibility (§9.7) | `reading.inbox`, mailbox row locks | `test_commit_visibility_and_cursor_high_water`, concurrent send and pagination tests |
| Restart-independent retrieval (§16.1 exit) | PostgreSQL-backed service with no content cache | Fresh Python process reads committed content in `test_database_immutability_and_restart_durability` |
| Bounded lookup, mailbox pages, filters (§10) | `routes.py`, keyset queries, batched resource checks | Lookup/filter test, pagination test, resource batching test; `test_policy_inventory.py` |
| Configured limits and due-date snapshot foundation | `config.py`, send-time timezone resolution | `test_limits_and_due_boundary`, `test_privilege_seed_and_configuration_validation` |
| Future workflow storage foundation | Draft version, completion/amendment, and capture constraints | Table/type and negative integrity checks; full workflow gates remain assigned to later phases |

## Verification results

The final Phase 1 run passed **26 tests**: 16 messaging integration tests and
10 policy/schema inventory checks. Fresh initialization, migration upgrade,
schema dump parity, and preservation of pre-upgrade data all passed. Both
disposable databases were dropped successfully. Python compilation and
`git diff --check` also passed. A subsequent focused rerun passed the due-date
boundary test, including rejection of `9999-12-31` with the stable
`message_due_date_out_of_range` code; both databases from that run were also
dropped successfully.

Reproduce the Phase 1 gate with:

```sh
backend/services/api/.venv/bin/python tools/test_messaging.py \
  backend/services/api/tests/test_messaging.py \
  backend/services/api/tests/test_policy_inventory.py
```

The runner obtains connection settings from the environment or `.env` solely
to create disposable databases through the PostgreSQL administrative database.
It never points pytest at the configured persistent ERMS database.

The original broader regression run completed with **234 passed and one
failed**. The failure was a stale unconditional-policy assertion for
`GET /api/v1/permissions`. The approved security specification permits a
resource-specific catalogue through the matching ACL-management global
privilege, while the full catalogue requires `authorization.administer`.

That mismatch is now resolved. The generated registry records the conditional
privileges explicitly, and runtime tests cover all three request scopes against
no privilege, each ACL-management privilege, both ACL-management privileges,
and authorization administration. They also verify response scope, invalid
resource types, and unauthenticated access. The endpoint already enforced the
approved rule and required no behavior change.

The correction's disposable-database regression run passed **45 tests** across
`test_policy_inventory.py`, `test_global_privilege_enforcement.py`, and
`test_individual_acl_authorization.py`. The previously failing dependency test
now applies to unconditional global policies and passes. Fresh/upgrade schema
parity and preservation checks passed again. Two existing Starlette test-client
deprecation warnings remain; there are no failures in this correction's suite.

The test runner creates unique fresh and upgrade databases, initializes and
compares their schemas, tests only the fresh disposable database, and drops both
in a `finally` block. No persistent ERMS database is used for a test run. The
focused tests also create a new API-independent Python process to verify
retrieval without process-local messaging state.

## Installation and remaining phase boundaries

For a new empty database, initialize from `database/schema.sql` alone. For an
existing database at migration 032, apply
`database/migrations/033_add_messaging_kernel.sql`. Then run
`database/seeds/messaging.sql` separately. It uses event source `seeding` and
grants exchange only to ALL_PRIVS by default; Monitor and Notification
Administration go to ALL_PRIVS and SYS_ADMIN. Other exchange grants require
explicit profile administration. Restart the API after deployment.

Configuration defaults are documented in `.env.example`. No WebUI text or
translation artifacts were changed in Phase 1. Reason codes are stable API
values; frontend localization and LTR/RTL verification belong to Phase 2.

Phase 2 still supplies the human UI, shared selectors, draft operations,
relationships, completion workflows, amendments, and full action-status
presentation. Phase 3 supplies NOTIFY and the real-time gateways. Phase 4
supplies registered producer/configuration services. Phase 5 supplies capture,
retention-group purge, restoration, monitoring, and production hardening.

The storage foundation retains whole connected groups and creates no delivery
tombstones. Ordinary deletion is deliberately blocked at this stage; the
later group-purge service must perform the authorized whole-group deletion and
receipt-marker transition together. Phase 1 is not a production-release gate
for the complete subsystem.
