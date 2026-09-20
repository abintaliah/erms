# Organizational Workspaces — Implementation Specification

**Status:** Review draft — not approved and not implemented  
**Project:** ERMS / wathiq  
**Prepared:** 20 September 2026  
**Revision:** 0.1

## 1. Purpose

This specification proposes organizational workspaces for wathiq. A workspace
is the organizational context in which a user acts. An aggregation and every
record within it are held in the custody of one organizational unit, called
the owning organizational unit. During ordinary use, a user can discover and
operate on governed content only when it belongs to the user's selected
workspace.

The feature is intended to:

- establish explicit organizational custody for aggregations and records;
- prevent users from unintentionally mixing content belonging to different
  organizational responsibilities;
- make access follow effective role assignments without rewriting resource
  ACLs when personnel move;
- reduce disclosure through search, browse, favourites, counts, and direct
  links; and
- give authorized information-governance personnel a controlled and audited
  organization-wide view.

This document is a review draft. It records recommended behaviour and
identifies decisions that must be approved before implementation.

## 2. Relationship to the authorization model

Workspace scope is an additional mandatory authorization gate. It does not
replace authentication, global privileges, security clearance, resource ACLs,
or lifecycle and structural rules.

For an ordinary governed-resource operation, access requires all applicable
gates to succeed:

```text
active authenticated account
AND currently effective role
AND valid selected workspace
AND resource belongs to selected workspace
AND required global privilege
AND sufficient security clearance
AND required resource ACL permission
AND applicable lifecycle and integrity rules
```

An information-governance role may bypass the ordinary workspace-membership
and resource-ACL scope only through the explicit cross-workspace mechanism in
Section 10. It does not silently bypass global privileges, security clearance,
lifecycle rules, structural rules, or auditing.

The server and database authorization predicates are authoritative. A header
switcher, hidden control, client-side filter, route guard, or cached UI state
must never be treated as enforcement.

## 3. Scope

### 3.1 Included

This proposal includes:

- mandatory organizational ownership for aggregations and records;
- derivation of workspace eligibility from effective role assignments;
- selection, display, switching, and expiry of the current workspace;
- workspace-scoped creation, viewing, searching, browsing, and navigation;
- explicit information-governance access across workspaces;
- governed transfer of custody between workspaces;
- workspace-aware ACL defaults;
- preservation of custody history;
- migration of existing governed content; and
- database, REST API, API-client, UI, audit, and automated-test changes.

### 3.2 Excluded from the initial version

Unless separately approved, the initial version does not include:

- implicit access to descendant org units from a role in an ancestor unit;
- personal, project, ad hoc, or user-created workspaces;
- content owned by more than one org unit at the same time;
- an `All Workspaces` org unit or ownership value;
- workspace-specific classification schemes;
- negative ACL grants;
- direct workspace membership unrelated to an effective role;
- silent or automatic custody changes following org-chart restructuring; or
- cross-workspace aggregation hierarchies.

## 4. Terminology

### 4.1 Owning organizational unit

The organizational unit with present custody and accountability for an
aggregation or record. The proposed database field is
`owning_org_unit_id`. Ownership is governed metadata, not an ACL grant and not
the identity of the creating user.

### 4.2 Workspace

A selectable operational context corresponding to exactly one active org
unit. Its displayed name is the current name of that org unit. Several
effective roles in the same org unit produce one workspace.

### 4.3 Workspace eligibility

A user is eligible for an org-unit workspace when at least one of the user's
role assignments is currently effective and its role belongs to that exact org
unit. Effective-role rules remain those defined by the security and
authorization specification, including account, assignment, role, and org-unit
hierarchy status.

Eligibility is calculated from distinct org-unit IDs, not from the number of
roles. A role in an ancestor org unit does not confer eligibility for a
descendant workspace in the initial version.

### 4.4 Current workspace

The one eligible workspace selected for the interactive session. It controls
ordinary governed-resource queries and commands. It does not change the
user's roles, privileges, clearance, or ACL memberships.

