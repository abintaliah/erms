# Organizational ownership — Phase 5 completion

Phase 5 introduces `org_unit_members`, displayed as **All org unit members**,
as a contextual synthetic ACL principal. It is available for explicit ACL
configuration but is not yet added automatically when resources are created.

## Meaning and evaluation

The principal grants a permission when the subject has at least one currently
effective role in the resource's owning organizational unit. The ACL row does
not store an org-unit identifier: membership is evaluated against the current
resource owner and current role assignments each time authorization is
checked.

`org_unit_members` remains independent of the global-privilege and security-
clearance gates. Information-governance bypass behavior is unchanged.

## Storage and API

- All four resource and child-default ACL tables accept `org_unit_members`
  only with a null `role_id`.
- Each table has a partial unique index preventing duplicate contextual grants
  for one resource and permission.
- Permission dependencies apply exactly as they do to role and `everyone`
  grants.
- Real roles cannot use the reserved code `org_unit_members` or the reserved
  name `All org unit members`.
- ACL request, response, preview, effective-resolution, and access-explanation
  models identify contextual grants explicitly.

## User interface

The ACL editor can remove and re-add **All org unit members**. It explains the
principal in user language using the resource owner's name: everyone currently
working in that organizational unit, with membership updating automatically
when role assignments change. No separate org-unit selector is presented.

## Phase boundary

Existing ACL rows are not rewritten. Phase 6 will implement the **Create for**
selector and approved creator-role and org-unit-member default grant sets.
