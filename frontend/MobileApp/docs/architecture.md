# Mobile architecture

Current implementation as of 17 November 2026. The
[mobile specification](../../../specs/flutter-mobile-application.md) is the
product authority; [Phase 1 status](phase-1-progress.md) owns acceptance and
remaining work. Historical implementations are not architecture requirements.

## Ownership and source layout

Flutter presents existing ERMS APIs. Identity, credential policy, expiry,
capabilities, resource authorization, concurrency and audit outcomes belong to
the server. The current client is online-only and keeps user-specific protected
state in process memory. No networking, routing, persistence or state-management
package is required for the delivered foundation.

| Owner | Responsibility |
| --- | --- |
| `lib/app/app.dart` | App composition, lifecycle, locale resolution and the blocking session-validation overlay |
| `lib/core/config/app_environment.dart` | Explicit API base URL; HTTPS except allowed loopback development addresses |
| `lib/core/design/` | Wathiq brand and light-theme tokens |
| `lib/core/localization/message_catalogue.dart` | Validated packaged English/Arabic catalogues and parameter substitution |
| `lib/core/network/api_failure.dart` | Safe failure category and whitelisted feedback metadata; no arbitrary server diagnostics |
| `lib/features/auth/data/auth_api.dart` | Injectable `AuthApi`; `dart:io` transport; bearer headers, mobile identity and response parsing |
| `lib/features/auth/application/session_controller.dart` | Principal/token, credential state, initialized language preference, capability destinations and session-generation guards |
| `lib/features/auth/presentation/` | Sign-in, required-password form and Preferences |
| `lib/features/shell/presentation/` | Server-filtered drawer, retained Back navigation and responsive destination foundations |

API URLs are supplied at build/launch time. Do not compile credentials, session
material or protected content into the app. Later resource/discovery owners must
be designed against their approved phase, not added to the authentication owner.

## Authentication and language sequence

1. Before the saved preference is available, `WathiqApp` resolves the device's
   primary language: Arabic/RTL or English/LTR fallback. Regional Arabic is
   supported. The packaged catalogues require no authenticated request.
2. Login returns the existing session cookie and principal. The client retains
   the token only in memory and uses bearer authentication afterward.
3. If `must_change_password` is true, show the required form immediately. Do not
   request bootstrap or capabilities: the API intentionally forbids them in
   that credential state. No access-rule exception was introduced.
4. After successful replacement, refresh the principal, fetch effective language,
   then capabilities. Publish authenticated shell state only when setup succeeds.
   Ordinary login uses the same setup without the password-change step.
5. `hasEffectiveLanguagePreference` distinguishes a loaded server preference
   from fallback. Once loaded, the saved preference overrides device language;
   later device-language changes cannot replace it. Preferences updates remain
   server-authoritative. Clearing identity restores device fallback, not a
   previous user's language.

## Sessions, requests and recovery

`AUTH_SESSION_IDLE_MINUTES` and `AUTH_SESSION_ABSOLUTE_HOURS` are database-owned
API policy. The client records whether background return needs validation; it
has no elapsed-time expiry, session warning or reminder scheduler. Native startup
only cancels reminders left by older builds, without requesting notification
permission.

There is no periodic check on a healthy untouched foreground screen. Protected
navigation, authenticated request rejection and background return detect expiry
or revocation. An untouched screen may remain visible until such an action.
WebUI behavior and backend revocation remain unchanged. The retained backend
`/auth/me/session-status` endpoint is not called by Flutter.

Each asynchronous result belongs to the current session generation. Sign-out,
revocation or identity change makes old responses ineligible to update state or
restore protected navigation. A 401 clears identity; a 403 is not automatically
interpreted as expiry. Principal revalidation must not silently switch user IDs.

Network failures retain data behind a noninteractive gate with Retry/Sign out.
Only that existing foreground offline gate performs bounded reconnect reads.
Mutations are never replayed automatically. In particular, a lost password-change
response can follow a committed change: Retry reads the principal and resumes
setup rather than submitting the old password again.

## Password feedback

The transport recognizes only established password-change outcomes:

| API outcome | Mobile presentation |
| --- | --- |
| 422, `password must contain at least N characters` | Localized new-password field error using the server-provided minimum |
| 400, `current password is incorrect` | Localized current-password field error |
| 429, `password_attempts_locked` | Existing localized cooldown message using validated server seconds, with numeric `Retry-After` fallback |
| Other/unrecognized response | Safe generic failure; no reflected raw diagnostics or invented field highlighting |

Confirmation mismatch is a local equality check, not a password-policy rule.
A nonempty mismatch explains why submit is disabled and clears when corrected.
The client does not calculate password policy or recreate the lockout deadline.
Login failures retain established non-disclosing behavior.

## Translation lifecycle

Canonical English and Arabic live under `frontend/webui/i18n/`. Mobile assets are
synchronized copies; never edit them directly. Published database translations
become portable only after a complete administrator export is deliberately
merged into the canonical artifact, validated and synchronized into a build.
Publication does not live-update an installed mobile binary.

Preserve administrator wording and per-item provenance by `message_key`. Seed
missing local Arabic drafts only with `--missing-only`; do not overwrite
published translations to reconcile files. The current translation status is tracked
in [Phase 1 status](phase-1-progress.md#remaining-handoff-work).
