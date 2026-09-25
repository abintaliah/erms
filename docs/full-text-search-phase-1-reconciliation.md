# Full-text search Phase 1 reconciliation

**Specification:** `specs/full-text-search.md`, approved revision 0.23  
**Database under test:** PostgreSQL 18.6 (Homebrew)  
**Result:** Phase 1 verified; no deferrals or departures

## Delivery summary

Phase 1 installs the metadata-search and internal-service authentication
foundation only. It does not implement binary extraction, worker leases, the
global search endpoint, reindex operations, or search UI assigned to later
phases.

The canonical schema and upgrade migration now provide weighted record and
aggregation metadata vectors, explicit stored configurations, GIN indexes,
transactional synchronization, cascade cleanup, authorization-filtered
relations, protected indexer privileges/profile/role, and independently
revocable opaque service-key persistence. The API strictly separates person
sessions from text-indexer credentials and accepts the latter only under the
reserved internal route namespace.

## Forward reconciliation: requirement to evidence

| Requirement | Implementation | Verification | Result |
| --- | --- | --- | --- |
| P1-01 | `database/schema.sql`; migration 010 prerequisite block | Fresh and upgrade execution on PostgreSQL 18.6; Arabic catalogue/match assertion | verified |
| P1-02 | `record_search_documents`; record refresh trigger | Insert/update, A/B vector and rank assertions | verified |
| P1-03 | `aggregation_search_documents`; aggregation refresh trigger | Separate-row/vector and no-ancestor model inspection | verified |
| P1-04 | Stored `regconfig`, explicit `pg_catalog.simple`, two GIN indexes | Catalogue assertions and GIN `EXPLAIN` bitmap-index plans | verified |
| P1-05 | AFTER triggers and cascading foreign keys | Insert/update/delete SQL assertions | verified |
| P1-06 | `service_account_credentials` | Shape, lifecycle, service-target and password-negative assertions | verified |
| P1-07 | Protected `TEXT_INDEXER_SERVICE` profile and privilege trigger | Exact-membership and `ALL_PRIVS` catalogue assertions | verified |
| P1-08 | Protected service-only non-organizational system role | Person-assignment rejection; ordinary role list/search exclusion | verified |
| P1-09 | `service_authentication.py`; API middleware boundary | Seven unit/integration tests including malformed, wrong-route and person-session negatives | verified |
| P1-10 | `search.query.debug` grants | Exact four-profile catalogue assertion | verified |
| P1-11 | `authorized_*_search_documents` views | Unauthenticated base-row non-disclosure assertion; view-definition review | verified |
| P1-12 | Database, deployment, authentication and authorization operations docs | Link/content review | verified |
| P1-13 | Canonical schema plus migration 010 | Fresh/upgrade schema dumps identical except random `pg_dump` guard; disposable DB cleanup below | verified |
| P1-14 | Traceability matrix and this bidirectional report | Forward and reverse tables reviewed | verified |

## Reverse reconciliation: implementation to requirement

| Material behavior | Requirement owner | Scope disposition |
| --- | --- | --- |
| Metadata document tables, functions, triggers, views and GIN indexes | P1-01–P1-05, P1-11 | required |
| Privilege account-type metadata and two new privileges | P1-07, P1-10 | required |
| Protected profile and service-only system role | P1-07–P1-08 | required |
| API-key table, validation and service-password rejection | P1-06 | required |
| Strict key generator/parser/verifier and middleware route isolation | P1-09 | required |
| Role list/search suppression for the protected system role | P1-08 | required by “not selectable for person accounts” |
| PostgreSQL test runner default changed from 17 to 18 | P1-01, P1-13 and approved PostgreSQL-18 baseline | required |
| Documentation and traceability changes | P1-12, P1-14 | required |

No material Phase 1 implementation behavior is orphaned. No later-phase worker,
lease, extraction, global-search, reindex, administration-UI, or search-UI
behavior was introduced.

## Verification record

- Fresh database: `phase1_fresh_20260924_2215`.
- Upgrade database: `phase1_upgrade_20260924_2209` (pre-Phase-1 canonical
  schema followed by migration 010).
- Regression databases: `phase1_regression_20260924_2221` and
  `phase1_regression_20260924_2223`.
- `database/tests/full_text_search_phase1.sql` passed on fresh and upgraded
  schema paths.
- Service authentication: 7 passed.
- Full API regression suite: 247 passed in the clean full run; its two exposed
  PostgreSQL-18 `RESTRICT` SQLSTATE regressions then passed after the handler
  correction (249 covered tests total).
- Fresh and upgraded schema-only dumps differed only in `pg_dump`'s randomized
  `\\restrict`/`\\unrestrict` token.
- Both GIN indexes produced bitmap index scans in explicit-configuration
  representative `EXPLAIN` checks.

Every named database was created inside the isolated temporary PostgreSQL 18.6
cluster at `/tmp/erms-pg18-phase1.YFOZf4`. All were dropped and the cluster was
stopped and removed after verification. No persistent ERMS database was used.
