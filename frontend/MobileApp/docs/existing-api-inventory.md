# Existing API integration inventory

The [mobile specification](../../../specs/flutter-mobile-application.md) and each
owning subsystem define the contracts. This inventory identifies consumers; it
does not authorize a new endpoint, role, workflow or response shape.

## Phase 1 calls currently used by Flutter

All paths are relative to `/api/v1`.

| Method/path | Consumer/purpose | Important boundary |
| --- | --- | --- |
| POST `/auth/login` | Existing local-password sign-in; session cookie and principal | Mobile keeps the resulting token only in memory and uses bearer requests afterward; login errors remain non-disclosing |
| GET `/auth/me` | Principal, credential state, protected navigation/resume validation | Server owns identity/expiry; response must not switch user identity |
| POST `/auth/change-password` | Required credential replacement | Existing 400/422 validation and 429 cooldown feedback; never automatically replay a mutation |
| POST `/auth/logout` | Revoke current session | Local state clears even if the request fails |
| GET `/auth/me/mobile-capabilities` | Server-owned destination availability | Database-owned search setting; not a grant of resource access |
| GET `/i18n/bootstrap` | Effective saved language and available languages | Forbidden while password change is required; packaged device-language copy is used first |
| GET/PUT `/preferences` | Read/update language and timezone | PUT retains If-Match/version semantics; current saved language takes precedence over device language |

Owners: [authentication](../../../backend/services/api/authentication.py),
[localization/preferences](../../../backend/services/api/localization.py), and
[mobile transport](../lib/features/auth/data/auth_api.dart).

The separately approved `/auth/me/session-status` API returns principal status
without refreshing successful passive activity. It remains server-side but
Flutter no longer calls it, following the 5 November action-triggered-revocation
amendment. Do not reintroduce healthy-screen polling from historical examples.

## Later feature ownership

| Mobile journey | Existing owning contract |
| --- | --- |
| Dashboard, favourites and recent activity | Dashboard and User Favourites |
| Global discovery and diagnostics | Full-Text Search |
| Scheme and hierarchy navigation | Aggregation Classification Browser |
| Aggregation/record metadata and component lists | Aggregation/Record Detail and resource capability contracts |
| Component rendition and viewer audit | Document Viewing and Content Storage |
| Resource history | Event History and authorized resource-history projection |
| Visible actions, links and destinations | Security and Authorization capability responses |
| Wording, direction, dates, timezone and terminology | Internationalization and User Preferences |

Before implementing a later feature, verify its current methods, response fields,
server pagination, authorization, errors and concurrency behavior against source
and tests. The [5 November Phase 2 API map](phase-2-api-map.md) predates the latest
resource/favourites/search refactors and must be refreshed; its unresolved choices
have not been approved merely by documenting them.
