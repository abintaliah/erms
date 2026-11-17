# Phase 1 status and handoff

Maintained as of 17 November 2026. See the [documentation guide](README.md) for
scope and authority. The full earlier narrative is preserved in the
[historical progress record](history/phase-1-progress-through-2026-11-17.md).

## Status

Phase 1 was explicitly approved complete on 5 November 2026. Subsequent
integration review uncovered narrow authentication/feedback gaps, which are now
corrected and covered by regression tests. The latest device-language amendment
has passed native Android/iOS automation in place of the manual checkpoint,
as explicitly requested by the user. Its controlled-locale/injected-API scope
is recorded in the acceptance evidence.
This does not reopen waived historical session-reminder or timing experiments.

Phase 2 remains unimplemented. Its 5 November API map is a historical snapshot;
refresh it against the integrated API before designing or implementing content
screens. See [remaining handoff work](#remaining-handoff-work).

## Current behavior

- Sign-in and required password changes use the device's primary Arabic language
  or English fallback until a saved ERMS preference is available. The saved
  preference then takes precedence. Sign-out/revocation discards it and returns
  to the current device language.
- Required-password login retains the session and shows the form before making
  localization/capability calls that the API currently forbids. Successful
  replacement refreshes principal, language and navigation before opening the
  shell. Recovery revalidates state without replaying a password mutation.
- Password errors explain the server's minimum length or incorrect current
  password under the affected field. Lockout feedback uses server-provided retry
  seconds. Nonmatching confirmation has its own inline explanation; it clears
  on correction. Unknown server text is not displayed.
- The API owns expiry, lockout, capabilities and authorization. There is no local
  session-expiry timer, reminder, or healthy-screen polling. Protected actions
  and background return revalidate; an existing offline gate permits bounded
  safe-read recovery. Tokens and protected state remain in process memory.
- Native mobile identity and optional sanitized device model are recorded in
  existing audit/session contracts. Screen destinations remain Phase 1 navigation
  foundations; they are not completed Dashboard/search/content features.

Implementation details are in [architecture](architecture.md); concrete tests
are in the [validation matrix](validation-matrix.md).

## Latest verification and acceptance

| Evidence | Recorded result |
| --- | --- |
| Flutter analysis and unit/widget/HTTP suite, 17 November | Clean analysis; 115 tests pass |
| Password-attempt backend suite, 17 November | 21 tests pass in a new disposable database; database dropped |
| Published Arabic export, 17 November | Complete 4,089-key artifact promoted with publication provenance; wording unchanged |
| Latest native builds/installations | Android debug APK and iOS simulator app built, installed and launched on Pixel 8 and iPhone 18 Pro |
| Earlier post-merge build review | User reported both apps okay; not evidence for every later follow-up |
| Required-password success | User reported successful Android continuation after supplying a valid replacement password |
| Password-feedback review | User explicitly considered the requested feedback verification done; additional per-platform/scenario detail was not supplied |
| Device-language selection amendment | Native Android/iOS runs passed with controlled platform locales and an injected API, replacing the requested manual checkpoint; [retained evidence](verification/language-2026-11-17/README.md) |
| Tablet evidence | Retained 4 November landscape-only native layout tests used an injected API; live-server tablet authentication is not established |

Acceptance limits remain explicit: manual absolute-lifetime device testing was
waived; native tablet portrait/rotation was omitted by user approval; explicit
Retry versus automatic outage recovery, legacy-install reminder cleanup and
some individual language/platform observations were not separately reported.
Do not turn those limitations into claimed device passes or new unapproved gates.

## Translation export completed — 17 November 2026

A complete published Arabic export was produced directly from the configured
local database using the existing Translation Administration export builder in
a repeatable-read, read-only transaction. UTC timestamp handling matches the
API's export convention. All 4,089 active messages were exportable with no
missing/invalid entries and no reviewed-draft overrides.

The canonical Arabic artifact now contains publication provenance for
`mobile.authentication.password_too_short` and
`mobile.authentication.current_password_incorrect`. No wording changed, and all
4,087 previously curated entries were preserved exactly. Mobile asset sync
completed; its text is unchanged, so a provenance-only promotion needs no new
binary installation. Export reports/snapshots remain in gitignored
`.runtime/translation-promotion/`; the canonical artifact is the portable copy.

Catalogue quality/coverage/order/hash/runtime checks, 17 Arabic validator tests,
four Flutter catalogue tests and the targeted imported-provenance regression
pass. The regression used a new disposable database which was dropped afterward.
No publication/database state was modified by exporting. There is no remaining
translation export or publication task for these messages.

## Remaining handoff work

No additional manual language review or translation export is required for this
handoff. The user requested automated acceptance followed by commit/push. Both
native runs passed; [the procedure](language-acceptance.md) and
[evidence](verification/language-2026-11-17/README.md) document the controlled
platform-locale and injected-API scope. OS language preferences and real ERMS
accounts were not changed. After testing, normal `lib/main.dart` Android/iOS
simulator builds were rebuilt, reinstalled and launched on both targets.

The next product work is Phase 2:

1. Refresh [the API snapshot](phase-2-api-map.md) against the integrated API.
2. Settle the recorded contract choices and obtain required mockup approval.
3. Implement and validate read-only content features against the approved scope.
   Do not infer new API or workflow approval from the preparation notes.

Use `git status` for actual commit/push state. The repository's user-controlled
Git workflow still applies to subsequent work.

## Milestones

| Date | Outcome |
| --- | --- |
| 30 September | Phase 0 scaffold complete; mobile-focused visual direction approved |
| 4–5 November | Server-owned expiry/no-reminder amendment; action-triggered revocation; Phase 1 acceptance with recorded limits |
| 16 November | Synced fork/main integrated into all local branches; local database upgraded through migration 113 |
| 16–17 November | Required-password bootstrap sequencing corrected; configuration inventory reconciled; published translation export preserved |
| 17 November | Password validation/cooldown and confirmation feedback corrected; stale provenance test updated; device-language fallback approved, implemented and verified by native automation; published export completed |

For detailed upgrade effects and resolved review findings, use the
[November integration review](integration-review-2026-11.md). Workstation logs,
credentials and temporary database backup files remain under gitignored
`.runtime/`; they are not portable verification artifacts.
