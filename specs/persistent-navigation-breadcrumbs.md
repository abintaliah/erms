# Persistent Navigation Breadcrumbs — Technical Specification

**Status:** Implemented  
**Project:** ERMS  
**Prepared:** 18 September 2026  
**Revision:** 1.0

## 1. Purpose

ERMS allows a user to move through several pages while investigating an entity.
For example, the user may move from the Dashboard to an aggregation, from that
aggregation to a record, and from the record back to its containing
aggregation. A single Back button cannot expose or restore the complete path.

This specification introduces a persistent navigation breadcrumb at the top of
every authenticated page. It shows the user's current in-application navigation
path and allows the user to return directly to any earlier page in that path.

## 2. Terminology

### 2.1 Navigation breadcrumb

The navigation breadcrumb represents pages the user actually visited during
the current signed-in browser session. It is a history trail rather than a data
hierarchy.

Example:

```text
Dashboard  ›  Aggregations  ›  Annual Reports  ›  Record REC-2026-014
```

### 2.2 Structural breadcrumb

A structural breadcrumb represents an entity's place in a hierarchy, whether
or not the user visited every ancestor. The existing breadcrumb on an
Aggregation Detail page is structural.

Example:

```text
Aggregations  ›  Corporate Records  ›  Annual Reports  ›  2026 Reports
```

Navigation and structural breadcrumbs communicate different information. The
new navigation breadcrumb must not replace a structural breadcrumb. When both
are useful, the navigation breadcrumb appears at the page level and the
structural breadcrumb remains inside the page content.

## 3. Scope

This feature includes:

- one persistent navigation breadcrumb on every authenticated page;
- a per-user, per-browser-session navigation trail;
- direct navigation to any earlier breadcrumb entry;
- restoration of relevant page state when returning through the trail;
- bounded display and overflow handling;
- stale-target and authorization handling;
- keyboard and assistive-technology support; and
- integration with existing page-specific Back actions.

This feature does not include:

- a permanent cross-session browsing history;
- an audit log of pages viewed;
- replacement of entity-hierarchy breadcrumbs;
- recording modal dialogs as breadcrumb entries;
- recording every search, filter, sort, pagination, or tree expansion as a new
  breadcrumb entry; or
- exposing pages that the current user is not authorized to read.

## 4. Placement and presentation

The navigation breadcrumb appears below the global application header and above
the page title on every authenticated page. It remains in the same location as
the user navigates.

Each entry shows:

- a concise page or entity label;
- an optional icon where it improves recognition; and
- an accessible indication of the current page.

All entries except the final entry are interactive. The final entry represents
the current page and is not a link.

The control must be visually subordinate to the page title. It must not consume
an entire card or large vertical region.

## 5. Entry labels

Listing and workspace pages use their established navigation labels, including:

- Dashboard;
- Aggregations;
- Records;
- Classification schemes;
- Browse organization structure;
- Organization units;
- Roles;
- Users;
- Audit trail; and
- Login sessions.

Dedicated entity pages use a stable identifying label:

| Entity | Breadcrumb label |
| --- | --- |
| Aggregation | Aggregation title, with aggregation number available in a tooltip or accessible label |
| Record | Record title, with record number available in a tooltip or accessible label |
| Organization unit | Organization-unit name, with code available in a tooltip or accessible label |
| Role | Role name, with code available in a tooltip or accessible label |
| User | User name, with email available in a tooltip or accessible label |

Long labels are truncated visually without changing their full accessible name
or tooltip.

## 6. Navigation-trail semantics

### 6.1 Adding entries

A new entry is appended only when navigation changes the primary page content.
Opening or closing a dialog, changing an inline tab, expanding a tree node, or
changing search controls does not append an entry.

The following actions append an entry:

- selecting a primary navigation item;
- opening a dedicated entity page;
- opening a full workspace or browser page; and
- following an in-application link that replaces the primary page content.

