# Organization Structure Browser and User Details — Technical Specification

**Status:** Implemented  
**Project:** ERMS  
**Prepared:** 18 September 2026  
**Revision:** 1.5

## 1. Purpose

This specification defines a navigable organization-structure browser, a
dedicated User details page, and browse-enabled selectors for organization
units, roles, and users.

The browser gives users a structural view that complements the existing
management listings. It presents organization units, their roles, and the
users assigned to those roles without implying that a role owns its assigned
users.

## 2. Scope

This feature includes:

- a **Browse Organization Structure** navigation item and page;
- an expandable organization-unit, role, and user tree;
- a read-only summary pane for the selected node;
- persistent browser expansion, selection, filtering, and scroll state;
- navigation from summaries to the corresponding management interface;
- a dedicated User details page containing all actions for one user; and
- a reusable organization-structure browser for organization-unit, role, and
  user selectors.

This feature does not introduce or change authorization rules, role-assignment
semantics, organization-unit ownership, role supervision, or user lifecycle
semantics.

## 3. Navigation

The **Organization Structure** navigation section must contain the following
items in this order:

1. Browse
2. Organization Units
3. Roles
4. Users

Selecting **Browse** opens the full organization
browser. Returning to it must restore the user's previous browser state as
defined in section 8.

## 4. Page layout

The browser uses a two-pane layout:

- the left pane contains the searchable and expandable structure tree; and
- the right pane contains a concise read-only summary of the selected node.

The tree pane must remain independently scrollable. Selecting a node must not
collapse that node, reset the tree, or move the tree back to its beginning.
The summary pane must also scroll independently when its content is taller than
the available pane height.

On the full Browse page, the tree and summary container is 720 pixels high. This
additional height does not apply to selector dialogs, which retain their compact
520-pixel layout.

Before a node is selected, the summary pane displays brief guidance rather
than an empty card.

On a narrow viewport, the panes may stack or the summary may open as a drawer,
provided that tree state is preserved.

## 5. Tree hierarchy

### 5.1 Node order and containment

The tree uses the following hierarchy:

```text
Root organization unit
└── Child organization unit
    ├── Further child organization unit
    └── Role belonging directly to this organization unit
        └── User referenced through a role assignment
```

Organization-unit containment is the primary hierarchy. A role appears beneath
the organization unit identified by `roles.org_unit_id`. Supervisor-role
relationships do not alter tree placement and are shown in role summaries.

A user appears beneath a role through `user_role_assignments`. The same user
may therefore appear under several roles. Every occurrence refers to the same
user entity and must open the same User details page.

### 5.2 Initial state and lazy loading

On the first visit, the tree loads and shows root organization units only.
Children are loaded only when their parent is expanded:

- expanding an organization unit loads its direct child units and direct roles;
- expanding a role loads its user assignments; and
- user nodes cannot be expanded.

The client may cache loaded children for the browser session. A refresh action
must invalidate affected cached data and reload it from the API.

The tree toolbar must provide a visible **Refresh** action on both the full page
and selector dialogs.

The UI must show a local loading indicator on the node being expanded. Loading
one branch must not block interaction with already-loaded branches.

### 5.3 Node presentation

Every node shows:

- an icon identifying organization unit, role, or user;
- the entity name;
- the organization-unit or role code when applicable; and
- a lifecycle-status badge only where required by the rules below.

User nodes in the tree must use a standard person icon. They must **not** show
generated user avatars. Generated avatars remain appropriate in user listings,
user summaries, and the User details page.

Tree rows follow the established Classification tree presentation: separate
title and code lines, consistent indentation, fixed icon and expander columns,
and rounded hover and selection backgrounds.

The icon is the sole tree-level type indicator. Active organization units and
roles must not carry badges saying **Organization unit** or **Role**. These
labels duplicate the icons and add visual noise. An inactive or ineffective
organization unit or role retains a status badge because that badge conveys
lifecycle state rather than entity type. User nodes retain their account-status
badge.

Inactive organization units and roles remain visible and are visually muted.
Inactive and suspended users remain visible. A tooltip or accessible status
label must explain whether an organization unit or role is directly inactive or
ineffective because of an ancestor organization unit.

A user has an account status only: `active`, `inactive`, or `suspended`. Users do
not inherit an effective status from organization units or roles. An inactive
organization unit makes its descendant roles ineffective, and an inactive role
contributes no permissions, but neither changes the user's account status nor
prevents permissions from other effective roles from applying.

### 5.4 Role-assignment validity

Each user occurrence below a role represents a user-role assignment. Assignment
validity has three values:

- currently valid assignments;
- assignments whose `valid_from` is in the future; and
- assignments whose `valid_until` has passed.

Expired and future assignments are visible by default. The browser must offer a
filter that can show only currently valid assignments. Validity is evaluated
using the server time. `valid_from` is inclusive; `valid_until` is exclusive,
and a null `valid_until` has no upper bound.

