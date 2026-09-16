# Classification Scheme Subsystem — Technical Specification

**Status:** Approved — implementation baseline  
**Project:** ERMS  
**Prepared:** 16 September 2026  
**Revision:** 0.3 — root-only aggregation retention and disposition confirmed  
**Implementation state:** Implemented in migration 019, FastAPI, and NiceGUI

## 1. Purpose

This specification defines the classification-scheme subsystem for ERMS. It
covers classification schemes, hierarchical branch and terminal
classifications, inheritable retention rules, root-aggregation assignment,
search, recent selections, administration UI, aggregation UI, audit history,
migration of existing data, and automated testing.

The subsystem must preserve its business rules when data is changed outside the
NiceGUI application. PostgreSQL is therefore the final enforcement boundary;
FastAPI and NiceGUI provide validation, workflow, and presentation in addition
to—not instead of—database enforcement.

## 2. Scope

This iteration includes:

- Multiple simultaneously active classification schemes.
- Draft, published, deactivated, and reactivated schemes.
- Unlimited-depth classification hierarchies.
- Explicit branch and terminal classification types.
- Optional classification-owned retention rules with nearest-ancestor
  inheritance and child overrides.
- Optional root-aggregation-owned local retention rules that override the
  classification-derived rule for the root disposition unit.
- Mandatory effective retention rules for terminal classifications.
- Mandatory terminal-classification assignment for root aggregations.
- Classification search and lazy tree browsing.
- Per-user recent classification selections.
- Effective-retention-rule presentation for classifications and aggregations.
- REST APIs, NiceGUI administration, audit history, tests, and documentation.

The following remain outside this iteration:

- Retention trigger events, calculated disposal dates, disposal freezes,
  review workflows, transfer packages, destruction approval, or execution.
- Authorization beyond the current authenticated-system-administrator behavior.
- Service-account authentication.
- User, role, and organizational-unit lifecycle normalization. That work is a
  separate post-classification migration and has a milestone reminder.

## 3. Domain terminology

### 3.1 Classification scheme

A governed hierarchy of classifications issued by an authority. More than one
scheme may be active and published at the same time.

### 3.2 Branch classification

A structural classification that may contain child classifications. It is not
assignable to an aggregation. A branch may temporarily have no children while
administrators construct the tree.

### 3.3 Terminal classification

An assignable classification that cannot contain child classifications. A root
aggregation may only be assigned to a terminal classification.

### 3.4 Direct retention rule

A retention rule owned by the classification on which it is defined. It is not
reusable by, or directly attached to, another classification.

### 3.5 Effective retention rule

The nearest retention rule found by starting at a classification and walking
up its ancestor chain. A direct child rule overrides an inherited ancestor
rule. Inheritance never crosses a classification-scheme boundary.

### 3.6 Local aggregation retention rule

An optional rule owned by exactly one root aggregation. It overrides the rule
derived from the root aggregation's classification. It governs disposition of
that root aggregation as one disposition unit, including its descendants, but
is never copied or independently assigned to child aggregations. A child cannot
own a local retention rule.

## 4. Lifecycle semantics

### 4.1 No redundant scheme status

Classification schemes shall not have a separate `status` column.

```text
date_deactivated IS NULL     => active
date_deactivated IS NOT NULL => inactive
```

`date_deactivated` must not be in the future or precede `date_created`. Clearing
it reactivates the scheme.

### 4.2 Publication

`date_published` is nullable while a scheme is a draft. A scheme is available
for ordinary selection only when:

```text
date_deactivated IS NULL
AND date_published IS NOT NULL
AND date_published <= CURRENT_TIMESTAMP
```

A future `date_published` is permitted as scheduled publication but the scheme
remains unavailable until that time. Clearing or moving the publication date
into the future makes the scheme unavailable for new assignments without
altering existing assignments.

### 4.3 Deactivation effects

Deactivating a scheme:

- Does not deactivate or rewrite its classifications.
- Does not remove or change existing aggregation assignments.
- Does not impair normal operation of existing aggregations, records, or
  digital components.
