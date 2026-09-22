# User, Role, and Organizational-Unit Deletion — Technical Specification

**Status:** Implemented and verified in Security and Authorization Phase 12
**Project:** ERMS  
**Prepared:** 17 September 2026  
**Revision:** 0.3 — authentication and session lifecycle extracted

## 1. Purpose

This specification defines lifecycle deactivation, reactivation, and permanent
deletion for users, roles, and organizational units. It also defines the
required removal of the redundant `assigned_by` column from
`user_role_assignments`.

The design has four objectives:

- make deactivation and deletion separate, unambiguous operations;
- permit administrators to delete entities created in error without unnecessary
  preliminary steps;
- prevent deletion from silently damaging organizational structure or making
  governed content inaccessible; and
- preserve an immutable, intelligible audit history after live entities are
  deleted.

## 2. Terminology

### 2.1 Deactivate and inactive

**Deactivate** is a reversible lifecycle operation. For a user, role, or
organizational unit, successful deactivation produces this authoritative
stored state:

```text
date_deactivated IS NOT NULL
```

**Inactive** describes that resulting state. In this specification, an inactive
entity and a deactivated entity refer to the same lifecycle condition.

A suspended user is not deactivated. Suspension is represented by
`date_suspended IS NOT NULL` while `date_deactivated` remains null.

### 2.2 Suspend and unsuspend

Suspension is a temporary administrative security state and is distinct from
deactivation. Its authentication behavior, session revocation, transitions, and
UI requirements are defined in
[Authentication and Login-Session Lifecycle](authentication-and-login-session-lifecycle.md).
Suspension is not a prerequisite for, or blocker to, permanent deletion.

### 2.3 Reactivate

**Reactivate** is the reversible operation that restores a deactivated entity:

```text
date_deactivated IS NULL
```

`status` is exposed as a read-only generated projection for stable API and
search contracts. It is not independent lifecycle state.

### 2.4 Credential lock

A temporary credential lock is authentication state, not a user lifecycle
status and not a deletion blocker. Its semantics are defined in
[Authentication and Login-Session Lifecycle](authentication-and-login-session-lifecycle.md).

### 2.5 Permanently delete

**Permanently delete** removes the live database row. It is irreversible through
ordinary application operations. Permanent deletion does not erase immutable
event history.

Deactivation is not a prerequisite for permanent deletion. An active, inactive,
or suspended entity may be deleted when all deletion conditions are satisfied.

### 2.6 Deletion blocker

A **deletion blocker** is a condition that makes permanent deletion unsafe. A
blocked request must change nothing and must explain every detected blocker.

Related data that this specification explicitly designates for cascading
deletion is not a blocker.

## 3. General principles

1. Deactivation and permanent deletion are independent operations.
2. `DELETE` always means permanent deletion. It must never be an alias for
   deactivation.
3. Creating, updating, deleting, or otherwise acting on business entities does
   not by itself make a user account undeletable.
4. Audit participation does not block deletion. Event history stores actor
   identity snapshots so that it remains intelligible without a live user row.
5. Permanent deletion may cascade disposable data that exists only because its
   owner exists.
6. Permanent deletion must not silently break organizational structure,
   authorization continuity, or the recoverability of aggregations and records.
7. The authorization subsystem will use pure role-based access control. Users
   receive access through roles. Direct user-specific aggregation or record
   ACLs must not be introduced.
8. Every deletion decision must be evaluated transactionally against current
   database state. Execution uses the shared transaction-scoped authorization-
   continuity advisory lock and a target-row lock; it must not take broad table
   locks.
9. Login sessions are transient security state. Immutable authentication events,
   not retained session rows, are the durable authentication audit trail.

## 4. User deletion

### 4.1 Conditions that block deletion

A user must not be deleted when any of the following is true:

1. The target user is the authenticated user making the request.
2. Deletion would leave the system without another active user who has the
   effective reserved `system-administrator` role.
3. After the authorization subsystem is implemented, removing the user's role
   assignments would leave one or more protected aggregations or records with no
   effective authorized user.
4. A future live business relationship explicitly documented as non-cascading
   requires the user row to remain. Adding such a relationship requires an
   amendment to this specification; an unspecified foreign key must not create
   an accidental deletion policy.

The user does not need to be deactivated before deletion.

The following facts must not block deletion:

- the user has authenticated or has login-session history;
- the user has created, read, updated, moved, closed, reopened, or deleted an
  aggregation or record;
- the user has performed an administrative operation;
- event-history rows identify the user as their actor;
- the user has role assignments;
- the user owns unfinished record drafts;
- the user has credentials, sessions, favourites, or classification browsing
  preferences; or
