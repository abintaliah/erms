# Security and Authorization Subsystem — Technical Specification

**Status:** Draft for review  
**Project:** ERMS / wathiq  
**Prepared:** 19 September 2026  
**Revision:** 0.1

## 1. Purpose

This specification defines the security-classification and authorization model
for wathiq. It covers:

- security levels for roles, aggregations, and records;
- global privileges collected into reusable profiles;
- role-only access-control lists for aggregations and records;
- effective-role and assignment rules;
- information-governance access;
- authorization enforcement in the database, API, and UI;
- audit, cache, information-disclosure, and recovery requirements; and
- a phased implementation plan with a mandatory verification gate after every
  phase.

This is a pure role-based access-control design. Users acquire authorization
only through currently effective role assignments. Users and organizational
units never receive profiles, privileges, security clearances, or resource ACL
grants directly.

Authentication establishes who the caller is. Authorization determines what
that authenticated caller may do. The two subsystems remain separate.

## 2. Design principles

1. **Default deny.** An operation is denied unless every applicable gate grants
   it.
2. **Roles are the only grant-bearing principals.** There are no direct user
   grants and no organizational-unit grants.
3. **Allow grants only.** This version has no deny ACL and no conflict-resolution
   precedence.
4. **Profiles grant capabilities; ACLs grant scope.** A profile says what a role
   may do in principle. An ACL says where a role may do it.
5. **Security clearance is an independent mandatory gate.** Neither a privilege
   nor an ACL grant can reveal content above the caller's effective clearance.
6. **Lifecycle and structural integrity remain authoritative.** Authorization
   never overrides aggregation closure, optimistic concurrency, validation,
   retention, or database integrity unless a separately specified, audited
   override explicitly says so.
7. **No existence leakage.** Lists, searches, counts, favourites, trees,
   breadcrumbs, relationship summaries, and error messages must not reveal an
   inaccessible aggregation, record, or component.
8. **Server-side enforcement is authoritative.** Hiding or disabling a UI
   control is useful guidance, not security enforcement.
9. **Decisions are explainable and auditable.** The policy engine produces a
   stable reason code for internal use, while public responses avoid disclosing
   protected facts.
10. **Authorization changes are immutable audit events.** Profile, privilege,
    clearance, governance-role, and ACL changes must be attributable and
    reconstructable.

## 3. Terminology

### 3.1 Principal

The authenticated user for whom an authorization decision is being made.

### 3.2 Effective role

A role contributes authorization to a user only when all of the following are
true at the time of the request:

- the user account is `active`;
- the user-role assignment has reached its inclusive `valid_from` time;
- the assignment has no `valid_until`, or server time is earlier than that
  exclusive time;
- the role is active; and
- the role's owning organizational unit and every ancestor organizational unit
  are active.

An inactive or suspended user cannot authenticate. An inactive role, an
inactive organizational ancestor, a future assignment, and an expired
assignment contribute no authorization. They do not change the user's own
account status.

### 3.3 Global privilege

A stable, system-wide capability code describing an operation a role may
perform in principle. For resource operations it is necessary but not normally
sufficient: security clearance and an ACL permission are also required.

### 3.4 Profile

A named, reusable set of global privileges. Profiles are assigned only to
roles. A role may have multiple profiles, and its effective privileges are the
union of the privileges in all active assigned profiles.

### 3.5 Resource permission

An allow grant connecting one role, one permission code, and an aggregation or
record scope. It determines where the role may exercise a global capability.

### 3.6 Security level and effective clearance

A security level is an ordered classification such as `R — Restricted — 50` or
`TS — Top Secret — 100`. A role has exactly one security level. A user's
effective clearance number is the greatest level number among that user's
effective roles.

A resource is within clearance when:

```text
effective_user_clearance_number >= resource_security_level_number
```

Lower-clearance roles do not reduce or veto the clearance supplied by another
effective role. The phrase “if any role fails the security level check, deny”
must therefore not be implemented: it would make adding a harmless
lower-clearance role unexpectedly remove access. The correct failure condition
is **no effective role supplies sufficient clearance**.

### 3.7 Information-governance role

An effective role marked as an information-governance role may bypass a
resource ACL for governed content, subject to the restrictions in Section 12.
It is not a system-administrator role and is not a universal authorization
bypass.

## 4. Security levels

### 4.1 Data and ordering

Every security level contains:

| Field | Requirement |
| --- | --- |
| `id` | Internal immutable identifier |
| `code` | Required, unique, case-insensitive stable code |
| `name` | Required, unique human-readable name |
| `level_number` | Required, unique non-negative integer establishing a total order |
| `prevents_disposition` | Required Boolean; defaults to `false` |
| `version` | Optimistic-concurrency version |
| timestamps | Creation and last-update timestamps |

Higher numbers represent more restrictive information and greater clearance.
Code and level number are not interchangeable: integrations store the stable
code while decisions use the number.

At least one baseline level must exist. The canonical initial catalogue should
be supplied by a seed, not hard-coded into application logic. A proposed test
catalogue is:

| Code | Name | Number | Prevents disposition |
| --- | --- | ---: | --- |
| `U` | Unclassified | 0 | No |
| `I` | Internal | 25 | No |
| `R` | Restricted | 50 | No |
| `C` | Confidential | 75 | No |
| `TS` | Top Secret | 100 | Yes |

