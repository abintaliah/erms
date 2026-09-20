# User management subsystem

The user management subsystem models people, organizational structure,
organizational roles, and temporal assignments of users to roles. Authentication
and authorization are integrated subsystems with separate policy boundaries.

## Design boundaries

- A user represents a person known to the ERMS, not a login account.
- A role represents an organizational position.
- Every role belongs to exactly one organizational unit.
- A role may be supervised by another role in any organizational unit.
- Users acquire one or more roles through temporal assignments.
- Users do not receive privileges or ACL permissions directly.
- Credentials remain separate from the person row. Profiles, privileges,
  security clearances, and resource permissions are assigned through roles.

Profiles are named collections of global privileges. Profiles and resource ACL
entries are assigned to roles only. A user's effective access is derived through
current assignments to effective roles.

## Users

`users` contains:

| Field | Meaning |
| --- | --- |
| `id` | Internal `bigserial` identity |
| `name` | Culturally neutral complete name |
| `email` | Optional, globally unique ignoring case |
| `external_id` | Optional stable identifier from an external system |
| `status` | `active`, `inactive`, or `suspended` |
| `date_created` | Automatically assigned creation timestamp |
| `date_deactivated` | Timestamp at which the user was deactivated |

Names are not unique. The model makes no assumptions about given names, family
names, ordering, or number of name components.

`external_id` is intended for HR, directory, or identity-provider integration.
Authentication identities will later be modeled separately rather than turning
an email address or login name into the person's permanent identity.

## Organizational units

`org_units` contains:

| Field | Meaning |
| --- | --- |
| `id` | Internal `bigserial` identity |
| `parent_org_unit_id` | Optional parent organizational unit |
| `code` | Globally unique, case-insensitive stable code |
| `name` | Globally unique, case-insensitive name |
| `description` | Optional description |
| `status` | `active` or `inactive` |
| `date_created` | Automatically assigned creation timestamp |
| `date_deactivated` | Timestamp at which the organizational unit was deactivated |

The parent relationship supports an organizational hierarchy. PostgreSQL
rejects direct self-parenting and longer cycles.

## Roles

`roles` contains:

| Field | Meaning |
| --- | --- |
| `id` | Internal `bigserial` identity |
| `org_unit_id` | Mandatory owning organizational unit |
| `supervisor_role_id` | Optional supervising role |
| `code` | Globally unique, case-insensitive stable code |
| `name` | Globally unique, case-insensitive administrator-facing name |
| `description` | Optional description |
| `status` | `active` or `inactive` |
| `date_created` | Automatically assigned creation timestamp |
| `date_deactivated` | Optional deactivation timestamp |

Supervising and subordinate roles may belong to different organizational units.
PostgreSQL rejects direct self-supervision and longer supervisory cycles.

Globally unique names prevent ambiguous administration screens containing many
indistinguishable roles named “Manager.” Codes remain stable machine-facing
identifiers when names are revised.

## User-role assignments

`user_role_assignments` is a first-class auditable entity:

| Field | Meaning |
| --- | --- |
| `id` | Internal `bigserial` identity |
| `user_id` | Assigned user |
| `role_id` | Assigned organizational role |
| `date_assigned` | Automatically assigned audit timestamp |
| `valid_from` | Beginning of the effective period; defaults to `date_assigned` |
| `valid_until` | Optional exclusive end of the effective period |

The same user can hold the same role during separate periods. The combination
of user, role, and `valid_from` is unique. PostgreSQL rejects an end timestamp
earlier than its start timestamp.

The authenticated actor who creates, changes, or deletes an assignment is
recorded authoritatively in immutable event history. The assignment row does
not duplicate that actor identity.

## Status and authorization semantics

User account status, role effectiveness, and assignment validity are separate
concepts and must not be presented as interchangeable statuses:

- A user has one account status: `active`, `inactive`, or `suspended`. A user
  does not have a derived or inherited “effective status.”
