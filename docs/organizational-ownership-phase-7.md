# Organizational ownership — Phase 7 release readiness

Phase 7 completes operational hardening for the ordinary organizational
ownership feature. Exceptional transfer of all holdings from a defunct unit is
still deferred to Phase 8.

## Operational verification

The automated production-shaped rehearsal creates a 150-level aggregation
subtree containing 150 records and moves the complete subtree to an aggregation
owned by another organizational unit. It verifies:

- explicit ownership-change confirmation and reason;
- atomic propagation to every descendant aggregation and record;
- zero rows in `organizational_ownership_diagnostics` afterward;
- an immutable `MOVED_WITH_ACL_POLICY` event identifying the ownership change;
- completion within the regression latency budget; and
- use of `aggregations_owner_parent_number_browse_idx` and
  `records_owner_aggregation_number_browse_idx` for owner-scoped browsing.

The full disposable-database pipeline separately verifies canonical-schema and
migration parity, authorization, clearance, lifecycle, concurrency, history,
search, dashboard counts, backup/restore, and repeat-safe imports.

Dashboard operational hardening consolidates the former multi-request fan-out
into `GET /api/v1/dashboard/summary`. One refresh now uses one HTTP request and
one database-pool checkout, returns recent activity already hydrated for
display, and rejects overlapping refresh work within the same browser page.
This prevents multiple open dashboards from multiplying per-card and N+1
activity requests against the API pool.

## Monitoring and operations

`GET /api/v1/security-operations/reconciliation` now reports:

- `ownership_invariant_violation_count`;
- `ownership_invariant_violations_by_type`; and
- a critical `organizational_ownership_invariant_violation` finding whenever
  the diagnostic view is non-empty.

Administrators should treat any non-zero ownership finding as a deployment or
data-integrity incident. Preserve the affected database and audit history,
stop ownership-changing maintenance, identify the unsupported write path, and
repair through a reviewed migration. Do not directly rewrite individual owner
columns as an operational shortcut.

Wathiq does not maintain a separate in-process ownership or org-unit-members
authorization cache. Authorization reads current effective assignments and
resource ownership from PostgreSQL. The database triggers also govern writes
made by background workers, scheduled jobs, seeds, and migrations; those paths
must provide the same explicit move context when ownership changes.

## End-user and governance guidance

- **Create for** appears only during creation. After saving, the resource shows
  **Owning organizational unit**.
- Moving a record or aggregation to a parent owned by another unit changes the
  owner automatically and requires one explicit confirmation and a reason.
- Moving an aggregation changes the owner of its complete descendant subtree.
- Named-role ACL grants are retained; they are not silently translated when an
  ordinary move changes ownership. **All org unit members** immediately refers
  to the destination owner.
- Information-governance staff can inspect the immutable event history and the
  reconciliation report when reviewing a move.

## Governed correction and advanced-action presentation

An authorized information-governance user may use **Correct ownership** on a
root aggregation created for the wrong organizational unit. The action requires
`organization.ownership.correct`, sufficient clearance, a destination
`{org unit} — {role}`, preview, reason, and confirmation. It propagates the new
owner through the subtree, reassigns the original creator-role grants, preserves
unrelated named-role and `Everyone` grants, and records
`OWNERSHIP_CORRECTED`. Child aggregations and records change ownership only by
moving to another parent.

Aggregation details place **Move**, **Correct ownership**, **Child defaults**,
and **Record defaults** in a collapsed **Advanced** section. Record details put
**Move** there as well. This reduces clutter only; existing capability and
authorization checks remain authoritative.

## Deployment and rollback

Deployment rehearsal builds both a new database from `database/schema.sql` and
an upgraded database through every migration, compares security-critical
schema objects, runs all regressions, exercises backup/restore, and drops the
disposable databases afterward.

Application rollback may revert API/UI code only while retaining the upgraded
schema and audit history. Database rollback must use a separately reviewed
forward repair migration. It must never drop ownership history, guess inverse
subtree ownership, or restore broad legacy ACL defaults.

## Security and information-governance review

The implemented controls preserve the three independent authorization gates:
global privilege/profile policy, resource ACL (or governed bypass), and
security clearance. Ownership remains descriptive context rather than a hard
workspace boundary. Creation-role eligibility and parent-owner matching are
server-enforced, and ordinary ownership-changing moves require confirmation,
reason, authorization at both source and destination, transactional database
propagation, and audit history.

Phase 8 must not be exposed in the API or UI until its separate bulk-transfer
planning, ACL reconciliation, interruption recovery, and reporting controls are
implemented and approved.