### 6.2 Duplicate handling

Consecutive entries referring to the same logical page are collapsed into one
entry. Refreshing or re-rendering a page must not duplicate its entry.

Logical identity consists of:

- the page type for a listing, workspace, browser, Dashboard, or administration
  page; or
- the entity type and stable entity ID for a dedicated entity page.

The same page may appear more than once when the user genuinely returns to it
later through a different navigation sequence. Only consecutive duplicates are
automatically collapsed.

### 6.3 Selecting an earlier entry

Selecting an earlier breadcrumb entry:

1. restores that page and its saved state;
2. makes it the current final entry; and
3. removes every entry that followed it.

If the user then navigates elsewhere, the new destination is appended to this
shortened trail. The breadcrumb therefore follows ordinary back-stack
semantics and does not retain an inaccessible forward branch.

### 6.4 Page-specific Back actions

Existing Back buttons on Record and Aggregation Detail pages remain available.
They perform the same operation as selecting the immediately preceding valid
navigation-breadcrumb entry.

If no preceding entry exists, Back uses the page's safe fallback:

- Record Detail returns to Records;
- Aggregation Detail returns to Aggregations;
- Organization Unit Detail returns to Organization units;
- Role Detail returns to Roles; and
- User Detail returns to Users.

Back must not create a new breadcrumb entry for the page being restored.

## 7. Page-state restoration

Each breadcrumb entry stores only the state required to reconstruct its page.
It must not store rendered UI objects, database rows, credentials, or API
responses as authoritative data.

The state snapshot may include:

- selected search or browse mode;
- search text and advanced filters;
- sort field and direction;
- current pagination position;
- selected classification or organization-tree node;
- expanded tree-node identifiers;
- scroll position; and
- the stable ID of a selected or opened entity.

When an entry is restored, the UI reloads current data from the API and applies
the saved presentation state where still valid. Restoring history must not show
stale entity data merely because it was present when the entry was created.

Dialog state is not restored. A page returns with dialogs closed.

## 8. Persistence and lifecycle

The navigation trail is stored in NiceGUI's signed-in user session storage. It
survives navigation within the application and an ordinary page refresh during
the same authenticated session.

The trail is cleared when:

- the user signs out;
- authentication expires and the application returns to sign-in;
- a different user signs in through the same browser session; or
- the stored trail is invalid or cannot be safely decoded.

The trail is not synchronized between browsers or devices and is not stored as
business data in PostgreSQL.

## 9. Bounded display and storage

The complete in-session trail is bounded to the 20 most recent entries. When a
new entry exceeds this limit, the oldest entry is discarded.

At most five entries are shown directly:

- the first entry when it is still retained;
- the three most relevant recent ancestors; and
- the current page.

When additional entries are hidden, an ellipsis control appears between the
visible entries. Activating it opens a compact menu containing the hidden
entries in trail order. Selecting a hidden entry uses the same restoration and
forward-truncation semantics as selecting a visible entry.

On narrow screens, the control may show fewer entries, but the current page and
the immediately preceding entry must remain visible whenever space permits.

The trail length and visible-entry count are implementation constants for the
initial release. They may become configuration settings later if operational
experience demonstrates a need.

## 10. Stale, deleted, and unauthorized targets

Before restoring an entity page, the application retrieves the entity through
the normal authorized API.

- If the entity no longer exists, the application removes that breadcrumb
  entry, shows a concise notification, and restores the closest preceding valid
  entry.
- If access is denied, the application removes that entry and every descendant
  entry that depends on it, shows the normal authorization error, and restores
  the closest preceding authorized page.
- If a non-entity page no longer exists after an application revision, the
  application removes the unrecognized entry and continues with the remaining
  valid trail.
- A transient API failure does not permanently delete an otherwise valid entry.
  The current page remains visible with the established retry/error treatment.

Breadcrumb labels stored in session state are display hints only. They must not
be trusted for authorization or entity existence.

