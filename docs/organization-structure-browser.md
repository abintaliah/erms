# Organization structure browser

The web UI provides **Browse** above the organization-unit,
role, and user administration links. It loads only root organization units at
first, then loads direct child units and roles when a unit is expanded and role
assignments when a role is expanded. This keeps initial rendering bounded even
for large structures.

The full Browse page is centered on one full-width, independently scrollable
organization tree. Clicking a node name opens the existing Organization Unit,
Role, or User detail page directly; the separate chevron only expands/collapses
its branch. Detail pages retain their metadata and management actions. Their identity headers
place the icon/avatar beside the name at the reading-start edge and Back at the
opposite edge: icon right/Back left in Arabic, icon left/Back right in English.
The Back arrow points right in Arabic and left in English. Their
existing Back action restores the tree through navigation history.

User occurrences belong to role assignments, so one person may appear under
more than one role. Each occurrence opens the same User details view while
preserving its assignment ID in the saved tree selection. Tree user nodes use a
person icon rather than an avatar. Full-page browsing makes no summary requests;
selector dialogs retain their compact tree/summary and confirmation behavior.
Nodes without the corresponding detail-page privilege remain visible for
browsing, without an active detail link.

Search covers organization-unit code, name, and description; role code, name,
and description; and user name and email. Search responses contain the stable
organization-unit ancestor path and, for users, the role and assignment IDs.
Choosing a result loads and expands that path and opens its existing detail
page. In selector dialogs it still selects and scrolls to the matching node. Result cards include codes, user email, and the role context for every user
assignment occurrence. Entity-type, effective-status, and assignment-validity
filters are kept in a collapsible filter row. A Refresh action invalidates the
loaded branch cache and reloads expanded paths.

Expansion, selection, selected assignment, search, filters, and tree scroll
position are stored in NiceGUI's signed-in user session storage. They survive
navigation to another application page and are cleared at sign-out. Stale
selected entities are discarded without clearing the rest of the saved state.
The full-page tree occupies the available browser width. Selector tree and
summary panes scroll independently. User-node selection is keyed by
role-assignment ID as well as user ID, so repeated clicks on duplicate user
search results reliably select the intended occurrence.

The full-page tree browser is 720px high; selector browsers remain
520px high. Organization rows deliberately reuse the Classification tree's
name/code typography, indentation, expanders, icons, hover state, and selection
state. Icons identify organization units and roles, so active nodes do not also
show redundant **Organization unit** or **Role** badges. A badge remains when it
communicates lifecycle state, such as an inactive role or organization unit.

Users have only their own account lifecycle status: active, inactive, or
suspended. Organization-unit inactivity can make roles ineffective, but it does
not make the user ineffective and does not suppress permissions obtained from
other effective roles.

Role-assignment timing is separate relationship information. It determines
whether that particular role assignment currently contributes permissions; it
does not alter the user's account status. Because this distinction is too
specialized for a tree label, user nodes show only account status. Assignment
validity remains visible in selector occurrence summaries, the validity
filter, and existing assignment-management views.

## User details

Organization units and roles open dedicated detail views containing lifecycle
explanations, inherited effects, relationship counts, and their existing
management actions. Their management listings include Open actions leading to
those views. The Users listing has an Open action leading to the
dedicated user details view.

In browser summaries, Direct status and Effective status explain their meaning
as tiny subtitles inside the corresponding field, before its separator. The
dedicated Organization Unit and Role details pages use the same field-level
guidance and do not show a separate status-explanation panel. User
summaries show Account status rather than Effective status and render avatars
through the same deterministic component, size, initials, stable-key color, and
framework-resistant background style used by the Users listing.
That view contains the deterministic avatar and account metadata, role
assignments, retained login sessions, and the existing user actions: edit,
activate/deactivate, suspend/unsuspend, temporary password, role assignments,
event history, and revocation of active login sessions. Its session table uses
server-side filtering, sorting, and paging with a configurable five-row default
(`USER_DETAILS_SESSION_LIMIT`). Its role-assignment table also has a fixed
five-row viewport, paging, sortable columns, and role/status/validity filters.
Both tables use a compact 190px height. There is no View All link. Permanent
deletion is not exposed.