### 4.5 Cross-workspace scope

An explicit information-governance operating mode that can discover governed
content across multiple owning org units. It is not an org unit, cannot own
content, and must never be persisted in `owning_org_unit_id`.

### 4.6 Custody transfer

The exceptional, audited operation that changes content from one owning org
unit to another. The user-facing action is **Transfer to Workspace**. The
recommended privilege name is **Transfer Content Between Workspaces**, with
the code `workspace.transfer` and category `exceptional`.

## 5. Core policy decisions

The implementation should adopt the following invariants:

1. Every aggregation has one non-null owning org unit.
2. Every record has one non-null owning org unit.
3. A child aggregation has the same owning org unit as its parent.
4. A record has the same owning org unit as its containing aggregation.
5. An aggregation hierarchy never crosses a workspace boundary.
6. Ordinary moves are confined to the current workspace.
7. A custody transfer is a distinct exceptional action, not an ordinary move.
8. Transferring an aggregation transfers its complete descendant aggregation
   and record subtree atomically.
9. Transferring an individual record requires a destination aggregation in the
   destination workspace.
10. Clients cannot choose or override ownership during ordinary creation.
11. Org-unit renaming or re-parenting does not change content ownership.
12. Org-unit deactivation does not silently reassign content.

These invariants are required to keep the aggregation tree, ACL inheritance,
browse behaviour, and workspace boundary consistent.

## 6. Data model

### 6.1 Governed resources

Add the following columns after the migration stages in Section 15 are
complete:

| Table | Column | Rules |
| --- | --- | --- |
| `aggregations` | `owning_org_unit_id bigint` | Required; references `org_units(id)` with `ON DELETE RESTRICT` |
| `records` | `owning_org_unit_id bigint` | Required; references `org_units(id)` with `ON DELETE RESTRICT` |

Storing ownership on records is deliberate denormalization for high-volume
search and filtering. The database must enforce equality with the containing
aggregation. API callers must never supply record ownership independently.

Recommended indexes include:

```text
aggregations(owning_org_unit_id, parent_aggregation_id,
             aggregation_number COLLATE "C", id)
records(owning_org_unit_id, aggregation_id,
        record_number COLLATE "C", id)
```

Search-specific composite or full-text indexes must place workspace scope so
that filtering occurs before count, sorting, faceting, and pagination.

### 6.2 Ownership enforcement

Database constraints or constraint triggers must reject:

- a child aggregation whose owner differs from its parent;
- a record whose owner differs from its containing aggregation;
- an ordinary hierarchy move across owners; and
- direct ownership updates outside the governed transfer procedure.

The transfer procedure must be the only application path allowed to update
ownership after creation. Authorization cannot rely solely on preventing the
field from appearing in the UI.

### 6.3 Primary workspace

Wathiq must model how a user's primary workspace is selected. The recommended
model is:

- add `is_primary boolean NOT NULL DEFAULT false` to
  `user_role_assignments`;
- allow at most one primary assignment for a user over any overlapping
  effective period; and
- optionally retain the last selected eligible workspace as a user preference.

The exact temporal uniqueness mechanism requires database design review. The
implementation must not infer primacy from role ID, insertion order, org-unit
name, or the earliest assignment.

### 6.4 Session workspace state

The selected workspace may be stored as server-controlled session state. The
server must nevertheless revalidate eligibility on every request that uses it.
Role expiry, role deactivation, org-unit deactivation, assignment removal, or
account changes must take effect without requiring a new login.

A client-provided workspace ID is an input to validation, never trusted
authorization state. If a request supports an explicit workspace header or
parameter, the server must verify that it matches authorized session context.

### 6.5 Custody history

The existing immutable event-history system must record ownership at creation
and every transfer. A transfer event must retain at least:

- transferred root entity type and ID;
- source and destination org-unit IDs;
- snapshots of source and destination org-unit code and name;
- actor and effective governance role where applicable;
- actor's current workspace or cross-workspace scope;
- timestamp and request/correlation ID;
- mandatory transfer reason;
- approval information, if required by policy;
- counts of affected aggregations and records; and
- the chosen ACL treatment and its outcome.

