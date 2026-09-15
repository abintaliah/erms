# Record creation drafts

Record drafts let a user assemble record metadata and digital components before
creating an authoritative record. Uploading a staged component does not create
or update a record. The record and every staged component become authoritative
only when the draft is committed.

## Lifecycle

1. `POST /api/v1/record-drafts` starts an open draft.
2. `PATCH /api/v1/record-drafts/{id}` saves its record metadata.
3. `POST /api/v1/record-drafts/{id}/components` stages one or more files.
4. Components may be listed, removed, or reordered while the draft is open.
5. `POST /api/v1/record-drafts/{id}/commit` validates and creates the complete
   record package in one database transaction.
6. `DELETE /api/v1/record-drafts/{id}` discards the metadata and staged blobs.

Open drafts expire after seven days by default. Expired drafts cannot be edited
or committed. A later housekeeping job should physically remove expired drafts.

## Atomic commit

Commit locks the draft, validates its required aggregation, record number, and
title, then inserts the record, ordered component metadata, PostgreSQL blobs,
and content audit events. If any operation fails, the transaction rolls back and
no partial authoritative record remains.

## Authorization boundary

`record_drafts.owner_user_id` is nullable until authentication supplies an
application user. Once authentication is introduced, every draft endpoint must
require draft ownership (or an administrative draft privilege). Committing a
draft should require the record-create privilege for its selected aggregation.
Operations on an already committed record remain separate permissions, such as
component add, reorder, replace, and remove; they are not implicitly granted by
record-create.

## Component ordering

Both staged and committed reorder endpoints accept the complete desired order:

```json
{
  "components": [
    {"id": 31, "component_order": 1},
    {"id": 12, "component_order": 2}
  ]
}
```

The list must contain every component exactly once and positions must be
contiguous from 1. Removal automatically closes any numbering gap.
