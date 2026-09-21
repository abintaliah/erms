# Organizational Ownership — Phase 0 Readiness Record

**Status:** Complete
**Completed:** 20 September 2026
**Governing specification:** `specs/organizational-ownership-and-default-acls.md` revision 0.6

## 1. Phase outcome

Phase 0 establishes the approved implementation contract and identifies the
code, data, operational, and verification surfaces affected by organizational
ownership and default ACLs. It intentionally makes no database or runtime
behaviour changes.

The approved contract includes:

- `owning_org_unit_id` on aggregations and records;
- strict containment-based ownership;
- the combined **Create for** `{org unit} — {role}` selector;
- the `org_unit_members` pseudo-principal, displayed as
  **All org unit members**;
- the exact default permission sets in Section 9 of the specification;
- persistent dormant local ACLs under live inheritance;
- deterministic greenfield ownership and ACL initialization;
- authorized per-org-unit dashboard counts;
- reasoned, singly confirmed ordinary ownership-changing moves; and
- deferrable exceptional bulk transfer as the final implementation phase.

## 2. Privilege catalogue contract

The exceptional privilege code is approved as:

```text
organization.holdings.transfer
```

Display name:

```text
Transfer Defunct Organization Holdings
```

Purpose:

> Transfer every aggregation and record owned by a defunct organizational unit
> to one active destination under the approved ACL-reconciliation workflow.

Category: `exceptional`.

This is a reserved future privilege. Phase 0 records it in the authorization
catalogue design only. It must not be inserted into the database privilege
catalogue, assigned to a profile, returned by the API, or grant any capability
until the optional Phase 8 workflow is implemented.

When Phase 8 is implemented, the operation additionally requires:

- an effective information-governance role;
- sufficient clearance for every affected resource;
- a complete and valid ACL-reconciliation plan;
- a non-blank reason; and
- one explicit confirmation.

It is not a generic bypass and requires no dual approval.

## 3. User-interface contract

The combined selector label is approved as **Create for**. Options use:

```text
{org unit name} — {role name}
```

Each distinct effective role produces one option. Several roles in one org
unit therefore repeat the org-unit name. Overlapping assignments to the same
role produce one option. When exactly one role is eligible, the control is
automatically populated and read-only.

The `org_unit_members` explanation is:

> Everyone currently working in **{org unit name}**. Membership updates
> automatically when role assignments change.

## 4. Affected implementation inventory

The following inventory is the minimum review surface. Implementation must
repeat repository-wide searches during each phase so newly added paths are not
missed.

### 4.1 Canonical schema and migrations

| Surface | Current location | Required later change |
| --- | --- | --- |
| Aggregation and record tables | `database/schema.sql` | Owner columns, foreign keys, indexes, and final non-null rules |
| Hierarchy and containment integrity | `database/schema.sql` | Owner equality and move propagation |
| Event-history snapshots and triggers | `database/schema.sql` | Org-unit references and ownership-change evidence |
| Privilege catalogue | `database/schema.sql`; future ordered migration | Phase 8 seed only |
| ACL grant/default tables | `database/schema.sql` | `org_unit_members` constraints and unique indexes |
| ACL initialization | `initialize_resource_acls()` in `database/schema.sql` | Approved effective and dormant defaults |
| Authorization predicates | `user_has_aggregation_permission()`, `user_has_record_permission()` and related functions in `database/schema.sql` | Contextual owner-unit match |
| Search projections | `authorized_aggregations_for_search`, `authorized_records_for_search` | Owner fields and filtering support |
| Database tests | `database/tests/` | Schema, migration, invariant, propagation, and ACL-principal coverage |

Every schema change must appear independently in the next ordered migration
and in the complete self-contained `database/schema.sql`. No SQL file may use
`psql` meta-commands or make the canonical schema invoke a migration.

### 4.2 API models and generic data access

| Surface | Current location | Required later change |
| --- | --- | --- |
| Create/update/read schemas | `backend/services/api/schemas.py` | Owner references and `creator_acl_role_id` contract |
| Generic CRUD visibility and relations | `backend/services/api/crud.py` | Include owner fields without weakening existing authorization |
| Aggregation and record search | `backend/services/api/search.py` | Owner filter and projections |
| Root, child, and record creation | `backend/services/api/main.py` | Validate selected role, derive owner, and initialize defaults |
| Ordinary aggregation and record moves | `backend/services/api/main.py`; `backend/services/api/resource_acls.py` | Atomic owner propagation, reason, confirmation, and ACL semantics |
| Draft/save workflow | record-draft routes in `backend/services/api/main.py` | Bind the selected role and owner through final save |

