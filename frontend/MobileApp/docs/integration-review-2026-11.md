# November 2026 integration and compatibility review

Consolidated on 17 November 2026. This records the integration performed and its
outcomes; it does not approve new product scope. Current behavior, acceptance and
remaining work live in [architecture](architecture.md),
[validation](validation-matrix.md) and [Phase 1 status](phase-1-progress.md).

## Integration scope

The synced fork and upstream `main` reached `7bd0b4d8`, following the mobile
branch's previous integration with `0cfd587`. The 16 November operation brought
that `main` into all eight existing local branches. Six branches required
conflict resolution. The branch updates were subsequently pushed to the fork
at the user's request; later local commits/work must be checked with `git status`
rather than inferred to have been pushed.

The incoming changes included WebUI screen-owner extraction, route-local API
policy inventory metadata, password-attempt enforcement fixes, authentication
concurrency changes, dashboard/search optimizations, shared search-result caches,
new pagination/default settings, resource/creator projections and disposition
workflow updates. They did not require a Flutter application-shell redesign.

Mobile-specific compatibility retained during the merges:

- Existing mobile capability endpoint and database-owned search availability.
- Mobile audit source and sanitized device-model user-agent information.
- Server-owned expiry, action-triggered revocation and generation isolation.
- Session presentation/audit labels ported to the new WebUI screen owners.
- English/Arabic catalogues merged by contextual key without regenerating over
  administrator wording; mobile assets synchronized to canonical sources.
- Current API authentication transaction in a worker thread and compatible
  `FOR NO KEY UPDATE` session locking. Do not restore older session locking or
  move synchronous database waits onto the async event loop.

Route-local `operation_policy` metadata does not replace existing access checks.
Added principal fields do not remove the fields consumed by Flutter. Search,
favourites, resource-history, pagination and creator metadata changes must be
reviewed when refreshing the Phase 2 API map; the old snapshot is not current.

## Review findings and resolution

| Finding | Resolution/current state | Verification |
| --- | --- | --- |
| Required-password sign-in called forbidden localization bootstrap and cleared identity on 403 | Handle credential state before bootstrap/capabilities; retain form/session, then complete setup after successful replacement | Controller, HTTP restriction/request-order and bilingual phone/tablet tests; later Android success reported |
| Password validation and cooldown details were discarded; generic text incorrectly implied highlighted fields | Map only recognized server outcomes to localized field/cooldown feedback; confirmation mismatch has an inline explanation | 400/422/429 HTTP tests, safe fallback and parameter checks; user accepted feedback review |
| Cooldown translation regression expected a historical machine batch | Assert imported administrator provenance against the canonical artifact, retain draft/publication safety and idempotence/manual-wording checks | All 21 password-attempt tests pass in a disposable database; cleanup succeeded |
| Three existing page-size settings omitted from configuration authority inventory | Reconcile the inventory generator and checked-in report with defaults 10/25/25 and actual consumers | Authority/template checks and 17 configuration tests passed; no setting value or environment variable changed |
| English-only sign-in prevented Arabic feedback before preference loading | User-approved §6 amendment: device Arabic or English fallback until saved ERMS preference is available | 115-test Flutter suite, clean analysis, native Android/iOS acceptance with controlled locales/injected API, and normal builds pass |

The bootstrap gap was an existing mobile integration defect exposed by the
review, not a claim that WebUI extraction introduced it. The translation test
failure was a stale assertion, not a production lockout or publication failure.

## Local database upgrade

The configured loopback `erms` database was backed up before applying migrations
095–113 in filename order. No persistent database was used for test fixtures.
No remote/deployed database was changed by this local upgrade.

Migration 112 required idle clients/index publishing, rewrite space and an
exclusive chunk-table rewrite. Required `VACUUM ANALYZE` completed afterward.
The `search_vector` policy was verified as MAIN/LZ4; actual values included 1,419
LZ4-compressed vectors and 1,784 small uncompressed vectors. Those are observations
from this local dataset, not performance results for other installations.

Migration 113 installed the three page-size defaults. The database settings were
already correct; the later inventory repair changed documentation/tooling only.
No additional migration or manual setting-value adjustment was needed for these
mobile follow-ups.

For another installation, inspect its migration history and follow
[database upgrade/maintenance instructions](../../../database/README.md). Do not
replay older migrations over a newer schema merely because a historical receipt
is missing, and do not roll a database back to accommodate an older checkout.
Private backups/logs remain in gitignored `.runtime/`, not in this documentation.

## Translation handoff

The 16 November complete administrator export was incorporated with published
provenance, including the user-approved correction to `الوثائق الحيوية`.
Subsequent password feedback added two keys with Arabic drafts and preserved all
4,087 existing entries. Current artifacts/assets contain 4,089 active keys.
The user published both messages locally. On 17 November a complete published
export was obtained with the existing export builder in a read-only transaction
using the API's UTC timestamp convention. All 4,089 keys validated and were
promoted to the canonical Arabic artifact. The two new entries gained publication
provenance; no wording or existing curated entry changed. Mobile synchronization
and the affected provenance regression passed. Exporting did not modify the
database, and no translation handoff is still pending for these two messages.

Follow [the current handoff](phase-1-progress.md#remaining-handoff-work) for the
remaining review/Git/Phase 2 work. No private credentials, account passwords or
session tokens belong in source documentation.

## Evidence limits

The initial focused review recorded 54 passing backend checks and one stale
provenance failure, plus a separate successful probe confirming bootstrap 403
under mandatory-password state. The corrected password-attempt module later
passed all 21 tests. Disposable databases were cleaned up after each run.

The current Flutter suite has 115 passing tests and clean analysis. Recent native
builds and installations succeeded. User-reported acceptance, automated widget
coverage and live-server device acceptance remain distinct. Retained native
tablet evidence is landscape-only with an injected API. Older review conclusions
are in the [history index](history/README.md); use the current status for open work.
