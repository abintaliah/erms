# Segmented PostgreSQL Digital Content Storage — Implementation Specification

**Status:** Implemented — segmented-storage baseline
**Project:** ERMS  
**Prepared:** 17 September 2026  
**Revision:** 1.1 — implementation completed 17 September 2026

## 1. Purpose

This specification defines an optional PostgreSQL content-storage provider that
stores a digital component as an ordered set of `bytea` segments rather than as
one `bytea` value. It removes the current single-value size ceiling and permits
large files to be uploaded, staged, downloaded, previewed, and replaced without
materializing the complete file in application or database memory.

This provider is intended to remain useful for installations that deliberately
keep content in PostgreSQL. It does not replace the planned S3-compatible object
storage provider. Both providers must implement the same storage interface so
that content APIs and records-management behavior do not depend on where bytes
are stored.

### 1.1 Implemented baseline

The implemented baseline segments synchronous multipart uploads, records their
internal upload sessions, streams full and ranged responses, safely stages
replacements, segments record drafts, promotes drafts without reconstructing a
file, and supplies manual/dedicated-worker cleanup. Public initiate/append/resume
endpoints are not yet exposed; interrupted transfers currently roll back as one
request transaction. Those endpoints can be added later without changing the
content-set or segment model defined here.

## 2. Background and design decision

PostgreSQL `bytea` values are subject to an approximately 1 GiB value limit.
TOAST may compress or move a large value out of line, but it does not remove
that limit. The current `digital_component_blobs` table stores one complete
file in one `bytea` column and the current API builds the complete upload in
memory before inserting it.

The approved design divides a file into independently stored segments:

```text
Digital component 42 (2.4 GiB)
    segment 0  ── 16 MiB
    segment 1  ── 16 MiB
    segment 2  ── 16 MiB
       ...
    segment N  ── remaining bytes
```

Segments are read in sequence and streamed to the HTTP client. They must not be
concatenated into a single SQL value or a complete in-memory Python `bytes`
object.

The default segment size shall be **16 MiB**. It must be configurable within a
safe operational range. Segments around 8–32 MiB are preferred; 500 MiB
segments are technically possible but rejected as the default because each
segment may still be materialized by the driver, causing excessive per-request
memory use and slow cancellation.

## 3. Scope

This work covers:

- segmented storage for committed digital components;
- segmented storage for files staged in record drafts;
- streaming upload, replacement, download, and preview;
- HTTP byte-range requests;
- upload state, finalization, cancellation, and abandoned-upload cleanup;
- whole-file and optional per-segment integrity checks;
- migration of existing single-row content without data loss;
- storage-provider abstraction for a later S3 implementation;
- audit events and operational metrics; and
- automated database, API, and integration tests.

This work does not implement S3 storage, virus scanning, content encryption at
the application layer, deduplication, or multipart uploads directly from a
browser to object storage.

## 4. Domain invariants

1. A digital component is dependent on exactly one record. Deleting a record
   continues to cascade through its digital components and all stored segments.
2. A stored segment belongs to exactly one digital component and has exactly
   one zero-based sequence number within that component.
3. A complete component has a contiguous sequence from `0` through
   `segment_count - 1`; gaps and duplicate sequence numbers are invalid.
4. The sum of segment sizes must equal `digital_components.size_in_bytes`.
5. The checksum calculated over the ordered, unmodified byte stream must equal
   the component's whole-file checksum.
6. Only content in the `available` state may be downloaded, previewed, or
   committed from a draft.
7. An incomplete upload must never appear to users as a valid digital
   component.
8. Closed-aggregation protections continue to apply to creating, replacing, or
   deleting content and to every segment mutation.
9. File bytes and segment bytes must never be copied into `event_history`.

## 5. Data model

### 5.1 Committed content sets and segments

