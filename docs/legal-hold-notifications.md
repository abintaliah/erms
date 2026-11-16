# Built-in legal-hold notifications — implementation report

Approved contract: `specs/legal-holds.md`, revision 1.1, notification extension
approved 3 October 2026. Implementation and verification are complete.
The extension implements the two agreed producers and
the approved seven-day reminder rule.

## Delivered behavior

- `holds.responsibility_assigned`: notifies each newly assigned owner/contributor
  on creation and subsequent responsibility changes. Unchanged assignments and
  removals send nothing. Each assignment uses the hold event-history ID and
  person ID for idempotency.
- `holds.approaching_end`: one reminder per hold/end-timestamp pair, while the
  hold is active and within its final seven days. Only current active owners and
  contributors receive it. Open-ended, scheduled, and expired holds are excluded.
  Changed dates may receive a new reminder; returning to a previously notified
  date does not repeat it. Durable checkpoints survive message purge.
- Both producers are optional, with feature-owned audiences, normal initial
  priority, no structured resource links, no read receipts or messaging actions,
  and no confidential hold names or case details in the supplied templates.
- Assignment changes and notifications commit atomically. Reminder delivery and
  its checkpoint likewise commit atomically. Failure rolls back both sides.
- A bounded API worker uses the existing pool, one transaction-scoped leader
  lock across instances, and approximately one-minute checks. Inactive audiences
  do not consume the candidate page. Reminder failures do not prevent messaging
  retention cleanup from running.

## Configuration and translations

The explicit Python registry, portable catalogue seed, English/Arabic template
asset, canonical schema, migration 038, and configuration installer are included.
The installer requires an active notification administrator, records source
`seeding`, preserves active configurations and pending drafts, and uses ordinary
validation/activation. It does not fabricate a system user or bypass language
coverage requirements. Optional producers remain dormant until configured.

Arabic templates use the checked-in term **«تعليق قنوني»**. No UI catalogue keys
were added, changed, or removed for this extension; existing administrator
wording and provenance were preserved. The new subject/body pairs are versioned
notification configuration, not duplicate terminology keys. Operators review
the supplied template pairs when activating them and can subsequently edit them
through Notification Administration.

## Requirement and test evidence

The acceptance tests are in
`backend/services/api/tests/test_hold_notifications.py`.

| Requirement | Implementation | Acceptance evidence |
| --- | --- | --- |
| Notify new responsibilities only | Hold create/update/contributor hooks and `notify_assignments` | Creation, owner change, added contributors, unchanged assignments, removals, event replay |
| Fixed seven-day active window | `process_reminders` | Exact seven-day boundary, exclusive end timestamp, scheduled/open-ended/expired exclusions |
| Current eligible recipients | Feature-owned audience resolvers | Changed owner, removed contributor, inactive accounts, empty audiences, bounded candidate pages |
| One reminder per end timestamp | Checkpoint table and stable source event identifier | Parallel workers, changed date, reverted date, repeated scans |
| Retention independence and worker leadership | Durable hold checkpoint and transaction-scoped advisory lock | Real notification purge followed by worker scan; competing leader lock |
| Atomic failure | Consistent-snapshot business transaction and shared notification writer | Injected failure after notification write rolls back owner change, envelope, deliveries, and checkpoint |
| Governed optional configuration | Existing configuration service and installer | Disabled producers, existing-version preservation, installer authorization, contract/readiness checks |
| Bilingual privacy-safe content | Separate English/Arabic template pairs | Rendered Arabic term, no confidential title, correct recipients, receipt/action fields disabled |
| Canonical deployment consistency | Schema, migration 038, separate catalogue seed | Fresh/upgrade schema parity and existing-data preservation |

The combined regression run passed **40 tests** covering the initial producer
acceptance cases, existing legal-hold workflows, Phase 4 notification
administration, and policy inventory. The expanded final producer suite passed **9 tests** in 18.78 seconds, including
worker leadership and real post-purge duplicate prevention. These counts overlap
and should not be added. No functional test failures remain.
Internationalization catalogue checks, Python compilation, and whitespace checks
passed. Existing Starlette/AnyIO deprecation warnings are unrelated to this work.

## Deployment boundary

