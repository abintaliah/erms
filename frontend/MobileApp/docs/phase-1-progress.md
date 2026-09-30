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
  platform family without a device fingerprint.
- Sign-in errors are reduced to non-disclosing client categories.
- Explicit sign-out clears local protected state even when the server request
  fails.
- Obsolete sign-in responses cannot restore a cleared or revoked session.
- Background lifecycle handling retains sessions before 15 minutes and clears
  them at or after 15 minutes; the 10-minute warning boundary is exposed through
  a best-effort scheduler interface whose failure cannot extend the session.
- Focused model, HTTP-contract, and session-state tests pass, and Flutter static
  analysis reports no issues.

## Pending

- Implement the approved sign-in and required-password-change screens using
  canonical catalogue keys and the WebUI logo.
- Implement authenticated phone and tablet shell layouts, destination
  disclosure, sign-out, and central loading/error/offline/revocation states.
- Connect lifecycle handling to Flutter application lifecycle events and add
  the platform notification implementation for the best-effort warning.
- Validate the authentication contract against a running non-production ERMS
  service.
- Complete English, Arabic, LTR, RTL, iOS, Android, phone, and tablet runtime
  verification for all delivered Phase 1 screens.