A **content set** is one complete candidate copy of a digital component's file.
It is a concrete database object, not an abstract "generation." A component
normally has one active content set. While that file is being replaced, it may
also have one staged content set whose segments are still being uploaded or
verified. The active set remains downloadable until the staged set is complete.

```sql
CREATE TABLE digital_component_content_sets (
    id                    bigserial PRIMARY KEY,
    digital_component_id  bigint NOT NULL
        REFERENCES digital_components (id) ON DELETE CASCADE,
    status                text NOT NULL
        CHECK (status IN ('staged', 'active', 'superseded', 'failed')),
    size_in_bytes         bigint,
    segment_count         integer,
    checksum_algo         text,
    checksum_value        text,
    date_created          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_completed        timestamptz,
    CHECK (size_in_bytes IS NULL OR size_in_bytes >= 0),
    CHECK (segment_count IS NULL OR segment_count >= 0)
);

CREATE UNIQUE INDEX digital_component_one_active_content_set_idx
    ON digital_component_content_sets (digital_component_id)
    WHERE status = 'active';
```

`digital_components.active_content_set_id` points to the content set currently
served to users. The foreign key must ensure that the referenced content set
belongs to that component; this may be enforced with a composite unique key and
foreign key or by the finalization function under a row lock.

The existing one-row-per-component `digital_component_blobs` table will become
an ordered segment table belonging to a content set. Retaining the blobs table
name minimizes migration churn.

```sql
CREATE TABLE digital_component_blobs (
    id                    bigserial PRIMARY KEY,
    content_set_id        bigint NOT NULL
        REFERENCES digital_component_content_sets (id) ON DELETE CASCADE,
    segment_no            integer NOT NULL,
    segment_size          integer NOT NULL,
    segment_checksum_algo text,
    segment_checksum_value text,
    content               bytea NOT NULL,
    date_stored           timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT digital_component_blobs_set_segment_unique
        UNIQUE (content_set_id, segment_no),
    CONSTRAINT digital_component_blobs_segment_no_nonnegative
        CHECK (segment_no >= 0),
    CONSTRAINT digital_component_blobs_segment_size_positive
        CHECK (segment_size > 0),
    CONSTRAINT digital_component_blobs_segment_size_matches
        CHECK (segment_size = octet_length(content))
);

CREATE INDEX digital_component_blobs_component_order_idx
    ON digital_component_blobs (content_set_id, segment_no);
```

The unique constraint provides deterministic ordering and prevents duplicate
segments. `id` follows the project's convention that non-join tables have a
`bigserial` primary key. The component-and-segment index supports ordered full
reads and range lookup.

The maximum allowed segment size is application configuration rather than a
large hard-coded database limit. The database migration may add a conservative
absolute check after operational testing establishes an appropriate ceiling.

Per-segment checksums are recommended and configurable. The whole-file
checksum remains authoritative.

### 5.2 Digital component metadata

Extend or clarify `digital_components` with:

```sql
active_content_set_id bigint
upload_completed_at timestamptz
```

`size_in_bytes`, `checksum_algo`, and `checksum_value` continue to describe the
complete logical file, not an individual segment.

`digital_components.content_status` shall support these states:

```text
pending → uploading → available
                    ↘ failed
                    ↘ quarantined
available → deleted
```

During replacement, an already available component remains `available` because
its old active content set is still readable. Progress and failure of the
replacement are represented by its upload session and staged content set, not
by making the component unavailable.

If backwards compatibility makes a separate `uploading` value unnecessarily
disruptive, `pending` may represent an active incomplete upload. The API and
documentation must nevertheless distinguish incomplete content from metadata
awaiting an upload. The preferred implementation adds `uploading` explicitly.

The active content set's `segment_count` is null until successful finalization,
positive for a non-empty available file, and may be zero if zero-byte files are
supported through an explicit policy. Empty files cannot be represented by a
positive-size segment and therefore require finalization with zero segments.

### 5.3 Draft content segments

The current `record_draft_components.content bytea` column has the same
single-value limitation and must not remain in the large-file path. Move staged
bytes to a dependent segment table:

