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

## Pending

- Implement authenticated phone and tablet shell layouts, destination
  disclosure, sign-out, and central loading/error/offline/revocation states.
- Connect lifecycle handling to Flutter application lifecycle events and add
  the platform notification implementation for the best-effort warning.
- Complete English, Arabic, LTR, RTL, iOS, Android, phone, and tablet runtime
  verification for all delivered Phase 1 screens.