Historical events must remain intelligible after an org unit is renamed,
re-parented, or deactivated.

## 7. Workspace derivation and sign-in behaviour

At authentication and whenever workspace state is refreshed, the server
calculates the distinct active org units supplied by the user's effective
roles.

Selection follows this order:

1. If no eligible workspace exists, select none.
2. If exactly one eligible workspace exists, select it.
3. If an effective primary assignment exists, select its org unit.
4. Otherwise, if the last-used workspace remains eligible, select it.
5. Otherwise require the user to choose before accessing governed content.

If several effective roles belong to the selected org unit, all continue to
contribute privileges, clearance, and ACL matches under the current
authorization model. Selecting a workspace does not select only one role and
does not suppress roles in other units for global privilege or clearance
calculation unless a later authorization revision explicitly adopts that
different model.

This last rule is security-sensitive and must be confirmed during review. For
example, a higher clearance supplied by an effective role in another org unit
would continue to contribute to effective user clearance under the presently
approved authorization specification.

## 8. No-workspace state

A user with no effective roles has no eligible workspace. The application
header displays **No current workspace**.

In this state the user cannot list, search, browse, open, create, modify,
download, print, share, favourite, or otherwise access governed aggregations,
records, or components. Direct URLs and APIs must enforce the same result.

The user may still access non-governed functions that do not require a
workspace, such as their profile, help, session management, and logout. Any
administrative capability intended to work without a workspace must be listed
and approved explicitly rather than arising accidentally.

## 9. Ordinary workspace enforcement

### 9.1 Read paths

The current workspace predicate applies consistently to:

- aggregation and record detail endpoints;
- simple and advanced search;
- result totals, facets, grouping, and type-ahead suggestions;
- classification-based browsing and tree badges;
- aggregation hierarchy browsing;
- breadcrumbs and related-resource summaries;
- favourites, recent items, dashboard cards, and saved links;
- event history exposed from resource pages;
- component listing, viewing, downloading, printing, and sharing;
- exports, reports, bulk selections, and background report generation; and
- any identifier-resolution or existence-check endpoint.

Filtering must happen before count, sort, and pagination. A resource outside
the selected workspace must not be revealed through titles, identifiers,
counts, timing-sensitive error distinctions, or stale cached data.

### 9.2 Create paths

When creating a root aggregation, its owner is the current workspace org unit.
When creating a child aggregation or record, ownership is copied from the
parent aggregation after confirming that the parent belongs to the current
workspace.

Ordinary create payloads must not expose `owning_org_unit_id`. If supplied by a
client, it should be rejected as an unknown or immutable field rather than
trusted. Creation is unavailable in the no-workspace state and the
cross-workspace governance scope.

### 9.3 Forms and concurrent switching

An edit or create form is bound to the workspace in which it was opened. If
the current workspace changes before submission, the application must either:

- reject the stale submission and require the form to be reopened; or
- show the original and current workspaces and require explicit
  reconfirmation without changing the form's ownership context.

The application must never silently assign a submission to a newly selected
workspace. Upload sessions, drafts, and background completion callbacks require
the same binding.

### 9.4 Favourites and direct links

A favourite does not grant access. Favourites outside the selected workspace
must not appear in ordinary workspace lists. If a user has an eligible
workspace containing the item, the UI may offer to switch workspaces without
revealing protected metadata before authorization succeeds.

Loss of eligibility invalidates direct links and favourites immediately for
access purposes but does not need to delete the personal favourite relation.
Regaining eligibility may make it visible again if every other gate succeeds.

## 10. Information-governance cross-workspace access

### 10.1 Separate operating scope

Authorized information-governance users should have a clearly labeled
**All Workspaces** scope or dedicated governance page. It must be visually and
semantically distinct from an ordinary workspace.

The cross-workspace interface should support filters for workspace,
classification, security level, lifecycle state, retention status, and other
governance attributes. Every result must display its owning workspace
prominently.

