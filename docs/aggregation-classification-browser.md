# Browsing aggregations through classification schemes

The Aggregations page provides two complementary ways to locate content:

- **Search** finds aggregations by number, title, or description and retains the
  recently created and recently updated lists.
- **Browse classification** presents published classification schemes as a
  navigable hierarchy extending from classifications through aggregations to
  records.

The detailed implementation contract is in
[`../specs/aggregation-classification-browser.md`](../specs/aggregation-classification-browser.md).

## Using Browse classification

Open **Aggregations** from Records Management and select **Browse
classification**. Choose a scheme from the selector above the workspace.
Published schemes are available for browsing. A deactivated scheme remains
visible when it explains existing aggregation governance and is marked
inactive; deactivation prevents new assignments but does not erase history.

The left pane is an independently scrollable tree. The right pane shows concise
information about the selected aggregation or record without closing,
collapsing, or navigating away from the tree.

The hierarchy is:

```text
Classification scheme
└── Branch classification
    └── Terminal classification
        └── Root aggregation governed by that terminal
            ├── Child aggregation
            │   ├── Descendant aggregation
            │   └── Record
            └── Record
```

Only root aggregations appear directly beneath a terminal classification.
Child aggregations appear beneath their actual parent, and records appear
beneath their containing aggregation. Digital components are not tree nodes;
the record summary shows their count and the existing record interface provides
access to them.

Branch classifications, terminal classifications, aggregations, and records
use distinct hierarchy, label, folder, and document icons. Closed aggregations
are marked in the tree.

## Details pane and navigation

Selecting an aggregation shows its business number, title, description,
lifecycle dates, closed status, direct child and record counts, classification
context where applicable, and effective retention rule. The rule states
whether it is a local aggregation override or inherited from classification
governance. **Open aggregation** navigates to the existing complete aggregation
view.

Selecting a record shows its number, title, description, originated and created
dates, containing aggregation, and digital-component count. **Open record**
opens the existing record interface.

Browse state—including the selected scheme, expanded paths, loaded pages,
selection, and collection filters—is retained when switching temporarily back
to Search during the same signed-in browser page. Signing out clears it so
protected information is not retained for the next user.

Recently created and updated aggregations remain available in a collapsed
**Recent aggregation activity** section below the browser.

## Large collections

The browser never downloads a whole scheme or aggregation subtree. It loads
only the first 50 immediate children when a node is expanded. This applies to
root and child classifications, governed root aggregations, child
aggregations, and records.

When more items exist, a synthetic row such as the following appears:

```text
Load 50 more records · 50 of 1,247
```

Activating it appends the next page. The API permits page sizes from 1 to 100;
the NiceGUI client uses 50. Collections larger than one page expose a local
filter. Filtering is executed by PostgreSQL against that immediate collection,
not merely against rows already present in the browser.

Loading and errors are shown inside the affected node. A confirmed empty
result displays an appropriate empty message. A failed request preserves
already loaded rows and offers **Retry**. Requests superseded by a scheme,
filter, refresh, or navigation change cannot populate the newer tree context.

## Ordering and cursors

Classifications are ordered by code, aggregations by aggregation number, and
records by record number. The entity ID is the stable final tie-breaker. The
initial implementation uses PostgreSQL's deterministic `C` collation, so this
is lexical rather than natural-number ordering.

Pagination uses server-generated opaque cursors rather than numeric offsets.
Each cursor is bound to its parent collection and filter. Reusing it for a
different parent or query returns `400 invalid or mismatched browse cursor`.

## REST API

The read-only browser endpoints are:

```http
GET /api/v1/browse/classification-schemes
GET /api/v1/browse/classification-schemes/{scheme_id}/roots
GET /api/v1/browse/classifications/{classification_id}/children
GET /api/v1/browse/classifications/{classification_id}/aggregations
GET /api/v1/browse/aggregations/{aggregation_id}/children
GET /api/v1/browse/aggregations/{aggregation_id}/records
GET /api/v1/browse/aggregations/{aggregation_id}/summary
GET /api/v1/browse/records/{record_id}/summary
```

Paged endpoints accept `limit`, `cursor`, and `query` and return:

```json
{
  "items": [],
  "next_cursor": null,
  "total": 0
}
```

Node responses include immediate-child counts. Aggregation nodes contain child
aggregation and record counts; record nodes contain digital-component counts.
Only terminal classifications may serve the governed-aggregation endpoint. A
request for a branch classification returns `409`.

## Database support

Migration
[`026_add_classification_browser_indexes.sql`](../database/migrations/026_add_classification_browser_indexes.sql)
adds compound indexes for each parent relationship and its deterministic browse
order: classification scheme/parent and classification code; classification
and aggregation number; parent aggregation and aggregation number; and
containing aggregation and record number. New databases receive the same
indexes directly from `database/schema.sql`.

## Authorization boundary

The current implementation uses the authenticated application session but does
not yet apply per-record authorization because that subsystem has not been
built. The purpose-built browse endpoints are the future enforcement boundary.
Authorization must be incorporated into their PostgreSQL queries before totals,
counts, ordering, and cursors are calculated. Hiding rows only in NiceGUI would
leak inaccessible entity existence through counts and continuation state and is
therefore not acceptable.

## Verification

API tests use a fresh temporary PostgreSQL instance and cover hierarchy
scoping, direct relationships, counts, filters, lexical order, cursor
continuation, cursor misuse, and rejection of aggregation browsing on a branch
classification. The temporary instance is torn down after the suite. Frontend
tests cover the browse client contract alongside the existing UI helpers.

```bash
database/tests/run.sh
PYTHONPATH=. frontend/webui/.venv/bin/python -m pytest -q \
  frontend/webui/tests --ignore=frontend/webui/tests/e2e
```