## Browse-enabled selectors

Organization-unit, role, and user lookup controls retain their searchable select
and add a **Browse organization structure** action. The tree uses the full
dialog width above its compact summary, scrolls horizontally and vertically,
and does not wrap labels:

- organization-unit mode shows organization units only;
- role mode uses organization units for navigation, shows roles, and does not
  load users; and
- user mode permits drilling through units and roles to users.

Only the selector's target entity type can be confirmed. Inactive or otherwise
ineffective target nodes remain visible for context but cannot be selected. The
dialog always provides visible Select, Clear selection, and Cancel actions.
Role and User assignment dialogs expose labeled Browse controls beside their
existing searchable selects.

## API

The browser uses these bounded endpoints under `/api/v1/browse/organization`:

- `GET /roots`
- `GET /org-units/{id}/children`
- `GET /roles/{id}/users`
- `GET /org-units/{id}/summary`
- `GET /roles/{id}/summary`
- `GET /search`
- `GET /api/v1/auth/sessions/page` for bounded User-detail session pages

Branch endpoints accept a maximum of 100 results. Search accepts `entity_type`
and `status`; role users accept assignment `validity`. All six organization
browser endpoints require the `organization.browse` global privilege. This
permits read-only exploration of the hierarchy and concise summaries; it does
not permit opening or administering the full Organization Unit, Role, or User
pages. Those destinations continue to require `organization.administer` or
`identity.users.administer`, as appropriate.

## Verification

Backend integration tests run through `database/tests/run.sh`, which creates a
new PostgreSQL container and removes it on completion. Frontend regression tests
are under `frontend/webui/tests`. Browser click testing must likewise use a
disposable database rather than the developer's local data.

## Tree-centered redesign verification — 29 September 2026

The user approved the clickable tree design, unchanged detail pages, and reuse
of existing translation keys. See
[verification and traceability](organization-tree-redesign-verification.md).

## Sibling ordering

The API sorts before applying limits and offsets. Root units and each child
unit/role group use PostgreSQL ICU numeric collation `erms_code_natural`
(`und-u-kn-true`), so `UNIT-2` precedes `UNIT-10` in both UI languages. Entity ID
is the final tie-breaker. PostgreSQL must include ICU support. New databases
receive the collation from `database/schema.sql`; existing databases must apply
`database/migrations/029_organization_tree_ordering.sql` before this API version.

Child responses defer roles while `more_org_units` is true. During that phase,
`roles` is empty and `more_roles` indicates whether an unconsumed role exists,
using a bounded one-row lookup. Clients advance each offset by the number of
rows actually returned. The final unit page can also contain the first role
page; subsequent pages contain the remaining roles. This preserves units before
roles across the entire branch without downloading the hierarchy or changing
the response fields. Organization-unit-only selectors still omit roles.

Role users sort by the same localized display-name fallback as entity rendering,
then user ID and assignment ID. The SQL chooses a nonempty exact-language
translation object, then a base-language object, then the canonical name when
the chosen object has no name. It uses the installed PostgreSQL ICU collation
for the language tag, falling back through less-specific language tags to ICU's
language-neutral collation. Collation identifiers are safely quoted; language
values remain bound parameters. There is no new cache. Arabic names therefore
sort using Arabic alphabetical rules, independently of RTL layout. Codes and
name ties remain deterministic for unchanged data; offset pages are not a
snapshot across concurrent edits, so Refresh reloads branches after mutations.

Verification: `test_organization_sibling_codes_are_natural_and_units_precede_all_roles`
covers root/child natural ordering, group boundaries, offsets and selectors;
`test_organization_users_sort_displayed_names_before_pagination` covers English,
Arabic, one-row pages and duplicate-name ties. Existing organization interaction
tests cover expansion restoration and navigation to unchanged detail pages.
This change adds no UI text or translation keys and does not change search ranking.
