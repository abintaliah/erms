# Classification schemes and retention rules

The classification subsystem organizes root aggregations under one or more
governed file plans and resolves the retention rule that applies to each
aggregation hierarchy. Its approved design is recorded in
[`../specs/classification-scheme-subsystem.md`](../specs/classification-scheme-subsystem.md).

## Classification scheme lifecycle

A scheme is active while `date_deactivated` is null. It is selectable only when
it is both active and published (`date_published` is not null and is not in the
future). A future publication timestamp schedules availability. Deactivation
does not change existing classifications, aggregation assignments, records, or
digital components; it only prevents new assignments or moves into that scheme.
Reactivation clears `date_deactivated`. Deactivation and reactivation require a
change reason and are written to the immutable event history.

Publication may be reversed only while a scheme remains unused. The explicit
**Unpublish** action clears `date_published`, requires a reason, and records the
change in event history. It exists to correct accidental or premature
publication; it is not a way to withdraw a scheme that has already governed
records.

PostgreSQL sets the immutable `date_first_used` timestamp the first time a root
aggregation is assigned to any classification in the scheme. Publication by
itself does not set this value. Once set, the scheme cannot be unpublished or
hard-deleted, even if all affected aggregations are subsequently moved or
deleted. This preserves the historical governance context. Such a scheme must
be deactivated when it should no longer accept assignments.

## Classification lifecycle

A classification is directly active while its own `date_deactivated` is null.
For a new assignment it must also be *effectively active*: its scheme and every
classification in its ancestor path must be active. Deactivating a branch
makes its complete subtree unavailable for new aggregation assignments without
rewriting descendant rows. A descendant can still have an independent direct
deactivation; reactivating its ancestor does not clear that state. The UI
distinguishes **Inactive**, **Inactive via ancestor**, and **Inactive via
scheme**.

Classification deactivation is prospective. Existing assignments remain intact
and continue resolving the same classification and retention rules. Deactivate
and reactivate operations require a reason and current version and are audited.

On first assignment, PostgreSQL permanently records `date_first_used` on the
selected terminal, every ancestor in its path, and its scheme. Ancestors count
as historically used because they supplied governance context and may have
supplied inherited retention. Reassignment or deletion of the aggregation does
not clear these markers.

## Branches, terminals, and hierarchy

Classifications have unlimited hierarchy depth and are explicitly one of:

- Branch (`account_tree`): may contain children and cannot be assigned to an
  aggregation.
- Terminal (`label`): cannot contain children and may be assigned to a root
  aggregation when it has an effective retention rule.

A parent and child must belong to the same scheme. Cycles and children beneath
a terminal classification are rejected by PostgreSQL, including writes that
bypass the API.

## Retention rules

A classification may define zero or one rule. The effective classification rule
is the nearest direct rule found while walking from that classification toward
the root. A child rule overrides an ancestor rule. Every terminal must have a
direct or inherited effective rule; this is checked at transaction commit so an
administrator can create a terminal and its rule atomically.

A root aggregation may additionally define one local rule, with a mandatory
justification. It overrides the classification-derived rule for the complete
root disposition unit. Child aggregations can never own classifications or local
retention rules. Their UI therefore presents the governing root's effective rule
read-only. No disposal dates or disposition execution are performed in this
iteration.

## Assignment rules

Every newly created or structurally changed root aggregation must reference one
eligible terminal classification. Child aggregations must have
`classification_id = NULL`. Existing root aggregations predating migration 019
are intentionally not assigned invented classifications; the database check is
staged as `NOT VALID`, while triggers enforce all new changes immediately.

For the greenfield development database, migration 020 explicitly remediates
those legacy roots to `100-10 — General` in `TESTCS — Test Classification
Scheme`. Every affected aggregation receives a normal immutable UPDATE event
with source `migration`, actor type `automated_process`, an explicit backfill
reason, and structured metadata identifying the migration, authorization basis,
scheme, and classification. The migration then validates the deferred
root-classification invariant.

Migration 021 provides a realistic demonstration scheme for an electricity and
water utility. `EWA-FCS — Electricity and Water Authority Functional
Classification Scheme` contains 52 classifications arranged as four roots,
twelve branches and thirty-six assignable terminals. Every terminal has its own
documented retention rule, with periods and final actions tailored to the
business function. The seed is development-only, idempotent, and fully audited
as an automated migration.

Migration 024 provides a complementary general corporate scheme. `GCS — General
Classification Scheme` contains 52 classifications: four roots for
Administration, Human Resources, Finance and Asset Management; twelve child
branches; and thirty-six terminal classifications. Each terminal has a
function-specific retention rule and detailed disposal instructions. The seed
is idempotent and its scheme, classification and rule creation events all carry
the same migration source, automated-process actor, explicit reason and
structured bulk-operation provenance.

The NiceGUI aggregation form presents eligible terminals with code, title, and
description. Its searchable hierarchy-aware list places the current user's
recent selections first. The number retained in this list is configured by
`CLASSIFICATION_RECENT_SELECTION_LIMIT`, which defaults to `4`.

## Administration workspace

Classification schemes and their classifications are administered together in
one workspace. Its fixed-height upper row places the scrollable scheme list on
the left and the selected scheme's information on the right. Selecting a scheme
updates that adjacent read-only information pane. The full-width lower area
retains the classification search and side-by-side classification tree and
classification-information panes, so the current scheme remains explicit and
does not need to be selected again when creating a classification.
Scheme list cards are deliberately compact. Their descriptions occupy one line,
truncate with an ellipsis when necessary, and expose the complete description
in a hover tooltip.

