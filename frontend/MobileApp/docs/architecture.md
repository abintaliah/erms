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
    network/            future HTTP transport and error mapping
    routing/            future typed route ownership
  features/             future mobile feature modules by user journey
```

Phase 0 deliberately uses Flutter SDK facilities only. Networking, state, and
routing packages will be selected when their concrete requirements are known;
adding a framework merely to populate the scaffold is not an architectural
decision.

## Environment boundary

API base URLs and other environment values must be supplied at build or launch
time. Production credentials, session material, API tokens, and protected
content must never be committed to the repository or compiled as constants.