- An inactive or suspended user cannot authenticate. This restriction comes
  from the user's own account status, not from an organization unit or role.
- A role is effective only when the role, its owning organization unit, and
  every ancestor organization unit are active.
- Making a role or organization unit inactive does not change the status of an
  assigned user. It only prevents the affected role from contributing
  permissions.
- Permissions from the user's other effective roles remain available, provided
  their assignments are currently valid.
- Assignment validity belongs to one user-role relationship. It is current when
  server time is at or after the inclusive `valid_from` and, when present,
  before the exclusive `valid_until`. Future and expired assignments contribute
  no permissions but do not change either the user or role lifecycle status.

The organization tree therefore shows an assigned user's account status only.
It does not put assignment validity on the user node as if it were another user
status. Administrators can inspect assignment validity in the selected
occurrence summary, assignment filters, and assignment tables.

## Lifecycle and deletion

Deactivation is available only through explicit lifecycle operations:

- Users become `inactive` and receive `date_deactivated`.
- Roles become `inactive` and receive `date_deactivated`.
- Organizational units become `inactive` and receive `date_deactivated`.

Rows remain available for historical references. Deleting a role assignment
removes the assignment itself, while its immutable before-state remains in
event history.

`DELETE /api/v1/users/{id}`, `DELETE /api/v1/roles/{id}`, and
`DELETE /api/v1/org-units/{id}` permanently remove an eligible live row.
They never mean deactivation. Each request requires `If-Match` and a non-blank
`X-Change-Reason`; the entity may be active, inactive, or suspended.

Each entity also exposes `GET .../{id}/deletion-preflight`. The response includes
the entity version, whether deletion is allowed, every known blocker, dependency
counts, and data that will cascade. Execution repeats the same analysis under a
transaction-scoped authorization-continuity advisory lock plus a target-row
lock, so a preflight result is advisory rather than an authorization token. The
advisory lock coordinates only participating continuity mutations; it does not
lock whole tables or block unrelated writes.

User deletion is blocked for self-deletion, removal of the last effective
authorization administrator, or loss of the last effective highest-clearance
human governance custodian while protected resources exist. Role deletion is
blocked for the reserved system-administrator role, supervised roles, any live
resource ACL or default-child ACL reference, and the same continuity failures.
Organizational-unit deletion is blocked for `SYSTEM`, child units, or owned
roles. There is no force or recursive override.

Eligible user deletion cascades credentials, sessions, assignments, drafts,
favourites, and classification preferences. Eligible role deletion cascades
assignments. Organizational-unit deletion does not recursively delete anything.
Immutable event history remains, including the final entity before-state and a
security-safe summary of transient session data removed with a user.

### Users

- An inactive user cannot authenticate and any existing login sessions are
  revoked in the same transaction as deactivation.
- The user's role assignments remain stored for history, but cannot contribute
  authorization while the user is inactive.
- Reactivation clears `date_deactivated`; retained assignments can become
  effective again when their dates, roles, and organization hierarchy permit.
- A suspended user is also unable to authenticate, but suspension is distinct
  from deactivation and does not set `date_deactivated`.
- Explicit `POST .../{id}/suspend` and `POST .../{id}/unsuspend` operations
  govern suspension. Suspending revokes active sessions; unsuspending does not
  restore them.

### Roles

- Deactivation does not deactivate assigned users and does not delete or end
  their assignments.
- An inactive role contributes no privileges or ACL permissions. Authentication
  principals omit it from their effective roles.
- Reactivation clears `date_deactivated` and allows otherwise valid retained
  assignments to become effective again.

### Organizational units and inherited effectiveness

- Deactivating an organizational unit does not rewrite its roles, users,
  assignments, child units, or descendant roles.
- It does **not** deactivate any user account and does **not** revoke or otherwise
  end any user's active login sessions. Session revocation occurs only when the
  user is deactivated or a session is explicitly revoked.
