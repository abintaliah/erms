# Dashboard

## Client API

All dashboard clients, including web and mobile clients, should load the
dashboard through this single authenticated endpoint:

```http
GET /api/v1/dashboard/summary?recent_limit=4&recent_since=2026-08-22T00:00:00Z
```

Do not construct the dashboard by issuing separate entity-search, count,
favourites, recent-activity, classification-metric, or ownership-count
requests. That fan-out consumes multiple HTTP connections and database-pool
checkouts, can produce an internally inconsistent snapshot, and can overload a
small deployment when several dashboards refresh together. The summary
endpoint performs the complete read through one HTTP request and one database
pool checkout.

The query parameters are:

| Parameter | Required | Default | Meaning |
| --- | --- | ---: | --- |
| `recent_limit` | No | `7` | Maximum recent items for each entity-type/operation group; accepted range is 1–50 |
| `recent_since` | No | No lower bound | ISO 8601 timestamp; excludes older personal activity |

The response has this stable top-level shape:

```json
{
  "overview_counts": {"aggregations": 12, "records": 48},
  "classification_metrics": {
    "published_scheme_count": 1,
    "draft_scheme_count": 0,
    "inactive_scheme_count": 0,
    "branch_count": 8,
    "terminal_count": 24,
    "assignable_terminal_count": 20,
    "draft_terminal_count": 0,
    "inactive_classification_count": 0
  },
  "unclassified_root_count": 2,
  "ownership_counts": [
    {
      "org_unit_id": 10,
      "org_unit_code": "FIN",
      "org_unit_name": "Finance",
      "aggregation_count": 6,
      "record_count": 31
    }
  ],
  "favourites": {"aggregations": [], "records": []},
  "recent_activity": []
}
```

`overview_counts` always includes the aggregation and record counts visible to
the caller. Administrative entity totals are included only when the caller has
their corresponding global privileges; classification metrics remain zero
without classification-administration privilege. Holdings,
favourites, and recent activity use the same resource-visibility rules as their
normal APIs. `ownership_counts` contains only organizational units in which the
current user has a currently effective role, with each unit appearing once.
Favourites and recent activity are private to the authenticated user.

Clients should prevent overlapping refreshes of this endpoint. A refresh
requested while one is already in flight should reuse, await, or decline the
existing request rather than start another concurrent dashboard load.

The Dashboard combines authorized entity totals with personal recent records
activity. Aggregation and record totals follow the caller's resource visibility.
Administrative totals are available only to callers with the corresponding
global privileges. Recent aggregation and record lists are scoped to the
currently authenticated user.

## Personal favourites

Authenticated users can mark aggregations and records as private favourites by
selecting the heart control in entity tables, aggregation content lists, and
the full aggregation or record interface. A filled heart removes the favourite.
Favourite state remains available across sessions and is isolated by user.

The Dashboard shows separate newest-first previews for favourite aggregations
and records. Each preview observes `DASHBOARD_FAVOURITE_ITEM_LIMIT`. When a
collection exceeds that limit, **View all** opens its complete scrollable list.
Selecting an entry opens the existing aggregation or record interface. Removing
an entry updates the preview and complete list without opening the entity.

The Aggregations and Records search and listing pages also show the
authenticated user's corresponding favourites preview above recent activity or
search results. They use the same limit and **View all** behavior as the
Dashboard previews.

Favourites are navigation preferences rather than governed entity changes.
They do not update entity versions or create event-history entries. Deleting a
user, aggregation, or record automatically removes its dependent favourite
relationships.

## Personal recent activity

An item qualifies when its immutable event-history entry:

- has `actor_user_id` equal to the authenticated user's ID;
- is a `CREATE` or `UPDATE` event for an aggregation or record; and
- occurred within the configured rolling period.

Each category is ordered by `event_history.occurred_at`, newest first. The time
shown on a card is that activity timestamp. Deleted entities are omitted because
there is no current entity to open.

## Configuration

The NiceGUI service reads these settings from the process environment or the
project `.env` file:

| Variable | Default | Meaning |
| --- | ---: | --- |
| `DASHBOARD_FAVOURITE_ITEM_LIMIT` | `5` | Maximum entries in each Dashboard and entity-listing favourites preview |
| `DASHBOARD_RECENT_ITEM_LIMIT` | `4` | Maximum items shown in each created/updated aggregation/record category |
| `DASHBOARD_RECENT_DAYS` | `30` | Rolling number of days included in personal recent activity |

All values must be positive integers. Actual process environment variables
override `.env` values. Restart the NiceGUI service after changing either
setting.