Assignment validity is a property of the relationship between a user and a
role. It is not a user status and must not be shown as a badge or secondary
status on a user node in the tree. A user node shows only the user's account
status. Assignment validity remains available in the selected occurrence's
summary, the assignment-validity filter, and assignment-management tables.

## 6. Search and filtering

The full browser provides one search control capable of matching:

- organization-unit code, name, and description;
- role code, name, and description; and
- user name and email address.

Search results must include enough ancestor context to identify and reveal each
matching path. Selecting a search result expands the required ancestors,
selects the matching node, and scrolls it into view.

Each result must use a consistently aligned card-like presentation. It shows
the entity name and code where applicable, a user's email address, and the role
code and name for each user-assignment occurrence. A user assigned to two
matching roles therefore appears as two distinguishable results, and each
result reveals its corresponding occurrence in the tree.
Repeatedly choosing different occurrences of the same user must move selection
between the corresponding role-assignment nodes every time; selection identity
therefore includes the assignment identifier, not only the user identifier.

Filters must support entity type, effective status, and role-assignment
validity. Advanced filters should remain visually unobtrusive when unused.
Clearing search or filters restores the prior expansion state rather than
collapsing the tree.

## 7. Summary pane

### 7.1 Organization-unit summary

The summary includes:

- code, name, and description;
- direct and effective status, including the source of inherited inactivity;
- parent organization unit;
- number of direct child organization units; and
- number of roles directly belonging to the unit.

It provides an **Open organization unit** action.

Direct-status guidance appears immediately below the Direct status label, and
effective-status guidance appears immediately below the Effective status label.
The pane does not use a separate “How status works” card. The dedicated
organization-unit details page uses the same field-level treatment and must not
show a separate status-guidance panel.

### 7.2 Role summary

The summary includes:

- code, name, and description;
- direct and effective status;
- organization unit;
- supervising role, if any;
- number of directly supervised roles; and
- number of assigned users, with current, future, and expired assignment counts.

It provides an **Open role** action.

Role status guidance uses the same inline subtitle treatment as organization
unit status guidance. This applies to both the browser summary and the dedicated
Role details page; neither uses a separate status-guidance panel.

### 7.3 User summary

The summary includes:

- deterministic user avatar;
- name and email address;
- account type (`person` or `service`);
- account status, without an inherited/effective user status;
- the role through which this occurrence was selected; and
- that role assignment's `valid_from`, `valid_until`, and current validity.

It provides an **Open user** action. Selecting the same user beneath different
roles changes the assignment context shown in the summary but does not change
the user destination.

The summary avatar uses exactly the same deterministic initials, stable-key
color, size, and rendering treatment as the avatar in the Users listing. Its
background color must not be replaced by the UI framework's default avatar
color.

## 8. Browser-state persistence

The application must preserve the following state for the authenticated browser
session:

- expanded organization-unit and role node identifiers;
- selected node type and identifier;
- selected role-assignment identifier when a user occurrence is selected;
- tree scroll position;
- search text;
- filter values; and
- summary-pane display state on responsive layouts.

State must survive navigation from the browser to an organization unit, role,
or user interface and back to the browser. It must also survive navigation to
other application sections in the same browser tab.

State must be scoped to the signed-in user and browser session. Signing out
clears it. One user's state must never be restored for another user.

When restored state refers to an entity that was deleted or is no longer
readable, the application removes only that invalid reference. Other valid
expanded nodes, filters, and scroll state remain intact. If the selected node
is invalid, the summary returns to its unselected guidance state.

## 9. Entity navigation

Summary actions must retain browser state before navigating.

- **Open organization unit** opens the dedicated Organization Unit details page.
- **Open role** opens the dedicated Role details page.
- **Open user** opens the dedicated User details page described in section 10.

The Organization Unit and Role details pages expose their metadata, direct and
effective lifecycle status with explanatory guidance, inherited inactivity,
relationship counts, and all existing management actions. They are extensible
locations for additional metadata introduced later.

The Organization Units and Roles listings each provide a visible Open action
which navigates directly to the selected entity's dedicated details page.

## 10. User details page

### 10.1 Route and purpose

The application must provide a stable User details route equivalent to
`/users/{user_id}`. The Users listing remains the management overview; the
details page is the extensible interface for one user and future user metadata.

### 10.2 Information

The page initially shows:

- deterministic avatar, name, email, external identifier, and account type;
- lifecycle status and deactivation date when applicable;
- role assignments and their validity periods;
- a fixed-height, server-paged table of active, expired, and revoked login
  sessions; and
- user event history.

Additional user metadata may be added without expanding the Users listing.
The session page size is configurable and defaults to five. The table provides
Previous and Next controls plus filter and sort controls. Filtering, sorting,
and paging are performed by bounded API queries; the User details page must
never fetch the user's entire session history merely to render the table. It
does not show a separate View All action.