The business must approve the production catalogue before its seed is treated
as canonical.

`prevents_disposition` is policy metadata for the future disposition subsystem.
In this subsystem it is stored, administered, displayed, audited, and exposed,
but it does not itself change ordinary read or write authorization.

### 4.2 Assignments and defaults

- Every role has one non-null `security_level_id`.
- Every aggregation has one non-null `security_level_id`.
- Every record has one non-null `security_level_id`.
- Existing rows are migrated to the approved baseline level.
- A new child aggregation defaults to its parent's security level.
- A new record defaults to its containing aggregation's security level.
- A new root aggregation requires an explicit level or receives the configured
  baseline level.

### 4.3 Hierarchical monotonicity

A descendant must not be less restrictive than its parent:

```text
child aggregation level >= parent aggregation level
record level            >= containing aggregation level
```

This invariant prevents a user from seeing a child while being unable to see
the path that contains it. Moving or reclassifying a branch or record must
validate the complete affected subtree before committing. Raising a parent's
level is rejected if it would create an inconsistent descendant only when the
implementation cannot atomically raise those descendants; bulk propagation
must be an explicit, previewed, audited operation.

Lowering a resource's security level is more sensitive than raising it because
it expands the audience. It requires the dedicated global privilege
`security.resource.downgrade`, the resource's `security_level.change`
permission, a non-blank reason, and an immutable domain event.

A caller may not assign a resource or role a security level higher than the
caller's own effective clearance, except through a separately specified
break-glass procedure. This prevents administrators from creating information
that neither they nor any operational custodian can subsequently inspect.

### 4.4 Catalogue changes and deletion

Changing a level number immediately changes access for every referencing role
and resource. Changing a role's assigned level can likewise add or remove
clearance for every currently assigned user. Both operations therefore require
previewing affected counts, optimistic concurrency, a reason, explicit
confirmation, access-continuity re-evaluation, and immediate policy-cache
invalidation.

A referenced security level cannot be deleted. Deletion is allowed only when no
role, aggregation, or record references it and it is not the configured
baseline. Merging or replacing levels must be a separate bulk migration, not a
cascade delete.

## 5. Privileges and profiles

### 5.1 Privilege catalogue

Privilege codes are immutable lowercase dotted identifiers. Display names and
descriptions may change. Privileges are seeded system definitions, not
free-form administrator input.

The initial catalogue is:

#### Platform and administration

| Code | Purpose |
| --- | --- |
| `authorization.administer` | Create and maintain profiles, profile privileges, role-profile assignments, governance-role flags, and resource ACLs |
| `security_levels.administer` | Create and maintain the security-level catalogue |
| `identity.users.administer` | Create, edit, activate, deactivate, suspend, unsuspend, issue temporary passwords for, and eventually delete users |
| `identity.sessions.administer` | Inspect and revoke other users' login sessions |
| `organization.administer` | Create, edit, activate, deactivate, and eventually delete organizational units and roles; maintain role supervision and assignments |
| `classifications.administer` | Create, edit, publish, unpublish, activate, deactivate, migrate, and delete classification schemes and classifications |
| `audit.view` | View the system-wide audit trail and entity histories |

`identity.users.administer` and `organization.administer` are deliberately
separate. The old example `ADMINISTER_USERS` is too broad if it also silently
controls roles and organizational units.

#### Aggregations

| Code | Purpose |
| --- | --- |
| `aggregation.view` | Discover and view aggregation metadata |
| `aggregation.create_root` | Create a root aggregation |
| `aggregation.create_child` | Create a child aggregation, subject to the parent ACL |
| `aggregation.modify` | Change aggregation metadata |
| `aggregation.move` | Move an aggregation branch |
| `aggregation.reclassify` | Change its governing classification |
| `aggregation.close` | Close an aggregation |
| `aggregation.reopen` | Reopen a directly closed aggregation |
| `aggregation.delete` | Permanently delete an otherwise eligible aggregation |
| `aggregation.security.change` | Raise or otherwise change its security level; lowering also requires `security.resource.downgrade` |
| `aggregation.acl.manage` | Maintain aggregation-scoped ACL grants |

#### Records and digital components

| Code | Purpose |
| --- | --- |
| `record.view` | Discover and view record metadata |
| `record.create` | Commit a new record into an aggregation, subject to the aggregation ACL |
| `record.modify` | Change record metadata |
| `record.move` | Move a record to another aggregation |
| `record.delete` | Permanently delete an otherwise eligible record |
| `record.security.change` | Raise or otherwise change its security level; lowering also requires `security.resource.downgrade` |
| `record.acl.manage` | Maintain direct record ACL grants |
| `record.component.view` | Render or preview component content |
| `record.component.download` | Download original component content |
| `record.component.add` | Add a new committed component |
| `record.component.replace` | Atomically replace the content of an existing component |
| `record.component.remove` | Remove a committed component |
| `record.component.reorder` | Change component order |
| `record.component.share` | Use a future controlled external/internal sharing workflow |
| `record.component.print` | Use a future controlled printing workflow |

#### Exceptional operations

| Code | Purpose |
| --- | --- |
| `security.resource.downgrade` | Lower an aggregation or record security level |
| `closure.override` | Future explicit override of the closed-branch mutation freeze; not implemented merely by adding the code |
| `authorization.recovery` | Use a future audited break-glass recovery workflow |

