# Internationalization Phase 5 implementation contract

Phase 5 hardens the approved internationalization and user-preferences
subsystem for production search, caching, time handling, observability, and
release verification. The later approved profile amendment expands the
multilingual entity set to seven without changing these hardening rules.

## Translated search and query plans

Search continues to apply its existing authorization predicates and matches
canonical metadata plus translated `name`, `title`, and `description` values
for enabled languages. The translated branch uses an indexed conservative
prefilter followed by exact field and enabled-language verification, avoiding
an unbounded JSONB expansion on every candidate row. Migration 022 and the
canonical schema install `pg_trgm` GIN expression indexes for all seven covered
entity tables. Database verification forces index selection and checks the
resulting plan, as well as proving that disabling a language immediately
removes its translated values from search results.

## Catalogue caching

Compiled API catalogues remain keyed by normalized language and immutable
catalogue revision and are served with revision-derived ETags. A publication
invalidates only the affected language. The authenticated bootstrap now
reports the effective language's revision rather than a revision from another
language. The WebUI keeps a private session copy keyed by that same language
and revision, avoiding a catalogue API request when bootstrap and session
state agree. Draft edits do not invalidate ordinary-user caches.

## Time and date boundaries

`WATHIQ_DEFAULT_WORKING_TIMEZONE` remains the sole application default and is
validated as a canonical IANA zone; the checked-in environment default is
`Asia/Dubai`. Browser controls collect a wall time in the signed-in user's
working timezone. The WebUI resolves that wall time before submission,
rejects nonexistent DST times, requires an explicit earlier/later choice for
overlaps, and sends a UTC instant. Instant-bearing API request fields require
an explicit UTC marker or numeric offset. PostgreSQL continues to persist
instants as `timestamptz`; rendering converts them from UTC into the explicit
user timezone. Date-only values never pass through timezone conversion.

Tests cover positive and negative offsets, a non-whole-hour offset, DST gaps
and overlaps, leap day, Arabic and English rendering, and offset-free API
input rejection.

## Observability and readiness

The localization service records aggregate and per-language counters for
catalogue cache hits and misses, invalidations, compile duration, fallback
use, invalid translation syntax, preference validation failures, and timezone
resolution/DST failures. Bounded structured log events accompany catalogue
compilation, invalidation, missing keys, invalid parameters, and timezone
failures without recording translated content or preference values.

`GET /health` includes localization readiness, the configured defaults, the
default catalogue ETag, and the counters. Readiness fails if the configured
default timezone cannot be resolved or the default catalogue cannot compile.

## Verification evidence

- canonical schema and migrations through 022 passed on uniquely named,
  disposable PostgreSQL databases;
- translated search result and forced query-plan tests passed for enabled and
  disabled language states;
- all 318 API/database tests passed, including the final timezone-contract
  cases, and every disposable database was removed;
- all 200 WebUI tests passed;
- the contextual catalogue checker, Python compilation, JSON validation, and
  `git diff --check` passed;
- live in-app-browser inspection passed against an isolated stack initialized
  from the canonical schema. The English login shell rendered with `lang=en`,
  `dir=ltr`, no horizontal overflow at 1280 px, and no browser warnings or
  errors. The live health response reported localization ready, English as the
  default language, `Asia/Dubai` as the environment-configured timezone, a
  catalogue ETag, and cache/compile/fallback telemetry. The API, WebUI, browser
  tabs, and disposable PostgreSQL container were then stopped and removed.
