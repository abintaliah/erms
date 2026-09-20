# Security and authorization implementation — Phase 10

Status: implemented and verified

Phase 10 makes the Web UI reflect the authorization rules enforced by the API and database. UI visibility and disabled states are usability aids only: every operation continues to be re-authorized by the server when clicked, so a policy change after rendering cannot be bypassed with a stale page.

## Administration surfaces

The System Administration navigation now exposes the complete Phase 10 catalogue:

- Security Levels, including ordered level numbers and disposition-prevention flags;
- Profiles and their privilege editor with impact preview;
- the read-only global Privileges catalogue;
- the read-only aggregation and record Permissions catalogue; and
- Governance Custody, visible only with `authorization.administer`.

Roles display and edit their mandatory profile and security clearance. Information-governance roles carry field-level guidance that they bypass resource ACLs only; global privilege, the governance role's own clearance, effective assignment, active ancestry, and resource-integrity rules remain mandatory.

The Governance Custody page presents highest-clearance custodian count, governance roles, effective assignment count, and zero/single-custodian warnings. The two-person production recommendation remains policy guidance and is not a deployment blocker.

## Resource access and explanations

Aggregation and record detail pages offer **Why this access?**. The explanation dialog supports every defined resource operation and displays:

- the final allowed/denied outcome and stable decision code;
- assignment, privilege, clearance, ACL, and integrity gates;
- effective versus required clearance;
- effective ACL source;
- Everyone, privilege, clearance, ACL, and governance contributors; and
- retained dormant overrides that do not currently affect the decision.

Users with `authorization.explain` may select another person from a minimal identity list containing only id, name, email, and status. These other-user explanations remain audited as specified in Phase 9. The selector endpoint does not disclose credentials, sessions, role secrets, or protected resource data.

## ACL and inheritance presentation

The ACL editor identifies the effective source before editing. It explains that inherited ACLs are live, not snapshots, and that a local override remains dormant while inheritance is enabled. The separate child-aggregation and child-record default editors retain their distinct semantics:

- child-aggregation defaults may mirror the effective resource ACL live or use a custom template;
- custom child-aggregation templates remain dormant when mirroring is selected; and
- child-record defaults are independently managed and inherited live by records that have not opted out.

The Everyone principal is visually distinct. Permission selections automatically close over prerequisite permissions before save. Changes remain atomic, versioned, reason-bearing, impact-previewed where applicable, and validated again by the API and deferred database constraints.

## Capability-aware controls

Resource detail actions consume the authoritative capability endpoints. Digital-component preview, download, add, remove, and reorder controls are evaluated independently. Unavailable controls are disabled or replaced with concise guidance rather than implying that all component access is one permission.

Aggregation and record mutation buttons continue to be driven by current server capabilities. Regardless of their rendered state, the subsequent API request rechecks the user's live assignments, roles, profile privileges, clearance, ACL, governance qualification, resource version, and resource state. The existing stale-policy API tests prove that controls rendered under an earlier policy cannot bypass a later revocation.

Dialogs use labelled controls, explicit close labels, keyboard-operable native buttons/selects/switches, and textual status alongside color and icons. Authorization outcomes therefore do not depend on color alone.

## Disposable test isolation

The disposable PostgreSQL harness now mounts `/var/lib/postgresql/data` as a per-run tmpfs. This prevents the official PostgreSQL image from leaving anonymous data volumes after `docker run --rm`, guarantees test data disappears with the container, and avoids gradual Docker storage exhaustion.

## Verification

The complete database/API suite ran against a newly created tmpfs-backed disposable PostgreSQL database and passed all **176 tests**. The container and its database were removed afterward. Coverage includes:

- self and other-user explanations;
- least-disclosure and privilege enforcement for the explanation user picker;
- governance custody and warnings;
- stale-policy render-to-operation behavior at the authoritative API boundary;
- privilege, clearance, ACL, governance, closure, version, and dependency enforcement; and
- automatic policy-inventory drift detection for the new API and UI actions.

The Web UI regression suite passed all **68 tests**, including authorization operation catalogues, effective ACL source labels, denial identification, navigation privileges, permission dependencies, and API-client routing. Python compilation and whitespace validation also passed.

## Deliberately deferred

Phase 11 adds audit, monitoring, performance, and recovery hardening: security-event dashboards, denial monitoring, workload and query-budget validation, reconciliation tooling, backup/restore exercises, and operational runbooks.