Reserved future privileges grant nothing until the corresponding workflow is
implemented. They must not become generic Boolean bypasses.

### 5.2 Profile structure and assignment

Each profile contains a stable code, name, description, lifecycle status,
version, and a set of privileges. An inactive profile contributes no
privileges, but its role assignments remain so it can be safely reactivated.

Roles may receive any number of profiles. Users and organizational units cannot
receive profiles. The database and API must reject such assignments rather
than merely omitting them from the UI.

Changing a profile affects every role using it. The UI must show the number of
affected roles and effective users before saving a privilege-set change.

Profiles must not contain resource ACL permissions. A profile grants capability
everywhere in principle; resource ACLs restrict the locations where that
capability can be exercised.

## 6. Resource permission catalogue

Permission codes are also stable lowercase dotted identifiers. They are
separate definitions from global privileges even when their names are similar.
This deliberate two-key model answers two different questions:

```text
Global privilege: may this role perform this kind of action at all?
ACL permission:   may this role perform it on this resource or inherited scope?
```

### 6.1 Aggregation permissions

| Permission | Applies to |
| --- | --- |
| `aggregation.view` | View/discover aggregation metadata and its permitted summary counts |
| `aggregation.modify_metadata` | Edit ordinary aggregation metadata |
| `aggregation.delete` | Delete an eligible aggregation |
| `aggregation.close` | Close the aggregation |
| `aggregation.reopen` | Reopen a directly closed aggregation |
| `aggregation.add_child` | Create a direct child aggregation |
| `aggregation.add_record` | Commit a record directly into the aggregation |
| `aggregation.move` | Move this aggregation as a source |
| `aggregation.receive_child` | Accept an aggregation moved beneath it |
| `aggregation.reclassify` | Change the governing classification |
| `aggregation.security_level.change` | Change the aggregation security level |
| `aggregation.acl.manage` | Maintain this aggregation's ACL |
| `aggregation.history.view` | View its entity history |

Moving an aggregation requires `aggregation.move` on the source and
`aggregation.receive_child` on the destination, plus the matching global
privilege and clearance for both. This prevents a user with control over only
one side from moving information across boundaries.

### 6.2 Record permissions

| Permission | Applies to |
| --- | --- |
| `record.view` | View/discover record metadata |
| `record.modify_metadata` | Edit ordinary record metadata |
| `record.delete` | Delete an eligible record |
| `record.move` | Move the record as a source |
| `record.receive` | Accept a moved record into an aggregation scope |
| `record.security_level.change` | Change the record security level |
| `record.acl.manage` | Maintain the record's direct ACL |
| `record.history.view` | View its entity history |
| `record.component.list` | See component names and metadata |
| `record.component.view` | Render or preview component content |
| `record.component.download` | Retrieve original bytes |
| `record.component.add` | Add a component |
| `record.component.replace` | Replace one component's content atomically |
| `record.component.remove` | Remove a component |
| `record.component.reorder` | Change component ordering |
| `record.component.share` | Use the future controlled sharing workflow |
| `record.component.print` | Use the future controlled printing workflow |

Viewing record metadata does not automatically permit opening or downloading
its component content. `record.component.list` permits the UI to show component
metadata without disclosing bytes.

### 6.3 Replacement is an atomic operation

Replacing a component is not modeled as permission to remove followed by
permission to add. It is its own atomic operation because it:

- preserves component identity and ordering;
- provides one optimistic-concurrency boundary;
- prevents a failure between removal and addition from leaving the record
  incomplete;
- can preserve an explicit prior-content audit/version relationship; and
- supports a narrower duty in which a user may correct a component but may not
  delete it outright.

The implementation may internally write old and new content rows, but the
authorization decision and domain event are `record.component.replace`.

## 7. ACL model and inheritance

### 7.1 Grant shape

An ACL grant contains:

- the securable scope (`aggregation` or `record`) and its identifier;
- the granted role;
- the permission definition;
- inheritance flags where the scope is an aggregation;
- version and timestamps; and
- no user identifier and no deny flag.

The relational design must preserve real foreign keys. Separate aggregation
and record grant tables, or partitioned tables with enforced references, are
preferred over an unconstrained polymorphic `resource_type/resource_id` pair.

Duplicate effective grants are rejected by a unique constraint. Removing one
of several routes to the same effective permission does not remove the other
routes.

Creating a direct grant for a role whose clearance is presently below the
resource level is rejected because it is misleading and cannot be exercised.
If an existing role is subsequently lowered, its now-insufficient grants remain
stored but become dormant; the change preview must identify their count. They
contribute again only if the role later regains sufficient clearance. A grant
may exist before the role receives a matching global privilege, but it remains
inert until both gates are satisfied.

### 7.2 Aggregation scopes

An aggregation ACL can grant:

1. aggregation permissions on that aggregation;
2. aggregation permissions inherited by descendant aggregations;
3. record permissions inherited by records directly or recursively contained
   in that aggregation branch.

The ACL editor must present these as explicit scopes, not as an ambiguous
single “inherit” checkbox:

```text
This aggregation
Descendant aggregations
Records in this aggregation branch
```

Direct grants and inherited grants are additive. There is no deny entry to
cancel an inherited grant. If future requirements need exceptions, they require
a new specification rather than overloading an allow-only model.

