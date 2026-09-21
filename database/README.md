# ERMS database setup

## New database

Execute exactly one file:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f database/schema.sql
```

`schema.sql` is the canonical bootstrap entry point and physically contains the
complete current schema. It uses standard SQL and does not depend on `psql`
include commands or separate migration files. Do not execute individual
migration files when initializing a new database.

`schema.sql`, every migration, every seed, and every database test fixture must
contain PostgreSQL SQL only. Client-specific meta-commands such as `\\i`,
`\\ir`, `\\set`, and `\\copy` are prohibited. Command-line clients may still
be configured externally (for example, `psql -v ON_ERROR_STOP=1`).

## Seed data

Schema creation, schema migration, and seed data are separate workflows.
`schema.sql` never invokes a seed. Apply an optional script from
`database/seeds/` explicitly, and only after the database is on the latest
canonical schema. Seed scripts do not record schema migration versions.

The schema deliberately contains no shared default password. Once the empty
schema has been loaded, create its one-time bootstrap administrator with:

```bash
backend/services/api/.venv/bin/python -m backend.services.api.manage_auth \
  bootstrap \
  --name "Bootstrap Administrator" \
  --email bootstrap@erms.local
```

The command generates and displays a unique 24-hour temporary password and
forces it to be changed at first login. It refuses to run in a database that
already contains users. See [`../docs/authentication.md`](../docs/authentication.md)
for the complete security model, reserved objects, audit behavior, recovery
procedure, and post-bootstrap checklist.

## Existing database

Apply only migrations not already recorded in `schema_migrations`, in filename
order. To add event history and then user management to a database containing
the core records schema:

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/001_add_event_history.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/002_add_user_management.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/003_add_content_storage_and_entity_versions.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/004_add_record_drafts.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/005_add_authentication.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/006_enforce_closed_aggregations.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/007_freeze_closed_aggregation_metadata.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/008_cascade_record_digital_components.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/009_user_management_lifecycle.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/010_rename_org_unit_deactivation_date.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/011_normalize_org_unit_event_history.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/012_backfill_anonymous_event_actor.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/013_snapshot_event_actor_identity.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/014_backfill_webui_event_source.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/015_reclassify_lifecycle_normalization_events.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/016_snapshot_role_assignment_parties.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/017_rename_system_accounts_to_service.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/018_rename_system_actor_to_automated_process.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/019_add_classification_schemes.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/020_backfill_legacy_root_classification.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/022_govern_classification_scheme_deletion.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/023_govern_classification_lifecycle.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/026_add_classification_browser_indexes.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/027_segment_postgresql_content.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -1 \
  -f database/migrations/028_add_user_favourites.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/030_remove_assignment_attribution_and_prepare_user_deletion.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/031_rename_human_accounts_to_person.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/032_add_security_levels.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/033_add_privileges_profiles_and_role_authorization.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/034_add_resource_acl_inheritance.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/035_enforce_resource_read_authorization.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/036_enforce_resource_mutation_authorization.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/037_enforce_draft_component_authorization.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/038_add_security_operations_indexes.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/039_shorten_builtin_profile_codes.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/040_add_information_governance_profiles.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/041_grant_governance_security_level_administration.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/042_add_organization_browse_privilege.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/043_add_event_reference_snapshots.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/044_add_organizational_ownership_foundation.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/045_assign_existing_organizational_ownership.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/046_enforce_organizational_ownership.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/047_expose_organizational_ownership_in_search.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/048_add_org_unit_members_acl_principal.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/049_initialize_organizational_acl_defaults.sql

psql "$DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f database/migrations/050_add_root_ownership_correction.sql
```

The historical files numbered 021 and 024 are retained only for databases
whose migration history already includes those legacy seed migrations. Do not
use them to seed new databases. Their canonical replacements live under
`database/seeds/` and are run explicitly after `schema.sql`.

The `-1` option wraps the migration in one transaction. Migration 001 is safe
to apply to the current development database where the event-history objects
were initially installed before migration tracking was introduced; it preserves
existing events and records the migration version. Migration 002 adds users,
organizational units, roles, temporal role assignments, hierarchy safeguards,
searchable indexes, and event-history triggers.
Migration 003 adds PostgreSQL-backed digital-component content storage and
database-managed optimistic-concurrency versions for all mutable entities.

Migration 033 seeds the immutable global-privilege catalogue and reserved
profiles, safely backfills one profile for every role, and adds the
information-governance role flag without yet enforcing privileges on business
routes.

