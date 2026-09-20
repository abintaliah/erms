# Security and authorization implementation — Phase 11

Status: implemented and verified

Phase 11 makes the authorization subsystem observable, measurable, recoverable, and operationally documented without weakening confidentiality or immediate revocation.

## Monitoring and reconciliation

The new Security Operations UI and API provide sanitized aggregates for security events and denial groups. Only decision code, required privilege, count, and timestamps are exposed for denials; protected snapshots and request content are excluded.

Continuity reconciliation reports effective authorization administrators, effective highest-clearance governance custodians, and security-hierarchy violations. Zero counts are critical; single-person counts are advisory. A read-only CLI provides JSON output and a monitoring-compatible critical exit status.

## Index and performance review

Migration 038 adds a partial `(operation, occurred_at DESC)` event-history index limited to monitored security operations. Integration tests verify its presence and execute 25 authenticated summary requests within a five-second budget.

No authorization cache was introduced. Measurements do not justify the invalidation complexity, and uncached evaluation preserves immediate revocation after session, assignment, role, profile, organization-unit, clearance, or ACL change.

## Audit resilience

Tests verify denial envelopes exclude tokens and protected content. Actor name and email snapshots remain unchanged after the user is renamed. The operation-policy registry is advanced to Phase 11 and covers the new globally privileged endpoints and UI actions.

## Backup and recovery

The disposable suite now creates a complete PostgreSQL 17 dump, restores it into a separate database, and checks authorization predicates, catalogues, permissions, and immutable actor snapshots. The restored database is dropped and the original tmpfs-backed test database is disposed after the run.

The operational runbook documents monitoring, alert thresholds, reconciliation, access explanation, version-matched backup, isolated restore validation, last-administrator recovery, zero-custodian recovery, corruption response, and the decision not to cache.

## Break glass

A separate draft records constraints and outstanding decisions. It is explicitly unapproved and unimplemented. Phase 11 introduces no hidden bypass.

## Verification

- Complete disposable database/API suite: **180 passed**.
- Full independent-database dump/restore exercise: passed.
- Web UI regression suite: **69 passed**.
- Security summary latency budget and monitoring-index check: passed.
- Immediate revocation tests: passed.
- Audit snapshot rename resilience and denial least-disclosure tests: passed.
- Python compilation, policy-inventory drift detection, schema parity, and whitespace validation: passed.

## Next phase

Phase 12 implements the previously approved authorization-dependent permanent deletion semantics for users, roles, and organization units, including continuity simulation, blocker explanations, immutable deletion evidence, concurrency, rollback, and cascade verification.