### 7.3 Record scopes

A record ACL grants record permissions on that record only. Effective record
permissions are the union of:

- direct grants on the record; and
- applicable record permissions inherited from its containing aggregation and
  ancestors.

Moving a record changes its inherited ACL immediately. The move preview must
show whether effective access will be gained or lost and must pass the
access-continuity rule before committing.

### 7.4 Creation and orphan prevention

Creation must not produce inaccessible content:

- A root aggregation requires global `aggregation.create_root`; its initial ACL
  must include at least one effective role capable of viewing and administering
  it, unless an approved governance role already satisfies continuity.
- Creating a child requires global `aggregation.create_child`, sufficient
  clearance, and `aggregation.add_child` on the parent.
- Committing a record requires global `record.create`, sufficient clearance,
  and `aggregation.add_record` on the destination aggregation.
- New children and records dynamically inherit grants; inherited grants are not
  copied into duplicate direct rows.

Every ACL mutation is transactionally rejected if it would leave protected
content without an effective authorized user capable of discovering, viewing,
and administering access to it. This is the same access-continuity concept used
by the user/role deletion specification.

## 8. Global privilege to resource-permission mapping

Every protected operation has one explicit policy mapping. Representative
mappings are:

| Operation | Required global privilege | Required resource permission(s) |
| --- | --- | --- |
| List/open aggregation | `aggregation.view` | `aggregation.view` |
| Edit aggregation metadata | `aggregation.modify` | `aggregation.modify_metadata` |
| Add child | `aggregation.create_child` | `aggregation.add_child` on parent |
| Add/commit record | `record.create` | `aggregation.add_record` on destination |
| Move aggregation | `aggregation.move` | `aggregation.move` on source and `aggregation.receive_child` on destination |
| Close/reopen | `aggregation.close` / `aggregation.reopen` | Matching close/reopen permission |
| Delete aggregation | `aggregation.delete` | `aggregation.delete` |
| Open record metadata | `record.view` | `record.view` |
| Edit record metadata | `record.modify` | `record.modify_metadata` |
| Move record | `record.move` | `record.move` on record and `record.receive` inherited from destination aggregation |
| Delete record | `record.delete` | `record.delete` |
| List components | `record.view` | `record.view` and `record.component.list` |
| Preview component | `record.component.view` | `record.view` and `record.component.view` |
| Download component | `record.component.download` | `record.view` and `record.component.download` |
| Add/replace/remove/reorder | Matching component privilege | `record.view` and matching component permission |
| Change resource level | Matching `*.security.change` privilege | Matching `*.security_level.change` permission |
| Manage resource ACL | Matching `*.acl.manage` plus `authorization.administer` | Matching `*.acl.manage` permission |
| View entity history | `audit.view` | Matching `*.history.view` permission |

Root aggregation creation has no parent ACL, so its global privilege and
clearance/default/continuity checks are the complete resource authorization.

System-wide administration operations such as user administration and
classification administration have no aggregation or record ACL gate. They
still require an effective role with the appropriate global privilege.

## 9. Authorization decision algorithm

### 9.1 Normal resource operation

The policy engine evaluates one immutable request context and returns an allow
or deny decision with an internal reason code.

1. **Authentication gate.** Require a valid, unrevoked session for an active
   user. A suspended, inactive, locked, expired, or unauthenticated principal is
   rejected according to authentication policy.
2. **Effective-role gate.** Resolve current effective roles using account,
   assignment, role, and organizational-ancestry rules. If none exist, deny.
3. **Operation and integrity gate.** Confirm the requested operation is valid
   for the resource state. Closure, retention, parent/child restrictions,
   optimistic concurrency, and validation remain independent blockers.
4. **Global-privilege gate.** If no effective role obtains the operation's
   global privilege through an active profile, deny.
5. **Security-clearance gate.** If the greatest security level among effective
   roles is below any involved resource's level, deny. Multi-resource
   operations such as moves must pass for source, destination, and affected
   descendants.
6. **ACL gate.** If none of the user's effective roles has the required direct
   or inherited permission, deny, unless the narrowly defined
   information-governance ACL bypass applies.
7. **Allow.** Execute the operation transactionally and audit it as required.

The role supplying the global privilege, the role supplying clearance, and the
role supplying the ACL permission may differ. This is intentional union-based
RBAC and matches the rule that a user receives the union of all effective role
authorizations. The decision explanation must retain the contributing role IDs
for administrators and tests.

### 9.2 Global administrative operation

For an operation with no resource ACL, evaluate authentication, effective
roles, operation integrity, and the required global privilege. Security-level
clearance is additionally required whenever the operation reads or changes a
specific protected resource.

### 9.3 Multiple required permissions

Where an operation requires several permissions, such as moving a resource or
viewing a component, all required permissions must be present. They may be
supplied by different effective roles unless a future separation-of-duties rule
explicitly requires one role to hold the complete set.

### 9.4 Denial responses

For a known resource on which the caller lacks `view`, read, update, delete,
history, component, and ACL endpoints return the same public `404` response as
an absent resource. Search and list endpoints silently omit it. This prevents
existence probing.