- Prevents new assignment or reclassification into any classification in the
  scheme.
- Removes the scheme and its classifications from ordinary selectors and
  recent-selection results.
- Leaves it visible in administration and audit interfaces.

## 5. Data model

All mutable first-class tables use `bigserial` primary keys, database-managed
optimistic-concurrency `version`, and event-history triggers consistent with
the existing project.

### 5.1 `classification_schemes`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `code` | `text` | Required, nonblank, globally case-insensitive unique |
| `title` | `text` | Required, nonblank |
| `description` | `text` | Optional |
| `authority` | `text` | Optional issuing/approving authority |
| `scope_note` | `text` | Optional coverage and application statement |
| `edition` | `text` | Optional edition/revision label |
| `date_created` | `timestamptz` | Automatically assigned |
| `date_updated` | `timestamptz` | Automatically maintained |
| `date_published` | `timestamptz` | Nullable; may be scheduled in the future |
| `date_deactivated` | `timestamptz` | Nullable; cannot be future or before creation |
| `version` | `bigint` | Positive optimistic-concurrency value |

Deletion is restricted while classifications exist. Operationally used schemes
should be deactivated rather than deleted.

### 5.2 `classifications`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `classification_scheme_id` | `bigint` | Required scheme, `ON DELETE RESTRICT` |
| `parent_classification_id` | `bigint` | Nullable self-reference, `ON DELETE RESTRICT` |
| `code` | `text` | Required; case-insensitive unique within scheme |
| `title` | `text` | Required, nonblank |
| `description` | `text` | Optional |
| `authority` | `text` | Optional classification-specific authority |
| `scope_note` | `text` | Optional applicability guidance |
| `keywords` | `text` | Optional discovery terms |
| `is_terminal` | `boolean` | Required; defaults to `false` |
| `date_created` | `timestamptz` | Automatically assigned |
| `date_updated` | `timestamptz` | Automatically maintained |
| `version` | `bigint` | Positive optimistic-concurrency value |

Rules:

- A parent must belong to the same scheme.
- A classification cannot be its own parent or ancestor.
- Hierarchy depth has no configured business limit.
- `is_terminal = false` permits children and prohibits aggregation assignment.
- `is_terminal = true` prohibits children and permits root-aggregation
  assignment if all other eligibility rules pass.
- Branch-to-terminal conversion requires no children and an effective rule.
- Terminal-to-branch conversion requires no assigned aggregations.
- Reparenting cannot move a classification between schemes.
- Deletion is restricted while children or aggregation assignments exist.

The UI must not rely on color alone to distinguish types:

- Branch: Material icon `account_tree`, label “Branch”.
- Terminal: Material icon `label`, label “Terminal”.

The icons must be used consistently in tree nodes, cards, search results,
breadcrumbs, and selector results, with accessible tooltips or text.

### 5.3 `classification_retention_rules`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `classification_id` | `bigint` | Required, unique, `ON DELETE CASCADE` |
| `current_period_years` | `integer` | Required, nonnegative |
| `intermediate_period_years` | `integer` | Required, nonnegative |
| `final_disposition` | `text` | Controlled values below |
| `instructions` | `text` | Optional detailed retention/disposal instructions |
| `date_created` | `timestamptz` | Automatically assigned |
| `date_updated` | `timestamptz` | Automatically maintained |
| `version` | `bigint` | Positive optimistic-concurrency value |

Controlled `final_disposition` values:

```text
destruction
transfer_to_external_archive
selective_preservation
retain_as_local_archives
```

A classification may own zero or one rule. Deleting a classification cascades
to its rule. Rules are not reusable.

### 5.4 `aggregation_retention_rules`

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `aggregation_id` | `bigint` | Required, unique, `ON DELETE CASCADE` |
| `current_period_years` | `integer` | Required, nonnegative |
| `intermediate_period_years` | `integer` | Required, nonnegative |
| `final_disposition` | `text` | Same controlled values as classification rules |
| `instructions` | `text` | Optional detailed retention/disposal instructions |
| `justification` | `text` | Required, nonblank reason for the local override |
| `date_created` | `timestamptz` | Automatically assigned |
| `date_updated` | `timestamptz` | Automatically maintained |
| `version` | `bigint` | Positive optimistic-concurrency value |

