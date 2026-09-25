# Full-text search Phase 3 reconciliation

Date: 2026-09-25. Specification revision: 0.23.

Phase 3 adds the approved controlled `full_text` grammar leaf to record,
aggregation, and digital-component search; deterministic relevance sorting;
bounded authorized attribution and snippets; the cursor-based global search
contract; allowlist-only privileged diagnostics; forced component and
record-batch reindex operations; safe attempt/batch/component status; and
authorized reindex controls in the existing record details and component cards.

The implementation keeps authorization inside each PostgreSQL query before
matching, ranking, pagination, attribution, or freshness reporting. It never
accepts raw `tsquery`, SQL, configuration names, tables, columns, weights, or
dictionaries. Snippet markers are fixed non-HTML delimiters and component
attribution is capped.

Migration 012 and the canonical schema add the previously missing
`record.component.reindex` privilege with the exact four protected profile
grants, plus durable record-reindex batch snapshots. Component reindex reuses
an equivalent active job; a terminal job does not suppress a later forced
attempt. Record reindex locks and snapshots the current component set, refreshes
metadata in the same transaction, and reports queued, already-running, and
unavailable dispositions independently.

Verification evidence is maintained in
`docs/full-text-search-implementation-traceability.md`. Phase 4 remains
responsible for the responsive global header/results page and the browser-only
diagnostics panel; Phase 3 adds only the specified existing-detail-page reindex
actions and state feedback.

Completed verification:

- canonical schema loaded cleanly into a uniquely named disposable PostgreSQL
  18 database;
- migration 012 recreated the Phase 3 tables, constraints, indexes, privilege,
  and four protected-profile grants in a second disposable database;
- normalized canonical and migration-created Phase 3 object dumps were equal;
- the complete API suite passed 258 tests, followed by six focused Phase 3
  tests including the SYS_ADMIN-without-resource-access non-bypass case;
- 103 frontend authorization/entity/Phase 3 UI tests passed;
- the generated operation-policy registry and canonical authorization catalogue
  tests passed; and
- Python compilation, JSON validation, shell-independent static checks, and
  `git diff --check` passed.
