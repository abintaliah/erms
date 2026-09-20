# Security and authorization implementation — Phase 2

Status: implemented and verified

This phase establishes global privileges, profiles, and the role-to-profile model. It intentionally does not enforce those privileges on existing business routes; global administrative enforcement begins in Phase 4 after the Phase 3 decision engine exists.

## Privilege catalogue

The runtime privilege catalogue is seeded from the approved specification and is read-only through the API. It contains 37 stable dotted privilege codes covering administration, aggregations, records, digital components, and exceptional operations. Global privilege dependencies prevent an internally inconsistent profile, such as granting `record.modify` without `record.view`.

Privilege codes are immutable. Introducing a privilege requires a reviewed database migration and an explicit update to any reserved profile that should receive it. In particular, **All privileges** does not silently acquire future privileges.

## Profiles

A profile is a named, versioned bag of global privileges. Profiles have no active/inactive lifecycle. Their stable code cannot be edited after creation; their name, description, and privilege membership can be maintained with optimistic concurrency and a mandatory change reason.

The reserved profiles are:

- **All privileges** (`ALL_PRIVS`), used to preserve existing behavior during migration;
- **System Administrator** (`SYS_ADMIN`), containing platform-administration privileges but no governed-content privileges; and
- **Information Governance Manager** (`INFO_GOV_MGR`) and **Information Governance Officer** (`INFO_GOV_OFFICER`), containing the same governance and classification-administration capabilities without bypassing clearance or global-privilege gates.

Before changing profile membership, the UI shows the number of affected roles and current assigned users. The API validates privilege dependencies, rejects stale versions, and prevents deletion while any role references the profile. Reserved profiles cannot be deleted.

## Role authorization fields

Every role references exactly one profile through a non-null, restrictive foreign key. Profiles cannot be assigned to users or organizational units, and a role cannot hold multiple profiles. During migration, **All privileges** is created and populated first, every existing role is assigned it, the backfill is verified, and only then is the role foreign key made mandatory.

New roles default to **All privileges** during this compatibility phase unless another profile is selected explicitly. The Roles listing identifies that compatibility assignment, and the role detail page explains that it should be replaced with a purpose-specific profile after review.

Roles also have an `is_information_governance` flag and the Phase 1 security clearance. The UI explains that the governance flag will bypass only resource ACLs: it does not bypass global privileges, the governance role's own clearance, effective assignments, closure rules, or other integrity controls.

## Continuity safeguards

Mutations that can remove effective authority are simulated in the same transaction. Profile membership changes, role profile changes, governance-flag or clearance changes, user suspension/deactivation, role or organization-unit deactivation, and assignment edits/deletion cannot remove:

- the last active person who effectively holds `authorization.administer`; or
- once protected resources and a universal custodian exist, the last active person assigned to an effective highest-clearance governance role with the required custody privileges.

The two-person custodian recommendation remains organizational policy rather than a system-enforced minimum. The application prevents the effective custodian count from reaching zero, as approved.

## API and UI

The API provides the read-only privilege catalogue, profile CRUD, complete profile-privilege replacement, affected-role/user impact previews, role-profile assignment and impact preview, and the new fields on role CRUD. Sensitive operations require `If-Match`; profile, profile-membership, profile-assignment, and governance-role changes require `X-Change-Reason` where applicable.

The Web UI adds Privileges and Profiles administration, a privilege-membership editor grouped by category, profile selection and governance guidance on role forms, profile information on role details, and a visible compatibility-profile warning in the Roles listing.

## Audit and migration provenance

Profile, privilege, and profile-membership rows use immutable event-history triggers. Domain events record profile membership replacement, role-profile assignment, governance-role changes, and role clearance changes. Migration 033 records automated migration provenance and a `ROLE_PROFILE_BACKFILL_COMPLETED` event with role, privilege, and unassigned-role counts.

## Verification

The Phase 2 gate was run against a newly created disposable PostgreSQL database, which the test runner removed afterward. It verifies:

- migration-upgrade and canonical clean-build schema parity;
- all 37 seeded privileges and the three reserved profiles;
- complete **All privileges** membership and existing-role backfill;
- valid composite profiles and dependency rejection;
- affected-role/user previews, role assignment, optimistic concurrency, and audit events;
- safe deletion and read-only runtime privilege definitions;
- impossibility of missing/multiple role profiles or direct user/organization-unit profile assignment;
- last-authorization-administrator and highest-clearance-custodian protection; and
- all pre-existing API/database behavior.

The disposable database/API suite passed 102 tests. The Web UI suite passed 60 tests.