```sql
CREATE TABLE record_draft_component_blobs (
    id                         bigserial PRIMARY KEY,
    record_draft_component_id  bigint NOT NULL
        REFERENCES record_draft_components (id) ON DELETE CASCADE,
    segment_no                 integer NOT NULL,
    segment_size               integer NOT NULL,
    segment_checksum_algo      text,
    segment_checksum_value     text,
    content                    bytea NOT NULL,
    date_stored                timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE (record_draft_component_id, segment_no),
    CHECK (segment_no >= 0),
    CHECK (segment_size > 0),
    CHECK (segment_size = octet_length(content))
);
```

Add upload status, segment count, and completion time to
`record_draft_components`, then remove its monolithic `content` column after
migration and verification. Committing a record draft should transfer segment
ownership without joining all bytes. The preferred implementation inserts the
final component metadata and copies or moves segment rows with set-based SQL in
the same short transaction.

### 5.4 Upload sessions

An upload session is recommended for resumability and cleanup:

```sql
CREATE TABLE content_upload_sessions (
    id                    bigserial PRIMARY KEY,
    digital_component_id  bigint REFERENCES digital_components (id)
        ON DELETE CASCADE,
    draft_component_id    bigint REFERENCES record_draft_components (id)
        ON DELETE CASCADE,
    content_set_id        bigint REFERENCES digital_component_content_sets (id)
        ON DELETE CASCADE,
    status                text NOT NULL,
    next_segment_no       integer NOT NULL DEFAULT 0,
    bytes_received        bigint NOT NULL DEFAULT 0,
    expected_size         bigint,
    checksum_algo         text NOT NULL DEFAULT 'sha256',
    date_created          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    date_updated          timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at            timestamptz NOT NULL,

    CHECK (
        (digital_component_id IS NOT NULL)::integer
        + (draft_component_id IS NOT NULL)::integer = 1
    )
);
```

Only one open session may target a given component. Session tokens exposed to a
client must be unguessable and stored as hashes if possession authorizes upload
continuation. The initial implementation may keep upload-session operations
behind an authenticated API session rather than expose a separate bearer token.

Upload-session status is distinct from component availability and shall use
these explicit states:

| State | Meaning | Are received segment bytes retained? |
|---|---|---|
| `uploading` | The client is actively sending segments. | Yes |
| `interrupted` | Transfer stopped unexpectedly and may be resumed before expiry. | Yes, temporarily |
| `finalizing` | All bytes arrived and integrity checks are running. | Yes |
| `completed` | The staged file was verified and made available. | Until ownership transfer or normal cleanup |
| `failed` | A permanent validation, checksum, or storage failure occurred. | No; delete promptly |
| `cancelled` | The user or administrator explicitly abandoned the upload. | No; delete promptly |
| `expired` | A resumable upload exceeded its permitted lifetime. | No; cleanup deletes them |

For a record draft, `completed` means **successfully staged**, not yet committed
as a record. Its rows in `record_draft_component_blobs` remain necessary until
the user creates the complete record package, removes the staged component,
cancels the draft, or the draft expires.

### 5.5 Explicit staged-content lifecycle

The lifecycle of `record_draft_component_blobs` is normative:

| Situation | Required treatment of staged rows |
|---|---|
| Upload is active | Keep every successfully committed segment. |
| Upload is interrupted but resumable | Keep segments only until the upload session expires. |
| Upload succeeds | Keep segments while the record draft remains open; they are the verified staged file. |
| User creates the record | Transfer/copy segments to the new committed content set, verify completion, then delete the draft rows through draft cleanup. |
| User removes the staged component | Delete its metadata and cascade-delete all staged segments. |
| User cancels the draft | Delete the draft and cascade-delete all staged segments. |
| Draft expires | Scheduled cleanup deletes the draft and all staged segments. |
| Upload fails a permanent validation or checksum check | Mark it failed and delete its segments promptly. |
| User explicitly cancels an upload | Mark it cancelled and delete its segments promptly. |
| API process or host crashes | Leave committed segments recoverable; resume before expiry or let scheduled cleanup remove them. |