## 11. Interaction with direct entry and refresh

If an authenticated session opens a page without an existing trail—for example
after a direct URL entry or after invalid stored state—the destination becomes
the first entry.

Refreshing the browser preserves the current trail and current entry. It does
not append a duplicate.

The initial post-login Dashboard becomes the first entry when no restorable
destination exists.

## 12. Accessibility

The breadcrumb uses semantic navigation markup with an accessible label such as
`Navigation history`.

- The current entry exposes `aria-current="page"`.
- Every interactive entry is keyboard focusable and activatable.
- Separators are hidden from assistive technologies.
- Truncated visual labels retain their complete accessible names.
- The overflow control announces the number of hidden entries.
- Keyboard focus moves to the restored page heading after navigation.
- Color is not the only means of distinguishing links from the current entry.

## 13. Security and privacy

Breadcrumb state is private to the signed-in browser session. It must never be
shared between users or included in another user's page.

The state contains stable entity identifiers and minimal presentation data. It
must not contain passwords, session tokens, uploaded content, confidential
metadata snapshots, or authorization decisions.

Every restoration performs ordinary server-side authorization. Possession of a
breadcrumb entry never grants access to its target.

Navigation itself is not added to immutable event history because viewing a
page is not currently an audited business operation. This decision may be
revisited separately if read-access auditing becomes a requirement.

## 14. Failure behavior

- An invalid session-state entry is skipped without preventing the application
  from loading.
- Failure to store presentation state must not prevent navigation.
- If the complete trail becomes unusable, it is reset to the current page.
- Breadcrumb failures must not leave the application showing a page whose title
  and current breadcrumb disagree.

## 15. Testing requirements

Automated tests must use a newly created disposable PostgreSQL database and
dispose of it cleanly after the test suite.

Tests must cover:

- entry creation for each primary page and dedicated entity type;
- suppression of consecutive duplicates during refresh and re-render;
- restoration of search, filter, pagination, tree, selection, and scroll state;
- removal of forward entries after selecting an earlier entry;
- Back-button equivalence with the immediately preceding breadcrumb;
- safe fallback when no preceding entry exists;
- retention of structural breadcrumbs alongside the navigation breadcrumb;
- the 20-entry storage limit and five-entry visible limit;
- overflow-menu navigation;
- narrow-screen presentation;
- deleted and unauthorized entity handling;
- transient API failure without permanent history loss;
- trail clearing at sign-out and user change;
- refresh and direct-entry behavior; and
- keyboard and screen-reader semantics.

A browser click test must exercise at least this path:

```text
Dashboard → Aggregations → Aggregation Detail → Record Detail
```

The test must navigate directly back to Aggregations through the breadcrumb,
verify that the later entries are removed, and confirm that the prior
Aggregations page mode and presentation state are restored.

## 16. Acceptance criteria

The feature is complete when:

1. every authenticated primary page shows the navigation breadcrumb in the same
   location;
2. the current page is the final, non-interactive entry;
3. earlier entries restore the selected page and relevant presentation state;
4. navigation backward removes the abandoned forward branch;
5. re-rendering and refreshing do not create duplicate entries;
6. Record and Aggregation Back buttons use the same history semantics;
7. structural breadcrumbs remain available where hierarchy context is needed;
8. long trails use accessible bounded overflow behavior;
9. deleted, stale, and unauthorized targets fail safely;
10. trails never cross authenticated-user boundaries; and
11. disposable-database automated tests and the required browser click test
    pass.

## 17. Review decisions requested

The following proposed defaults should be confirmed before implementation:

1. retain at most 20 entries in the session trail;
2. display at most five entries before using overflow;
3. preserve the trail across browser refresh but not across sign-out;
4. make existing detail-page Back buttons equivalent to one breadcrumb step;
   and
5. keep structural breadcrumbs separate from navigation history.