A root aggregation may own zero or one local rule. A child aggregation may own
none. The rule is not reusable and is deleted automatically with its root
aggregation. A deferred database constraint enforces that its owner remains a
root, allowing hierarchy changes and rule removal to be performed atomically.
Creating, changing, or removing a local rule requires a nonblank change reason
because it changes disposition governance. Removing the local rule immediately
restores the root's classification-derived effective rule.

Local rules may be used later by an authorized records administrator during
disposition review to prolong an aggregation's retention or prevent the
classification-derived disposition from applying. This iteration stores and
displays the override but does not calculate disposal dates or execute a
disposition workflow. Formal legal/regulatory holds remain a future,
separately-modelled capability rather than being hidden inside unusually large
retention periods.

### 5.5 `user_classification_selections`

| Column | Type | Rules |
| --- | --- | --- |
| `user_id` | `bigint` | Part of primary key; user reference |
| `classification_id` | `bigint` | Part of primary key; classification reference |
| `last_selected_at` | `timestamptz` | Last committed assignment time |
| `selection_count` | `bigint` | Positive usage count |

This is compact user preference state, not audit history. It is updated only
after a successful committed root-aggregation assignment or reclassification.
Opening, highlighting, or cancelling a selector does not count as a selection.

## 6. Retention inheritance and validation

The database shall provide an effective-rule resolver returning both the rule
and its provenance:

```text
effective_retention_rule(classification_id)
    => rule_id
       defined_by_classification_id
       inheritance_depth
```

The first rule encountered from the classification toward its root wins.

Every terminal classification must have an effective rule. It need not own a
direct rule. A deferred database constraint validates the invariant at
transaction commit so a terminal classification and direct rule can be created
atomically.

Validation is required after:

- Creating or updating a terminal classification.
- Reparenting a classification subtree.
- Creating, updating, or deleting a retention rule.
- Deleting or moving an ancestor that supplies an inherited rule.

Deleting a rule is rejected if any terminal descendant would be left without
an effective rule.

Reparenting a terminal classification or subtree can change effective rules.
The API must compute and return an impact preview. The UI must show old and new
rule provenance, the count of affected terminal classifications and assigned
aggregations, and require a change reason before committing. The database
rejects a move that leaves any terminal descendant without an effective rule.

For an aggregation, resolution is:

1. Find its root aggregation. For a root, this is itself.
2. Use the root aggregation's local rule when present.
3. Otherwise resolve the nearest direct or inherited rule from the root's
   assigned terminal classification.

The result includes `governing_root_aggregation_id`. For a child, the returned
rule is informational context: disposition acts on the governing root and not
on the child independently.

## 7. Aggregation classification

Add nullable `classification_id` to `aggregations`, referencing
`classifications(id) ON DELETE RESTRICT`.

The following invariant is database-enforced:

```text
parent_aggregation_id IS NULL  <=>  classification_id IS NOT NULL
```

In addition:

- A root aggregation may only reference a terminal classification.
- For a new assignment or changed classification, the scheme must be active
  and currently published.
- The classification must have an effective retention rule.
- A child aggregation must store no classification ID.
- A child aggregation must not own an aggregation retention rule.
- Moving a child to root requires an eligible classification in the same
  transaction.
- Moving a root beneath another aggregation requires clearing its
  classification and removing any local aggregation retention rule in the same
  transaction.
- An unchanged assignment under a subsequently inactive/unpublished scheme
  remains valid and operational.

The database, API, record-draft commit path, and UI must all observe these
rules. Classification does not propagate by copying IDs into child rows.

## 8. Aggregation retention presentation

Every aggregation detail view and edit/view dialog shall display the rule that
governs its root disposition unit:

- Effective retention periods.
- Final disposition label.
- Detailed instructions when present.
- The aggregation or classification that supplies the rule.
- A provenance badge and explanatory text.

Provenance has three independent parts:

