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

The hierarchy is lazy-loaded: root classifications are fetched when a scheme is
selected and a branch's direct children are fetched only when that branch is
expanded. Schemes use the `account_tree` icon, branch classifications use the
distinct `schema` icon, and terminal classifications use the `label` icon.
Selecting a node shows its complete path, metadata, and effective retention
rule, including whether that rule is direct or inherited.

Creation is contextual. **Add root** creates a root classification in the
selected scheme, while **Add child** creates beneath the selected branch with
both the scheme and parent locked by context. A terminal cannot expose an
add-child action. Scheme lifecycle actions, scheme and classification editing,
tree refresh, and classification search all remain in the same workspace.

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
NiceGUI aggregation selector searches code, title, and description. Both use
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
