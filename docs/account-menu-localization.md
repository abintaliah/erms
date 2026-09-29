# Account menu entity names

Login and `/auth/me` include `localized` projections for the signed-in user,
assigned roles and their organization units. They use the same enabled-language,
base-language and canonical-name fallback rules as the entity detail pages.
Canonical names remain in their existing response fields.

The frontend uses these display names in the account menu and derives avatar
initials from the displayed user name. It retains the email and stable identity
used for avatar color. Opening the menu refreshes the existing `/auth/me` response;
there is no per-role request fan-out or new cache. Language changes use the
existing preference reload lifecycle. No message keys or translation artifacts
are changed and no database migration is required.

`test_account_menu_names_follow_language_and_fall_back` verifies Arabic names
in login and `/auth/me`, canonical fields, missing-translation fallback, and
switching back to English against a disposable database.

Verification: all 15 authentication tests pass. Live browser checks confirmed
English and Arabic user, role and unit names, localized avatar initials, and
unchanged email in the account menu. No administrator translation export was
promoted and no new translation review is required.