1. **Classification assignment provenance**
   - Root: directly assigned to its terminal classification.
   - Child: classification context inherited from its root aggregation.
2. **Root aggregation override provenance**
   - Local override: defined specifically for the governing root aggregation.
   - No local override: resolve through classification context.
3. **Classification-rule provenance when no local override exists**
   - Direct: defined on that terminal classification.
   - Inherited: defined on an ancestor classification, whose code and title are
     displayed.

Example presentation:

```text
Effective retention
7 years current · 3 years intermediate · Destruction

Classification inherited from root aggregation AGG-001
FIN-AP-INV — Supplier Invoices

Rule inherited from FIN — Finance
```

For a local override on the root, the presentation instead states:

```text
Local root-aggregation retention rule
10 years current · 5 years intermediate · Retain as local archives

Overrides the rule inherited from FIN-AP-INV — Supplier Invoices
Reason: Extended during disposition review
```

The root aggregation UI provides create, edit, and remove-local-rule actions
with confirmation, change-reason capture, `If-Match` concurrency, and a
comparison against the classification-derived rule. Child aggregation views
provide no such controls. These controls are available before the future
authorization subsystem, but the specification records that they must later be
restricted to appropriately privileged records-administration roles.

## 9. Database enforcement

The canonical schema and migration shall provide reusable functions/triggers
for:

- Classification cycle prevention.
- Same-scheme parent enforcement.
- Branch/terminal structural enforcement.
- Scheme assignment eligibility.
- Effective retention-rule resolution.
- Root-only aggregation-local rule enforcement, precedence, disposition-unit
  resolution, and provenance.
- Deferred terminal-rule validation.
- Root/child aggregation classification enforcement.
- Recent-selection upsert from authenticated transaction context.
- Optimistic-concurrency version increments.
- Audit event capture.

Database errors must be mapped by FastAPI to stable HTTP 409 or 422 responses
with user-facing explanations rather than generic database failures.

## 10. Existing aggregation migration

Existing root aggregations currently have no classification. The migration must
not fabricate a legal retention rule or silently assign a generic
“Unclassified” schedule.

Rollout is staged:

1. Add subsystem tables, functions, APIs, and nullable aggregation reference.
2. Add the root/child constraint as `NOT VALID`. PostgreSQL enforces it for new
   and changed rows without pretending legacy roots already comply.
3. Provide an administrative report/search for legacy unclassified roots.
4. Create and publish the real classification scheme and classifications.
5. Classify every legacy root through an explicit administrative operation.
6. Validate the constraint across all rows.

The canonical `schema.sql` for a genuinely new database contains the fully
validated invariant immediately.

## 11. REST API

Resources:

```text
/api/v1/classification-schemes
/api/v1/classifications
/api/v1/classification-retention-rules
/api/v1/aggregation-retention-rules
```

Required operations include:

- Standard scheme CRUD with `If-Match` concurrency.
- Publish, deactivate, and reactivate scheme actions.
- Standard classification CRUD with `If-Match` concurrency.
- Transactional classification creation with an optional direct rule.
- Direct-rule create/update/delete.
- Lazy children query by scheme and `parent_classification_id`.
- Ancestor/path endpoint for breadcrumbs.
- Effective-rule endpoint with provenance.
- Reparent impact-preview and commit operations.
- Eligible published-scheme and classification queries.
- Current authenticated user’s recent eligible classifications.
- Aggregation effective-retention endpoint with full provenance.
- Aggregation-local-rule create, update, and delete operations requiring a
  change reason and `If-Match` where applicable; child targets return 422.
- Entity event-history endpoints.

Administrative endpoints may expose drafts and inactive schemes. Selector
endpoints must enforce eligibility server-side and never trust client filtering.

## 12. Search and wildcard matching

Classification schemes, classifications, and retention rules shall be added to
the controlled search registry. Classification searchable fields include:

- `id`
- `classification_scheme_id`
- `parent_classification_id`
- `code`
- `title`
- `description`
- `authority`
- `scope_note`
- `keywords`
- `is_terminal`
- creation/update dates