- the user is active, inactive, or suspended.

### 4.2 Access-continuity check

The future authorization subsystem must evaluate user deletion as if every role
assignment belonging to the target user had been removed.

Deletion is blocked when that simulated removal would leave any protected
aggregation or record with zero effective authorized users. Access inherited
from parent aggregations and access granted through every relevant role must be
included in the calculation.

An **effective authorized user** is an active user with a currently effective
assignment to an active role whose organizational-unit ancestry is active and
whose RBAC grants provide access to the target entity. The future authorization
specification must define the precise access capability that satisfies this
continuity rule; it must be sufficient for an authorized person to discover,
open, and administer the entity rather than merely proving that some unrelated
permission exists.

The response must identify the affected roles and provide the count of affected
aggregations and records. It may return a bounded sample of entity identifiers
when the complete list is large.

To resolve the blocker, an administrator must first do at least one of the
following:

- assign another active user to an appropriate permitted role;
- grant an appropriate role access to the affected content; or
- amend the content's inherited access policy without leaving it inaccessible.

Direct grants to an individual user are not a permitted resolution because the
system uses pure RBAC.

### 4.3 Data removed with a user

Successful user deletion must remove the following data in the same transaction:

| Related data | Required behavior |
| --- | --- |
| User-role assignments received by the user | Delete automatically |
| Record drafts owned by the user | Delete automatically, including draft components and temporary content |
| Credentials | Delete automatically |
| Login sessions owned by the user | Delete automatically; durable authentication events remain |
| References from other sessions' `revoked_by` field | Set to null |
| Favourite aggregations and records | Delete automatically |
| Classification selections and browsing preferences | Delete automatically |

Immutable event-history rows must not be deleted, rewritten, or anonymized by
ordinary user deletion.

### 4.4 User lifecycle and active sessions

Deactivating or suspending a user must revoke all of that user's active login
sessions in the same transaction. Reactivating or unsuspending the user must not
restore those sessions.

Deleting a user deletes every remaining login-session row belonging to that
user. This is acceptable because login sessions are operational authentication
state and the durable authentication history is recorded separately as defined
in Section 11.

## 5. Role deletion

### 5.1 Conditions that block deletion

A role must not be deleted when any of the following is true:

1. It is the reserved `system-administrator` role.
2. One or more other roles identify it as their supervising role.
3. An aggregation, record, or other governed entity has an ACL grant referencing
   the role.
4. An authorization mapping that must be transferred or deliberately removed
   references the role.
5. Deletion would leave protected content without an effective authorized user.

The role does not need to be deactivated before deletion.

When a role supervises other roles, the administrator must explicitly assign a
replacement supervisor or explicitly remove each supervisory relationship
before deleting the role. Deletion must not silently set subordinate roles'
`supervisor_role_id` to null.

When an ACL or another consequential authorization grant references the role,
the administrator must explicitly transfer or remove that grant. The deletion
operation must not silently erase it.

### 5.2 Data removed with a role

User-role assignments for the deleted role are ownership relationships and must
be deleted automatically in the same transaction, including expired and future
assignments, provided all access-continuity checks pass.

Immutable role and assignment event history must remain.

## 6. Organizational-unit deletion

### 6.1 Conditions that block deletion

An organizational unit must not be deleted when any of the following is true:

1. It is the reserved `SYSTEM` organizational unit.
2. It has one or more child organizational units.
3. It owns one or more roles.

The organizational unit does not need to be deactivated before deletion.

The administrator must move or explicitly delete child units and roles before
deleting their owning unit. Permanent deletion must not recursively delete an
organizational subtree or its roles.

Immutable organizational-unit event history must remain.

## 7. Pure role-based access control

Aggregation and record authorization must be granted to roles, never directly
to users. A user's effective access is derived from their current effective role
assignments.

The authorization data model and APIs must reject direct user-specific ACLs.
This rule applies to allow grants, deny grants, ownership grants, emergency
access grants, and any equivalent access-control relationship.

The authorization subsystem must provide a controlled recovery mechanism so an
authorization configuration error cannot make governed content permanently
unrecoverable. The authorization specification will define whether this is a
reserved recovery role, a break-glass workflow, or another audited mechanism.
That mechanism does not remove the access-continuity checks in this
specification.

## 8. Removal of `user_role_assignments.assigned_by`

### 8.1 Required change

The `assigned_by` column must be removed from `user_role_assignments`. This is an
essential corrective change, not an optional cleanup.

It must also be removed from:

- database indexes and foreign keys;
- API create, update, and response schemas;
- allowed search fields;
- frontend models and forms, if present;
- seed scripts and seed-data mappings;
- tests and fixtures; and
- user-management and API documentation.

