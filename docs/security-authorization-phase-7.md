# Security and authorization implementation — Phase 7

Status: implemented and verified

This phase enforces operation-specific authorization for aggregation and record mutations. A successful mutation now requires every applicable gate from the approved specification: an effective role, the exact global privilege, sufficient maximum effective clearance, and the exact permission from the resource's live effective ACL. A qualified information-governance role may bypass only the ACL gate.

## Database policy predicates

Migration 036 installs reusable PostgreSQL predicates for aggregation and record operations. They compose the Phase 6 non-disclosing view decision with the operation's global privilege and ACL permission. The canonical schema, incremental migration runner, disposable test harness, and reset fixture all include the migration.

The API locks each visible resource row before authorizing and mutating it. Policy is therefore evaluated inside the mutation transaction against current role assignments, profiles, clearances, resource levels, and live ACL inheritance. Optimistic versions remain mandatory and prevent a stale request from overwriting a concurrent change.

## Enforced aggregation operations

The API now distinguishes and independently enforces:

- root creation;
- child creation against the parent `aggregation.add_child` permission;
- metadata modification;
- deletion;
- close and reopen;
- move, with `aggregation.move` on the source and `aggregation.receive_child` on the destination;
- reclassification;
- security-level change, including caller clearance and the additional downgrade privilege;
- resource ACL administration; and
- default child-aggregation and child-record ACL administration.

A specialized action submitted through the general PATCH route does not accidentally require metadata-edit permission. A request containing multiple kinds of changes must pass every applicable operation gate.

Child aggregation creation derives its default security level from its parent. Root aggregations use the lowest configured level unless explicitly set. The caller must be cleared for the level that will actually be stored.

## Enforced record operations

The API independently enforces:

- creation against `aggregation.add_record` on the destination;
- metadata modification;
- deletion;
- move, with `record.move` on the record and `aggregation.receive_record` on the destination;
- security-level change, including caller clearance and downgrade privilege; and
- record ACL administration.

New records retain the approved baseline-level default rather than inheriting the containing aggregation's level. PostgreSQL continues to enforce the parent/child security invariant at commit time.

## ACL-aware moves and security workflows

Both the ordinary PATCH move and the ACL-aware preview/apply workflows enforce the source and destination sides. ACL-aware moves preserve the Phase 5 live-inheritance semantics and revalidate continuity inside the transaction.

Security-level preview/apply workflows require the matching resource security-change privilege and permission. When a remedy changes ancestors or descendants, the caller must be authorized for every affected aggregation and record. A combined move and security change additionally requires both move sides. No mutation is committed when any gate, hierarchy invariant, version, or continuity check fails.

## Capabilities and Web UI

Aggregation capability responses now include metadata edit, delete, close, reopen, move, reclassify, security-level change, ACL management, add-child, and add-record decisions. Record responses include metadata edit, delete, move, security-level change, ACL management, and component-list decisions.

The aggregation and record detail pages fetch these decisions and omit unavailable mutation controls. Add-child and add-record controls are evaluated independently. Reopen, metadata edit, delete, and ACL controls reflect the exact operation decision. The API remains authoritative, and a race or stale page is handled as a safe denial with a specific, user-readable privilege, ACL, clearance, or stale-version message.

The generated operation-policy inventory is updated to Phase 7 and marks the mutation and capability surfaces that are enforced.

## Verification

The complete database/API suite ran against a newly created disposable PostgreSQL database, which the harness disposed of cleanly afterward. It passed 165 tests.

The Phase 7 operation matrix specifically verifies:

- global privilege and resource permission are both required;
- an ACL permission cannot substitute for a missing global privilege, nor vice versa;
- aggregation and record moves require both source and destination authorization;
- a denied destination check rolls back the entire move;
- close is independent of metadata-modification permission;
- clearance failure conceals a resource with the same `404` response as absence;
- capability responses match the operation predicates; and
- stale mutations fail atomically without overwriting the committed version.

The Web UI regression suite passed 65 tests. Python compilation and diff validation also passed.

## Deliberately deferred

Phase 8 covers record-draft and digital-component mutation enforcement, upload/replace/remove/reorder semantics, content-operation capabilities, and the exceptional information-governance correction workflow for placing or moving records into closed aggregations. Phase 7 does not prematurely broaden those operations.