The existing `contains_ci`, `starts_with_ci`, and `ends_with_ci` operators remain
literal and safe. A new controlled text operator `matches_ci` remains available
in the API search grammar for advanced and future clients:

- `*` — zero or more characters.
- `?` — exactly one character.

The compiler must escape SQL `%`, `_`, and backslash before translating `*` and
`?`, use parameters rather than SQL interpolation, and retain the grammar’s
depth, condition-count, and value-length limits.

The selector’s simple search always applies case-insensitive literal containment
with `contains_ci`, ORed across code, title, and description. Users do not need
to enter wildcard characters. The selector does not automatically switch to
`matches_ci`; advanced clients may select that operator explicitly.

## 13. Configurable recent selections

Add to `.env.example` and API configuration:

```dotenv
CLASSIFICATION_RECENT_SELECTION_LIMIT=4
```

- Default: `4`.
- Minimum: `1`.
- Maximum: `20`.
- Controlled by the API; the UI does not maintain a competing hard-coded
  number.
- Results are scoped to the authenticated user and filtered to currently
  eligible terminal classifications.

The UI section is titled “Recently used” so changing the configured count does
not require wording changes.

## 14. NiceGUI administration UI

Add one **Classification Schemes** workspace under **Records Management** using
the classification-scheme icon previously reserved when aggregation icons were
changed to folders. Classifications do not have a second top-level navigation
entry: they are administered in the context of their scheme.

The workspace uses a vertically stacked master-detail layout:

- A fixed-height top panel lists and filters schemes, provides scheme creation,
  and scrolls vertically when required. Scheme cards lay their information out
  horizontally to use the available width.
- Selecting a scheme loads its classification hierarchy and details in the
  full-width panel below.
- Root classifications load with scheme selection; direct children load only
  when a branch is expanded.
- **Add root** fixes the selected scheme as context.
- **Add child** fixes both the selected scheme and selected branch as context;
  terminals cannot expose this action.
- Selecting a classification presents its path, metadata, effective retention
  rule, provenance, and contextual actions.
- Complete scheme and classification metadata is presented read-only without
  opening an edit dialog. Retention instructions and inheritance provenance are
  part of this view; future update authorization may remove Edit without
  removing permitted read access.
- Codes must be displayed in full. Description and scope-note values span the
  full detail-card width in multi-line, vertically scrollable regions.
- A root classification has no parent, so its Parent classification value is
  empty (`—`), not the misleading text “Root classification”. Tree nodes reserve
  a consistent expander column so their type icons align by hierarchy depth.
- Search results can focus their scheme and expand their ancestor path.

Scheme administration provides:

- Draft/published and active/inactive indicators derived from dates.
- Publish, unpublish/reschedule, deactivate, and reactivate actions.
- Metadata editing.
- Lazy-loaded arbitrary-depth classification tree.
- Breadcrumbs.
- Branch/terminal icons, text labels, and tooltips.
- Add-child only on branch classifications.
- Classification and direct-rule editing.
- Effective-rule and inheritance presentation.
- Warnings for incomplete branches and terminal validation failures.
- Search/filter view.
- Event-history actions.

## 15. Aggregation selector UI

Root aggregation creation and editing uses a purpose-built selector rather than
a generic numeric lookup. It has three modes.

### 15.1 Browse

- Shows all active, currently published schemes.
- Lazy-loads root classifications and children.
- Allows expansion of branches but selection only of terminals.
- Shows type icon, code, title, description, scheme, hierarchy path, and
  effective retention summary.

### 15.2 Search

- Searches code, title, and description.
- Uses automatic literal partial matching without requiring wildcard syntax.
- Shows scheme, hierarchy path, type, code, title, description, and effective
  retention provenance.
- Returns only eligible terminals.

### 15.3 Recently used

- Shows the configured number of the current user’s most recent committed
  selections.
- Automatically excludes classifications in inactive/unpublished schemes or
  classifications that are no longer terminal.

When an existing root uses a now-ineligible scheme, its current classification
remains visible with an explanatory warning and may remain unchanged. Once the
user changes away from it, it cannot be selected again while ineligible.