### 10.2 Privileges

Recommended new privilege codes are:

| Code | Category | Purpose |
| --- | --- | --- |
| `workspace.cross_scope.view` | `administration` or a new governance category | Enter cross-workspace scope and discover otherwise eligible governed content |
| `workspace.transfer` | `exceptional` | Transfer custody between workspaces |
| `workspace.cross_scope.export` | `exceptional` | Export results containing more than one workspace, if such exports are permitted |
| `workspace.administer` | `administration` | Configure workspace defaults and policies, if configuration is introduced |

The names and category of these privileges require approval. Cross-workspace
view requires both `workspace.cross_scope.view` and an effective role marked as
information governance. Ordinary content privileges and sufficient security
clearance remain required.

### 10.3 Bypass limits

The information-governance bypass may satisfy:

- ordinary membership in the owning resource's workspace; and
- the resource ACL permission, where the existing governance policy permits.

It must not satisfy:

- authentication or effective-role requirements;
- the relevant global content privilege;
- security clearance;
- closure, retention, legal-hold, optimistic-concurrency, or integrity rules;
- a separately protected exceptional privilege; or
- a required transfer reason or approval.

Cross-workspace searches, views, exports, and modifications must be auditable.
The system should support monitoring for unusually broad queries and exports.

### 10.4 Creation prohibition

The cross-workspace scope cannot own content. A governance user must enter a
real eligible destination workspace before ordinary creation. If future policy
allows governance users to create for a unit to which they are not ordinarily
assigned, that must be a separate explicit privilege and workflow.

## 11. Workspace transfer

### 11.1 Authorization

A transfer requires all of the following:

- `workspace.transfer`;
- access to the source workspace, either through ordinary eligibility or
  approved cross-workspace governance scope;
- access to the destination workspace;
- the appropriate modify/move permissions over the source object;
- the appropriate create/placement permissions at the destination;
- clearance sufficient for the complete transferred subtree; and
- satisfaction of closure, retention, hold, concurrency, and integrity rules.

Whether an information-governance user may transfer into an org unit without
an ordinary effective role there is an approval decision. The recommended
policy is to allow it only through cross-workspace governance scope and only
when the user holds `workspace.transfer`.

### 11.2 Preview and confirmation

Before commit, the user must see:

- source and destination workspaces;
- the root entity being transferred;
- counts of affected child aggregations, records, and components;
- classifications and security levels present in the subtree;
- ACL and inheritance consequences;
- conflicts or invalid destination conditions; and
- the proposed ACL treatment.

A non-blank reason is mandatory. High-risk transfers may require two-person
approval; that policy remains open for review.

### 11.3 Transactionality and concurrency

The transfer is one database transaction. It must lock or otherwise protect
the moving subtree and relevant destination so that concurrent creation,
movement, ownership change, or ACL edits cannot leave mixed ownership.

On failure, no resource changes owner. On success, all affected ownership,
placement, ACL changes, version increments, and audit events commit together.

### 11.4 Individual record transfer

An individual record transfer must select a destination aggregation in the
destination workspace. It is simultaneously a placement change and a custody
transfer. The destination aggregation's security envelope, lifecycle state,
record ACL defaults, and other placement constraints must accept the record.

### 11.5 ACL treatment

The transfer workflow must never silently retain inappropriate access or
silently erase deliberate restrictions. It should offer policy-controlled
choices such as:

- apply the destination workspace's approved ACL template;
- map source roles to approved destination roles; or
- retain compatible explicit grants and remove grants belonging exclusively to
  the source unit.

The default should be the safest centrally approved option, accompanied by an
impact preview. Source-unit role grants normally must not survive unless an
authorized reviewer deliberately approves cross-unit access.

## 12. ACL defaults and workspace membership

### 12.1 Principle

Workspace eligibility supplies a coarse organizational boundary. ACLs continue
to express need-to-know and the operations allowed on particular content.
Membership in a workspace must not automatically grant every permission.

