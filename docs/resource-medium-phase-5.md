# Resource medium, vital status, review and location — Phase 5

Phase 5 implements review reminders and governed aggregation locations. It is
not a review workflow or warehouse-management subsystem.

## Review scheduling

Aggregations and records expose the nullable `date_of_next_review` timestamp in
create, update, read, search and browse contracts. A non-null value must be
strictly later than the database server's current timestamp when it is first
written or changed. An existing date may naturally become overdue, and clearing
the field remains permitted.

`REVIEW_WARNING_WINDOW_DAYS` controls the upcoming window and defaults to 30.
`DASHBOARD_REVIEW_PREVIEW_LIMIT` controls each dashboard preview and defaults to
5. Both are non-negative integer environment settings validated at application
startup.

Clients should call `GET /api/v1/dashboard/summary`. Its review contract
contains:

- `review_warning_window_days`;
- complete `overdue_review_count` and `upcoming_review_count` totals;
- bounded `overdue_reviews` and `upcoming_reviews` previews.

Overdue previews are ordered by `date_of_next_review ASC, entity_id ASC`.
Upcoming previews use the same order so the nearest deadline appears first.
Only visible holdings owned by organizational units represented by the current
user's effective roles are included. Information-governance ACL bypass affects
visibility but does not manufacture organizational-unit membership.

Changing the date is scheduling metadata only. It does not complete a review,
record a finding, or produce a review-completed event.

## Aggregation locations

Only aggregations store locations. Records expose the effective locations of
their containing aggregation. Each field independently resolves to the nearest
ancestor with a non-null value:

- `assigned_location` is the expected or normal storage location;
- `current_location` is where the aggregation is currently held;
- `effective_assigned_location` and `effective_current_location` are derived
  read values.

Use `POST /api/v1/aggregations/{id}/location` with `If-Match` and a body
containing `reason` plus one or both location fields. Empty values are stored as
null and restore inheritance. The command requires the
`aggregation.location.change` global privilege and effective ACL permission;
the established information-governance role may bypass only the ACL gate.

The command is permitted on closed aggregations and records one
`RESOURCE_LOCATION_CHANGED` domain event containing old and new values and the
reason. It does not authorize changes to content, hierarchy, medium, ownership,
security level or vital status.

## Database authority

Migration `055_add_review_scheduling_and_governed_locations.sql` installs the
future-date triggers, governed-location trigger and location authorization
catalogue. Its replacement of the closed-hierarchy function preserves the
existing insert and delete branches: a permitted `BEFORE DELETE` must return
`OLD`, allowing the established `AFTER DELETE` event-history trigger to run.
The canonical schema contains the same final definitions independently.
