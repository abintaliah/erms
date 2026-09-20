# Security and authorization implementation — Phase 1

Status: implemented and verified

This phase establishes the security-level catalogue and the mandatory security metadata used by later authorization phases. It intentionally does not enforce user clearance yet; that begins in the later decision-engine phases.

## Data model

`security_levels` contains a stable code, name, unique non-negative level number, disposition-prevention flag, timestamps, and optimistic-concurrency version. The initial catalogue is:

| Code | Name | Level | Prevents disposition |
|---|---|---:|---|
| G | General | 0 | No |
| R | Restricted | 50 | No |
| S | Secret | 75 | No |
| TS | Top Secret | 100 | Yes |

Roles, aggregations, and records have mandatory `security_level_id` foreign keys. Record drafts may hold the selected level while a record is being prepared. Existing rows are migrated to the lowest numbered level.

New root aggregations, records, and roles default to the lowest numbered level. A new child aggregation defaults to its parent aggregation's level. A record deliberately does not inherit its containing aggregation's level.

## Hierarchy invariant

An aggregation's level must be greater than or equal to every direct child aggregation and record. Database triggers enforce the rule for creates, edits, moves, and security-level catalogue number changes. The API returns a conflict response with `security_hierarchy_violation` when a direct operation would break it.

The preview/apply API supports two explicit remedies:

- `raise_ancestors` raises insufficient destination ancestors to the requested level.
- `downgrade_subtree` lowers descendants that exceed the requested aggregation level.

Preview tokens bind the proposed operation to the observed entity versions. Apply rejects a stale preview, requires a change reason, and runs atomically. Ordinary direct downgrades also require `X-Change-Reason`.

## API and UI

The REST API provides versioned CRUD for security levels and preview/apply endpoints for hierarchy changes. Referenced levels cannot be deleted, and the current lowest baseline cannot be deleted.

The Web UI provides Security levels administration, security fields on aggregation, record, and role forms, safe defaults, parent-aware choices, downgrade-reason capture, and security labels on the corresponding detail pages. Child choices are limited to levels allowed by the selected parent.

## Audit events

Catalogue CRUD is recorded by the immutable entity-history trigger. Resource and role changes also emit `SECURITY_LEVEL_UPGRADED` or `SECURITY_LEVEL_DOWNGRADED`, including old/new identifiers and level numbers, the selected remedy, and the supplied reason.

## Verification

All database/API tests run in the project-standard disposable PostgreSQL container. The gate covers catalogue seeding, defaults, hierarchy enforcement, preview/remedy application, downgrade reasons, audit events, deletion protection, existing records-management behavior, and schema parity between the upgraded and clean-build Phase 1 structures. Frontend unit tests cover the updated entity definitions and API client behavior.
