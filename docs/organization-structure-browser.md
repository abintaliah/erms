# Organization structure browser

The web UI provides **Browse** above the organization-unit,
role, and user administration links. It loads only root organization units at
first, then loads direct child units and roles when a unit is expanded and role
assignments when a role is expanded. This keeps initial rendering bounded even
for large structures.

The left pane is an independently scrollable tree. The right pane summarizes the
selected organization unit, role, or user and provides the corresponding Open
action. User occurrences belong to role assignments, so one person may appear
under more than one role; every occurrence opens the same user details view while
retaining the selected assignment as summary context. Tree user nodes use a
person icon rather than an avatar.

Search covers organization-unit code, name, and description; role code, name,
and description; and user name and email. Search responses contain the stable
organization-unit ancestor path and, for users, the role and assignment IDs.
Choosing a result loads and expands that path and scrolls the selected node into
view. Result cards include codes, user email, and the role context for every user
assignment occurrence. Entity-type, effective-status, and assignment-validity
filters are kept in a collapsible filter row. A Refresh action invalidates the
loaded branch cache and reloads expanded paths.

Expansion, selection, selected assignment, search, filters, and tree scroll
position are stored in NiceGUI's signed-in user session storage. They survive
navigation to another application page and are cleared at sign-out. Stale
selected entities are discarded without clearing the rest of the saved state.
The tree and summary panes scroll independently. User-node selection is keyed by
role-assignment ID as well as user ID, so repeated clicks on duplicate user
search results reliably select the intended occurrence.

The full-page tree/summary browser is 720px high; selector browsers remain
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
validity remains visible in the selected occurrence summary, the validity
filter, and assignment tables.

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
and `status`; role users accept assignment `validity`. Authorization filtering
must be added to all six endpoints when the authorization subsystem is
introduced.

## Verification

Backend integration tests run through `database/tests/run.sh`, which creates a
new PostgreSQL container and removes it on completion. Frontend regression tests
are under `frontend/webui/tests`. Browser click testing must likewise use a
disposable database rather than the developer's local data.