Once a caller can view the resource, an attempted disallowed action may return
`403 Forbidden` with a stable, non-sensitive code such as
`insufficient_privilege`, `insufficient_clearance`, or
`insufficient_resource_permission`. Integrity conflicts remain `409 Conflict`.

Detailed contributing roles, security levels, and hidden ACL contents are
available only to authorized security administrators through an explicit
explain endpoint; they are never included in ordinary denial responses.

## 10. Additional mandatory checks

The four proposed gates are necessary but not complete. The implementation must
also account for:

- authentication and user lifecycle state;
- role, organizational ancestry, and assignment effectiveness;
- resource existence without leaking it;
- source and destination authorization for moves;
- authorization over every affected descendant in bulk operations;
- aggregation closure and future disposition holds;
- optimistic concurrency and current-state re-evaluation inside the write
  transaction;
- access continuity after ACL, role, assignment, profile, security-level, or
  lifecycle changes;
- draft ownership before a record exists;
- content-specific permissions separate from record metadata;
- audit-history confidentiality;
- background jobs and service accounts; and
- a controlled recovery path for accidental lockout.

These checks must not be collapsed into a single generic `is_admin` flag.

## 11. Record drafts

Drafts are transient pre-record workspaces and do not have a role ACL. Their
rules are:

- only the active owner may view or change an open draft;
- an administrator with a future explicitly named draft-recovery privilege may
  intervene; no implicit system-administrator shortcut is assumed;
- staged components use draft ownership, not committed-record permissions;
- draft creation requires `record.create` globally;
- commit re-evaluates the destination aggregation, security level,
  `aggregation.add_record`, closure, and all component constraints in the final
  transaction; and
- a draft that was valid when created may be denied at commit when policy has
  since changed.

Draft ownership is not a grant to the committed record. The resulting record's
effective ACL comes from the destination aggregation plus any valid direct ACL
created atomically by the commit workflow.

## 12. Information-governance roles

### 12.1 Recommended behavior

Roles receive a Boolean `is_information_governance` flag. For protected
aggregations and records, an effective governance role may bypass the **ACL
gate only** when that governance role's own security level is at least the
resource level.

It does not bypass:

- authentication or role effectiveness;
- the role's global privileges from profiles;
- security clearance;
- closure, retention, disposition, concurrency, or structural integrity;
- special lowering, external sharing, printing, ACL administration, user
  administration, classification administration, or authorization
  administration privileges; or
- the requirement for an explicit reason where one is normally required.

This means governance staff can be given a standard governance profile defining
their duties and can exercise those duties across all in-clearance content
without maintaining thousands of repetitive ACL entries.

The reserved System Administrator role is not automatically an information-
governance role and is not automatically entitled to protected business
content. Platform administration and records custody are different duties. If
one installation deliberately combines them, it must explicitly mark and
clear the appropriate role under the rules in this section.

### 12.2 Why security clearance should not be bypassed

**Recommended: do not bypass it.** Advantages:

- preserves least privilege and need-to-know classification boundaries;
- permits different governance teams for Restricted and Top Secret material;
- limits the impact of a mistakenly assigned governance flag;
- keeps security-level labels meaningful and independently auditable; and
- avoids turning an ordinary role field into a permanent break-glass account.

Allowing governance roles to bypass security levels would simplify centralized
oversight and recovery, but it would grant every governance officer access to
the organization's most sensitive content. A stolen governance account or
mistaken assignment would compromise all levels, and the security-level model
would no longer be an effective mandatory boundary for those users.

If rare cross-clearance access is operationally necessary, it should use a
separate time-limited break-glass workflow requiring a reason, strong
reauthentication, approval where feasible, prominent alerts, and immutable
events. It must not be implemented by broadening the governance flag.

### 12.3 Governance bypass scope

The bypass applies only when a resource ACL would otherwise deny an operation.
It must be visible in authorization explanations and audited on security-
sensitive operations as `authorization_basis: information_governance` with the
qualifying governance role snapshot.

A non-governance high-clearance role cannot lend its clearance to a
lower-clearance governance role for this bypass. At least one effective role
must be both governance-marked and sufficiently cleared.

## 13. Search, navigation, counts, and indirect disclosure

Authorization filtering must be part of the database query, not post-processing
after an unbounded result has been loaded.

- Search returns only viewable resources.
- Counts include only viewable resources unless an explicitly privileged
  administrative count is requested.
- Classification and aggregation trees omit inaccessible branches. The
  security monotonicity rule ensures a visible child never requires exposing an
  invisible parent.
- Breadcrumbs include only paths already authorized for the resource.
- Favourite entries disappear from the user's rendered list while inaccessible
  but may remain stored so access restoration can restore them. The favourite
  endpoint must not confirm a hidden target.
- Dashboard cards and recent-item lists use the same policy predicates.
- Relationship summaries, browse endpoints, exports, and autocomplete controls
  are authorization boundaries too.
- Digital-component identifiers, filenames, sizes, checksums, and media types
  are not exposed without `record.component.list`.
- Event history for a resource requires both `audit.view` and that resource's
  history permission and clearance. The system-wide audit trail is restricted
  and must redact protected snapshot values above the viewer's clearance.

## 14. Service accounts and background work

Service accounts are stored users and receive authorization through roles in
the same way as person accounts. They do not receive hidden privileges because
of account type.

