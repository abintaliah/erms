# ERMS REST API search grammar

The advanced search API uses a controlled JSON grammar. It supports nested
boolean expressions without accepting raw SQL, database table names, or
unapproved column names from clients.

## Endpoints

```text
POST /api/v1/aggregations/search
POST /api/v1/records/search
POST /api/v1/digital-components/search
POST /api/v1/event-history/search
POST /api/v1/users/search
POST /api/v1/org-units/search
POST /api/v1/roles/search
POST /api/v1/user-role-assignments/search
```

The ordinary `GET` collection endpoints remain available for simple equality
filters. Use the search endpoints for boolean logic, ranges, sets, null tests,
or case-insensitive text matching.

## Request structure

```json
{
  "where": { "field": "title", "operator": "contains_ci", "value": "contract" },
  "sort": [
    { "field": "date_created", "direction": "desc" }
  ],
  "limit": 100,
  "offset": 0
}
```

All properties are optional. With no `where`, all rows match. The defaults are
`limit: 100`, `offset: 0`, and ascending order by `id`. The maximum page size is
500. If a custom sort does not contain `id`, ascending `id` is automatically
added as the final key so pagination is deterministic.

The response contains the matching page and pagination metadata:

```json
{
  "items": [],
  "total": 0,
  "limit": 100,
  "offset": 0,
  "returned": 0
}
```

`total` is the number of matches before pagination, while `returned` is the
number of items in this response.

## Comparison expressions

A comparison has a field, operator, and—except for null operators—a value:

```json
{ "field": "size_in_bytes", "operator": "gte", "value": 1048576 }
```

Supported operators:

| Operator | Meaning | Value |
| --- | --- | --- |
| `eq` | Equal | One value |
| `ne` | Not equal | One value |
| `gt` | Greater than | One value |
| `gte` | Greater than or equal | One value |
| `lt` | Less than | One value |
| `lte` | Less than or equal | One value |
| `in` | Equal to any member | Array of 1–100 values |
| `not_in` | Equal to no member | Array of 1–100 values |
| `between` | Inclusive lower and upper bounds | Array containing exactly two values |
| `is_null` | Has no value | No `value` property |
| `is_not_null` | Has a value | No `value` property |
| `contains_ci` | Contains literal text, ignoring case | One string |
| `starts_with_ci` | Starts with literal text, ignoring case | One string |
| `ends_with_ci` | Ends with literal text, ignoring case | One string |

The three `*_ci` operators treat `%` and `_` as literal characters rather than
SQL wildcard characters. Null checks are accepted only for nullable fields.
Datetime values must be ISO 8601 timestamps with a timezone, such as
`2026-09-14T10:00:00Z`.

## Boolean expressions

### AND

Every child must match:

```json
{
  "and": [
    { "field": "aggregation_id", "operator": "eq", "value": 42 },
    { "field": "date_originated", "operator": "gte", "value": "2026-01-01T00:00:00Z" }
  ]
}
```

### OR

At least one child must match:

```json
{
  "or": [
    { "field": "title", "operator": "contains_ci", "value": "contract" },
    { "field": "description", "operator": "contains_ci", "value": "agreement" }
  ]
}
```

### NOT

The child must not match:

```json
{
  "not": {
    "field": "mime_type",
    "operator": "eq",
    "value": "application/pdf"
  }
}
```

Boolean expressions can be nested. Each expression object must contain exactly
one comparison or one of `and`, `or`, and `not`. `and` and `or` arrays cannot be
empty.

## Combined example

This query finds records from selected aggregations, originated during 2025,
whose title contains “contract” or whose description is null, while excluding
records with “draft” in the title:

```json
{
  "where": {
    "and": [
      {
        "field": "aggregation_id",
        "operator": "in",
        "value": [10, 20, 30]
      },
      {
        "field": "date_originated",
        "operator": "between",
        "value": [
          "2025-01-01T00:00:00Z",
          "2025-12-31T23:59:59Z"
        ]
      },
      {
        "or": [
          { "field": "title", "operator": "contains_ci", "value": "contract" },
          { "field": "description", "operator": "is_null" }
        ]
      },
      {
        "not": {
          "field": "title",
          "operator": "contains_ci",
          "value": "draft"
        }
      }
    ]
  },
  "sort": [
    { "field": "date_originated", "direction": "desc" },
    { "field": "record_number", "direction": "asc" }
  ],
  "limit": 50,
  "offset": 0
}
```

## Searchable fields

### Aggregations

`id`, `parent_aggregation_id`, `aggregation_number`, `title`, `description`,
`date_created`, `date_opened`, `date_closed`

### Records

`id`, `aggregation_id`, `record_number`, `title`, `description`, `date_created`,
`date_originated`

### Digital components

`id`, `record_id`, `component_order`, `file_name`, `date_created`,
`date_originated`, `mime_type`, `size_in_bytes`, `checksum_algo`,
`checksum_value`

### Event history

`id`, `occurred_at`, `transaction_id`, `entity_type`, `entity_id`, `operation`,
`actor_user_id`, `actor_name`, `actor_email`, `actor_type`, `source`,
`request_id`, `correlation_id`, `reason`

### Users

`id`, `name`, `email`, `external_id`, `status`, `date_created`,
`date_deactivated`

### Organizational units

`id`, `parent_org_unit_id`, `code`, `name`, `description`, `status`,
`date_created`, `date_deactivated`

### Roles

`id`, `org_unit_id`, `supervisor_role_id`, `code`, `name`, `description`,
`status`, `date_created`, `date_deactivated`

### User-role assignments

`id`, `user_id`, `role_id`, `assigned_by`, `date_assigned`, `valid_from`,
`valid_until`

The same field allowlists apply to sorting. Case-insensitive text operators are
valid only for text fields. Null operators are valid only for nullable fields.

## Safety and complexity limits

- Values are always sent to PostgreSQL as parameters.
- Fields, tables, operators, and sort directions come from server-side allowlists.
- A query can contain at most 50 comparison conditions.
- Boolean expressions can be nested at most five levels.
- An `in` or `not_in` array can contain at most 100 values.
- A request can contain at most 10 sort fields.
- A response can contain at most 500 items.
- Invalid queries return HTTP `422 Unprocessable Entity`.
