# User Favourites — Technical Specification

**Status:** Implemented
**Project:** ERMS  
**Prepared:** 17 September 2026  
**Revision:** 1.0 — implementation completed

## 1. Purpose

This specification defines personal favourites for aggregations and records.
An authenticated person account can mark an aggregation or record as a favourite,
see a configurable favourites preview on the Dashboard, use **View all** to see
the complete list, open a favourite, and remove an item from their favourites.

Favourites provide a direct navigation aid. They do not change an aggregation,
record, classification, retention rule, lifecycle state, access permission, or
any other records-management metadata.

## 2. Scope

This feature includes:

- persistent, per-user favourite aggregations and records;
- adding and removing favourites from aggregation and record interfaces;
- heart controls in aggregation and record result lists where an actions area
  already exists;
- a Dashboard section containing a configurable preview of favourites belonging
  to the authenticated user, with access to the complete list;
- navigation from each Dashboard favourite to the existing aggregation or
  record interface;
- database, REST API, API-client, NiceGUI, and automated-test changes; and
- automatic removal of a favourite relationship when its user or target entity
  is permanently deleted.

This feature does not include:

- shared, public, team, role, or organizational-unit favourites;
- folders, tags, notes, ordering, or ranking of favourites;
- favouriting classifications, classification schemes, digital components, or
  administrative entities;
- notifications about changes to favourited entities; or
- treating a favourite as a records-management event or entity modification.

## 3. Terminology and ownership

A **favourite** is a relationship between exactly one authenticated person account
and exactly one aggregation or record.

Favourites are private. A user may read and change only their own favourites.
The API derives the owner from the authenticated principal. A request must not
accept a user ID in its path, query string, or body for the purpose of choosing
the favourite owner.

Two users may independently favourite the same entity. Removing one user's
favourite must not affect any other user.

## 4. Functional requirements

### 4.1 Add a favourite

An authenticated user can add an existing aggregation or record to their
favourites. Adding an already-favourited item succeeds without creating a
duplicate relationship or returning an error.

Adding a favourite does not modify the target entity's `version`, event
history, date fields, or lifecycle state. A closed aggregation and a record in
an effectively closed aggregation may be favourited.

### 4.2 Remove a favourite

An authenticated user can remove an aggregation or record from their
favourites. Removing an item that is not currently a favourite succeeds and is
a no-op.

Removing a favourite does not modify the target entity.

### 4.3 List favourites

The user can retrieve all of their current favourite aggregations and records.
The result contains only existing entities that the user is permitted to see.
The current system permits every authenticated user to read aggregations and
records. When entity-level authorization is introduced, the favourites query
must apply the same read-authorization rules as the corresponding entity query.

Favourite lists are ordered by the time the item was added, newest first.
Aggregation and record lists are ordered independently.

### 4.4 Permanent entity deletion

Permanently deleting an aggregation or record automatically removes every
favourite relationship pointing to that entity. No stale Dashboard entry may
remain. Existing aggregation and record deletion rules remain unchanged.

### 4.5 User lifecycle

Changing a user's status to inactive or suspended does not delete their
favourites. The favourites remain available if the user is later restored to
active status.

Permanently deleting a user automatically deletes all favourite relationships
owned by that user.

Service accounts cannot establish an interactive authenticated session under
the current authentication model. The favourite tables nevertheless use the
general `users` foreign key; no additional database account-type constraint is
required.

## 5. Data model

Migration `029_add_user_favourites.sql` adds two relationship tables. Separate
tables are required so PostgreSQL can enforce foreign-key integrity for both
target types. A polymorphic `entity_type` and `entity_id` table must not be
used.

### 5.1 `user_favourite_aggregations`

| Column | Type | Rules |
| --- | --- | --- |
| `user_id` | `bigint` | Required; references `users(id)` with `ON DELETE CASCADE` |
| `aggregation_id` | `bigint` | Required; references `aggregations(id)` with `ON DELETE CASCADE` |
| `date_created` | `timestamptz` | Required; defaults to `CURRENT_TIMESTAMP` |

The primary key is `(user_id, aggregation_id)`. It prevents duplicate
favourites and provides the lookup index for a user's aggregation favourites.
An additional index on `(aggregation_id)` supports entity deletion and
diagnostics. An index on `(user_id, date_created DESC, aggregation_id)` supports
the Dashboard ordering.

### 5.2 `user_favourite_records`

| Column | Type | Rules |
| --- | --- | --- |
| `user_id` | `bigint` | Required; references `users(id)` with `ON DELETE CASCADE` |
| `record_id` | `bigint` | Required; references `records(id)` with `ON DELETE CASCADE` |
| `date_created` | `timestamptz` | Required; defaults to `CURRENT_TIMESTAMP` |