Migration 034 installs the aggregation and record permission catalogue,
deferred permission-dependency enforcement, FK-safe role/Everyone ACL grants,
resource overrides, live child defaults, mirror/custom aggregation-default
modes, inheritance flags, optimistic ACL versions, default Everyone/all
initialization, and audit triggers. Everyone remains synthetic and is never a
role row.

Migration 023 adds classification deactivation and immutable per-classification
first-use provenance. Assignment marks the terminal and every ancestor as
historically used. Only unused leaves in active, currently unpublished schemes
can then be permanently deleted; inactive paths are excluded from new
assignments without disturbing existing governance.
Migration 026 adds the compound relationship-and-business-identifier indexes
used by the cursor-paginated classification, aggregation, and record browser.
See
[`../docs/aggregation-classification-browser.md`](../docs/aggregation-classification-browser.md).
Migration 027 converts committed and draft binary content from one `bytea`
value per file to ordered segments, creates active/staged content sets and
upload sessions, and preserves existing content as segment zero. It is
transactional but intentionally does not use the command-line `-1` wrapper
because the migration contains its own transaction. See
[`../docs/content-storage.md`](../docs/content-storage.md).
Migration 028 adds private per-user aggregation and record favourites. The
relationships use cascading foreign keys, so deleting a user or target entity
cannot leave stale favourites.
Migration 030 removes the redundant client-supplied role-assignment actor,
prepares assignment and draft ownership for eventual governed deletion, and
adds the revoked-session cleanup index. The migration contains its own
transaction.
Migration 031 renames the interactive account type from `human` to `person`.
Migration 032 creates the security-level catalogue, seeds the approved General,
Restricted, Secret, and Top Secret levels, backfills mandatory role,
aggregation, and record references to General, and enforces the aggregation
container security invariant.
Migration 033 installs global privileges, single-profile role assignments,
effective-role policy data, information-governance role metadata, and the
approved compatibility profiles. Migration 034 installs resource permission
catalogues, aggregation and record ACL grants, live child inheritance,
synthetic Everyone grants, permission dependencies, and ACL concurrency
versions. Migration 035 installs the set-based visibility predicates and safe
search/audit projections used to enforce non-disclosing reads, protected
relationships, digital-component metadata access, and audit redaction.
Migration 036 adds the transaction-time aggregation and record operation
predicates used for operation-specific mutation, dual-sided move, security
change, and ACL-management authorization. Migration 037 adds private draft
ownership, component-operation predicates, commit-time reauthorization, and
the narrowly scoped transaction context used for audited record-placement
corrections into effectively closed aggregations. See the corresponding
`security-authorization-phase-2.md` through `security-authorization-phase-9.md`
documents under `docs/`.
Migration 043 preserves readable identity snapshots for entities referenced by
event before-state, after-state, and metadata fields. Migration 044 adds the
nullable organizational-ownership foundation to aggregations and records,
restrictive org-unit foreign keys, owner-oriented browse indexes, and owning
org-unit event-reference snapshots. It deliberately does not backfill owners,
make ownership mandatory, propagate ownership, or alter authorization.
Migration 045 deterministically assigns every existing root to an eligible
active role and its organizational unit, propagates the selected owner through
descendants and records, and retains the scored root mapping plus before/after
reconciliation counts for later ACL migration.
Migration 046 makes ownership mandatory, derives child and record ownership,
rejects direct owner changes, and atomically propagates ownership through
record and aggregation-subtree moves. Cross-owner moves require a reason and
explicit confirmation.
Migration 004 adds transactional record drafts. Migration 005 adds local
credentials, database-backed login sessions, and the original person/system
account types.
Migration 006 enforces direct and inherited aggregation closure throughout the
hierarchy, record, component, and blob layers. The complete business rules are
documented in [`../docs/aggregation-closure.md`](../docs/aggregation-closure.md).
Migration 007 freezes the aggregation metadata itself and permits only clearing
a directly closed aggregation's closure date.
Migration 008 makes digital components lifecycle-dependent on their record:
deleting a record atomically cascades to its component metadata and stored
content.
Migration 009 enforces user, role, and organizational-unit lifecycle state,
inherited organizational effectiveness, assignment eligibility, and the
status/timestamp invariants described in the user-management documentation.
Migration 010 renames the organizational-unit lifecycle timestamp from
`date_closed` to the consistent `date_deactivated` without changing its data.
Migration 011 performs the corresponding one-time terminology normalization in
existing `org_unit` audit payloads and restores the audit immutability trigger
within the same transaction.
Migration 012 retrospectively attributes legacy anonymous events to the agreed
administrator account. It records the basis and migration identifier in each
affected event's metadata and restores the audit immutability trigger within
the same transaction.
Migration 013 stores an immutable name and email snapshot alongside every
application-user actor and backfills those snapshots on existing events.
Migration 014 corrects legacy `api` source values to `web_ui` for the known
NiceGUI-only development period, records that basis in event metadata, and
leaves direct database events unchanged.
Migration 015 reclassifies the no-op lifecycle-normalization events generated
by migration 009 from `database` to `migration`, without changing genuine
direct-database provisioning events.
Migration 016 stores durable user and role identity snapshots on role-assignment
events and backfills existing events, so the audit trail does not depend on
opaque IDs or mutable current rows.
Migration 017 renames the non-interactive user account type from `system` to
`service`.
Migration 018 separately renames audit actor type `system` to the clearer
`automated_process`, backfills existing events with migration provenance, and
constrains future event actor types to `user`, `anonymous`, or
`automated_process`.
Migration 019 adds classification schemes, unlimited-depth branch and terminal
classifications, inheritable classification retention rules, root-aggregation
classification assignments, root-only local retention overrides, effective-rule
resolution, recent per-user selections, database enforcement, and audit history.
Existing unclassified root aggregations remain readable; the root-classification
check is deliberately installed `NOT VALID` so administrators can classify them
without fabricated defaults. New and changed roots are enforced immediately.
See [`../docs/classification-schemes.md`](../docs/classification-schemes.md).
Migration 020 is a development-data remediation authorized while the system is
still greenfield. It resolves the existing terminal `General` classification
inside `Test Classification Scheme`, verifies that the scheme is eligible and
the classification has an effective retention rule, assigns it to every legacy
unclassified root aggregation, records migration provenance in event history,
and validates the previously deferred root-classification constraint. It fails
rather than guessing when the named scheme or classification is absent or
ambiguous.
Migration 021 is an idempotent greenfield development seed. It creates and
publishes `EWA-FCS — Electricity and Water Authority Functional Classification
Scheme` with four functional roots, twelve branches, thirty-six terminals and
one realistic retention rule for every terminal. All seed events carry
`migration` source and structured provenance. It refuses to overwrite an
existing scheme with the same code or title.
Migration 024 is a second idempotent greenfield seed. It creates and publishes
`GCS — General Classification Scheme` with four roots covering Administration,
Human Resources, Finance and Asset Management; twelve child branches;
thirty-six assignable terminals; and a realistic terminal retention rule for
every terminal. Its 89 creation events use actor type `automated_process`,
source `migration`, a shared explicit reason, and structured metadata naming
the migration, authorization basis, scheme and expected hierarchy counts. It
refuses to overwrite an existing scheme with the same code or title.

