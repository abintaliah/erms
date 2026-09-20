# Security and authorization implementation — Phase 3

Status: implemented and verified

This phase establishes the reusable authorization decision engine and its immutable request context. It intentionally does not enforce the new policy on existing API routes; global administrative route enforcement begins in Phase 4, while persistent resource ACLs and their inheritance model begin in Phase 5.

## Request-scoped policy context

Each authenticated API request now receives a policy context materialized once from current database state. The frozen snapshot contains:

- the user and session authentication state;
- the evaluation timestamp;
- every effective role, its one assigned profile, privileges and security clearance;
- the role's information-governance flag; and
- excluded role assignments with stable reasons such as inactive role, inactive organizational ancestry, not-yet-started assignment, or expired assignment.

The snapshot is attached to the request independently of the older principal object. A policy change made after the snapshot is loaded does not alter decisions already being evaluated in that request; a later request receives a newly materialized context. This prevents one operation from observing a mixture of old and new authorization state.

## Decision engine

The engine evaluates the approved gates in order:

1. authentication and account/session state;
2. presence of at least one effective role;
3. operation and business-integrity constraints supplied by the caller;
4. the required global privilege;
5. maximum effective security clearance across all effective roles; and
6. every required resource permission in the supplied effective ACL.

The role supplying a privilege, the role supplying maximum clearance and roles supplying individual ACL permissions may differ. A lower-clearance role never vetoes a higher effective clearance. Multi-resource operations compare clearance against the highest involved resource level, and operations requiring multiple permissions must obtain all of them.

The engine has no role-name or System Administrator bypass. Information-governance roles bypass only a failed ACL gate, only after all preceding gates pass, and only when the governance role itself—not another role—has sufficient clearance for every involved resource.

## ACL boundary for Phase 5

The decision engine accepts an immutable, already-resolved effective ACL containing Everyone grants and per-role grants. It does not yet read ACL rows because those tables and live inheritance rules belong to Phase 5. This boundary allows the complete authorization semantics to be tested before coupling them to ACL storage and ensures routes will not grow independent authorization implementations.

## Stable decisions and explanations

Every decision returns:

- a stable allow or denial code;
- the ordered result of each evaluated gate;
- effective role IDs;
- privilege-contributing role IDs;
- maximum-clearance-contributing role IDs;
- ACL contributors for each required permission;
- permissions contributed by Everyone;
- qualified governance-bypass role IDs; and
- effective and required clearance values.

The stable denial codes distinguish missing authentication, revoked or expired sessions, inactive or suspended users, locked credentials, absence of effective roles, integrity rejection, insufficient global privilege, insufficient clearance and insufficient resource permission. These are internal policy results. Later route phases remain responsible for translating them into the approved non-disclosing `401`, `403`, `404` or `409` response.

## Verification

The Phase 3 gate was run against a newly created disposable PostgreSQL database, which the test harness removed afterward. It verifies:

- inactive and suspended users, locked credentials, revoked and expired sessions;
- inactive roles and inactive organizational ancestry;
- future and expired assignments, including the exclusive `valid_until` boundary;
- the mandatory single-profile role representation;
- no-role users;
- union-based privilege, clearance and ACL contribution across different roles;
- maximum-clearance behavior with lower-clearance roles present;
- clearance across multiple involved resources;
- Everyone grants and all-required-permissions behavior;
- the information-governance ACL bypass and its own-clearance requirement;
- independent operation/integrity rejection;
- absence of a role-name/System Administrator bypass;
- immutable request behavior when policy state changes; and
- database materialization of role profile privileges and role effectiveness.

The disposable database/API suite passed 125 tests. The Web UI suite passed 60 tests.
