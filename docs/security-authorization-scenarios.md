# Authorization configuration scenarios

This guide translates common working arrangements into the global privileges
and resource ACL permissions that an administrator must configure. It is the
practical companion to the authorization specification and implementation
phase documents.

Authorization remains multi-layered. A listed recipe succeeds only when the
person has an active account, a current assignment to an effective role,
sufficient security clearance, every listed global privilege, and every listed
permission from the resource's effective ACL. An information-governance role
may bypass the ACL gate only; it does not replace a missing global privilege or
clearance.

## Close an aggregation without editing its metadata

This separation is supported and is useful when closing a file is a controlled
business action performed by someone who should not rewrite its descriptive
metadata.

The role's profile needs:

- `aggregation.view`
- `aggregation.close`

The aggregation's effective ACL needs:

- `aggregation.view`
- `aggregation.close`

Do not grant `aggregation.modify` or `aggregation.modify_metadata`. The user
can view and close the open aggregation but cannot edit its title, description,
number, opening date, classification, parent, or security level. Reopening is a
separate operation and requires `aggregation.reopen` globally and on the ACL.

## Create a complete record, then make it immutable to its creator

Use this arrangement when a person must prepare new record metadata and files
as one package, but must not alter that authoritative record after saving it.

The role's profile needs:

- `aggregation.view`
- `record.view`
- `record.create`

The destination aggregation's effective ACL needs:

- `aggregation.view`
- `aggregation.add_record`

While the draft is open, `record.create` permits its owner to edit draft
metadata, stage files, remove or reorder staged files, and commit the entire
package. `record.component.add` is not needed for those creation-time files.

To keep the committed record immutable to that role, do not grant:

- `record.modify`
- `record.component.add`
- `record.component.replace`
- `record.component.remove`
- `record.component.reorder`

Viewing the saved record still depends on `record.view` globally and on the
record's effective ACL. Component listing, viewing, and downloading are also
separate read permissions and may be granted without granting component
mutation.

## Add files to an existing record without editing metadata

The role's profile needs `record.view` and `record.component.add`. The record's
effective ACL needs `record.view` and `record.component.add`. Do not grant
`record.modify` or `record.modify_metadata`.

This permits adding a new component after commit but does not permit changing
the record metadata, replacing an existing component, removing one, or changing
component order. Each of those actions has its own privilege and matching ACL
permission.

## Diagnose access for another person

The examiner needs `authorization.explain`. The examiner must also be able to
view the resource and satisfy its clearance boundary. This permits evaluating
another person's live roles, profile, clearance, and ACL contribution without
impersonating that person. The action is recorded in event history.

## Configuration checklist

For any scenario, verify all of the following rather than looking only at the
profile:

1. The person's account is active and not suspended or locked.
2. At least one assigned role is current and effectively active through its
   organization hierarchy.
3. The union of effective role profiles supplies the required global
   privileges.
4. The maximum clearance across effective roles meets the resource's security
   level.
5. The resource's live effective ACL grants the required permissions, unless a
   qualifying information-governance role supplies the documented ACL bypass.
6. Resource state rules, such as closed-aggregation restrictions, permit the
   operation.

Use **Why this access?** on the resource details page to inspect these gates for
the current user. Users with `authorization.explain` may inspect the result for
another person.