No persistent database was migrated, seeded, or activated during development.
Apply migration 038 (or initialize from the canonical schema), run the separate
producer catalogue seed, then use the administrator-attributed configuration
installer documented in `docs/deployment.md`. Existing configurations are never
overwritten. All database verification uses uniquely named disposable databases
with explicit cleanup. All test databases were successfully dropped.

## Localized producer names — 3 October 2026

Producer metadata now has a canonical English name and an entity `translations`
object. The shared entity localization projection supplies the effective name
and English fallback to Notification Administration and Monitor. Detail screens
retain the producer code as secondary technical information. Search matches
localized/English names and codes with bounded code-cursor pagination.

Migration 039 and the updated producer seed were applied to `demo`. The two
existing active configuration IDs and every template row were compared before
and after and remained identical. UI catalogue artifacts were not changed.

Verification: 29 backend tests passed (hold notifications and notification
administration), 8 frontend interaction tests passed, and catalogue validation
passed. Fresh/upgrade schema parity passed. Browser checks covered English and
Arabic names, the secondary code in details, Arabic search, and RTL appearance.
Evidence: `docs/verification/producer-names/ar.png`. No tests ran against `demo`.

### Recipient-rule labels

The recipient-rule selector now maps stable resolver values to contextual UI
catalogue labels in English and Arabic. Added keys:
`messaging.admin.audience.current_responsible_people` and
`messaging.admin.audience.newly_assigned_person`. The English manifest and Arabic
artifact remain sorted with matching key order and an updated catalogue hash;
all previous wording/provenance is preserved. No administrator export was
promoted. The checked-in new entries retain generated-draft provenance; their
Arabic values were separately published on `demo` through the existing
publication logic for the requested UI correction, attributed to administrator
6. All other 2,917 Arabic database rows were verified unchanged.

Verification: 8 frontend tests, including both rules in both languages and
unchanged submitted values; 10 backend regression tests; catalogue validation;
and live Arabic browser inspection passed. Screenshot:
`docs/verification/producer-names/recipient-rule-ar.png`. No database migration
was needed for this correction.

## Information-governor audience extension — 4 October 2026

The user approved including all information governors in both producers.
Contract version 2 resolves active person accounts with a currently valid
assignment to an effectively active `is_information_governance` role, together
with the existing responsible-person audience. Each assignment event remains
separate; recipient IDs are deduplicated within each event. Expiry reminders
also run when only governors are eligible. Supplied English/Arabic templates
use neutral wording suitable for both responsibilities and governance oversight.
Existing administrator versions and translations are preserved.

Traceability: the audience extension in `specs/legal-holds.md` is implemented in
`hold_notifications.py`; migration 043 advances existing producer contracts,
and the separate producer seed registers version 2 for new installations.
No schema DDL is required, so canonical schema creation remains self-contained.
The disposable runner applies 043 on its upgrade path.

Verification: 11 legal-hold notification tests passed, including both governor
notification types, expired assignments, recipient deduplication, and reminder
eligibility without active responsible people. Fresh/upgrade schema parity and
data preservation passed; both unique test databases were dropped. No tests ran
against the persistent database. UI catalogue artifacts and keys are unchanged;
the changed templates are versioned notification configuration.

Local deployment: migration 043 and separate seeds were applied to `erms`;
both producers were activated under administrator `yya@sa.gov.ae` with operational
owner `Legal governance`. Both requested accounts were verified as active,
effective governors. API health reports notification readiness without issues.

## Revised governor audience — 4 October 2026

The user revised the audience requirement: information governors receive only
approaching-expiry reminders. Responsibility-assignment notifications go only
to the newly assigned active owner/contributor; a governor personally assigned
receives their own assignment notification like any other responsible person.
The expiry audience and seven-day rule are unchanged.

This revision supersedes the earlier both-producer audience extension above.
`assigned_audience` implements the revised specification; assignment contract
version 3 and migration 044 upgrade existing deployments without modifying
administrator configurations, templates, or historical notifications. New
installations use the separate latest producer seed. No schema DDL is needed.
The regression test explicitly excludes governors from assignment deliveries
and includes effective governors in expiry deliveries, excluding expired roles.