The primary key is `(user_id, record_id)`. An additional index on `(record_id)`
supports entity deletion and diagnostics. An index on
`(user_id, date_created DESC, record_id)` supports the Dashboard ordering.

### 5.3 Canonical schema and migration tracking

The two tables and indexes must be present in both:

- `database/migrations/029_add_user_favourites.sql`, for existing databases;
  and
- `database/schema.sql`, for new databases.

The migration must be transactional and record
`029_add_user_favourites` in `schema_migrations` only after all objects have
been created successfully. `database/README.md` must include the migration in
the ordered upgrade instructions.

### 5.4 Audit behaviour

Favourite changes are personal interface preferences, not changes to governed
records. The favourite tables must not have entity-history triggers, and
favourite operations must not create entries in `event_history`.

Normal request IDs, authentication checks, application logs, and database
operational logs remain available for troubleshooting.

## 6. REST API

All endpoints require an authenticated principal and use the principal's
`user_id`. Requests made without a valid authenticated principal return `401`.

### 6.1 List all favourites

```http
GET /api/v1/favourites
```

Successful response: `200 OK`.

```json
{
  "aggregations": [
    {
      "id": 42,
      "aggregation_number": "FIN-2026",
      "title": "Annual financial administration",
      "parent_aggregation_id": null,
      "date_favourited": "2026-09-17T10:30:00Z"
    }
  ],
  "records": [
    {
      "id": 91,
      "record_number": "FIN-R-001",
      "title": "Approved budget",
      "aggregation_id": 42,
      "aggregation_number": "FIN-2026",
      "aggregation_title": "Annual financial administration",
      "date_favourited": "2026-09-17T10:31:00Z"
    }
  ]
}
```

The endpoint returns the complete current lists. It does not require the client
to make one request per favourite. Each collection is ordered by
`date_favourited DESC`, with the entity ID descending as the deterministic
tie-breaker.

### 6.2 Favourite an aggregation

```http
PUT /api/v1/favourites/aggregations/{aggregation_id}
```

The endpoint verifies that the aggregation exists and is readable by the
current user, then performs an insert with conflict handling. It returns
`204 No Content` whether the relationship was newly created or already
existed. A missing aggregation returns `404`.

### 6.3 Unfavourite an aggregation

```http
DELETE /api/v1/favourites/aggregations/{aggregation_id}
```

The endpoint deletes only the current user's relationship. It returns
`204 No Content` whether or not the relationship existed. It does not require
the aggregation itself to remain present.

### 6.4 Favourite a record

```http
PUT /api/v1/favourites/records/{record_id}
```

The endpoint verifies that the record exists and is readable by the current
user, then performs an insert with conflict handling. It returns
`204 No Content` whether the relationship was newly created or already
existed. A missing record returns `404`.

### 6.5 Unfavourite a record

```http
DELETE /api/v1/favourites/records/{record_id}
```

The endpoint deletes only the current user's relationship. It returns
`204 No Content` whether or not the relationship existed. It does not require
the record itself to remain present.

### 6.6 Concurrency and transactions

Favourite operations do not use `If-Match` because they do not update a
versioned entity. Composite primary keys and conflict-safe inserts make
concurrent duplicate requests safe. Each operation completes in one database
transaction.

The list endpoint joins relationship rows to the current aggregation or record
row. It must not return an unresolvable target even if a concurrent delete
occurs while the request is executing.

## 7. API client

`ErmsApiClient` gains the following operations:

```python
async def favourites(self) -> dict[str, list[dict[str, Any]]]
async def favourite(self, resource: str, entity_id: int) -> None
async def unfavourite(self, resource: str, entity_id: int) -> None
```

`resource` accepts only `aggregations` or `records`. The implementation must
not construct a request for any other resource.

The client continues to attach the current bearer token and
`X-Event-Source: web_ui` by using the existing `request` method.

## 8. User interface

### 8.1 Heart control

The favourite control is an icon button with two states:

| State | Icon | Colour | Tooltip and accessible label |
| --- | --- | --- | --- |
| Not a favourite | `favorite_border` | Neutral or primary | `Add to favourites` |
| Favourite | `favorite` | Red or the established strong accent | `Remove from favourites` |

The button must have a tooltip and an accessible label. State must not be
communicated by colour alone; the icon shape and label also change.

The control appears in:

- the aggregation detail header or primary aggregation summary card;
- the record detail-dialog header;
- aggregation search-result action cells;
- record search-result action cells;
- contained-aggregation cards where an action can be added without making the
  card ambiguous; and
- record rows within an aggregation's record table.

The heart is not an edit action and remains enabled for closed aggregations and
records in closed aggregation hierarchies.

### 8.2 Click behaviour