Successful upload therefore does **not** mean immediate deletion from the draft
blob table. It means that the staged file is complete and verified, ready to be
included when the user creates the record. Conversely, permanently failed,
cancelled, and expired uploads must not retain their bytes indefinitely.

## 6. Configuration

Add these environment settings and document them in every API environment
template:

| Setting | Default | Meaning |
|---|---:|---|
| `CONTENT_STORAGE_BACKEND` | `postgresql` | `postgresql` now; `s3` later |
| `CONTENT_SEGMENT_SIZE_BYTES` | `16777216` | Target PostgreSQL segment size (16 MiB) |
| `MAX_UPLOAD_SIZE_BYTES` | existing deployment value | Maximum complete logical file size |
| `CONTENT_UPLOAD_SESSION_TTL_SECONDS` | `86400` | Lifetime of an incomplete upload |
| `CONTENT_SEGMENT_CHECKSUMS_ENABLED` | `true` | Store and verify per-segment SHA-256 |
| `CONTENT_DOWNLOAD_DB_BATCH_SIZE` | `1` | Number of segments fetched ahead |

`MAX_UPLOAD_SIZE_BYTES` remains a policy and capacity control even though it
may now be configured above 1 GiB. It must be validated as a 64-bit integer.
The segment size must be bounded to a safe range, initially 1–64 MiB.

## 7. Storage-provider interface

Replace the current whole-file interface (`store(..., bytes)` and
`read(...) -> bytes`) with a streaming interface conceptually equivalent to:

```python
class ContentStorage(Protocol):
    def begin_upload(...): ...
    def append_segment(..., segment_no: int, data: bytes): ...
    def finalize_upload(..., size: int, checksum: str): ...
    def abort_upload(...): ...
    def iter_content(..., byte_range: tuple[int, int] | None = None): ...
    def delete(...): ...
```

The interface must expose a stream or iterator, not a complete file value.
PostgreSQL and future S3 providers implement the same logical contract.
Provider-specific storage keys remain internal. Public endpoints and domain
services must not branch on the configured backend.

## 8. Upload and replacement workflow

### 8.1 New upload

1. Authenticate the caller and validate record/aggregation lifecycle rules.
2. Create component or draft-component metadata in an incomplete state.
3. Create an upload session.
4. Read at most one configured segment from the incoming request stream.
5. Update the running whole-file digest and optional segment digest.
6. Insert the segment and commit it, or commit a small bounded batch.
7. Repeat without accumulating prior segments in memory.
8. In a short finalization transaction:
   - lock the component and upload session;
   - verify contiguous segment numbers;
   - verify segment count and summed size;
   - verify the computed whole-file checksum;
   - set authoritative size, checksum, and segment count;
   - set `content_status = 'available'` and completion time; and
   - close the upload session.
9. Emit one domain audit event for successful content upload. Segment inserts
   are storage implementation details and must not flood the audit trail.

The service must stop promptly when the request is cancelled. A failed or
disconnected request leaves an incomplete session eligible for continuation or
cleanup, never an available component.

### 8.2 Transactions

A multi-gigabyte upload must not use one transaction lasting for the entire
network transfer. Each segment or small segment batch is committed separately;
only finalization is atomic and short. This limits held locks and long-running
transactions, although all segment bytes still generate PostgreSQL WAL.

### 8.3 Replacement

Replacement must preserve the currently available content until the new upload
has passed final verification. The implementation shall use the concrete
content-set model from section 5.1:

1. Keep `digital_components.active_content_set_id` pointing to the existing
   active content set.
2. Create a second `digital_component_content_sets` row with status `staged`.
3. Associate the replacement upload session and every newly received segment
   with that staged content-set ID.
