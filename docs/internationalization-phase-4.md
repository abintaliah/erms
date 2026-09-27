# Internationalization Phase 4 implementation contract

Phase 4 implements multilingual metadata for the seven entity types
approved by the internationalization specification: classification schemes,
classifications, users, roles, organization units, security levels, and
authorization profiles. Profiles were added as the seventh approved entity by
the post-Phase-7 amendment implemented by migration 023.
Aggregations and records remain deliberately canonical, single-language
business content for the rationale recorded in the approved specification.

## Persistence and validation

Migrations 021 and 023 and the canonical schema add a nullable `translations
jsonb` column to each covered table, plus nullable canonical descriptions for
users and security levels. Translation maps are keyed by enabled BCP 47 language tag
and may contain only the approved `name`/`title` and `description` fields.
Database triggers reject unknown or disabled locales, empty locale objects,
unexpected fields, non-string values, surrounding whitespace, and blank
strings. GIN indexes support translated metadata discovery.

## API and authorization

Locale-scoped GET and PATCH operations are registered separately for each
covered entity type. Every route declares the exact approved
`<entity>.modify_metadata` dependency, requires optimistic concurrency through
`If-Match`, and requires `X-Change-Reason`. PATCH merges only the selected
locale, so administrators editing different locales do not overwrite each
other's values. Null explicitly removes a field; an empty locale is removed.
The owning entity's existing version and audit history are used.

Ordinary entity reads retain canonical fields, expose the translation map, and
add a `localized` projection. Resolution uses the signed-in user's preferred
language, then its base language for a regional tag, then canonical metadata.
Selectors and covered administration listings display the projection while
canonical edit controls continue to edit canonical values. Text search over
approved metadata fields matches canonical and translated values.

## WebUI

Existing covered-entity edit dialogs contain a compact, collapsed-by-default
translation card. It loads one selected language on demand and provides dense
icon-only load and remove actions with tooltips and accessible status text;
the dialog's main Save action persists the pending locale change. Translation
changes have their own reason and version lifecycle so the advanced feature
does not complicate the primary form.

The protected Text Indexing Service role and authorization profile use their
standard dialogs in translation-only mode. Every
canonical control is visible but disabled, relationship-browser actions are
suppressed where applicable, and canonical profile/role change-reason controls
are omitted. The main
Save action requires a loaded, changed locale plus a translation reason and
calls only the matching locale-scoped entity-translation endpoint. Ordinary
profile and role PATCH operations continue to reject canonical changes; role
lifecycle, assignment, and deletion APIs continue to reject the built-in role.

Profile translations use `profile.modify_metadata`, granted by default to both
`ALL_PRIVS` and `SYS_ADMIN`. Profile list, detail,
selector, and relationship references resolve the signed-in user's preferred
language. For protected built-in profiles, the application-owned catalogue
wording is only a fallback when no entity translation exists; it never
overrides an administrator-authored profile translation.

## Verification

- canonical-schema and migration-021 paths passed on disposable PostgreSQL;
- all 313 API/database tests passed and the disposable databases were removed;
- all 198 WebUI tests passed;
- contextual catalogue validation and `git diff --check` passed;
- live in-app-browser inspection passed against an isolated local stack backed
  by a uniquely named disposable PostgreSQL database initialized from the
  canonical schema. It verified the collapsed-by-default translation editor,
  on-demand Arabic metadata loading, localized administration-card values and
  sorting, right-edge RTL navigation, and desktop/mobile rendering at 1280×720
  and 390×844 without horizontal overflow. The inspection found and corrected
  canonical-value rendering in governance cards and bidi reordering of
  timestamps; the corrected build passed the same checks. The isolated API,
  WebUI, and PostgreSQL processes were then stopped and removed.
