# Security and authorization implementation — Phase 12

Status: implemented and verified

Phase 12 implements authorization-dependent permanent deletion for users,
roles, and organizational units. `DELETE` now has permanent semantics and is
separate from activate, deactivate, suspend, and unsuspend.

## Transactional preflight and execution

Each entity exposes a deletion-preflight endpoint returning a stable report with
all detected blockers, dependencies, cascade counts, and the version evaluated.
The permanent operation requires both `If-Match` and `X-Change-Reason`.

Execution does not trust an earlier preflight. It acquires the ERMS
transaction-scoped authorization-continuity advisory lock, locks only the target
row, repeats the complete analysis, verifies the entity version, and only then
deletes. Any failure rolls back the transaction and releases the advisory lock.

The same advisory lock is acquired by every application mutation that can
reduce administrator or custody continuity: relevant user, role, organization-
unit and security-level changes; assignment update/removal; profile privilege
replacement; and role-profile reassignment. It coordinates those policy
mutations without locking their tables. Unrelated row writes and ordinary reads
continue normally. Aggregation and record creation takes the shared form of the
same advisory lock: creations remain concurrent with one another but cannot race
the removal of the last custodian. Role/ACL insertion races remain protected by
the target role row lock and restrictive ACL foreign keys.

## Continuity and dependencies

User and role simulation excludes the proposed target while calculating:

- effective person accounts with `authorization.administer`;
- effective person accounts serving as highest-clearance universal information-
  governance custodians with the complete custody privilege set; and
- the number of protected aggregations and records.

The operation cannot remove the last effective authorization administrator or,
while protected content exists, the last qualifying human custodian. Service
accounts do not satisfy either person-continuity calculation.

Role preflight separately reports its profile, user assignments, subordinate
roles, local aggregation and record ACL grants, and both default-child ACL grant
types. Any ACL reference is a blocker: grants must be deliberately transferred
or removed and are never silently cascaded. A supervising role must first be
replaced or explicitly detached. `system-administrator` and the `SYSTEM`
organizational unit remain reserved.

## Cascades and immutable evidence

An eligible user deletion removes its role assignments, record drafts and draft
components, credentials, login sessions, favourites, and classification
preferences through the schema's narrowly defined cascades. References from
other sessions' `revoked_by` field become null. An eligible role deletion removes
its assignments. Organizational units never recursively remove descendants or
roles.

Before user sessions disappear, an immutable event records the deletion reason,
cascade counts, revocation scope and reason, and security-safe final session
snapshots: session identifier, IP address, bounded user agent, creation and last-
activity times, expiry times, and revocation time. Secret and CSRF material is
never copied. The ordinary `DELETE` audit trigger retains the complete final
before-state for the entity, and historical actor snapshots remain unchanged.

## Administrative UI

User, role, and organizational-unit detail pages now expose a distinct Delete
action. The confirmation dialog runs preflight first. Blocked operations show
every actionable reason and relevant count, with no force-delete control.
Eligible operations identify automatic cascades, state that the live row cannot
be restored, require an explicit reason, and submit the preflight version. A
server-side race conflict is still handled as authoritative.

## Verification

- Complete fresh disposable PostgreSQL database/API suite: **186 passed**.
- Authorization backup and isolated restore exercise: passed.
- Canonical-schema/migration parity and core SQL tests: passed.
- Web UI regression suite: **69 passed**.
- Dedicated deletion tests cover allowed deletion, self/reserved/dependency
  blockers, supervisor reassignment, stale-version rollback, immutable evidence,
  successful role/unit cleanup, and advisory-lock contention.
- The scale fixture seeds **5,000 users**, **10 roles**, **100 aggregations**, and
  **200 records**. Five user plus five role deletion preflights complete inside
  the combined **5-second** latency budget.
- While continuity coordination is held, an unrelated write completes inside
  **750 ms**, a competing continuity mutation waits, and PostgreSQL reports no
  heavyweight relation lock held by the coordination transaction.
- Python compilation, policy-inventory drift detection, and whitespace checks:
  passed.

The disposable database ran in tmpfs and was removed cleanly by the test harness.