### 8.2 Reason for removal

`assigned_by` duplicates the authoritative actor recorded by the assignment's
immutable `CREATE` event. Event history already records:

- the assignment entity ID;
- the authenticated actor's user ID;
- snapshots of the actor's name and email;
- the event timestamp;
- the complete created assignment;
- the change reason, source, request, and correlation metadata.

The column is not used for authorization, validity calculation, workflow, or a
current UI feature. It also creates an integrity defect because the current API
accepts it from the request payload, allowing a client to claim that another
user made the assignment. Audit actor identity is instead obtained from the
authenticated server-side principal and cannot be supplied by the client.

Removing the column also eliminates an unnecessary restrictive reference that
would otherwise complicate user deletion.

### 8.3 Fields that remain

The following assignment fields remain because they represent domain state:

- `user_id`: the user receiving the role;
- `role_id`: the assigned role;
- `date_assigned`: when the assignment was established;
- `valid_from`: when the assignment becomes effective; and
- `valid_until`: when its effective period ends, when applicable.

If a later workflow must record a formal approver who differs from the technical
operator, that is a distinct business concept. It must be specified explicitly
with approval state, approver identity, approval time, and supporting evidence.
The removed `assigned_by` column must not be reused for that purpose.

## 9. REST API

The API must use these operations consistently:

```text
POST   /api/v1/users/{id}/activate
POST   /api/v1/users/{id}/deactivate
POST   /api/v1/users/{id}/suspend
POST   /api/v1/users/{id}/unsuspend
DELETE /api/v1/users/{id}

POST   /api/v1/roles/{id}/activate
POST   /api/v1/roles/{id}/deactivate
DELETE /api/v1/roles/{id}

POST   /api/v1/org-units/{id}/activate
POST   /api/v1/org-units/{id}/deactivate
DELETE /api/v1/org-units/{id}
```

The existing behavior in which `DELETE` acts as a compatibility alias for
deactivation must be removed. This is a greenfield project with no production
deployment requiring that compatibility behavior.

Generic user updates must not accept `status`, `date_deactivated`, or
`date_suspended`. Lifecycle
state may be changed only through the explicit lifecycle endpoints so session
revocation and audit behavior cannot be bypassed.

Valid user transitions are:

```text
active    --deactivate--> inactive
active    --suspend-----> suspended
suspended --unsuspend---> active
suspended --deactivate--> inactive
inactive  --activate----> active
```

Calling a lifecycle endpoint from an incompatible state returns `409 Conflict`.
Permanent deletion remains available from every state when its deletion
conditions are satisfied.

### 9.1 Concurrency and reason

Every activate, deactivate, suspend, unsuspend, and delete request must require
the current entity version through `If-Match`.

A permanent-deletion request must include a non-blank audit change reason. The
reason describes why permanent deletion is appropriate; it must not be inferred
from a confirmation label.

### 9.2 Responses

- Successful permanent deletion returns `204 No Content`.
- A missing entity returns `404 Not Found`.
- A stale or missing version follows the existing optimistic-concurrency error
  contract.
- A deletion blocked by this specification returns `409 Conflict`.

A blocked response must use a stable machine-readable structure and report all
known blockers, not only the first one. Each blocker contains a code, a clear
message, and relevant counts or identifiers. Expected codes include:

```text
self_deletion
last_system_administrator
content_access_continuity
reserved_role
supervises_roles
role_has_acl_grants
role_has_authorization_references
reserved_org_unit
org_unit_has_children
org_unit_has_roles
```

## 10. Audit behavior

Successful permanent deletion must append an immutable `DELETE` event containing
the entity's complete final before-state. Cascade operations that affect audited
domain relationships must also produce their appropriate deletion events within
the same correlation context.

Existing history must remain unchanged. In particular, deleting a user must not
remove events for actions performed by that user. Actor snapshots allow those
events to remain understandable after the live user row is gone.

An event about the deleted entity and an event caused by the deleted user are
different concepts:

- an administrator's creation or deletion of a user is history about that user;
- an operation performed by that user is history attributed to that actor.

Neither kind of event prevents permanent deletion.

## 11. Authentication and login-session integration

Login-session purpose, authentication states, suspension, credential locking,
durable authentication-event metadata, session revocation, retention, cleanup,
and `revoked_by` semantics are defined by
[Authentication and Login-Session Lifecycle](authentication-and-login-session-lifecycle.md).

For permanent user deletion, this specification requires only that:

- deleting a user removes their transient session rows in the same transaction;
- the required final session audit information is written before those rows are
  removed and uses the deletion correlation context;