The larger XML example file plan is imported through the transactional seed
utility rather than embedded into SQL:

```bash
backend/services/api/.venv/bin/python database/seeds/import_mutamathilah.py \
  --database-url "$DATABASE_URL"
```

It imports `examples/fileplans/mutamathilah.xml` as draft unless the XML supplies
`date_published`. It maps `title_en` to the title and preserves the Arabic scheme
name and classification `title_ar` in description fields. It refuses collisions,
validates expected counts and deferred constraints, verifies all audit events,
and records the seed identifier in event metadata. It does not read or write
`schema_migrations`; repeat execution detects the already imported scheme.

## Tests

```bash
database/tests/run.sh
```

The test runner always creates a fresh disposable PostgreSQL container, builds
and tests its databases, and removes the container on success, failure, or
interruption. It never points tests at the standalone development database.

Migration 048 adds the contextual `org_unit_members` ACL principal to resource
and child-default ACLs. It reserves the synthetic identity against real roles
and updates authorization predicates so membership follows the resource owner
and current effective role assignments without rewriting ACL rows.

Migration 049 replaces the greenfield generated ACL contents with the approved
organizational defaults. It initializes creator-role and `org_unit_members`
grants for root ACLs, child-default policies, and dormant child/record local
ACLs while preserving existing inheritance flags. New resources use the same
initializer when the API supplies the validated creation role context.

Migration 050 adds `organization.ownership.correct` to the information-
governance profiles and installs the tightly scoped database context that
allows the governed API command to correct a root owner while normal direct
owner updates remain prohibited.
