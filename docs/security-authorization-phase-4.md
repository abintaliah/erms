# Security and authorization implementation — Phase 4

Status: implemented and verified

This phase enforces global privileges on non-resource administration routes. It does not yet apply resource ACLs or governed resource visibility to aggregations, records, or digital components; those controls begin in Phases 5 and 6.

## API enforcement

The API now uses the shared Phase 3 authorization engine and immutable request policy context to protect administration operations for:

- users;
- login sessions;
- organizational units and roles;
- authorization profiles and privileges;
- security levels;
- classification schemes and classifications; and
- the audit trail and entity history.

Each protected operation declares one exact global privilege. Authorization is evaluated from effective role assignments and their profiles rather than from role names. Inactive roles, inactive organizational ancestry, assignments outside their validity period, and stale, revoked, or expired sessions therefore cannot authorize an operation.

Denied requests return a stable, non-disclosing `403` response. The underlying policy decision code remains available to the immutable audit trail without exposing sensitive authorization structure in the client response.

## Bootstrap-safe administration

Runtime authorization has no special System Administrator role-name bypass. The bootstrap role is explicitly assigned the seeded `SYS_ADMIN` profile, whose privileges provide the required administrative access through the same policy mechanism as every other role.

The role code remains a provisioning identifier only. Creating another role with that code or name cannot bypass authorization, and removing its profile privileges removes its access. This confines bootstrap behavior to initial provisioning instead of creating a permanent hidden authorization path.

## Session administration and self-service

Listing sessions, revoking sessions in bulk, and issuing temporary passwords require `identity.sessions.administer`. A user may still revoke their own individual session as an authenticated self-service operation. Revoking another user's session invokes the administrative privilege check.

Authenticated principal responses now include the union of global privileges contributed by the caller's effective roles. This capability set drives presentation decisions in the Web UI; it does not replace server-side enforcement.

## Audit behavior

Every global-privilege denial produces an `AUTHORIZATION_DENIED` event using a separate database connection so the event is not lost with a failed business transaction. Its safe metadata records only:

- the required privilege;
- the stable policy decision code;
- the HTTP method; and
- the request path.

Credentials, tokens, request bodies, resource snapshots, and other secrets are not copied into denial metadata.

## Web UI capability handling

Administrative navigation destinations are shown only when the principal has their corresponding privilege. This covers classification administration, organization and role administration, user administration, audit viewing, session administration, security-level administration, and profile/privilege administration.

Dashboard administration counts and requests are likewise limited to resources the current principal is authorized to administer. This avoids predictable unauthorized calls while preserving the API as the authoritative security boundary.

## Reference visibility is not administration

Administrative privileges control changing or administering a catalogue or
organization entity. They do not control whether a signed-in person can see a
security-level label, classification path, organization-unit name, role name,
user name, or profile name when that value is needed to understand an
aggregation, record, selector, or permitted management screen. Those
read-only reference endpoints are available to authenticated users; their
lifecycle, assignment, privilege-membership, deletion, and other management
operations remain protected by their respective administrative privileges.

The Dashboard's personal recent-work sections use a separate self-only
endpoint. It returns only the signed-in person's own create/update references,
only where the resource remains currently visible to that person. It is not an
Audit Trail query and does not require `audit.view`, which remains exclusively
for system-wide audit history and administrative investigation.

The UI no longer treats possession of a specially named role as an administrative capability.

## Policy inventory

The generated operation-policy registry marks all Phase 4 global-administration operations as enforced and records their required privilege. The registry currently contains 155 API operations, of which 90 are protected by Phase 4 global-privilege dependencies. A structural test verifies that every one of those 90 operations has the corresponding FastAPI dependency, preventing a newly omitted or accidentally unprotected route from passing the phase gate.

## Verification

The complete database and API gate was run against a newly created disposable PostgreSQL database. The harness disposed of that database after the run. It verifies:

- authorized access for every global administrative privilege area;
- denial when the required privilege is absent;
- denial through inactive roles and expired assignments;
- rejection of revoked or otherwise stale sessions;
- safe and immutable authorization-denial audit events;
- absence of a System Administrator role-name bypass;
- bootstrap assignment of the explicit `SYS_ADMIN` profile;
- principal capability materialization; and
- exact dependency coverage for every Phase 4 route in the generated policy registry.

The disposable database/API suite passed 145 tests. The Web UI suite passed 62 tests. Static diff validation also passed.

## Deliberately deferred

Phase 4 does not create resource ACL storage, resolve live inherited ACLs, filter resource discovery, or enforce aggregation, record, and digital-component operations. Phase 5 introduces the approved ACL schema and inheritance model; Phase 6 applies governed discovery and resource-operation enforcement.