The system should not copy every role currently belonging to an org unit into
every newly created resource ACL. Such snapshots become large, fail to handle
future roles predictably, and obscure the intended access policy.

### 12.2 Proposed workspace principal

The preferred design is a dynamic ACL principal representing members of one
org unit, called `org_unit` at the data-model level and presented as
**Workspace members** in the UI. A grant matches when the user has at least one
effective role in the named org unit.

This proposal changes a principle in the currently approved security and
authorization specification, which states that roles are the only named
grant-bearing principals and org units never receive ACL grants. It must
therefore receive explicit security-model approval before implementation.

If that change is not approved, the fallback is centrally managed ACL
templates that expand to role grants. The fallback must define how newly
created roles are handled and how template updates affect existing resources.

The existing synthetic `everyone` principal must not be reinterpreted silently
as workspace members. Its current organization-wide meaning must either remain
stable or be migrated through a separately approved compatibility plan.

### 12.3 Recommended default templates

Each org unit may have approved templates for root aggregations, child
aggregations, ordinary records, and sensitive records. A typical general
template might grant:

- workspace members: view/list permissions only;
- creating role: routine operational permissions;
- designated custodian roles: records-management permissions; and
- workspace manager roles: selected administrative permissions.

Sensitive templates may grant access only to selected roles. Governance bypass
should remain a policy-engine rule and should not be copied into every ACL.

The template used, template version, and resulting grants must be recorded at
creation. An administrator must not be able to broaden defaults without the
appropriate privilege, concurrency check, and audit event.

## 13. Org-unit and role lifecycle

### 13.1 Assignment loss and restoration

When a user's last effective role in an org unit expires or is removed, the
corresponding workspace becomes ineligible immediately. No resource ACL update
is required. When eligibility returns, access may return automatically, but
only if privileges, clearance, ACLs, and other gates also pass.

### 13.2 Org-unit deactivation

An inactive org unit cannot:

- be selected as an ordinary workspace;
- receive newly created content; or
- be a transfer destination.

Existing content retains its owner. Authorized governance users must be able
to find and resolve holdings owned by inactive units. Deactivation should warn
or block according to approved policy when active roles, unresolved holdings,
drafts, or pending workflows remain.

### 13.3 Reorganization

Renaming or re-parenting an org unit preserves the same identity and ownership.
Merging, splitting, replacing, or retiring units does not automatically rewrite
content. Each custody change must use an audited bulk-transfer process or an
approved migration with equivalent history.

## 14. API and service requirements

Exact endpoint shapes may be finalized during implementation, but the API must
provide:

- the user's eligible workspaces and selection state;
- selection of one eligible current workspace;
- explicit entry to and exit from authorized cross-workspace scope;
- workspace-aware governed-resource endpoints;
- transfer preview and commit operations; and
- internal authorization explanations with stable reason codes.

Representative endpoints are:

```http
GET  /api/v1/workspaces
PUT  /api/v1/session/workspace
POST /api/v1/workspace-transfers/preview
POST /api/v1/workspace-transfers
```

The workspace-selection request should contain only the intended org-unit ID.
The server derives its display data and validates eligibility. Mutation
requests use the existing optimistic-concurrency convention where applicable.

Public denial responses must avoid existence leakage. Internal diagnostics
should distinguish at least:

- `no_effective_role`;
- `workspace_required`;
- `workspace_not_eligible`;
- `resource_outside_workspace`;
- `cross_scope_not_authorized`;
- `privilege_required`;
- `clearance_insufficient`;
- `acl_permission_required`;
- `workspace_transfer_required`; and
- lifecycle or integrity failures already defined elsewhere.

## 15. Migration and rollout

Ownership must not become `NOT NULL` until every existing row has a reviewed,
valid owner and all enforcement paths are ready.

Recommended rollout:

1. Approve this specification and its open decisions.
2. Add nullable ownership columns, indexes, history snapshots, and supporting
   transfer structures to both a migration and the canonical schema.
3. Produce an ownership-assignment report using hierarchy, creators, ACLs, and
   business custody data only as evidence, not as an unquestioned decision.
