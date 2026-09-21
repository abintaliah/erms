# Resource medium, vital status, review, and location — Phase 0 readiness

Phase 0 is complete. The approved domain policy and stable terminology are in
[`specs/resource-medium-vital-status-review-and-location.md`](../specs/resource-medium-vital-status-review-and-location.md).

## Inventory

| Area | Current implementation surface | Planned phase |
| --- | --- | --- |
| Canonical schema | `database/schema.sql`; aggregation, record, component, event, ACL and ownership triggers | Phase 1 columns/read functions; later integrity phases |
| Existing database upgrade | numbered SQL migrations through 050 | migration 051 in Phase 1 |
| API schemas | `backend/services/api/schemas.py` | Phase 1 read fields; Phase 2 write contracts |
| CRUD and authorized search | `crud.py`, `search.py`, authorized search views | Phase 1 read/search exposure |
| Browse tree | `browse.py` aggregation and record sources | Phase 1 badges/read fields |
| Creation and editing | `main.py`, NiceGUI entity forms and record-draft flows | Phase 2 and later phases |
| Digital components | content and draft component endpoints plus database triggers | Phase 3 |
| Deletion and capabilities | API delete routes, authorization capabilities, database dependencies | Phase 4 |
| Dashboard | consolidated summary endpoint and NiceGUI dashboard | Phase 5 |
| Event history | row triggers and governed domain events | Phase-specific extensions |
| Seeds and fixtures | `database/seeds`, SQL database tests, API fixtures | Phase 1 compatibility updates |

## Migration policy

- Backfill every existing aggregation and record with `medium='mixed'`.
- Backfill `is_vital=false`.
- Leave next-review dates and aggregation locations null.
- Records receive no stored location columns.
- Apply validation and non-null constraints only after deterministic backfill.
- Seed-created holdings explicitly use `mixed` and `false` unless a later test
  intentionally creates a different compatible scenario.

## Stable Phase 1 error codes

- `next_review_date_must_be_future`
- `record_location_is_derived`

Later-phase integrity and governed-action codes remain defined by the main
specification and are implemented with their corresponding phases.

## Configuration

- `DEFAULT_ROOT_AGGREGATION_MEDIUM=mixed`
- `REVIEW_WARNING_WINDOW_DAYS=30`
- `DASHBOARD_REVIEW_PREVIEW_LIMIT=5`

The repository root and deployed API environment examples document these
values. Runtime consumers are introduced in the phases that implement the
corresponding creation and dashboard behavior.
