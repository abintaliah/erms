# Authentication subsystem

## Scope and model

ERMS currently supports local, database-backed authentication. Authentication
establishes identity; authorization remains a separate subsystem. Users have an
`account_type` of `human` or `system`. System accounts represent software and
cannot use interactive password login. Administrative authority is assigned by
the reserved `system-administrator` role, never by a superuser flag on a user.

Future OIDC providers will map their subject identifiers to the same internal
users and issue the same internal sessions, keeping the rest of the application
independent of the authentication provider.

## Credentials and passwords

`user_credentials` contains one optional local credential per human user.
Passwords are hashed with Argon2id and neither hashes nor plaintext passwords
are exposed by the API or copied to event history. Repeated failures cause a
temporary account lock. Relevant settings are:

- `AUTH_PASSWORD_MIN_LENGTH` (default `12`)
- `AUTH_LOCKOUT_ATTEMPTS` (default `5`)
- `AUTH_LOCKOUT_MINUTES` (default `15`)

Administrators issue a random temporary password from the Users page. It is
shown once, expires after 24 hours, revokes existing sessions, and forces a
password change before the user can access normal application functions.

## Sessions

`login_sessions` stores only SHA-256 hashes of opaque session and CSRF tokens.
Sessions are shared through PostgreSQL, so they work across API workers and can
be revoked immediately. The browser cookie is HttpOnly and SameSite=Lax.
Cookie-authenticated write requests require the matching CSRF header. The
NiceGUI service keeps its API token in encrypted user storage and sends it as a
Bearer credential to the API.

- `AUTH_SESSION_IDLE_MINUTES` controls sliding idle expiry (default `30`).
- `AUTH_SESSION_ABSOLUTE_HOURS` controls the maximum lifetime (default `12`).
- `WEBUI_STORAGE_SECRET` encrypts NiceGUI user storage and must be replaced in
  every non-development deployment.
- `AUTH_COOKIE_SECURE` must be `true` when the API is served over HTTPS
  (it defaults to `false` only for local HTTP development).

The Login sessions page lists user, status, creation and activity times, IP,
and client description. A user can revoke their own sessions. Members of the
`system-administrator` role can see all sessions, force logout one session, or
force logout all sessions for a user. Destructive actions require confirmation.

## API

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/change-password`
- `GET /api/v1/auth/sessions`
- `DELETE /api/v1/auth/sessions/{session_id}`
- `DELETE /api/v1/auth/users/{user_id}/sessions`
- `POST /api/v1/auth/users/{user_id}/temporary-password`

All `/api/v1` endpoints except login require an active session. Health and API
documentation remain public. Suspended/inactive users and system accounts
cannot authenticate interactively.

## Bootstrap and recovery

Create the initial user and organization unit, then run:

```bash
backend/services/api/.venv/bin/python -m backend.services.api.manage_auth \
  administrator@example.org \
  --make-system-administrator \
  --org-unit-code ROOT
```

The command creates the reserved administrator role if necessary, assigns it,
revokes old sessions, and prints a single-use temporary password exactly once.
Running it without `--make-system-administrator` resets an existing human
user's local password.

## Audit history

Authentication emits secret-free domain events including
`AUTHENTICATION_SUCCEEDED`, `AUTHENTICATION_FAILED`, `PASSWORD_CHANGED`,
`PASSWORD_RESET`, and `SESSION_REVOKED`. Authenticated data changes populate
`actor_user_id` and use actor type `user`. Credential and session tables do not
use automatic snapshot triggers because their rows contain security secrets.

## OIDC extension point

A future `user_identities` table will associate `(provider, subject)` pairs
with internal users. After provider validation, OIDC login will create the same
opaque internal session used by local authentication. Roles, audit attribution,
session administration, and future authorization will therefore work the same
way for either provider.