Scheduled jobs and automated processes without a stored user must run under an
explicitly configured service principal or a narrowly scoped internal policy
identity. Every such path has a documented privilege set and event source.
Direct database ownership credentials are not an application authorization
mechanism.

## 15. Data model

The implementation must add, at minimum:

```text
security_levels
privileges
profiles
profile_privileges
role_profiles
permissions
aggregation_role_permissions
record_role_permissions
```

It must extend:

```text
roles        + security_level_id, is_information_governance
aggregations + security_level_id
records      + security_level_id
```

Recommended constraints include:

- unique case-insensitive codes;
- unique security-level numbers;
- non-null foreign keys after migration backfill;
- unique profile/privilege, role/profile, and resource/role/permission grant
  tuples;
- check constraints for inheritance applicability;
- restrictive deletion for referenced catalogue rows;
- indexes beginning with role, resource, permission, and security-level keys
  according to decision-query paths; and
- event-history triggers for every new administrative and grant table.

Security-definer database functions, if used, must have a fixed safe
`search_path`, the narrowest ownership possible, and no general client execute
grant.

## 16. API contract

### 16.1 Administrative resources

Versioned CRUD and lifecycle APIs are required for:

```text
/api/v1/security-levels
/api/v1/privileges                 (read-only catalogue)
/api/v1/profiles
/api/v1/profiles/{id}/privileges
/api/v1/roles/{id}/profiles
/api/v1/permissions                (read-only catalogue)
```

Role create/read/update adds `security_level_id` and
`is_information_governance`. Aggregation and record create/read/update add
`security_level_id` subject to field-level authorization.

### 16.2 ACL resources

ACL endpoints are nested beneath their scope:

```text
GET/POST   /api/v1/aggregations/{id}/permissions
PATCH/DELETE /api/v1/aggregations/{id}/permissions/{grant_id}
GET/POST   /api/v1/records/{id}/permissions
DELETE     /api/v1/records/{id}/permissions/{grant_id}
```

Bulk replacement must use optimistic concurrency and be atomic. A partial ACL
update must never leave a resource orphaned.

### 16.3 Effective-access and explanation

The UI may use:

```text
GET /api/v1/aggregations/{id}/capabilities
GET /api/v1/records/{id}/capabilities
```

These return only Boolean capabilities and safe display guidance for the
current caller. They are conveniences; each action endpoint re-authorizes.

An administrator-only explain endpoint may return contributing roles,
profiles, clearance, direct/inherited grants, governance basis, and denial
codes. It must be separately privileged and audited.

### 16.4 Concurrency and mutation context

Authorization administration and security-level changes require `If-Match` and
follow the existing optimistic-concurrency contract. Sensitive removals,
downgrades, governance-flag changes, privilege-set changes, and bulk ACL
changes require `X-Change-Reason`.

An authorization check immediately before a write does not replace rechecking
current policy-relevant rows under the write transaction. Profile, role,
assignment, hierarchy, security, and ACL changes must not race a protected
mutation.

## 17. User interface

The UI must provide dedicated pages for Security Levels, Profiles, and the
read-only Privilege and Permission catalogues. Role details show its clearance,
governance flag, assigned profiles, and resulting privileges.

Aggregation and Record detail pages show:

- security-level code and name prominently;
- whether disposition is prevented by that level;
- an Access panel listing direct and inherited role grants;
- the source aggregation for inherited grants;
- current-user capabilities where useful; and
- disabled actions with concise safe guidance when the resource itself is
  viewable.

ACL editors select roles through the organization-structure browser. They do
not offer users or organizational units. Permissions are grouped by entity and
operation family, and inheritance scope is explicit.

Every existing action must be rendered from capabilities, including buttons,
context menus, bulk actions, upload controls, links, search results, and tree
nodes. The UI must still handle `401`, `403`, `404`, and `409` because policy can
change after rendering.

## 18. Audit and security monitoring

Create, update, lifecycle, assignment, and deletion events are required for
security levels, profiles, profile privileges, role profiles, governance flags,
and ACL grants. Event metadata must preserve human-readable snapshots of the
affected role, profile, privilege/permission, scope, security level, inheritance
settings, actor, reason, request, and correlation context.

Domain events are required for at least:

```text
PERMISSION_GRANTED
PERMISSION_REVOKED
PROFILE_ASSIGNED
PROFILE_UNASSIGNED
SECURITY_LEVEL_CHANGED
SECURITY_LEVEL_DOWNGRADED
GOVERNANCE_ACCESS_USED
AUTHORIZATION_DENIED
```

Routine successful read checks need not each create an event; doing so would
overwhelm the audit trail. Content view, download, share, print, governance
bypass, break-glass use, repeated denials, and security administration are
security-relevant and must be recorded according to configurable audit policy.

Denial events must not store secrets, component content, session tokens, or
protected metadata the actor was not allowed to see. Rate limiting or
aggregation may be used for repeated identical denials without losing incident
visibility.

## 19. Caching and performance

Correctness precedes caching. The first implementation may calculate decisions
from indexed current state. If caching is introduced:

- keys include user, operation, resource, and policy revision;
- assignment, role, organizational ancestry, profile, privilege, security
  level, ACL, move, and lifecycle changes invalidate affected entries;
- a cached allow must never outlive session revocation or policy change;
- write transactions still revalidate authoritative state; and
- tests prove revocation takes effect immediately.