Role assignments use a fixed-height table with at most five visible rows,
native paging controls, sortable columns, and filters for role name/code, role
status, and assignment validity. Both this table and the login-session table use
a compact 190-pixel viewport.

### 10.3 Actions

Subject to the same rules already enforced by the API, the page provides all
currently available user actions:

- edit user metadata;
- activate or deactivate;
- suspend or unsuspend;
- issue a temporary password;
- add and remove role assignments;
- revoke eligible login sessions; and
- view event history.

Unavailable actions remain visible but disabled when that improves layout
consistency and communicates the applicable state rule. The page must not
introduce permanent deletion before the deletion and authorization
specifications permit it.

## 11. Browse-enabled selectors

### 11.1 Shared component

Organization-unit, role, and user selectors retain their existing searchable
selection control and add a **Browse organization structure** action. The
action opens a selector dialog using the same hierarchy data, status rules,
icons, lazy loading, and summary presentation as the full browser.

The full page and selector dialogs must share one hierarchy model and loading
service. They must not implement separate definitions of effective status,
assignment validity, or entity placement.

### 11.2 Organization-unit selection mode

- Organization-unit nodes are selectable.
- Role and user nodes are hidden and are not loaded for this selector mode.
- When the field requires an effective unit, inactive or effectively inactive
  units are visible but cannot be confirmed.

### 11.3 Role selection mode

- Organization units are navigational and reveal their roles.
- Role nodes are selectable.
- User nodes are hidden and are not loaded for this selector mode.
- When the field requires an effective role, directly or effectively inactive
  roles are visible but cannot be confirmed.

### 11.4 User selection mode

- Organization units and roles are navigational.
- User nodes are selectable.
- The same user may appear under multiple roles, but every occurrence returns
  the same `user_id`.
- The selector must clearly show the path and role through which a user was
  found without treating that role assignment as the selected value.
- When the field requires an active user, inactive and suspended users are
  visible but cannot be confirmed.

### 11.5 Selection behavior

Each selector dialog contains:

- text search;
- the applicable status and validity filters;
- the hierarchy tree;
- a concise selected-item summary;
- **Select** and **Cancel** actions; and
- an explicit **Clear selection** action when the field is optional.

Double-clicking a valid selectable node may confirm it, but a visible Select
action remains required for accessibility and predictability.

The Role Assignments dialog for a user provides a visible **Browse** control for
role selection. The User Assignments dialog for a role provides the equivalent
control for user selection; neither dialog relies on an unexplained icon alone.

Selector state is preserved while its containing form remains open. Selector
state does not overwrite the full browser's persisted state.

The selector tree receives the full dialog width above a compact summary and
scrolls independently. Node labels use the same single-line truncation and
two-line name/code presentation as the Classification tree rather than wrapping.

## 12. Data and API requirements

The API must support bounded, authorization-aware reads for:

- root organization units;
- direct child units of one unit;
- direct roles of one unit;
- role assignments and corresponding users for one role;
- summary counts for organization units and roles; and
- cross-entity organization-structure search results with revealable paths.

Responses must expose stable identifiers, direct status, effective status and
its reason, and assignment validity information. Endpoints must be paginated or
otherwise bounded; the UI must not fetch every organization unit, role, user,
and assignment merely to render the initial roots.

The future authorization subsystem must filter every node, count, search
result, and selector option by the authenticated principal's read access. A
parent needed only to reveal an authorized descendant may be returned as
restricted navigational context without exposing unauthorized metadata.

## 13. Accessibility and usability

- Tree navigation must support keyboard focus, expand/collapse, selection, and
  an accessible label for node type and status.
- Icons and color must not be the only indicators of type or lifecycle state.
- Focus moves to the summary heading after an explicit request to view a node's
  details only when doing so does not disrupt keyboard tree navigation.
- Loading and error states are localized to the affected tree branch whenever
  possible.
- Empty organization units and roles show an explicit “no children” state.

## 14. Acceptance criteria

The feature is complete when automated tests and browser click tests establish
that:

1. the new navigation item appears in the required location;
2. initial loading retrieves root units without loading the complete tree;
3. units expand through descendants, roles, and assigned users;
4. duplicate appearances of one user resolve to the same User details page;
5. user nodes in the tree do not display avatars;
6. selecting each node type shows the specified summary and working Open action;
7. browser state is restored after opening an entity and returning;
8. signing out prevents that state from being restored for another user;
9. search reveals and selects matching nodes with their ancestor paths;
10. user tree nodes show account status without presenting assignment validity
    as another user status, while validity remains available in the summary,
    filter, and assignment tables;
11. the User details page exposes all existing user actions;
12. each selector mode permits only the correct entity type and returns its
    stable identifier; and
13. large structures remain responsive because branch loading and API results
    are bounded.
