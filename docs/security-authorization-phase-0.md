# Security and authorization — Phase 0 baseline

Phase 0 freezes the application surface before authorization enforcement is
introduced. It deliberately changes no runtime authorization decision.

The approved specification is
[`specs/security-and-authorization-subsystem.md`](../specs/security-and-authorization-subsystem.md),
revision 0.6.

## Machine-readable artefacts

- [`security/operation-policy-registry.json`](../security/operation-policy-registry.json)
  inventories every FastAPI operation at the authoritative authorization
  boundary. Client controls are deliberately outside this registry.
- [`security/catalogue-seed.json`](../security/catalogue-seed.json) freezes the
  approved initial security levels, global privileges, aggregation and record
  permissions, permission dependencies, and initial profiles. It is a Phase 0
  policy artefact; Phase 1 and Phase 2 will turn the relevant portions into
  canonical database seeds.

The operation registry records both the current access class and the intended
policy class. `phase_0_enforced` is false throughout: target privilege and
permission fields document future enforcement hooks and do not grant or deny
access yet.

The current access classes are:

| Class | Current meaning |
| --- | --- |
| `public` | Callable without a login; currently health and login only |
| `authenticated_only` | The global authentication middleware is the only access gate |
| `system_administrator` | Existing hard-coded System Administrator dependency |
| `globally_privileged` | Future global-privilege gate; not enforced in Phase 0 |
| `resource_scoped` | Future privilege, clearance, lifecycle, and ACL gates; not enforced in Phase 0 |

## Completeness guard

Run the generator after deliberately adding or removing an API route, or
changing an operation's policy classification:

```bash
PYTHONPATH=. backend/services/api/.venv/bin/python tools/generate_policy_inventory.py
```

The resulting diff must be reviewed as a security-policy change. The Phase 0
test regenerates the inventory in memory and fails when it differs from the
committed file. This prevents a new API operation from silently escaping the
inventory. Moving, renaming, or adding client controls does not create an API
policy change and therefore does not churn this artefact.

### Ownership and review workflow

The registry is a generated JSON source-control artefact, not a database table
and not a runtime authorization mechanism. Its generator is
`tools/generate_policy_inventory.py`; its output is
`security/operation-policy-registry.json`; and
`backend/services/api/tests/test_policy_inventory.py` is the completeness
guard that compares the committed JSON with freshly generated output.

The developer or coding agent that deliberately changes an API route or its
policy classification must:

1. implement the real authorization check in the API and, where applicable,
   the database;
2. run the generator command above;
3. inspect the JSON diff and confirm that every added, removed, or reclassified
   operation has the intended privilege and resource permission; and
4. submit that diff with the implementation for review.

The reviewer is the person responsible for accepting the code change—during
interactive development this may be the project owner reviewing the coding
agent's work; in a team workflow it is the designated code/security reviewer.
Regeneration is mechanical and may be performed by a person or an AI coding
agent. Review is a judgment step and must not be treated as complete merely
because the generator ran or the JSON changed.

The registry is defence-in-depth for visibility, traceability, and regression
detection. It does not grant or deny access. Runtime enforcement remains in the
API authorization functions and database integrity rules.

### Client applications

NiceGUI, Flutter, and any future frontend are untrusted API consumers. They do
not receive separate copies of the authorization policy and cannot grant access
by rendering a control. Every request is re-authorized by the API against live
roles, privileges, clearance, ACLs, lifecycle state, and integrity rules.

A client may maintain an optional action inventory for UX coverage—for example,
to check that destructive actions handle `403`, `409`, and stale-policy
responses—but that inventory is not security evidence and is not part of this
registry. Client-only changes require ordinary product review, not API policy
approval. A client change requires security review when it also adds or
reclassifies an API operation.

## Characterized existing behavior

The baseline preserves and tests the existing behavior for:

- public health and login operations;
- authentication required for business, identity, and audit APIs;
- aggregation and record lifecycle and hierarchy behavior;
- closed-aggregation restrictions;
- record-draft ownership and commit behavior;
- event-history generation and filtering;
- user, role, organizational-unit, session, classification, favourite, browse,
  retention, and digital-component operations; and
- optimistic concurrency and rollback behavior already covered by the
  regression suite.

All database-backed verification must use the disposable PostgreSQL environment
created and destroyed by `database/tests/run.sh`. The development database must
never be used for this verification.

## Phase 0 verification record

**Result:** GO — Phase 0 verification passed on 19 September 2026. Work must
pause for review before Phase 1 begins.

Tests and checks performed:

- deterministic regeneration of the registry: 136 API operations and 155 Web
  UI actions;
- JSON parsing and catalogue referential-consistency checks;
- Python syntax compilation for the API, Web UI, tests, and inventory tool;
- complete database and API suite through `database/tests/run.sh`: **90
  passed** against a newly created disposable PostgreSQL container database;
- complete frontend unit suite: **60 passed**; and
- `git diff --check`: passed.

The first disposable-database run produced one failure in the new registry
test because FastAPI's generated operation ID for a GET/HEAD route depended on
unordered method iteration. No existing regression test failed. The registry
identifier was changed to the stable canonical form `METHOD:path`; the complete
suite was then rerun successfully. The disposable test container was removed by
the test runner after each run, including the failed run.

Remaining Phase 0 limitations and risks:

- This phase inventories intended policy hooks but deliberately enforces none
  of them. Existing authenticated-only and hard-coded System Administrator
  behavior remains unchanged.
- The approved catalogue is machine-readable policy data, not database data.
  Phase 1 seeds security levels; Phase 2 seeds privileges and profiles.
- UI inventory identifiers contain source line numbers. Refactoring an
  interactive control intentionally requires regeneration and security review,
  even when its visible behavior is unchanged.
- FastAPI currently emits duplicate generated-operation-ID warnings for the
  GET/HEAD component content and rendition routes. The Phase 0 registry does
  not rely on those generated identifiers, but the warning should be cleaned up
  during later API maintenance.