4. Verify the staged set's segment sequence, total size, and whole-file
   checksum.
5. In one short transaction, lock the component, mark the old set
   `superseded`, mark the staged set `active`, and change
   `active_content_set_id` to the new set.
6. Delete the superseded set and its cascading segments after the switch. This
   may happen immediately after commit or through cleanup.

If upload or verification fails before step 5, delete the staged set and leave
`active_content_set_id` unchanged. The old file therefore remains downloadable.
There is no undefined "upload generation" or "staging association": the staged
content-set row and its ID are the explicit association.

Optimistic concurrency through `If-Match` remains required. The version checked
at upload start must be revalidated at finalization.

### 8.4 Record draft commit

Record creation continues to be an atomic domain operation: the record and all
of its component metadata become visible together. Every staged component must
be `available` and verified before the Create Record action is enabled. The UI
must continue to state that creation is unavailable while files are uploading.

Draft segment rows are transferred or copied to committed component segment
rows without assembling a complete file. Draft cleanup cascades to abandoned
segments.

## 9. Download and preview workflow

### 9.1 Full response

Retrieve segments with:

```sql
SELECT segment_no, content
FROM digital_component_blobs
WHERE content_set_id = $1
ORDER BY segment_no;
```

The selected content-set ID is obtained from
`digital_components.active_content_set_id`; staged and superseded sets are
never served by the normal content endpoint.

The API returns a `StreamingResponse` whose iterator yields each segment (or
smaller views of it) in sequence. It must not use SQL `string_agg`, application
`b''.join(...)`, or any equivalent operation that reconstructs the complete
file before sending it.

Set at least:

- `Content-Type` from verified component metadata;
- `Content-Length` to the complete logical size;
- `Content-Disposition` with a safely encoded filename;
- `Accept-Ranges: bytes`;
- `ETag` derived from the immutable content checksum/version; and
- appropriate cache and security headers.

Cancellation must stop database reads and release the connection promptly.

### 9.2 HTTP range requests

Support one byte range per request initially:

```http
Range: bytes=START-END
```

Return:

- `206 Partial Content` and a correct `Content-Range` for a satisfiable range;
- `416 Range Not Satisfiable` with `Content-Range: bytes */TOTAL` otherwise;
- the full `200` response when no range is supplied.

For fixed-size segments:

```text
first segment = floor(START / configured segment size)
last segment  = floor(END   / configured segment size)
```

Fetch only the intersecting segments, trim the first and last segment in the
application, and stream the selected bytes. Do not assume that all historic
content uses the current configured size; stored segment sizes and cumulative
offsets are authoritative. A future optimization may persist each segment's
starting byte offset.

Range support is required for resumable downloads, PDF.js range loading, and
native audio/video seeking. `HEAD` should return the same relevant headers
without reading content.

## 10. Connection-pool behavior

A streaming PostgreSQL download holds a database connection while its iterator
reads segments. Large or slow downloads can therefore exhaust the API pool.
The implementation must:

- fetch only a small bounded number of segments ahead;
- release the connection immediately on completion or disconnect;
- configure download concurrency separately from ordinary request concurrency;
- record pool wait time and stream duration;
- consider a dedicated content-read connection pool; and
- document that S3 redirects or direct object streaming are preferred at high
  concurrency.

Loading all segment rows with `fetchall()` is prohibited.

## 11. Cleanup and recovery

The implementation shall provide **both**:

1. a cleanup command that can be executed manually by an administrator, with
   dry-run and bounded-batch options; and
2. an automatically scheduled invocation of the same cleanup service for normal
   operation.

The cleanup logic must live in one reusable application service so scheduled
and manual runs cannot develop different semantics. It must not run as an
uncoordinated NiceGUI or FastAPI in-process timer: multiple API workers could
run it concurrently and API restarts would make its schedule unreliable. Run
the command from a dedicated worker process, operating-system scheduler,
container scheduler, or equivalent deployment scheduler. A database advisory
lock shall prevent overlapping cleanup runs.