### 4.3 Authorization and ACLs

| Surface | Current location | Required later change |
| --- | --- | --- |
| In-memory policy model and role loading | `backend/services/api/authorization_policy.py` | Owner-aware pseudo-principal evidence |
| Resource operation checks | `backend/services/api/resource_authorization.py` | Preserve privilege, clearance, ACL, governance, and lifecycle gates |
| ACL read/write, inheritance, defaults, previews, and moves | `backend/services/api/resource_acls.py` | New principal and persistent dormant ACL behaviour |
| Authorization explanations | `backend/services/api/governance_authorization.py` | Explain `org_unit_members` matches |
| Privilege/profile administration | `backend/services/api/authorization_admin.py` | Phase 8 privilege impact only |
| Login/effective-role materialization | `backend/services/api/authentication.py` | Supply distinct effective-role options and org-unit identity |
| Custody continuity checks | `backend/services/api/security_operations.py`; `backend/services/api/permanent_deletion.py` | Reassess Phase 8 privilege/profile consequences |

### 4.4 Browse, discovery, reporting, and indirect access

| Surface | Current location | Required later change |
| --- | --- | --- |
| Classification and hierarchy browse | `backend/services/api/browse.py` | Owner references and optional owner filter |
| Favourites | `backend/services/api/favourites.py` | Owner display while preserving authorization |
| Recent activity | authenticated recent-item queries in `backend/services/api/authentication.py` | Owner display and cache correctness |
| Dashboard | dashboard data calls and authorized resource queries | Per-effective-org-unit aggregation and record counts |
| Event history and security history | `backend/services/api/main.py`; `backend/services/api/security_operations.py` | Ownership snapshots and move evidence |
| Exports and reports | current and future aggregation/record export paths | Optional owner filtering after authorization |

Counts, filters, facets, and exports must always operate on already authorized
resources. Ownership is not an authorization predicate.

### 4.5 Web UI and API client

| Surface | Current location | Required later change |
| --- | --- | --- |
| API payloads and responses | `frontend/webui/api_client.py` | Selected role, owner filters, owner references, and dashboard counts |
| Create forms and saved-record workflow | `frontend/webui/app.py` | **Create for** selection and read-only single-role state |
| Aggregation and record details | `frontend/webui/app.py` | Owning-org-unit display |
| Search and browse interfaces | `frontend/webui/app.py` | Owner filters and labels |
| Dashboard | `select_dashboard()` in `frontend/webui/app.py` | Separate authorized counts per effective org unit |
| ACL editor | ACL rendering and replacement flow in `frontend/webui/app.py` | New pseudo-principal and dormant-local round-trip |
| Move previews and confirmation | aggregation and record movement UI | Owner change, affected counts, reason, and one confirmation |

### 4.6 Test suites

At minimum, later phases affect:

- `backend/services/api/tests/test_api.py`;
- `backend/services/api/tests/test_authorization_policy.py`;
- `backend/services/api/tests/test_phase7_mutation_authorization.py`;
- `backend/services/api/tests/test_phase8_content_authorization.py`;
- `backend/services/api/tests/test_resource_acls.py` or its current equivalent;
- browse, search, favourites, history, dashboard, draft, and migration tests;
- `frontend/webui/tests/`; and
- browser tests for create, ACL, dashboard, and move workflows.

Tests that assert exact privilege counts or exact catalogue membership must not
change until the Phase 8 privilege is actually seeded.

## 5. Migration strategy and rollback preparation

### 5.1 Greenfield backfill inputs

The deterministic assignment utility requires:

- active roles and their active org-unit hierarchies;
- root aggregation number, title, and description;
- normalized matching rules;
- a stable role ordering;
- a stable root ordering; and
- a report destination outside immutable event history until the transaction
  succeeds.

Identical input must produce identical ownership and selected-role mappings.
An empty eligible-role set is a hard failure.

