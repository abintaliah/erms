# Security and authorization implementation — Phase 5

Status: implemented and verified

This phase establishes persistent aggregation and record ACLs, live parent-default inheritance, the synthetic Everyone principal, dependency enforcement, impact previews, and custody safeguards. It deliberately does not filter general resource reads; non-disclosing read enforcement begins in Phase 6.

## Permission catalogue and grant storage

Migration 034 installs the approved 14 aggregation permissions and 16 record permissions together with their transitive dependencies. Four FK-safe grant tables keep resource ACLs separate from the two aggregation child-default templates:

- aggregation resource ACL grants;
- aggregation default child-aggregation grants;
- aggregation default child-record grants; and
- record resource ACL grants.

Every grant is an allow grant addressed either to one real role or to the explicit synthetic `everyone` principal. Database checks and API models make user principals, organizational-unit principals, deny entries, fabricated Everyone role IDs, and ambiguous principal shapes impossible. Role foreign keys use restrictive deletion.

`Everyone` is not seeded as a role and cannot be created as a role name or code. It supplies only an ACL permission; it supplies no global privilege, effective role, or security clearance.

## Initialization and inheritance

Every new local resource override and every custom child template is initialized with Everyone and every valid permission for its resource type. This is an initialization default, not a permanent grant.

Root aggregations use their local resource ACL. Non-root aggregations and records default to `inherit_acl_from_parent=true`; their initialized local override remains stored but dormant. Effective resolution never merges inherited and local grants.

An aggregation's default child-aggregation mode is one of:

- `mirror_resource_acl`, which live-references that aggregation's current effective resource ACL; or
- `custom`, which uses its stored child-aggregation template.

Mirroring propagates through arbitrarily deep inheriting branches. A local resource override or custom-template mode forms an explicit boundary. Switching a custom template back to mirror mode retains the custom grants, version, and audit history in a dormant state. Default child-record ACLs are independent record-permission templates because aggregation and record permissions are intentionally different catalogues.

## Permission dependencies and clearance

The editor automatically closes the selected permission set over all prerequisites. The API accepts only a complete desired set and rejects missing prerequisites with the stable `permission_dependency_violation` code. Deferred database constraint triggers independently enforce the same invariant at transaction commit, allowing rows to be replaced in any order without permitting an invalid final state.

The database also verifies that a permission belongs to the correct aggregation or record catalogue. Role grants whose role clearance is below the protected resource level are rejected. If a role is lowered later, its existing stored grants remain dormant rather than being destroyed.

## Atomic APIs and concurrency

Nested endpoints expose resource ACLs and both aggregation child defaults. Responses explicitly distinguish effective, inherited, local-override, custom, mirrored, and dormant state and expose independent optimistic-concurrency versions.

Bulk replacement is transactional. A stale ACL version returns `409`; invalid dependencies, principals, permission types, and clearance combinations roll back without changing grants or versions. Parent-default preview endpoints report grant additions/removals, recursively affected aggregation and record counts, and potentially affected users before the UI asks for confirmation.

Default changes lock the affected inheriting resources while applying, preventing hierarchy and inheritance changes from interleaving with the calculation. Move-preview and transactional move endpoints support both approved choices:

- continue inheriting from the destination; or
- preserve current effective access as a new local override.

The latter captures the current effective ACL and changes the parent and inheritance mode in one transaction.

## Custody continuity and auditing

ACL and default-template changes are rejected when the resource has no active person assigned to an effective information-governance role with sufficient clearance and the global authorization-administration capability. This preserves a human governance custodian even when ordinary ACL access is restricted.

Grant tables have immutable event-history triggers. Semantic bulk changes additionally record reasoned `ACL_REPLACED`, default-child ACL replacement, and move-policy events. Dormant grants never participate in effective resolution or custody decisions.

## Web UI

Aggregation and record details now expose an Access editor. Aggregations additionally expose editors for child-aggregation and child-record defaults. The editor:

- explains the limited meaning of Everyone;
- distinguishes inheritance and dormant overrides;
- exposes mirror versus custom child-aggregation mode;
- adds permission prerequisites interactively;
- requires a change reason;
- previews inherited impact before confirmation; and
- submits the complete ACL atomically.

## Verification

The complete database and API gate ran against a newly created disposable PostgreSQL database, which the harness removed cleanly afterward. It verifies:

- the complete permission catalogue and Everyone/all initialization;
- rejection of direct user/org grants, deny grants, fabricated Everyone roles, duplicates, wrong permission types, and insufficient role clearance;
- live parent-default changes and multi-level mirror propagation;
- custom-template boundaries and retained dormant templates/overrides;
- API and deferred-database dependency closure;
- optimistic concurrency and atomic rollback;
- recursive impact preview and move-time inherit-versus-override behavior;
- custody/orphan prevention; and
- ACL and template audit history.

The disposable database/API suite passed 155 tests. The Web UI suite passed 65 tests. Python compilation, policy-inventory regeneration, canonical/upgrade schema parity, and diff validation also passed.

## Deliberately deferred

Phase 5 stores and resolves ACL policy but does not yet use it to hide aggregations, records, components, histories, search results, counts, favourites, breadcrumbs, or tree nodes. Phase 6 applies clearance and effective ACL predicates consistently across every read and discovery path with approved `404` non-disclosure behavior.
