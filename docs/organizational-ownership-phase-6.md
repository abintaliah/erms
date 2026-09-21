# Organizational ownership — Phase 6 completion

Phase 6 implements the combined **Create for** creation context and the approved
organizational ACL defaults.

## Creation behavior

- `GET /api/v1/creation-role-options` returns one option per distinct current
  effective role as **{org unit} — {role}**.
- Root aggregation ownership is derived from the selected role; clients cannot
  submit an independent owner.
- Child aggregation and record choices are restricted to roles in the parent
  aggregation's owner. Creation is rejected when the user has no such role.
- Parent selection precedes **Create for** in both workflows. Record creation
  disables **Create for** until a parent is selected; aggregation creation
  allows a blank parent and explains that this creates a root whose owner comes
  from **Create for**.
- Parent changes preserve an eligible role selection, clear an ineligible one
  with an accessible explanation, and explicitly report when no eligible role
  exists.
- One eligible role is selected automatically and shown read-only. Multiple
  eligible roles require an explicit selection.
- Required fields are marked with `*`, and forms display a `* Required fields`
  legend. Optional fields remain unmarked; the optional aggregation Parent
  field has an explicit root-creation hint.
- **Create for** is not stored as a resource field. Saved resources display
  **Owning organizational unit**; the role choice remains visible through ACL
  grants and creation audit metadata.

The saved-record workflow passes the selected role at commit time, after the
destination aggregation is known. Direct record creation follows the same
server-side validation.

## ACL initialization

Migration `049_initialize_organizational_acl_defaults.sql` installs the exact
Section 9 grant sets for:

- root aggregation local ACLs;
- each aggregation's child-aggregation and child-record defaults;
- dormant local ACLs on inheriting child aggregations; and
- dormant local ACLs on inheriting records.

Roots use their local ACL. Children and records continue to inherit effective
access by default, so initializing a dormant local ACL does not widen the
parent policy. Switching to local override simply activates the last stored
local ACL.

The migration also rewrites mapped greenfield holdings using the Phase 2
root-to-role mapping without changing placement or inheritance flags.

## Audit and verification

Creation events include the selected role ID/code and derived org-unit ID in
metadata. Focused regression coverage verifies duplicate-unit role options,
owner derivation, exact grant sets and omissions, dormant inheritance behavior,
and denial where the parent owner has no matching effective role.