- A role is **effectively active** only when the role itself is active and its
  owning organizational unit and every ancestor unit are active.
- Consequently, deactivating a unit makes roles in that unit and every
  descendant unit ineffective. Users remain active and roles assigned through
  other active branches remain available.
- Reactivating the unit clears `date_deactivated` and restores descendant role
  effectiveness except where a role or another unit in its ancestry is
  independently inactive.
- Supervisory and historical relationships remain visible even while a role is
  ineffective.

### Assignment safeguards

New or reassigned role assignments require an active user and an effectively
active role. Existing assignments are retained across lifecycle transitions.
The database enforces these requirements so alternate clients cannot bypass
the UI.

Lifecycle timestamps are database-normalized and constrained: inactive users
and roles have `date_deactivated`, as do inactive organizational units. Active
or suspended entities have no deactivation timestamp. Future lifecycle
timestamps are rejected.

### Administrative UI behavior

The organization-unit, role, and user lists expose explicit Activate and
Deactivate actions with a confirmation that explains the consequences. User
lists additionally expose Suspend and Unsuspend. User status columns and
filters show the user's account status. Role and organization-unit status
presentation may show effective status: a role whose own row is active is
nevertheless ineffective when its organizational unit or an ancestor unit is
inactive. A tooltip identifies whether the cause is direct or inherited.

Assignment dialogs keep existing assignments visible for historical clarity,
but do not offer inactive users or effectively inactive roles as new assignment
targets. Each retained assignment displays the current effective status of its
role or user. An inactive role is marked as such even if the assignment itself
is still retained, and its tooltip distinguishes a directly inactive role from
one made ineffective by an inactive organizational unit or ancestor. The
assignment controls are disabled when the selected subject is not effective.
If the signed-in administrator deactivates their own user, the UI is immediately
cleared and returns to the login screen after the server revokes the session.

## Event history

The following entity types are audited automatically:

```text
user
org_unit
role
user_role_assignment
```

Their creation, update, deactivation, assignment changes, and assignment
deletion use the same transactional immutable event history as records
management entities.

Migration 011 normalized legacy organizational-unit audit payloads from
`date_closed` to `date_deactivated`. This was a one-time schema terminology
correction: it changed no event identity, timestamp, actor, operation, or field
value. The event-history mutation guard is removed only inside that migration's
transaction and is restored before it commits.

## REST API

Each primary resource supports create, list, retrieve, partial update, explicit
lifecycle operations, advanced search, and history:

```text
/api/v1/users
/api/v1/org-units
/api/v1/roles
```

Explicit lifecycle operations append `/activate` or `/deactivate` to an entity
URL and require the current version through `If-Match`.
Users additionally provide `/suspend` and `/unsuspend`. Permanent `DELETE` is
intentionally unavailable until the authorization subsystem is implemented.

Role assignments support ordinary CRUD, search, and history:

```text
/api/v1/user-role-assignments
```

Relationship navigation endpoints are:

```text
GET /api/v1/users/{user_id}/roles
GET /api/v1/roles/{role_id}/users
```

These return assignment resources, including their validity periods, rather
than hiding assignment metadata behind user or role objects.

Advanced search endpoints are:

```text
POST /api/v1/users/search
POST /api/v1/org-units/search
POST /api/v1/roles/search
POST /api/v1/user-role-assignments/search
```

They use the controlled grammar in [`search-grammar.md`](search-grammar.md).

## Deferred authorization model

No current status or role assignment is treated as an authorization decision
yet. The future authorization subsystem will add:

```text
privileges
profiles
profile_privileges
role_profiles
aggregation ACLs referencing roles
record ACLs referencing roles
```

Only roles will receive profiles, privileges, and ACL permissions. Effective
user access will be resolved from the user's active role assignments together
with inherited permissions, security levels, caveats, and other future policy
layers.