- prior authentication events remain unchanged;
- deleting a user who revoked another user's session may set the live
  `revoked_by` reference to null; and
- the immutable revocation event continues to identify the revoker through its
  actor snapshots.

## 12. Administrative UI

User, role, and organizational-unit interfaces must present distinct actions:

- **Activate**, when applicable;
- **Deactivate**, when applicable; and
- **Permanently delete**.

User interfaces must additionally present:

- **Suspend** for an active user; and
- **Unsuspend** for a suspended user.

The user list must distinguish Active, Suspended, Inactive, and derived
Temporarily locked conditions. A credential lock is supplementary authentication
state and must not replace the user's lifecycle status.

The UI must never label deactivation as Delete.

Permanent deletion requires a confirmation dialog that:

- identifies the exact entity by name and stable code or email where available;
- states that the live entity cannot be restored;
- lists data that will be deleted automatically;
- obtains a mandatory change reason;
- requires explicit confirmation; and
- submits the displayed entity version.

The server remains authoritative. The UI may preflight eligibility to provide a
better explanation, but it must handle a transactional `409 Conflict` if state
changes before deletion.

When deletion is blocked, the UI must show actionable explanations rather than
a generic foreign-key or conflict error. It must not offer a force-delete or
recursive-delete override.

## 13. Smoke-test and pre-production reset

Ordinary entity deletion is not an environment-reset mechanism.

Before operational production handover, an environment containing only setup or
smoke-test data may be reset using a separate, deliberately destructive database
reset procedure. That procedure recreates the database from the canonical
schema and required production seeds and may therefore remove the pre-handover
audit history.

After operational production use begins, application deletion removes live
test entities according to this specification but retains the immutable audit
trail recording their creation and removal.

## 14. Database changes

Implementation requires a migration that, at minimum:

1. removes `user_role_assignments.assigned_by` and its index;
2. changes `user_role_assignments.user_id` to `ON DELETE CASCADE`;
3. changes `user_role_assignments.role_id` to `ON DELETE CASCADE`;
4. changes record-draft ownership to `ON DELETE CASCADE`;
5. preserves credential, session, favourite, and classification-preference
   cascades;
6. preserves `login_sessions.revoked_by` as `ON DELETE SET NULL`;
7. keeps `roles.supervisor_role_id` restrictive so supervised roles block
   deletion;
8. keeps role ownership of organizational units restrictive; and
9. keeps organizational-unit parent relationships restrictive.

The implementation must also provide the indexes and bounded cleanup query
needed to remove expired and revoked login sessions after the configured
retention period.

The canonical schema must be updated with the same final constraints.

## 15. Acceptance criteria

The feature is acceptable only when automated tests demonstrate all of the
following:

- active users, roles, and eligible organizational units can be deleted without
  prior deactivation;
- the three `DELETE` endpoints perform permanent deletion, not deactivation;
- self-deletion and deletion of the last effective system administrator are
  rejected;
- deleting a user cascades assignments, drafts, credentials, sessions,
  favourites, and preferences as specified;
- user audit participation does not block deletion and historical actor
  snapshots remain readable afterward;
- deleting a role cascades its assignments when no blocker exists;
- a supervising role cannot be deleted until subordinate relationships are
  reassigned or removed;
- a role referenced by an ACL or consequential authorization mapping cannot be
  deleted;
- deletion is rejected when it would leave governed content without an
  effective authorized user;
- the reserved role and organizational unit cannot be deleted;
- an organizational unit with children or roles cannot be deleted;
- `assigned_by` is absent from the database, API schemas, searches, UI, seeds,
  and documentation;
- deletion conflicts return structured, actionable reasons;
- optimistic-concurrency and mandatory-reason requirements are enforced;
- deleting a user records the required session-removal summary before cascading
  their transient session rows;
- deleting a revoking user may clear a session's live `revoked_by` reference
  without losing the immutable actor snapshot; and
- all database-backed tests run against a newly created disposable PostgreSQL
  database that is removed cleanly after the test run.

## 16. Authorization decisions resolved before implementation

The following details were resolved by the approved Security and Authorization
Subsystem specification before this deletion feature was implemented:

- the complete pure-RBAC privilege, permission, and live-inheritance ACL schema;
- continuity through effective authorization administrators and highest-
  clearance human information-governance custodians;
- a separately reviewed break-glass design, which remains unimplemented and is
  not a deletion override; and
- uncached transactional continuity analysis, backed by operational monitoring
  and reconciliation.

Those decisions must preserve the pure-RBAC and no-inaccessible-content
requirements established by this specification.