Clicking the heart toggles the state without navigating away from or opening
the surrounding entity. Event propagation must be stopped when the heart is
inside a clickable row or card.

The UI updates the heart immediately, then sends the API request. On success,
it keeps the new state and shows a brief confirmation:

- `Added to favourites`; or
- `Removed from favourites`.

If the request fails, the UI restores the previous state and shows the
standard error notification. While the request is in progress, that heart
control is disabled to prevent overlapping toggles.

### 8.3 Initial state

After authentication, the page loads the user's favourites once and keeps two
in-memory sets of target IDs for the current browser page. Entity renderers use
these sets to choose the correct icon state. A successful toggle updates the
corresponding set.

Signing out clears both sets. Signing in as another user must reload favourites
before authenticated entity content is shown, preventing state from the prior
user from appearing.

Refreshing the Dashboard reloads favourites from the API so changes made in
another browser page or session become visible.

## 9. Dashboard

The Dashboard adds a **Your favourites** section after the system overview and
governance-attention content and before **Your recent records activity**.

The section contains two cards or columns:

1. **Favourite aggregations**; and
2. **Favourite records**.

Each card initially shows no more than the configured number of entries. The
limit applies independently to aggregation favourites and record favourites;
for example, a limit of five permits up to five aggregations and five records
in the Dashboard preview. Entries retain the newest-first order returned by the
API.

When a collection contains more entries than its preview limit, its card shows
a **View all** action with the total count, for example **View all (12)**. The
action opens a dialog containing the complete collection. The dialog uses a
bounded, scrollable list, retains newest-first ordering, and provides the same
open and unfavourite actions as the Dashboard preview. Closing the dialog
returns to the Dashboard without losing its state.

The **View all** action is omitted when the complete collection already fits in
the preview. The UI must never imply that the preview is the complete list when
additional entries exist.

### 9.1 Aggregation entry

Each aggregation entry shows:

- a folder icon;
- aggregation title;
- aggregation number;
- a filled heart button for removal; and
- a navigation affordance such as a chevron.

Clicking the entry calls the existing `open_aggregation` workflow and displays
that aggregation's full interface.

### 9.2 Record entry

Each record entry shows:

- a document icon;
- record title;
- record number;
- containing aggregation number and title as secondary context;
- a filled heart button for removal; and
- a navigation affordance such as a chevron.

Clicking the entry calls the existing `show_record_details` workflow and opens
the existing record interface.

### 9.3 Removing an item from the Dashboard

Clicking the filled heart removes only that item and does not open it. After a
successful request, the entry disappears immediately. If the request fails,
the entry remains and the error is shown. When an item is removed from a
Dashboard preview and more favourites exist in that collection, the next item
in newest-first order fills the newly available preview position. The total in
the **View all** action updates immediately and the action disappears if the
remaining collection fits within the configured limit.

### 9.4 Empty states

If both collections are empty, the section displays:

> You haven't added any favourites yet. Select the heart on an aggregation or
> record for quick access here.

If only one collection is empty, its card displays `No favourite aggregations`
or `No favourite records` while the other collection remains visible.

Loading uses the Dashboard's existing spinner treatment. A favourites request
failure uses the existing Dashboard error handling and must not render stale
data from another user.

### 9.5 Configuration

The NiceGUI service reads the following setting from the process environment or
the project `.env` file:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `DASHBOARD_FAVOURITE_ITEM_LIMIT` | `5` | Maximum aggregation entries and maximum record entries shown in their respective Dashboard preview cards |

The value must be a positive integer. An absent value uses the default of five.
An invalid or non-positive value is a configuration error and must use the
project's existing configuration-error behaviour rather than being silently
accepted. A process environment variable overrides the `.env` value. The
NiceGUI service must be restarted after the setting changes.

This setting limits presentation only. It must not limit the API response, the
in-memory favourite-ID sets, the total shown by **View all**, or the contents of
the complete-list dialog.

## 10. Authorization and security

The following rules are mandatory:

- The server, not the client, selects the owner from the authenticated
  principal.
- SQL statements for list, insert, and delete operations include the
  authenticated `user_id`.
- A user cannot infer another user's favourites through response content,
  counts, status codes, or timing-dependent existence checks intentionally
  exposed by the application.
- Add operations verify the target through the same read boundary used by the
  corresponding aggregation or record endpoint.
- Future entity-level authorization must be applied both when a favourite is
  added and when favourites are listed.
- The UI's in-memory favourite sets are convenience state only and are never an
  authorization boundary.

## 11. Error handling