Child aggregation forms do not provide an editable selector. They display the
governing root aggregation, inherited classification context, and root
disposition rule as read-only information. They explicitly state that
disposition acts on the root aggregation, not the child independently.

Every root aggregation detail view also provides a clearly separated **Local
retention override** panel. When absent, it says which classification rule is
effective. When present, it displays the local rule prominently, shows the
classification-derived rule it supersedes, and provides edit/remove actions.
Child aggregation views show the same governing information without local-rule
actions.

## 16. Audit history

Automatic immutable history covers schemes, classifications, and retention
rules. Domain events include:

```text
CLASSIFICATION_SCHEME_PUBLISHED
CLASSIFICATION_SCHEME_DEACTIVATED
CLASSIFICATION_SCHEME_REACTIVATED
CLASSIFICATION_REPARENTED
RETENTION_RULE_CHANGED
AGGREGATION_RETENTION_RULE_CREATED
AGGREGATION_RETENTION_RULE_CHANGED
AGGREGATION_RETENTION_RULE_REMOVED
AGGREGATION_CLASSIFIED
AGGREGATION_RECLASSIFIED
```

Events snapshot human-readable scheme/classification code and title, hierarchy
path, old/new effective rule provenance, actor identity, reason, source, and
correlation context. Audit UI must not present opaque IDs as the primary label.

## 17. Testing

All database and API tests use the existing disposable PostgreSQL environment
and are torn down after the suite.

Required coverage:

- Fresh canonical schema and full migration chain.
- Multiple active/published schemes.
- Draft, scheduled, inactive, and reactivated scheme behavior.
- Date validation and derived lifecycle state.
- Arbitrary-depth hierarchy creation.
- Cycle and cross-scheme-parent rejection.
- Branch/terminal creation and transitions.
- Child-under-terminal rejection.
- Direct, inherited, and overridden classification rules.
- Root aggregation local-rule creation, update, removal, precedence, cascade
  deletion, required reasons, and optimistic concurrency.
- Child local-rule rejection through both API and direct SQL.
- Root local-rule governance of child display context without storing or
  independently executing a rule on the child.
- Deferred terminal effective-rule enforcement.
- Rule deletion impact on terminal descendants.
- Rule cascade on classification deletion.
- Classification/scheme deletion restrictions.
- Root aggregation mandatory classification.
- Child aggregation classification prohibition.
- Root-to-child moves requiring atomic removal of both classification and local
  aggregation rule; child-to-root moves with an eligible classification and an
  optional newly created local rule.
- Root/child hierarchy transitions.
- Existing assignments surviving scheme ineligibility.
- Reparent impact preview and validation.
- Literal partial and wildcard search, including escaping tests.
- Per-user recent-selection isolation and configured limits.
- Optimistic-concurrency conflicts.
- Audit snapshots and domain events.
- NiceGUI branch/terminal rendering, lazy loading, browse/search/recent selector
  behavior, inactive assignment display, and aggregation retention display.

## 18. Documentation deliverables

Implementation updates or creates:

- `docs/classification-schemes.md`
- `docs/search-grammar.md`
- `docs/event-history.md`
- `database/README.md`
- `frontend/webui/README.md`
- `.env.example`

The final operational documentation must distinguish direct classification
assignment, inherited classification context, direct classification rule,
inherited classification rule, and a local aggregation override.

## 19. Acceptance criteria

The subsystem is complete only when:

1. This specification is approved.
2. Database constraints protect all hierarchy, terminal, retention, scheme,
   and aggregation invariants from direct SQL as well as API use.
3. Existing roots are explicitly classified and the final constraint validates.
4. API and NiceGUI workflows implement the specified behavior.
5. Effective rule and provenance are visible for every aggregation.
6. Search, recent selections, audit history, and concurrency are tested.
7. Disposable-database, API, frontend, and applicable browser tests pass.
8. User and technical documentation is complete.
9. The classification subsystem changes are committed to git.

Only after item 9 is satisfied does the separate user/role/org-unit lifecycle
cleanup reminder become actionable.