List and search authorization must use set-based SQL predicates. An endpoint
must not fetch 500 rows and issue per-row authorization queries. Performance
tests must detect N+1 policy evaluation and verify representative indexes.

## 20. Bootstrap, recovery, and lockout prevention

The canonical seed creates the privilege and permission catalogues, baseline
security levels, a System Administrator profile, and assignments to the
reserved `system-administrator` role. Bootstrap is explicit provisioning, not a
runtime bypass hidden in an email address or user ID.

Changes that could remove the last effective authorization administrator or
last access-continuity custodian are rejected transactionally. The existing
reserved-role and future deletion rules continue to apply.

A future break-glass procedure must be operationally separate, time-limited,
strongly authenticated, reasoned, alerted, and audited. Until that workflow is
specified and implemented, there is no break-glass API flag.

## 21. Interaction with permanent deletion

After this subsystem is complete, the deletion specification may be
implemented. User and role deletion simulations must account for:

- effective assignment and role rules;
- global privileges and profile assignments;
- security clearance;
- direct and inherited ACLs;
- information-governance access; and
- the requirement that protected content retains at least one effective human
  custodian capable of viewing it and administering its access.

A service account alone does not satisfy the human-custodian continuity rule.
Role deletion remains blocked while ACL grants or profile relationships require
explicit transfer or removal.

## 22. Verification requirements common to every phase

Every phase ends at a mandatory verification gate. Work does not continue to
the next phase until its tests pass and the phase result is reviewed.

All database-backed tests must:

1. create a uniquely named disposable PostgreSQL database;
2. initialize it from the canonical schema or complete migration path required
   by the test;
3. point every fixture and process only at that database;
4. run success, denial, rollback, concurrency, and audit assertions; and
5. terminate connections and drop the database whether tests pass or fail.

No authorization test may run against the local development database. Browser
tests also use a disposable database and test accounts created for that run.

Each phase must additionally pass:

- migration idempotency and canonical-schema parity checks;
- unit and API regression suites;
- event-history assertions for new mutations;
- `git diff --check` and syntax/static checks;
- documentation consistency review; and
- a recorded stop/go summary listing tests run, failures, and remaining risks.

## 23. Phased implementation plan

### Phase 0 — Policy inventory and characterization

**Goal:** Freeze the current endpoint/action inventory and existing lifecycle,
closure, draft, audit, and hierarchy behavior before enforcement changes.

**Deliverables:**

- a machine-readable operation-to-policy registry covering every API route;
- characterization tests proving current behavior;
- an explicit list of public, authenticated-only, globally privileged, and
  resource-scoped operations; and
- approved initial security-level, privilege, permission, and profile seeds.

**Verification gate:** No route or UI action is absent from the registry; all
existing regression tests pass in disposable environments.

### Phase 1 — Security-level foundation

**Goal:** Add the catalogue and non-null role/aggregation/record references
without enforcing access yet.

**Deliverables:**

- schema, constraints, seed, migration backfill, APIs, and basic admin UI;
- hierarchy monotonicity enforcement;
- audited create/update/delete and level changes; and
- security-level fields on existing entity forms and details.

**Verification gate:** Migration upgrade and clean build produce identical
schemas; defaulting, monotonicity, referenced deletion, concurrency, and audit
tests pass. Existing data remains readable.

### Phase 2 — Privilege, profile, and role-profile administration

**Goal:** Implement the global capability model without enforcing it on
existing business routes.

**Deliverables:**

- seeded privilege catalogue;
- profile CRUD/lifecycle, profile-privilege membership, and role-profile
  assignment;
- reserved System Administrator profile;
- role governance flag and clearance administration; and
- affected-role/user previews for profile changes.

**Verification gate:** Union, inactivity, assignment, optimistic-concurrency,
last-administrator protection, and complete audit tests pass. Direct user or
organizational-unit profile assignment is impossible at every layer.

### Phase 3 — Pure policy engine and decision explanations

**Goal:** Implement one reusable authorization engine before wiring it into
routes.

**Deliverables:**

- effective-role, privilege-union, clearance, and decision functions;
- stable allow/deny reason codes and contributing-role explanations;
- request-scoped principal and policy context; and
- exhaustive table-driven unit tests.

**Verification gate:** Tests cover active/inactive/suspended users; role and
ancestor inactivity; future/expired assignments; multiple profiles; multiple
clearance roles; no-role users; and policy changes during a request. The engine
contains no route-specific ad hoc administrator bypass.

### Phase 4 — Global administrative privilege enforcement

**Goal:** Protect non-resource administration routes first.

**Deliverables:**

- enforcement for user, session, organization, authorization, security-level,
  classification, and audit administration;
- bootstrap-safe system-administrator behavior; and
- UI capability handling for those sections.

**Verification gate:** For every protected route, allow, missing privilege,
inactive role, expired assignment, stale session, and audit tests pass. A
separate unprivileged account cannot reach the operation through API or UI.

### Phase 5 — ACL schema, inheritance, and continuity

**Goal:** Add role-only aggregation and record ACLs without yet filtering all
read paths.

**Deliverables:**

- permission catalogue and FK-safe grant tables;
- direct and inherited effective-permission queries;
- nested ACL APIs, bulk atomic replacement, and ACL editor;
- source/destination and descendant scope representation; and
- access-continuity simulation and rejection.