| Condition | Required result |
| --- | --- |
| Unauthenticated request | `401 Unauthorized` |
| Favourite target does not exist on `PUT` | `404 Not Found` |
| Target exists but is not readable | `404 Not Found`, unless the application later adopts a uniform `403` policy |
| Repeated `PUT` | `204 No Content`; no duplicate row |
| Repeated `DELETE` | `204 No Content` |
| Database temporarily unavailable | Existing `503` handling and retry guidance |
| UI toggle fails | Restore prior heart state and show an error |
| Target is deleted after Dashboard load | Opening it shows the existing not-found error, then a Dashboard refresh removes it |

## 12. Performance requirements

The list endpoint uses at most one query for aggregation favourites and one
query for record favourites. It must not issue one entity query per favourite.

Dashboard loading requests favourites in parallel with its other independent
data requests. Adding or removing one favourite must not reload all
aggregations or records.

The indexes defined in Section 5 must support lookup by user, newest-first
ordering, and foreign-key target deletion without sequentially scanning the
relationship tables.

## 13. Automated testing

### 13.1 Database and migration tests

Tests must verify:

- successful migration and migration tracking;
- both composite primary keys reject duplicates;
- required columns and foreign keys are enforced;
- deleting an aggregation cascades to its favourite rows;
- deleting a record cascades to its favourite rows;
- deleting a user cascades to both favourite tables;
- user deactivation does not delete favourites; and
- favourite operations do not create entity-history events.

### 13.2 API tests

Tests must verify:

- authentication is required for every endpoint;
- a user can favourite and unfavourite an aggregation;
- a user can favourite and unfavourite a record;
- repeated `PUT` and `DELETE` calls are idempotent;
- a missing target returns `404` on `PUT`;
- one user cannot list or delete another user's favourites;
- list results contain the required hydrated fields and deterministic ordering;
- aggregation and record favourites are returned in their correct collections;
- deleted targets disappear automatically; and
- closed entities can be favourited.

### 13.3 API-client tests

Tests must verify the HTTP method and path used by each client operation, the
accepted resource values, authentication propagation through the common
request path, and `204` response handling.

### 13.4 NiceGUI tests

Tests must verify:

- outlined and filled heart states render correctly;
- toggling updates state and calls the correct API operation;
- a failed toggle restores the previous state;
- rapid repeated clicks cannot create overlapping requests;
- clicking a heart inside a clickable row or card does not navigate;
- signing out clears the in-memory state;
- the Dashboard renders empty, aggregation-only, record-only, and mixed lists;
- each Dashboard preview independently observes the configured limit;
- the default preview limit is five;
- invalid and non-positive configuration values are rejected;
- **View all** appears only when a collection exceeds the limit and shows its
  correct total;
- **View all** exposes every returned favourite in the selected collection;
- removing a Dashboard favourite removes the correct entry;
- removing an entry from the complete-list dialog updates both the dialog and
  Dashboard preview;
- clicking an aggregation favourite opens the correct aggregation;
- clicking a record favourite opens the correct record; and
- one user's browser state is not shown after another user signs in.

Browser-level end-to-end coverage must exercise at least one complete workflow:
sign in, favourite an aggregation and record, confirm both on the Dashboard,
open each item, unfavourite each item, and confirm the empty state.

## 14. Acceptance criteria

The feature is complete only when all of the following are true:

1. An authenticated user can add or remove an aggregation favourite using a
   heart control.
2. An authenticated user can add or remove a record favourite using a heart
   control.
3. Favourite state persists across page refreshes, sign-out, and later sign-in.
4. Favourites are isolated between users.
5. The Dashboard shows up to the configured number of favourite aggregations
   and records, using a default limit of five for each collection.
6. When either collection exceeds the configured limit, **View all** exposes
   every current favourite in that collection.
7. Selecting a Dashboard aggregation opens the existing aggregation interface.
8. Selecting a Dashboard record opens the existing record interface.
9. Removing a favourite from the Dashboard does not open the item.
10. Closed aggregations and records in closed hierarchies can be favourited and
   unfavourited.
11. Deleting a target entity leaves no stale favourite relationship.
12. Favourite changes do not alter target versions or create entity-history
    events.
13. All database, API, API-client, UI, and end-to-end tests described in this
    specification pass.

## 15. Implementation locations

The implementation is expected to change at least:

- `database/migrations/029_add_user_favourites.sql`;
- `database/schema.sql`;
- `database/README.md`;
- `backend/services/api/schemas.py`;
- a dedicated backend favourites module or `backend/services/api/main.py`;
- `backend/services/api/tests/`;
- `frontend/webui/api_client.py`;
- `frontend/webui/app.py`;
- `frontend/webui/config.py`;
- `frontend/webui/tests/`; and
- the browser end-to-end test suite when present.

Implementation documentation is maintained in `docs/dashboard.md`. This
specification remains the normative statement of required behaviour until
superseded by a later revision.