### 5.2 Deployment boundaries

- Phase 1 adds nullable storage only.
- Phase 2 backfills and verifies ownership but retains ACLs until the new
  principal exists.
- Phase 3 enforces ownership invariants.
- Phase 5 introduces `org_unit_members` without applying it by default.
- Phase 6 replaces greenfield generated ACL contents with approved defaults.
- Phase 8 is optional and independent of core-feature release.

### 5.3 Rollback rules

Before `NOT NULL` and runtime enforcement, rollback may remove the nullable
columns and indexes only after verifying that no dependent release is active.

After ownership becomes enforced or exposed:

- prefer rolling the application forward;
- do not discard confirmed ownership or immutable history;
- disable new UI entry points through the feature flag if necessary;
- retain owner columns while reverting readers to compatibility behaviour; and
- restore an earlier ACL snapshot only through a reviewed compensating
  migration with recorded counts.

Rollback must never delete event history, guess inverse subtree ownership, or
partially revert ACL schema while new principal rows remain.

### 5.4 Pre-deployment evidence

Every data-changing phase must capture:

- schema migration version and checksum;
- row counts for roots, descendants, records, and ACL grants;
- null and containment-mismatch counts;
- deterministic assignment report and checksum;
- ACL grant counts by principal type and permission;
- migration duration and query plans for representative owner filters; and
- cleanup confirmation for the disposable verification database.

## 6. Monitoring contract

Later implementation must expose logs or metrics for:

- null aggregation or record owners;
- child/parent and record/aggregation owner mismatches;
- rejected direct owner mutations;
- ownership propagation duration and affected counts;
- failed or rolled-back moves;
- create attempts without an eligible role in the owning unit;
- `org_unit_members` authorization matches and denials by stable reason code;
- owner-filter and dashboard-count query latency;
- ACL dependency or clearance failures during initialization; and
- Phase 8 plan-validation, execution, interruption, and reconciliation status
  if that phase is implemented.

No metric or log may expose protected resource titles or content to an
unauthorized observer.

## 7. Verification matrix

| Area | Required evidence |
| --- | --- |
| Canonical schema | Fresh database created from `database/schema.sql` has the final structure and constraints |
| Upgrade migration | Pre-feature database upgrades to the same structure and data outcome |
| Determinism | Repeated backfills over identical input produce identical mappings and checksums |
| Containment | Roots, descendants, records, and moves preserve owner invariants |
| Authorization | Privilege, clearance, named role, `Everyone`, `org_unit_members`, and governance evidence remain independently testable |
| Inheritance | Dormant ACL edits survive inherited/local round-trips unchanged |
| Defaults | Every Section 9 grant and omission is exact, including dependency closure |
| Discovery | Search, browse, counts, favourites, history, and exports remain authorization-safe |
| Dashboard | Each effective org unit appears once with separate authorized aggregation and record counts |
| Concurrency | Create, record move, subtree move, and ACL changes cannot leave partial state |
| Audit | Owner creation and changes are historically reconstructable |
| Performance | Owner filters, contextual ACL evaluation, and dashboard counts meet agreed query-plan and latency thresholds |
| Optional Phase 8 | ACL reconciliation and ownership transfer cannot diverge, including after interruption |

Database-backed verification must use a new uniquely named disposable database
for each run, initialize it through the path under test, point the complete
test process at it, and drop it after success or failure. Development, staging,
production, and other persistent databases must never be test targets.

## 8. Phase 0 completion gate

- [x] Governing specification approved.
- [x] `organization.holdings.transfer` code, purpose, category, and deferred
  activation recorded in the authorization catalogue design.
- [x] **Create for** label, option format, and single-role behaviour confirmed.
- [x] Deterministic greenfield assignment responsibility and algorithm
  confirmed.
- [x] Database, API, authorization, discovery, UI, and test surfaces inventoried.
- [x] Migration rollback and evidence requirements documented.
- [x] Monitoring requirements documented.
- [x] Verification matrix documented.
- [x] Exceptional bulk transfer remains isolated as a deferrable final phase.

Phase 0 is complete when documentation validation passes. Phase 1 may then add
the nullable ownership schema foundation; it must not introduce runtime
ownership enforcement or ACL behaviour.
