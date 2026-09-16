# Dashboard

The Dashboard combines system-wide entity totals with personal recent records
activity. Aggregation, record, user, role, and organizational-unit totals are
system-wide. The recent aggregation and record lists are scoped to the currently
authenticated user.

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
| `DASHBOARD_RECENT_ITEM_LIMIT` | `4` | Maximum items shown in each created/updated aggregation/record category |
| `DASHBOARD_RECENT_DAYS` | `30` | Rolling number of days included in personal recent activity |

Both values must be positive integers. Actual process environment variables
override `.env` values. Restart the NiceGUI service after changing either
setting.