4. Let information-governance reviewers resolve ambiguous holdings.
5. Backfill root aggregation ownership and propagate it to descendants and
   records.
6. Validate that every hierarchy and record containment relationship has one
   consistent owner.
7. Add database enforcement for creation, containment, and transfer.
8. Update every read, search, browse, history, component, favourite, export,
   and background-processing path.
9. Add session selection and UI workspace behaviour.
10. Run leakage, concurrency, authorization, and migration verification.
11. Make both ownership columns `NOT NULL`.
12. Enable strict workspace enforcement only after production readiness review.

A generic fallback org unit must not be assigned merely to satisfy `NOT NULL`.
Unresolved ownership must be reported and explicitly resolved.

All database-backed verification must follow the repository requirement to use
a newly created disposable PostgreSQL database initialized from the canonical
schema or required migration path, followed by unconditional cleanup.

## 16. Background processing, integrations, and caching

Interactive session workspace state is unsuitable for scheduled jobs,
retention processing, ingestion, migrations, and integrations. Each such
process must declare and validate one of:

- a specific owning org-unit context;
- a bounded set of org units; or
- an approved organization-wide governance scope.

Service accounts do not gain implicit all-workspace access. Their scope and
privileges must be explicit and auditable.

Authorization and result caches must include all policy inputs that can alter
the result, including user, selected workspace or cross-scope state, role and
assignment effectiveness, resource owner, privileges, ACL version, security
level, and relevant lifecycle state. Role or ownership changes must invalidate
or safely expire affected entries.

## 17. User interface requirements

The application header must always display one of:

- the current workspace's org-unit name;
- **Select workspace** when several are eligible but none is selected;
- **No current workspace** when none is eligible; or
- a visually distinct **All Workspaces — Governance** indicator.

The workspace switcher appears next to the profile control and lists each
distinct eligible org unit once. It should show the org-unit code where names
could be ambiguous. Switching refreshes workspace-scoped navigation, counts,
favourites, recent items, searches, and open content.

The UI must prominently display owning workspace on governed detail pages and
cross-workspace results. Ordinary create forms show ownership as read-only
context rather than an editable field.

Information-governance users must consciously enter cross-workspace scope.
Warning styling and wording should make organization-wide searches and actions
unmistakable.

## 18. Verification requirements

Automated tests must cover at least:

### 18.1 Eligibility and selection

- zero, one, and several effective roles;
- several roles in the same org unit yielding one workspace;
- primary assignment and last-used fallback;
- future, expired, inactive-role, and inactive-org-unit assignments;
- eligibility disappearing during an active session; and
- workspace spoofing through request parameters or headers.

### 18.2 Resource isolation

- list, detail, search, count, facet, pagination, classification browsing,
  hierarchy browsing, breadcrumbs, favourites, recent items, history, and
  components;
- direct URL and identifier guessing;
- exports and background jobs;
- cache separation between workspaces; and
- absence of protected titles, identifiers, counts, and timing distinctions.

### 18.3 Creation and structure

- automatic ownership of roots, children, and records;
- rejection of client-supplied ownership;
- rejection of mixed-owner hierarchy and record containment;
- stale form submission after workspace switching; and
- draft and upload ownership binding.

### 18.4 Governance

- cross-workspace view requiring both governance status and privilege;
- security clearance and global privileges remaining mandatory;
- ACL bypass occurring only where specified;
- cross-workspace creation being prohibited;
- audit events for cross-workspace searches and operations; and
- no cross-workspace export without its approved privilege.

### 18.5 Transfers

- complete subtree transfer;
- individual record transfer with destination placement;
- source and destination authorization;
- ACL preview and approved treatment;
- closed, retained, held, or clearance-conflicting content;
- concurrent child creation, movement, and ACL changes;
- full rollback on any error; and
- immutable, reconstructable custody history.

### 18.6 Migration

- unambiguous backfill;
- explicit reporting of ambiguous or missing ownership;
- hierarchy consistency validation;
- canonical-schema parity with migration results; and
- `NOT NULL` enforcement only after a complete validated backfill.

