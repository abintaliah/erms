# Phase 0 architecture boundary

## Principles

- Flutter is a presentation client of the existing ERMS API.
- The server is authoritative for identity, capabilities, authorization,
  validation, concurrency, resource visibility, and audit outcomes.
- User-specific and protected state remains in memory in the initial online-only
  client.
- Feature code must depend on typed client boundaries rather than reconstructing
  server policy.
- Requests are owned by a route or state generation so obsolete responses can
  be ignored after navigation, query changes, refresh, logout, or user changes.
- Mutations are never retried automatically.

## Source layout

```text
lib/
  app/                  application composition and shell
  core/
    design/             Wathiq mobile tokens and shared presentation
    localization/       governed catalogue loading and lookup
    network/            shared transport-safe failure categories
    routing/            future typed route ownership
  features/
    auth/                typed authentication contract and session ownership
```

The Phase 1 authentication client uses `dart:io` HTTP facilities behind an
injectable `AuthApi` boundary and keeps session state in a plain controller.
No networking, state-management, persistence, or routing package is required
for this unit. A later package may be selected only when a concrete requirement
cannot be met cleanly with the pinned SDK.

## Environment boundary

API base URLs and other environment values must be supplied at build or launch
time. Production credentials, session material, API tokens, and protected
content must never be committed to the repository or compiled as constants.

## Phase 1 server-owned session scope

Preferences, capabilities, principal and locale are process-memory state owned
by the current session generation. Freshness comes from sign-in, explicit
Preferences reads/mutations, and foreground session validation. Logout,
revocation and background expiry clear that state; obsolete requests cannot
write into a later generation. Errors retain existing in-memory data behind a
noninteractive gate and never populate persistent caches. English is restored
when identity clears; saved language remains server-authoritative.

Session idle and absolute expiry belong exclusively to the API application
settings (`AUTH_SESSION_IDLE_MINUTES` and `AUTH_SESSION_ABSOLUTE_HOURS`). The
client records only whether a background return needs server validation; it has
no elapsed-time cutoff, local expiry clock or reminder scheduler. Server-valid
sessions resume, unauthenticated responses clear protected state, and network
failures retain the noninteractive validation gate. Native startup cancels only
legacy reminders from older builds without requesting notification permission.
