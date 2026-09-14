# Optimistic concurrency

Every mutable entity has a positive `version` starting at `1`. PostgreSQL
increments it on every update, including updates made outside the API.

API `PATCH`, entity `DELETE`, content replacement, and content deletion require
an `If-Match` header containing the version last read by the client:

```http
PATCH /api/v1/records/42
If-Match: 3
Content-Type: application/json

{"title": "Revised title"}
```

Quoted (`"3"`) and weak (`W/"3"`) forms are also accepted. A successful update
returns the entity with its incremented version. A missing header returns
`428 Precondition Required`; a stale version returns `412 Precondition Failed`
and includes the current version. The client should reload the entity, show the
conflict to the user, and let them decide whether to reapply their changes.

The internal `version` change is retained in audit snapshots but omitted from
`changed_fields`, so that list describes business-data changes.