## 19. Operational benefits

If implemented as specified, organizational workspaces provide:

- clear current custody and organizational accountability;
- access removal and restoration following effective assignments without ACL
  rewrites;
- reduced accidental disclosure and cross-department mistakes;
- safer and simpler creation defaults;
- stronger separation of duties for multi-role users;
- more meaningful holdings, retention, disposition, and compliance reporting;
- a governed process for reorganizations and custody transfers;
- reduced ACL administration when dynamic workspace membership or controlled
  templates are used;
- explicit scope for service accounts and automated processes; and
- centralized, audited organization-wide governance oversight.

## 20. Risks and mitigations

| Risk | Required mitigation |
| --- | --- |
| UI-only filtering | Enforce scope in database-backed server predicates on every path |
| Mixed ownership in one hierarchy | Database invariants and atomic subtree transfer |
| Over-broad departmental defaults | View-only workspace defaults plus sensitive templates and role-specific grants |
| `everyone` accidentally becomes workspace-local | Add a distinct principal or approve an explicit migration; never reinterpret silently |
| Stale access after role expiry | Revalidate workspace eligibility on every request |
| Search/count inference | Filter before count, facets, sort, and pagination |
| Incorrect legacy ownership | Staged review and validation before `NOT NULL` |
| Org restructure erases history | Stable org-unit IDs and immutable custody events |
| Governance mode causes accidental broad action | Separate scope, strong visual indication, narrow privileges, reasons, and audit |
| Transfer leaks source access | Required ACL impact preview and approved destination policy |
| Cache crosses workspaces | Workspace-aware cache keys and invalidation |
| Background jobs act without scope | Explicit bounded service context |
| Workspace switch changes an open form | Bind form and upload state to the originating workspace |

## 21. Decisions required before approval

Reviewers must decide:

1. Whether the field name is `owning_org_unit_id` as recommended.
2. Whether ownership is stored on both aggregations and records or derived for
   records; this draft recommends storing both with enforced equality.
3. Whether to add a dynamic `org_unit` ACL principal, despite the current
   roles-only authorization principle.
4. The exact default ACL templates and whether workspace members receive view
   access by default.
5. Whether global privilege and effective clearance continue to combine roles
   across all org units while a workspace is selected.
6. The primary-assignment data model and fallback selection order.
7. Whether information-governance users may transfer to/from units in which
   they have no ordinary effective role.
8. Whether high-risk or bulk transfers require dual approval.
9. How ACLs are transformed during transfer.
10. Whether an inactive org unit with holdings blocks deactivation or merely
    warns and creates a remediation task.
11. The privilege catalogue names, categories, and dependencies.
12. Which administrative pages, if any, remain usable without a workspace.
13. Whether cross-workspace search and view events require a dedicated audit
    event for every access or aggregated session-level logging.
14. Workspace numbering rules: retain globally unique aggregation and record
    numbers or introduce workspace-local uniqueness.

No implementation should begin until decisions 2, 3, 5, 6, 7, 9, and 11 are
approved because they materially affect schema and authorization design.

## 22. Acceptance criteria

The feature is ready for approval only when all of the following are true:

- every aggregation and record has exactly one valid owning org unit;
- database rules prevent mixed-workspace containment;
- ordinary creation derives ownership without accepting a client override;
- a user can enter only workspaces supplied by currently effective roles;
- every governed read and mutation path enforces selected workspace scope;
- role expiry removes workspace access without ACL modification;
- restored eligibility restores only the access allowed by all remaining
  authorization gates;
- governance cross-scope is explicit, privileged, clearance-aware, and audited;
- transfers are previewed, reasoned, atomic, and historically reconstructable;
- search and navigation do not leak resources from another workspace;
- no-workspace users cannot access governed content;
- migrations leave no unresolved or inconsistent ownership; and
- canonical schema, upgrade migration, API behaviour, UI behaviour,
  documentation, and automated tests agree.