**Verification gate:** Direct user/org grants and deny grants are rejected;
inheritance, union, move previews, duplicate prevention, atomic rollback,
orphan prevention, and ACL audit tests pass.

### Phase 6 — Read authorization and information-leak prevention

**Goal:** Enforce view, history, search, listing, tree, count, favourite,
breadcrumb, and component-metadata access.

**Deliverables:**

- set-based authorization predicates on every read path;
- `404` non-disclosure behavior;
- clearance enforcement and audit-history redaction; and
- current-user capability endpoints.

**Verification gate:** Cross-user matrix tests prove hidden resources cannot be
inferred through IDs, totals, pagination, sorting, searches, trees, favourites,
recent items, relationships, histories, or timing-sensitive alternate paths.
Query-count tests reject N+1 implementations.

### Phase 7 — Aggregation and record mutation enforcement

**Goal:** Enforce global privileges, clearance, and ACLs on metadata and
structural operations.

**Deliverables:**

- create, modify, delete, close, reopen, move, reclassify, security-change, and
  ACL-management enforcement;
- dual-sided move authorization;
- transactional policy revalidation; and
- UI action capabilities and safe denial handling.

**Verification gate:** An operation matrix covers each privilege/permission,
source and destination, direct/inherited grant, clearance boundary, closure,
concurrency race, rollback, and event-history result.

### Phase 8 — Draft and digital-component enforcement

**Goal:** Protect the complete content lifecycle.

**Deliverables:**

- draft ownership and commit-time reauthorization;
- list/view/download/add/replace/remove/reorder enforcement;
- reserved share and print behavior that remains unavailable until implemented;
  and
- atomic replacement authorization and audit.

**Verification gate:** Tests prove metadata-only viewers cannot see bytes or
component metadata, replacement is not achievable through partial remove/add,
draft policy changes are caught at commit, closed branches remain frozen, and
failed content operations leave no orphaned blobs or rows.

### Phase 9 — Information-governance ACL bypass

**Goal:** Add the narrowly scoped governance behavior only after normal policy
is proven.

**Deliverables:**

- governance-role ACL bypass requiring that same role's sufficient clearance;
- continued global-privilege and integrity enforcement;
- governance-basis explanations and events; and
- administrative warnings and assignment visibility.

**Verification gate:** Tests prove governance bypasses ACL only; never bypasses
clearance, missing privilege, inactive ancestry, invalid assignment, closure,
special downgrade, or unrelated administration. A non-governance high-clearance
role cannot lend clearance to a low-clearance governance role.

### Phase 10 — Complete authorization-aware UI

**Goal:** Make every interface accurately reflect enforced capabilities without
depending on the UI for security.

**Deliverables:**

- Security Levels, Profiles, catalogues, role authorization, and ACL pages;
- capability-aware buttons, selectors, tables, trees, dialogs, bulk actions,
  and explanatory disabled states;
- polished security-level and inherited-access presentation; and
- accessible keyboard and screen-reader behavior.

**Verification gate:** Disposable-database browser tests cover representative
personas and policy changes between render and click. Direct API tests prove
hidden controls cannot be bypassed.

### Phase 11 — Audit, monitoring, performance, and recovery hardening

**Goal:** Prove the subsystem is operable under load and diagnosable without
weakening confidentiality.

**Deliverables:**

- security-event dashboards and denial monitoring;
- authorization explain tooling;
- index and query-plan review;
- cache design only if measurements require it;
- last-administrator and access-continuity operational tooling; and
- a separately reviewed break-glass specification, if still required.

**Verification gate:** Load and query-count targets pass; revocation is
immediate; audit snapshots remain intelligible after renames/deletions; denial
logs contain no protected content; backup/restore and recovery exercises are
documented.

### Phase 12 — Authorization-dependent permanent deletion

**Goal:** Implement the previously approved user, role, and organizational-unit
deletion semantics now that access-continuity decisions are reliable.

**Deliverables:**

- transactional deletion preflight and execution;
- role ACL/profile dependency reporting;
- human-custodian continuity simulation; and
- UI explanations and immutable deletion events.

**Verification gate:** All blocker, allowed deletion, race, cascade, audit, and
rollback scenarios in the deletion specification pass against a disposable
database. No protected resource becomes inaccessible after a permitted
deletion.

## 24. Approval decisions required before Phase 1

The following decisions should be confirmed during review:

1. Approve or replace the proposed security-level seed catalogue.
2. Confirm that a user's effective clearance is the maximum across effective
   roles and that a lower-clearance role does not veto it.
3. Confirm union-based RBAC, allowing privilege, clearance, and ACL permission
   to be contributed by different effective roles on the normal path.
4. Confirm hierarchical security monotonicity: descendants may be equally or
   more restricted, never less restricted than their parent.
5. Confirm that information-governance roles bypass only the ACL, must
   themselves have sufficient clearance, and still require global privileges.
6. Confirm the aggregation-to-descendant ACL inheritance scopes.
7. Confirm that component preview, download, share, and print remain separate
   permissions.
8. Confirm that component replacement is an atomic permission distinct from
   add and remove.
9. Confirm whether system-wide Audit Trail viewers may see redacted events for
   above-clearance resources or should not see those events at all. This draft
   recommends showing the event envelope with protected snapshots redacted.