The hierarchy is lazy-loaded: root classifications are fetched when a scheme is
selected and a branch's direct children are fetched only when that branch is
expanded. Schemes use the `account_tree` icon, branch classifications use the
distinct `schema` icon, and terminal classifications use the `label` icon.
Selecting a node shows its complete path, metadata, and effective retention
rule, including whether that rule is direct or inherited.

Creation is contextual. The add icon in the Classification tree header creates
a root classification in the selected scheme and sits beside the tree-refresh
action. The adjacent child-classification icon creates beneath the selected
branch with both the scheme and parent locked by context. It is disabled until
a branch is selected and remains disabled for terminal classifications. Scheme
lifecycle actions, scheme and classification editing, tree refresh, and
classification search all remain in the same workspace.

The selected-classification pane contains audited deactivate, reactivate, and
delete actions. Delete remains visible when unavailable, but is disabled with
the exact reason. Deactivation is the normal alternative for a classification
that has already participated in governance.

Viewing metadata does not require entering an edit workflow. Selecting a scheme
shows its authority, scope note, edition, publication and lifecycle dates, and
audit timestamps in a read-only information panel. Codes are shown in full;
description and scope-note fields use full-width, multi-line scroll regions.
Selecting a classification shows its authority, scope note, keywords, parent
and full path, timestamps, and
complete effective retention rule including disposition instructions and the
classification from which an inherited rule originates. When an inherited rule
applies, the view also states whether the selected classification has its own
direct rule. Edit controls are separate and may later be hidden by authorization
without hiding information the user is allowed to view.

For a root classification, **Parent classification** displays an empty value
(`—`); “Root classification” is not presented as though it were a parent.
Tree rows reserve the same expander space for every node so branch and terminal
icons remain aligned at each hierarchy depth.

## Search

Classification code, title, description, and keywords support safe
case-insensitive partial search in the scheme administration workspace. The
NiceGUI aggregation selector searches the same four fields. Both use
`contains_ci`, so entering `finance` automatically finds values containing that
text without requiring wildcards.
The controlled API grammar retains `matches_ci` for advanced future clients;
there, `*` means zero or more characters and `?` means exactly one character.
SQL `%` and `_` remain literal rather than becoming caller-controlled patterns.

## API overview

The REST API exposes `/api/v1/classification-schemes`,
`/api/v1/classifications`, nested direct and effective retention-rule routes,
`/api/v1/classifications/recent`, classification paths, and aggregation local
and effective retention-rule routes. Mutable entities use `If-Match` optimistic
concurrency. OpenAPI contains the exact request and response schemas.

## Audit and deletion

Schemes, classifications, classification rules, and aggregation-local rules are
audited using the same immutable event-history subsystem as other entities.
Classification rules cascade only when their owning classification is deleted;
local rules cascade only when their owning root aggregation is deleted. Foreign
keys otherwise restrict deletion while children or assignments exist.

### Classification deletion rules

A classification may be permanently deleted only when every condition is true:

- Its scheme is currently unpublished and active. Previous publication followed
  by unpublication does not permanently bar deletion.
- Its immutable `date_first_used` is null; neither it nor descendant governance
  has ever caused it to govern an aggregation.
- It is a leaf. Individual deletion never silently cascades through a subtree,
  so child classifications must be removed first.
- No aggregation currently references it.
- The request supplies the current version and a nonblank deletion reason.

PostgreSQL rechecks these conditions even for direct SQL. Its directly owned
retention rule and users' recent-selection rows cascade as dependent data;
immutable event history remains. The UI explains whether the administrator must
unpublish or reactivate the scheme, remove children, or deactivate a historically
used classification instead.

### Scheme deletion rules

Permanent deletion is deliberately limited to schemes which are both currently
unpublished and have never governed an aggregation:

- `date_published` must be null. An unused scheme that was published by mistake
  may first be unpublished with a recorded reason.
- `date_first_used` must be null. Once any classification has been assigned to
  an aggregation, this value is permanent and deletion remains forbidden.
- No aggregation may currently reference a classification in the scheme. This
  is checked again inside the deletion transaction as a defensive integrity
  condition.
- The caller must supply the current scheme version and a non-blank deletion
  reason.

An eligible empty scheme is deleted directly. If an eligible scheme contains a
draft classification hierarchy, PostgreSQL removes that hierarchy from the
deepest classifications upward in the same transaction, then removes the
scheme. Direct classification retention rules and users' recent-classification
selection entries cascade with their classifications. No aggregation, record,
digital component, or aggregation-local retention rule is deleted by this
operation. If any validation fails, the entire transaction is rolled back.

The scheme, classifications, and directly owned retention rules generate their
normal immutable deletion events. Event history is retained after the source
rows disappear and includes the administrator's reason. Optimistic concurrency
prevents deletion when the scheme changed after the UI loaded it.

The administration UI always explains why deletion is unavailable. A published
but unused scheme instructs the user to unpublish it first. A scheme with
`date_first_used` explains that it has governed aggregations and must be
deactivated instead. For an eligible populated draft, the confirmation displays
the number of branch and terminal classifications that will be removed and
warns that the operation cannot be undone.
