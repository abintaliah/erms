# Phase 1 progress record

Status: In progress

Started: 30 September 2026

## Completed

- English/LTR and Arabic/RTL authentication and application-shell mockups were
  approved with the canonical WebUI logo refinement.
- The existing `/api/v1/auth/login`, `/me`, `/change-password`, and `/logout`
  contracts are represented by an injectable mobile authentication boundary.
- Principal, role, privilege, session, and required-password-change response
  fields are parsed through typed models with malformed-response rejection.
- Session tokens and protected principal state remain in memory only.
- Mobile requests identify themselves as `WathiqMobile/0.1` plus the truthful
  platform family without a device fingerprint and use the approved `mobile`
  audit source.
- Sign-in errors are reduced to non-disclosing client categories.
- Explicit sign-out clears local protected state even when the server request
  fails.
- Obsolete sign-in responses cannot restore a cleared or revoked session.
- Background lifecycle handling retains sessions before 15 minutes and clears
  them at or after 15 minutes; the 10-minute warning boundary is exposed through
  a best-effort scheduler interface whose failure cannot extend the session.
- Focused model, HTTP-contract, and session-state tests pass, and Flutter static
  analysis reports no issues.
- The approved canonical WebUI facet logo is reproduced as a dependency-free
  Flutter vector painter from the source SVG geometry and colors.
- English/LTR and Arabic/RTL sign-in screens use canonical catalogue keys for
  brand, field, action, and non-disclosing failure text.
- Required-password-change presentation uses existing canonical password keys,
  keeps protected destinations unavailable, validates confirmation locally,
  and delegates the actual change to the existing API contract.
- Application composition now switches from signed out to password change or
  authenticated state exclusively from the in-memory session controller.
- Anonymous startup is explicitly English and does not follow the device
  locale. After authentication, the existing localization bootstrap contract
  makes the user's effective language authoritative immediately; protected
  locale state resets to English at logout or session expiry.
- Live iOS authentication against the local API reached the authenticated
  Dashboard and persisted `AUTHENTICATION_SUCCEEDED` with source `mobile` and
  user agent `WathiqMobile/0.1 (ios)`.

## MobileFlutterV0.2 — session and capability continuation, 4 October 2026

- The user confirmed successful v0.1 authentication testing; this continuation
  keeps that boundary and remains on `MobileFlutterV0.2`.
- The user approved the read-only `/api/v1/auth/me/mobile-capabilities` response.
  It returns server-owned destination availability, respects the existing
  credential-change gate, and hides Global Search when disabled. It grants no
  resource access. The mobile client does not reconstruct authorization from
  role names or privilege combinations.
- Implemented destinations (Dashboard, User/Profile, Preferences, Sign out)
  disclose navigation from that response. The tablet separator uses directional
  borders, and the profile displays only authenticated response data.
- Flutter lifecycle observation starts one continuous background interval;
  repeated hidden/paused callbacks cannot restart the 15-minute clock.
- Returning before the limit revalidates the principal and capabilities; server
  revocation clears the session immediately. Offline/error revalidation uses a
  nondismissible centered gate retaining rendered content underneath, with
  explicit safe-read Retry and Sign out. A single foreground-only 30-second
  probe revalidates connectivity without mutation retries or overlapping reads. Sign-out also gates interaction.
- Native iOS/Android adapters schedule one best-effort local warning at ten
  background minutes using generic localized text only. Android uses inexact
  scheduling without exact-alarm permissions and suppresses warnings delivered
  after the fifteen-minute boundary. Resume, sign-out, and process startup
  cancel stale warnings; permission denial cannot change the timeout.
- Session generations prevent delayed preference/bootstrap/capability responses
  from restoring cleared identity, language, destination, or preference state.
  Revocation replaces the Navigator, removing pushed protected routes.
- Added five `mobile.*` contextual keys to the authoritative English catalogue
  and merged only their missing Arabic drafts into the canonical artifact.
  Existing translation text and per-item provenance are unchanged. Both mobile
  language assets are synchronized to 2,899 active keys. No administrator export
  was promoted; the five new Arabic drafts require administrator review.
- Corrected a catalogue-validator false positive: MSG-007 explicitly requires
  the conventional `Re:` reply prefix in every language. Its existing artifact
  text/provenance are preserved and the exception is exact-key/exact-value.
- Verification: 52 Flutter unit/widget checks pass; Flutter analysis reports no
  issues; Android debug APK and iOS simulator native builds passed. Two backend
  capability tests passed using unique disposable fresh/upgrade databases;
  schema parity passed and both databases were dropped. Three database-free
  invariant-prefix validator tests and full catalogue coverage/order/placeholder/
  blank/terminology/stale-key/hash checks passed.

## Pending

- Global Search entry and the remaining approved drawer destinations need
  their shell integration; downstream content workflows remain assigned to
  their specified phases.
- Complete English, Arabic, LTR, RTL, iOS, Android, phone, and tablet runtime
  verification, including actual OS warning permission/delivery and cancellation.
  Compiled native adapters and mocked channel checks do not establish OS delivery.
- Phase 1 remains in progress; its complete exit gate is not yet claimed.
