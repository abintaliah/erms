# Full-text search Phase 2 reconciliation

Date: 2026-09-24. Specification revision: 0.23.

Phase 2 repository implementation is **complete and reconciled**. The durable PostgreSQL 18 queue/state/history/staging
model, upload/replacement scheduling, seven authenticated REST operations,
lease reclaim and fencing, atomic publication, REST-only worker, official Tika
distribution validation, bilingual language/OCR policy, bounded maintenance,
backfill/reconciliation, launcher, local-stack lifecycle, rate limiting,
metrics command, and operator documentation are implemented.

Verification completed:

- fresh `database/schema.sql` loaded cleanly on a unique disposable PostgreSQL
  18 database;
- migration 011 loaded on a second disposable database and normalized Phase 2
  table/index/constraint/trigger definitions matched the canonical schema;
- the complete API suite passed: 253 tests, including exact
  content retrieval, staging/publish, terminal retry idempotency, expired lease
  reclaim, and obsolete-generation rejection;
- all seven canonical SQL suites passed on PostgreSQL 18;
- focused Phase 2 API tests passed for publication/replacement, reconciliation,
  cleanup boundaries, advisory-lock leadership, metrics safety, lease loss and fencing;
- five worker tests passed for normalization, language, chunking, page-limit,
  owned abandoned-temp cleanup and its startup scan bound;
- launcher self-test verified Java, the complete distribution layout, and
  `tika-pipes-fork-parser` presence;
- the production-path corpus passed 99.69% English recall and 97.74% Arabic
  recall against the approved 90%/75% gates.

The real local-stack supervisor was also exercised against a disposable
PostgreSQL 18 database: it provisioned a mode-`0600` loopback-only credential,
started the API and indexer, registered the worker through a real claim before
reporting readiness, detected a deliberately killed
indexer, exited non-zero, and shut down the managed API.

Production Linux validation of systemd/workload egress, CPU, memory,
process-count, and temporary-storage controls remains a deployment gate. It is
documented and cannot be truthfully executed on this macOS development host;
it does not represent missing Phase 2 repository implementation.
