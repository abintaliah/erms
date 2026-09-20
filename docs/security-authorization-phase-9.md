# Security and authorization implementation — Phase 9

Status: implemented and verified

Phase 9 formalizes the information-governance ACL bypass and makes its operation inspectable and auditable. The bypass remains deliberately narrow: it substitutes only for a missing resource ACL permission when one effective governance role is itself cleared for the resource.

## Governance bypass boundary

The existing PostgreSQL policy functions and the in-process policy engine now operate as one documented contract:

- authentication, active account state, current assignment, active role, and active organization ancestry remain mandatory;
- the operation's exact global privilege remains mandatory;
- maximum effective clearance remains the ordinary security gate;
- when the ACL gate fails, at least one effective role must be both information-governance-marked and independently cleared to the resource level;
- clearance from a separate non-governance role cannot qualify a lower-clearance governance role;
- special downgrade privileges, reasons, optimistic versions, hierarchy rules, closure, and all other integrity controls remain mandatory; and
- the Phase 8 record-placement correction remains the only closure exception.

The reserved System Administrator role receives no implicit content or governance bypass. Administrative APIs still require their own unrelated privileges.

## Governance-basis events

Successful protected operations that needed the ACL bypass append an immutable `INFORMATION_GOVERNANCE_BYPASS_USED` event. Its metadata identifies:

- `authorization_basis: information_governance`;
- the required global privilege;
- the missing ACL permission replaced by the bypass; and
- snapshots of every qualifying governance role, including role, profile, security-level code, and level number.

Resource-detail views, component preview/download operations, and resource mutations use this evidence path. Events are written in the operation transaction, so a failed or rolled-back mutation does not leave a misleading successful-bypass event.

## Access explanations

`POST /api/v1/authorization/explain` evaluates an aggregation or record operation without impersonating the selected user and without changing application state.

For the authenticated caller, any visible resource can be explained without an additional diagnostic privilege. The response contains:

- each decision gate and its pass/fail code;
- effective and excluded roles, including exclusion reasons;
- each role's profile, privileges, clearance, and governance flag;
- privilege, clearance, ACL, Everyone, and governance contributors;
- the effective ACL source and source resource;
- effective grants and any dormant local override grants; and
- the final decision code.

Explaining another user additionally requires `authorization.explain`. The examiner must independently be able to view the resource and pass its clearance boundary. The subject may be denied or unable to view it; that denial is the purpose of the diagnostic. The server loads the subject's live account, role, assignment, profile, clearance, and ACL state without creating a session.

Every other-user diagnostic appends `ACCESS_EXPLANATION_VIEWED`, recording examiner, selected user, resource, requested operation, outcome, and decision code. Credentials, sessions, tokens, and component bytes are never returned.

## Administrative custody visibility

`GET /api/v1/authorization/governance-custody` requires `authorization.administer` and returns:

- the security-level catalogue;
- all information-governance roles with profile, clearance, direct/effective status, and current-assignee count;
- each assignment with user status, validity interval, role effectiveness, and calculated current effectiveness;
- the number of effective highest-clearance universal custodians whose profiles contain the complete custody privilege set; and
- a critical zero-custodian or advisory single-custodian warning when applicable.

This is visibility and warning functionality. It does not replace the already implemented transactional last-custodian protections, and it does not enforce the approved policy recommendation that production should maintain two assignees.

## Policy inventory

The generated operation-policy registry is advanced to Phase 9. It records enforcement for governance diagnostics, resource capabilities, and the aggregation/record detail surfaces where governance-basis evidence is produced.

## Verification

The complete database/API suite ran against a newly created disposable PostgreSQL database and passed all **175 tests**. The harness disposed of the database cleanly afterward. Phase 9 tests verify that:

- a qualified governance role bypasses only a missing ACL and produces role-snapshot evidence;
- a high-clearance non-governance role cannot lend clearance to a low-clearance governance role;
- governance status does not replace a missing global privilege;
- governance status grants no unrelated identity or system administration;
- governance explanations and actual operations continue to enforce closed-branch integrity;
- self explanations disclose the correct governance basis;
- other-user explanations require examiner-side access and are audited; and
- custody diagnostics expose assignments and resilience warnings.

The Web UI regression suite passed all **65 tests**. Python compilation and diff validation also passed.

## Deliberately deferred

Phase 10 adds the complete authorization-aware user interface: administration pages, ACL editors, access-explanation panels, governance-custody presentation, capability-aware actions, disabled-state guidance, and browser-level persona tests. Phase 9 supplies the authoritative APIs and audit contract for that work.
