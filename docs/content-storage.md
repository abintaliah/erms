# Digital component content storage

Digital components are lifecycle-dependent parts of their record. The
`digital_components.record_id` foreign key uses `ON DELETE CASCADE`: deleting
an open record atomically deletes its component metadata, and each component's
stored PostgreSQL blob is then removed by its own cascading foreign key. The
record-deletion confirmation in the UI states this consequence explicitly.

## Current design

Digital component metadata remains in `digital_components`. Binary content is
stored separately in `digital_component_blobs.content`, a PostgreSQL `bytea`
column. PostgreSQL can move large `bytea` values into its TOAST storage
automatically, so normal entity queries do not have to retrieve the bytes.

The separation is deliberate: the API uses a content-storage interface whose
current implementation is PostgreSQL. A future S3 implementation can use
`storage_backend = 's3'` and `storage_key` without changing the public content
endpoints or the rest of the records model.

`CONTENT_STORAGE_BACKEND` selects the provider and currently accepts only
`postgresql`. `MAX_UPLOAD_SIZE_BYTES` defaults to 52,428,800 bytes (50 MiB).
The API calculates the file size and SHA-256 checksum; clients do not supply
trusted values for uploaded content.

## Endpoints

- `POST /api/v1/records/{record_id}/digital-components/upload` creates the
  component and accepts multipart fields `file`, `component_order`, and an
  optional `date_originated`.
- `GET /api/v1/digital-components/{id}/content` downloads the content.
- `PUT /api/v1/digital-components/{id}/content` replaces the content and
  requires `If-Match`.
- `DELETE /api/v1/digital-components/{id}/content` removes the stored bytes,
  marks the component as `deleted`, and requires `If-Match`.

Content operations add `CONTENT_UPLOADED`, `CONTENT_DOWNLOADED`,
`CONTENT_REPLACED`, and `CONTENT_DELETED` events. These events store file name,
MIME type, size and checksum metadata only. File bytes are never copied into
`event_history`.

## Operational boundary

This PostgreSQL provider is suitable for getting the system running and for
modest files. Before adopting large files or high download volume, add the S3
provider and stream content directly from object storage. Database backups,
replication, and storage capacity currently include all uploaded content.