The command should have an interface conceptually similar to:

```text
python -m backend.services.api.content_cleanup --dry-run
python -m backend.services.api.content_cleanup --batch-size 100
```

Each scheduled or manual run shall find expired/interrupted upload sessions,
permanently failed sessions, cancelled sessions, expired record drafts, and
superseded content sets eligible for deletion, then:

1. move sessions to the correct terminal state (`expired`, `failed`, or
   `cancelled`);
2. delete their staged segments and staged content sets;
3. delete incomplete metadata when domain rules permit;
4. cascade-delete draft component bytes when a draft expires;
5. delete superseded committed content sets only after confirming they are not
   referenced by `active_content_set_id`; and
6. emit summary/domain audit events describing the cleanup outcome, without
   content bytes.

Cleanup must operate in bounded batches, be idempotent, and report counts and
bytes reclaimed. A failed cleanup batch must be safe to retry. Successfully
staged components belonging to an unexpired open draft are not abandoned
uploads and must not be removed merely because their upload session completed.

Finalization must be idempotent. Retrying an already completed finalization
returns the completed component rather than duplicating segments. Appending an
already stored segment number is accepted only when its size and checksum match;
otherwise return a conflict.

Startup and administrative integrity checks should be able to report:

- missing or duplicate sequence numbers;
- size mismatches;
- unavailable components with orphaned segments;
- available components without the declared number of segments; and
- expired upload sessions.

## 12. Audit history

Emit domain-level events such as:

- `CONTENT_UPLOAD_STARTED`;
- `CONTENT_UPLOADED`;
- `CONTENT_UPLOAD_FAILED`;
- `CONTENT_UPLOAD_ABORTED`;
- `CONTENT_REPLACED`; and
- `CONTENT_DELETED`.

Routine downloads retain the existing audit policy. If downloads are audited,
one event represents the user action, not every HTTP range request generated by
a viewer.

Event metadata may contain component ID, filename, MIME type, complete size,
checksum, segment count, storage backend, correlation ID, and failure reason.
It must never contain content or segment payloads.

## 13. Migration strategy

Because the application remains greenfield, the canonical schema may be
updated directly, but a migration is still required for the standalone
development database and repeatable upgrades.

The migration shall:

1. create the new segmented structures and metadata columns;
2. create one active content set for every existing stored component, point
   `active_content_set_id` to it, and treat the existing blob as segment `0`,
   preserving bytes and `date_stored`;
3. migrate draft component content in the same manner;
4. calculate/store segment sizes and optional segment checksums;
5. set segment count and completion metadata for existing available content;
6. verify row counts, summed byte sizes, and whole-file checksums;
7. install indexes, constraints, and closed-aggregation protection triggers;
8. switch application reads and writes to segmented storage; and
9. remove obsolete monolithic columns only after verification.

Do not rewrite all existing large values in one unbounded transaction. The
migration must be restartable or process content in bounded batches if the
development dataset becomes substantial.

Rollback must be explicitly limited: segments whose combined size exceeds the
single-`bytea` limit cannot be safely collapsed into the old schema.

## 14. API and UI behavior

The existing public content URLs should remain stable where possible. Clients
need not know how content is segmented.

For resumable uploads, add explicit initiate, append, status, finalize, and
abort operations, or adopt a standard resumable-upload protocol in a later
revision. The API must return upload progress in bytes and percentage when the
expected size is known.

The NiceGUI interface must:

- stream file input instead of reading the whole browser upload into server
  memory;
- show per-file progress and clear uploading/finalizing states;
- disable record creation until every draft component is finalized;
- permit cancellation and safe retry;
- preserve staged order independently of segment order; and
- use the same download/view controls regardless of storage provider.

## 15. Security requirements

- Authenticate and authorize every upload-session and content operation.
- Never trust client-supplied MIME type, size, checksum, segment number, or
  completion claim without server validation.
