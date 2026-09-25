# Full-text search Phase 5 reconciliation

## Outcome

Phase 5's repository implementation is complete. The approved rollout is now
an explicit, independently reversible sequence: migrate with workers and search
disabled; enable automatic scheduling and workers; perform bounded backfill;
pass load, quality and readiness gates; enable API search; then enable the
header. Rollback never deletes source content or derived index tables.

Approved revision 0.26 additionally replaces generic service-account
administration with a dedicated **Text Indexers** workflow. The person-only
`identity.text_indexers.administer` privilege is seeded only to `ALL_PRIVS` and
`SYS_ADMIN`; creation atomically installs the service identity, protected sole
role assignment and initial one-time key.

Approved revision 0.27 adds a privilege-gated **Health** section to that
workflow. It distinguishes API liveness from indexing readiness, exposes only
privacy-safe operational aggregates, refreshes on demand, and queues bounded,
idempotent backfill passes of 1–500 components.

Approved revision 0.28 fixes each worker process to one claimed job and moves
extraction concurrency to independently supervised worker processes with
unique IDs and separate restart/resource controls.

Approved revision 0.29 clarifies the deployment boundary: one text-indexer
service owns a configurable child-process pool. The default count is two,
each child claims one job, and the supervisor restarts failed child slots.

Approved revision 0.30 exposes built-in roles in ordinary Roles administration
as read-only entries. Generic selectors and mutation APIs remain closed to
them, while the text-indexer role links authorized administrators to the
dedicated Text Indexers workflow.

## Forward reconciliation

| Approved requirement | Evidence | Result |
| --- | --- | --- |
| Deploy disabled and migrate | disabled `.env.example` defaults; migration 013 | satisfied |
| Enable automatic new-content indexing | transaction-local scheduling gate and canonical trigger | satisfied |
| Run bounded backfill | maintenance `reconcile --batch-size` | satisfied |
| Observe load and quality | privacy-safe metrics, readiness, quality gate and runbook stop conditions | satisfied |
| Enable header last | separate API/UI flags and health output | satisfied |
| Non-destructive rollback | documented reverse sequence; pending freshness retained | satisfied |
| FTS-54 deployment baseline | hardened unit, HTTPS/secret/network instructions and Phase 2 security controls | satisfied in repository; production operator applies host firewall and credentials |
| FTS-55 final traceability | final Phase 5 matrix and full acceptance audit | satisfied |
| FTS-56–58 dedicated administration | migration 016, atomic API, generic-path guards, dedicated Wathiq list/detail UI and browser/API verification | satisfied |
| FTS-59 operational health and bounded backfill | dedicated health/backfill APIs, Health cards and dialog, authorization/privacy/idempotency tests, operations guide and live browser verification | satisfied |
| FTS-60 process-isolated concurrency | claim size one, process count two, supervisor-owned child pool, generated IDs, regression tests and local/production scenarios | satisfied |
| FTS-61 read-only built-in role visibility | opt-in list API, mutation guards, Built-in list/detail presentation and dedicated Text Indexers link | satisfied |

## Reverse reconciliation

Every Phase 5 change maps to an approved rollout, security, monitoring,
freshness, or traceability requirement. The feature flags introduce no new
role, privilege, resource type, search behavior, or data lifecycle. The
systemd artifact operationalizes the already approved isolated worker model.

## Verification

- The approved machine benchmark passes the release gate: English 99.69%
  (minimum 90%), Arabic 97.74% (minimum 75%), and marker recall 100%
  (minimum 90%).
- Python compilation and focused rollout/UI tests pass.
- Canonical-schema and migration behavior is verified on a unique disposable
  PostgreSQL 18 database, including scheduling-off pending state, no job,
  scheduling-on job creation, and cleanup.
- Full API and frontend regressions pass against a disposable PostgreSQL 18
  database: 273 API and 157 frontend tests; the database is dropped afterward.
- The dedicated navigation, list, details and atomic-create dialog were
  compared live in the Wathiq shell. A temporary verification administrator
  was removed afterward while its audit history was deliberately preserved.
- The Health cards and bounded backfill dialog were compared live with the
  established Wathiq administration layout. The UI displayed active/stale
  workers, queue age/state, failures, drift, stale documents, lease recovery,
  readiness and the 1–500 batch control without exposing document content or
  credentials.

## Deployment boundary

Repository work cannot switch a production environment's flags, install its
service account/key, or apply its host firewall. Those are execution steps for
the target Linux environment, not missing implementation. The runbook supplies
the exact order, gates, stop conditions and rollback sequence.