- Apply existing closed-aggregation rules at upload start and finalization.
- Sanitize filenames used in response headers.
- Bound segment size, total size, open sessions per user, request duration, and
  concurrent content streams.
- Ensure a user cannot append segments to another user's draft or upload.
- Make error responses avoid leaking storage keys or database details.
- Leave a future hook between finalization and availability for malware
  scanning/quarantine.

## 16. Operational implications

Segmentation removes the per-value limit; it does not make PostgreSQL object
storage operationally free. Every content byte still affects:

- primary database capacity and I/O;
- WAL generation and replication bandwidth;
- backups, restore time, and point-in-time recovery;
- vacuum behavior after replacement/deletion;
- connection-pool occupancy during downloads; and
- database failover and maintenance windows.

Deployments must monitor total content bytes, segment count, incomplete bytes,
upload failure rate, stream concurrency, pool wait time, throughput, WAL volume,
replica lag, and cleanup results. Capacity planning must include content growth
and backup retention.

## 17. Testing and acceptance criteria

### 17.1 Database tests

- Segment numbers are unique per component and ordered correctly.
- Invalid numbers and size mismatches are rejected.
- Deleting a record cascades through component metadata and all segments.
- Draft deletion cascades through all draft segments.
- Closed-aggregation protections block segment mutations.
- Migration preserves existing bytes, timestamps, sizes, and checksums.

### 17.2 API tests

- Uploads crossing multiple segments finalize with the correct byte count and
  SHA-256 checksum.
- Full downloads reproduce the exact original byte stream.
- Ranges wholly inside one segment and spanning segment boundaries return exact
  bytes and correct headers.
- Prefix, suffix, open-ended, invalid, and unsatisfiable ranges behave per HTTP.
- Disconnect and cancellation release resources.
- Oversized uploads return `413` without becoming available.
- Missing, duplicated, corrupted, or out-of-order segments fail finalization.
- Replacement failure leaves the old content available.
- Concurrent or stale `If-Match` replacement returns a conflict.
- Expired sessions and orphan segments are cleaned safely.
- Zero-byte file behavior matches the chosen policy.

At least one automated test must use a logical payload larger than the test
segment size so segmentation is exercised without allocating gigabytes. A
separately tagged/manual soak test should cover multi-gigabyte content.

### 17.3 UI tests

- Multiple large staged components show independent progress.
- Create Record remains disabled until finalization completes and explains why.
- Cancellation, retry, reorder, and removal update the UI immediately.
- PDF.js and native media controls issue successful range requests.
- UI behavior does not differ between PostgreSQL and future S3 providers.

### 17.4 Acceptance criteria

The feature is accepted when:

1. no upload or download path assembles an entire large file in API memory;
2. files larger than 1 GiB can be uploaded and downloaded byte-for-byte in the
   multi-gigabyte integration test environment;
3. range requests work across segment boundaries;
4. incomplete or corrupt uploads cannot become available;
5. record drafts support the same large-file limits as committed components;
6. deletion and closed-aggregation business rules remain enforced;
7. existing content migrates without checksum changes; and
8. documentation clearly states the PostgreSQL operational trade-offs and the
   future S3-compatible alternative.

## 18. Recommended implementation sequence

1. Add schema, migration, constraints, indexes, and integrity tests.
2. Replace the storage protocol with streaming methods.
3. Implement segmented draft uploads and finalization.
4. Implement atomic draft-to-record segment transfer.
5. Implement streaming full downloads and `HEAD`.
6. Implement single-range HTTP responses.
7. Implement staged/active content-set replacement, cancellation, and both
   scheduled and manual cleanup execution.
8. Update NiceGUI progress, retry, and cancellation behavior.
9. Add migration verification, multi-gigabyte soak tests, metrics, and
   operational documentation.
10. Retain the provider boundary so S3-compatible storage can be added without
    changing domain or client APIs.
