# Notifications and In-App Messaging — Proposed Specification

**Status:** Proposed  
**Project:** ERMS / Wathiq  
**Prepared:** 30 September 2026  
**Revision:** 1.17 — linked user-messaging UI mockup

## 1. Purpose

This specification defines a durable, asynchronous, in-app notifications and
messaging subsystem for Wathiq. It allows the system to notify a user and allows
one user to send a message to one or more other users.

Messages are stored before delivery is attempted. A frontend-neutral real-time
event interface can then notify connected clients with low latency. Each
frontend decides how to present that event; for example, NiceGUI may show a
toast and a future Flutter application may show an in-app banner.

The live connection is an optimization, not the message store and not proof of
delivery. A temporary network failure, closed client, or restarted application
must not lose a committed message.

### 1.1 Non-normative user-interface mockup

The repository includes a
[clickable user-to-user messaging mockup](../docs/mockups/wathiq-user-messaging.html)
covering Inbox, Outbox, Drafts, Compose, message reading, replies, forwarding,
follow-ups, recipient selection, action completion, and action amendments.

The mockup is a design and review aid only. It does not create an API contract,
authorize behavior, or override this specification. If the mockup and this
specification differ, this specification is authoritative. Production user
interfaces must also comply with the design language, internationalization,
accessibility, authorization, performance, and frontend-specific requirements
applicable to that implementation.

## 2. Scope

This subsystem includes:

- system notifications addressed to users;
- messages sent by one user to one or more users;
- user, Wathiq-role, and organizational-unit recipient selectors;
- `To` and `Cc` recipients;
- one independently identifiable recipient copy per addressee;
- inbox, unread state, message reading, and read receipts;
- a human sender's Outbox containing previously sent messages;
- private saved message drafts;
- a privilege-gated operational Monitor page;
- replies and Inbox forwards linked to an earlier recipient copy, plus Outbox
  forwards and follow-ups linked to an earlier sent envelope;
- rich-text message bodies;
- links to Wathiq resources;
- priority and action-required indicators;
- optional action due dates, reply-based completion acknowledgments, and late
  indicators;
- a frontend-neutral near-real-time event interface for connected clients;
- NiceGUI toast notification as one presentation adapter;
- durable catch-up after disconnection or application restart; and
- capture of an authorized sent or received message and its linked
  reply/forward/follow-up chain as a Wathiq record through the existing record-draft
  workflow.

This subsystem does not include:

- email, SMS, mobile push notifications, or any other external delivery
  channel;
- attachments or embedded copies of Wathiq resources;
- group conversations, chat rooms, presence, or typing indicators;
- automatic authority to view a linked Wathiq resource;
- action assignment, instructions, progress stages, escalation, reassignment,
  approval, or another action-management workflow; or
- a guarantee that a person has understood or acted upon a message.

## 3. Terms

**Message envelope** means the parent object created by one send operation. It
holds the fields that are identical for every recipient, and its related rows
hold the original recipient selections and resource links.

**Send-level message data** means the parts of a sent message that belong to the
whole send and therefore are stored once rather than copied into every
recipient's Inbox row. They are the sender snapshot, subject, priority, security
level, body, message-level flags, relationship references, original recipient
selectors, expanded addressee snapshots, and structured resource links. They do
not include recipient-specific mailbox sequence, read time, action-completion
state, or deletion state.

**Recipient copy** means the durable inbox item created for exactly one `To` or
`Cc` recipient. Each recipient copy has its own globally unique ID and its own
read state.

**System message** means an envelope created by an approved Wathiq process
rather than by a person. Its displayed sender name is `system`.

**Live signal** means a transient instruction to a connected client to refresh
or display a newly committed recipient copy. A live signal is not the message
itself and is not durable delivery.

**Real-time gateway** means an authenticated backend API connection that emits
live signals to a client or frontend adapter. The gateway is independent of
NiceGUI and may use a documented WebSocket or server-sent-event protocol.

**Database notification channel** means PostgreSQL `LISTEN`/`NOTIFY` used to
tell every real-time gateway instance that a committed delivery may be
available. The notification is a transient wake-up signal, not the durable
message store.

**Read receipt** means the sender-visible fact that a specified recipient copy
was first marked as read. It is available only when the sender requested read
receipts.

**System-message language variant** means one immutable rendered subject/body
pair for a registered enabled language, produced from the same system event,
configuration version, and typed context as every other language variant of
that envelope.

## 4. Core rules

### MSG-001 — In-app only

The subsystem shall not depend on email or another external delivery system.
A message is delivered to the user's Wathiq inbox.

### MSG-002 — Allowed senders

Wathiq may send a system message to a user. An authenticated person user may
send a user message to one or more users only when they have the
`messaging.user_messages.exchange` global privilege.

A user message shall store both the sender's user ID and the sender-name
snapshot that was current when it was sent. A system message has no sending
user ID and stores the sender-name snapshot `system`. Later changes to a user's
name or deletion of a user must not rewrite the historical sender name.

### MSG-003 — Required message fields

Every recipient copy shall expose:

- its globally unique ID;
- sender name;
- subject;
- priority;
- security level, when currently authorized for the viewer;
- rich-text body;
- whether action is required;
- action due date and the viewer's applicable derived action status;
- whether the copy has been read;
- the original `To` recipient selectors;
- the original `Cc` recipient selectors;
- when it was sent; and
- whether a read receipt was requested.

`is_read` is recipient-specific. It shall be derived from whether the recipient
copy has a `read_at` timestamp rather than maintained as an independent boolean
that could disagree with that timestamp.

### MSG-004 — Addressing

A send operation shall contain at least one `To` recipient. It may contain
multiple distinct `To` recipients and multiple distinct `Cc` recipients.

The same user shall not occur more than once in one envelope and shall not be
both a `To` and a `Cc` recipient. Recipient membership and displayed recipient
names shall be snapshotted at send time.

A sender cannot address their own user account. Inactive or suspended users
shall not be returned by recipient search, accepted as direct selectors, or
included by role or organizational-unit expansion.

A human user lacking `messaging.user_messages.exchange` shall not be returned
or accepted as a recipient for a human-authored message. This restriction does
not prevent registered backend producers from delivering system messages.

One send is limited by default to 100 combined `To` and `Cc` selectors and
2,000 distinct concrete recipients after expansion. The API rejects the send
atomically when either limit is exceeded; it does not truncate an audience.
These are deployment configuration values read from validated environment
variables. Values must be positive, changing them requires an application
restart, and increasing them requires transaction, notification-volume, and UI
performance testing. The effective values shall be exposed in the compose
capabilities response so clients can explain a limit before final send.

### MSG-005 — Role and organizational-unit recipients

The sender may place one or more Wathiq roles or organizational units in `To`
or `Cc`, in addition to selecting individual users.

A role selector must identify an effectively active role. It expands at send
time to every active person user who currently has that role as an effective
role under Wathiq's existing effective-role rules. This includes assignment
validity, user status, role status, and the status of the role's owning
organizational unit and its ancestors.

For a human-authored message, role and organizational-unit expansion includes
only users who currently have `messaging.user_messages.exchange` through an
effective role. System-message audience expansion does not require that
privilege.

An organizational-unit selector must identify an active organizational unit.
It expands at send time to every active person user who currently has at least
one effective role directly owned by that organizational unit. It does not
implicitly include users whose effective roles belong only to descendant
organizational units; a descendant unit must be selected separately.

Expansion uses one database transaction snapshot. Later changes to users,
assignments, roles, or organizational units do not add or remove recipients
from an already-sent message.

The sender's original selectors and their displayed names are preserved as the
immutable `To` and `Cc` headers. The expanded concrete users are preserved as
the immutable delivery and receipt-status list available to the sender. A
recipient does not gain permission to enumerate every expanded user merely
because they received the message.

If a user matches several selectors, that user receives one copy only. If the
user is reached through both `To` and `Cc`, `To` takes precedence. If expansion
of a human user's role or organizational-unit selector includes the sender,
the sender is excluded before deduplication and recipient-limit evaluation. If
expansion produces no eligible concrete user, sending fails without creating
an envelope or delivery.

### MSG-005A — Shared selector components

Within each frontend implementation, every messaging interface that selects a
user, role, organizational unit, or security level shall reuse the corresponding
selector component already used elsewhere in that same frontend. Thus WebUI
messaging reuses the established WebUI selectors, while a Flutter messaging UI
reuses the selectors established by the Flutter application. This applies to
Compose, Drafts, recipient validation, Notification Administration audiences,
controlled test sends, filters, and any later messaging interface that presents
one of these entity selectors.

This requirement does not require WebUI and Flutter to share UI source code,
widgets, packages, rendering behavior, or other implementation technology. Each
frontend reuses and remains consistent with its own component system while all
frontends consume the same frontend-neutral messaging APIs and server-enforced
rules.

The messaging subsystem shall not introduce a messaging-only user selector,
role selector, organizational-unit selector, or security-level selector, nor
copy the shared component's search, pagination, display, accessibility, RTL, or
selection behavior into a separate implementation. Messaging may configure the
shared components for single or multiple selection, `To` or `Cc` placement,
bounded search, retained selected values, and messaging-specific eligibility or
validation explanations.

If an established selector in that frontend lacks a capability required by this
specification, that capability shall be added to that frontend's shared
component through a general reusable interface and verified against its
existing consumers. It shall not be solved by creating or maintaining a
messaging-specific fork within that frontend. Reuse of a UI component does not
replace server-side messaging authorization,
clearance, activity, privilege, expansion, deduplication, or send-time
validation.

### MSG-006 — Fan-out

Sending one envelope to multiple addressees shall create exactly one recipient
copy for each distinct addressee. Every copy shall have a different globally
unique ID. All copies shall refer to the same envelope. Subject, priority,
rich-text body, action-required state, receipt request, sender snapshot, and
relationship references are stored once on that envelope and are not duplicated
into delivery rows. Address selectors and expanded addresses are also stored
once per envelope rather than copied into every delivery.

Each delivery row stores only the recipient-specific identity and state needed
for that user's inbox, including recipient user, `To`/`Cc` classification,
mailbox sequence, creation time, and read time. Reading a recipient copy joins
that delivery to its message envelope and address rows.

Read state shall be independent. One recipient reading their copy must not mark
another recipient's copy as read.

The entire send and fan-out operation shall be atomic: either the envelope and
all recipient copies are committed, or none of them are.

### MSG-007 — Reply

A sender with `messaging.user_messages.exchange` may create a new message as a
reply to a recipient copy they are allowed to read. The new envelope shall
store relationship kind `reply` and that copy's globally unique ID in
`related_delivery_id`.

The earlier subject or body shall not be embedded automatically in the reply.
The earlier message remains a separate item and is loaded only when the user
opens the link to it. A recipient of the reply receives the same read-only
linked-message access defined for a forward; possession of the referenced UUID
without a delivery of the reply does not grant access.

A message in the sender's Outbox is not replied to. The equivalent sender-side
operation is **Send follow-up**. The original sender may create a new message
with relationship kind `follow_up` and `related_envelope_id` pointing to an
active Outbox envelope they currently own and may read. The follow-up is a new
immutable envelope with a newly selected recipient list; recipients are not
automatically inherited from the earlier message. The earlier subject and body
are linked, not embedded or copied.

Receiving the follow-up grants the same read-only linked-message access defined
for a forward, subject to the earlier message's current availability, the
recipient's current clearance, and all resource-specific authorization checks.
The UI shall call this operation **Send follow-up**, not Reply, so it does not
imply that the sender is replying to themselves.

### MSG-008 — Forward

A sender with `messaging.user_messages.exchange` may create a new message as a
forward of a recipient copy they are allowed to read. The new envelope shall
store relationship kind `forward` and that copy's globally unique ID in
`related_delivery_id`.

The original sender may also forward an active Outbox envelope they currently
own and may read. In that case, the new envelope stores relationship kind
`forward` and the earlier envelope's globally unique ID in
`related_envelope_id`. The sender chooses a new recipient list; the earlier
recipients are not automatically inherited.

The earlier subject or body shall not be embedded automatically in the forward.
A forward is a link to an earlier message, not a content copy. Receiving the
forward grants that recipient read-only access through the forward to the
complete earlier message, including its sender, subject, security level,
priority, action-required flag, body, resource links, and original `To` and `Cc`
selector headers.

This grant does not expose another recipient's delivery row, read state, or the
sender's read-receipt status because those are recipient-specific operational
state rather than shared message content. Possession of a delivery UUID alone
never grants access; the server derives the grant from an authenticated user's
own delivery of the forwarding envelope.

One envelope may have at most one relationship kind and one valid source. A
reply uses a delivery source; a follow-up uses an Outbox-envelope source; and a
forward uses either a delivery source or an Outbox-envelope source, never both.

An envelope marked `is_test = true` or whose `message_kind` is
`action_amendment_notice` cannot be used as the source of a reply, forward, or
follow-up.

### MSG-009 — Read state

A recipient may mark only their own copy as read. The first successful
transition records `read_at`. Repeating the operation is idempotent and must not
change the original timestamp.

Displaying a toast or listing a message in the inbox does not mark it as read.
The UI marks it as read when the user opens the message.

### MSG-010 — Read receipts

The sender may request read receipts for an envelope. When requested, the
sender may see which recipient copies have been read and the first-read time of
each copy.

The receipt is derived from the durable recipient copy's `read_at` value. It
does not depend on the recipient remaining connected and does not require a
separate external delivery channel. Reading a copy before or after a network
interruption produces the same durable result once the read request succeeds.

If read receipts were not requested, recipient read state shall not be exposed
to the sender through the messaging interface.

### MSG-011 — Resource links

A body may contain structured links to Wathiq resources. A linked resource's
effective security-level number must be less than or equal to the message's
security-level number:

```text
linked_resource_security_level_number <= message_security_level_number
```

The sender must also be currently authorized to read the resource. A resource
that the sender cannot read, or whose level is higher than the message level,
cannot be added. Changing the compose form's message level shall immediately
revalidate every existing resource link. The server shall repeat resource
existence, sender authorization, and security-level validation in the final
send transaction; client validation is not sufficient.

Wathiq resource links shall be inserted through the structured resource-link
control and stored separately from ordinary external hyperlinks. A raw internal
URL must not bypass resource validation. The rich-text renderer associates each
stored link occurrence with its normalized resource-link row.

One message may contain at most 50 structured Wathiq resource links by default.
The limit is a validated positive environment configuration value, is returned
by the compose capabilities API, and is enforced again in the send transaction.
Ordinary external hyperlinks in rich text remain governed by body-size and
sanitization rules rather than this structured-link count.

A resource link conveys no continuing access right. On every inbox-page status
evaluation, message open, and resource open, the server applies the target's
current authentication, authorization, security-level, lifecycle, and existence
checks. The link is currently unavailable to a recipient when, among other
reasons:

- the recipient no longer has sufficient effective clearance or another
  required permission for the resource;
- the resource's current security level has risen above the message level;
- the resource is no longer readable in its current lifecycle state; or
- the resource has been deleted or no longer exists.

If the message itself remains readable, an unavailable resource link shall be
rendered as a non-clickable, non-disclosing placeholder with a localized reason
appropriate to what the user is permitted to know. The message remains readable
and its other valid links remain usable. The API must not return protected
target metadata merely to explain the failure.

Authorization revocation cannot retract information that a recipient already
read, copied, cached, printed, or captured before the change. These rules
prevent subsequent retrieval and make current unavailability visible; they do
not claim retroactive erasure.

### MSG-012 — Rich text safety

The body shall use Wathiq's approved rich-text format. The server shall validate
and sanitize it on write against an explicit allowlist. Executable script,
event-handler attributes, unsafe URLs, active embedded content, and other
unsupported markup shall be rejected or removed before storage.

The client shall render only the sanitized representation. Sanitization is a
security boundary and must not rely only on browser-side code.

### MSG-013 — Immutability

After send, the sender, address list, subject, priority, security level, body,
`action_required`, action due fields, receipt request, reply link, forward link,
and sent time shall not change. Recipient read timestamps and separately
recorded action-completion acknowledgments are the only mutable message state
defined by this specification.

This revision does not define editing, recalling, deleting, archiving, or
expiry of sent messages. Reply-based action completion is defined narrowly by
MSG-015.

### MSG-014 — Message security level

Every envelope shall have exactly one Wathiq security level. It must never be
null. The default is the active configured security level having the lowest
`level_number`, consistent with Wathiq's existing baseline-level rule.

The sender's effective clearance is the greatest `level_number` among the
sender's currently effective roles, using the existing Wathiq security model.
The user sender may select only a message security level whose `level_number`
is less than or equal to that effective clearance. If the sender makes no
explicit selection, the lowest configured level is used. A user sender with no
effective role cannot send a message because even the mandatory baseline level
cannot be authorized through an effective role.

A system-message producer has authority to use only the lowest configured
security level. It cannot request, retain, or derive authority to assign a
higher message level.

Every concrete recipient of a secured message must have current effective
clearance greater than or equal to the message's security-level number at send
time:

```text
recipient_effective_clearance_number >= message_security_level_number
```

For a direct-user selector, a user below the required clearance cannot be
selected. A role or organizational-unit selector expands only to users who
meet the message clearance. If it resolves to no eligible user at the selected
level, that selector cannot be added to `To` or `Cc`.

The server shall re-evaluate the sender, selected message level, selectors, and
every expanded recipient in the final send transaction. Client-side filtering
or an earlier recipient preview is not sufficient authorization.

A secured reply, forward, or follow-up must have a security level at least as
restrictive
as every referenced earlier message. The sender must be cleared for that level,
and every new recipient must satisfy it. A link must not be used to disclose a
more highly secured earlier message through an unsecured or lower-level reply,
forward, or follow-up.

When a secured message or linked earlier message is opened, the server shall
re-evaluate the authenticated user's current effective clearance. A user whose
clearance has since fallen below the message level retains the delivery row but
cannot retrieve protected subject, body, headers, or resource-link details
unless sufficient clearance is restored.

### MSG-015 — Action due date, acknowledgment, and lateness

When `action_required = true`, the sender may supply an `action_due_date` as an
informational target date. The date does not define what the action is and does
not create assignment, progress, escalation, approval, or workflow behavior.
When `action_required = false`, `action_due_date` and its timing fields must be
null.

The sender enters the due date as a local date in their effective Wathiq
working timezone. The server stores:

- the entered `action_due_date`;
- the sender's IANA `action_due_timezone` snapshot; and
- `action_due_at`, the instant at the start of the following local date in that
  timezone.

This makes the entire selected due date available and gives every viewer the
same objective late boundary. The due date must not precede the sender's current
local date when the message is sent.

Action completion is tracked independently for each recipient delivery. When a
recipient replies to an action-required message and their delivery is not yet
completed, the compose UI shall prompt **Is the action done?** The default is
unchecked. If checked, sending the reply atomically records one immutable
completion acknowledgment for that recipient's original delivery and links it
to the reply envelope.

The completion acknowledgment is permitted only when:

- the authenticated user owns the original recipient delivery;
- the reply's `relationship_kind` is `reply` and its `related_delivery_id` is
  that delivery ID;
- the original user sender is a `To` recipient of the reply and cannot be
  removed while **Is the action done?** is checked;
- the original envelope has `action_required = true`; and
- no completion has already been recorded for that delivery.

The reply containing the completion acknowledgment informs the original sender
through the ordinary durable reply delivery and its near-real-time notification.
The reply shall visibly state **Action completed**, and the original sender's
sent-message recipient status shall update accordingly. No separate email,
escalation, or workflow task is created.

For each recipient delivery, the current action status is derived as follows:

| Condition | Status |
| --- | --- |
| The original envelope has `action_required = false` | Not applicable |
| Completion exists and the latest fair effective due boundary is null or was not passed | Completed |
| Completion exists and `completed_at` passed the latest fair effective due boundary | Completed late |
| No completion exists and the effective action has been withdrawn | Withdrawn |
| No completion exists and the effective due boundary is null or has not passed | Outstanding |
| No completion exists and the effective due boundary has passed | Late |

The effective action and due boundary are derived from the immutable original
fields followed by the amendments in sequence under MSG-023. A later fair
extension or removal may correct Completed late to Completed, but an amendment
must never turn Completed into Completed late. `Late` is never stored as an independent boolean. Both the original sender and
the applicable original recipient shall see the same derived late indicator.
With multiple recipients, one recipient's completion does not complete or
change another recipient's status.

Crossing the due boundary does not create a new message, toast, escalation, or
background workflow. The indicator is derived whenever the authorized inbox,
message, or sent-status view is read or refreshed.

An ordinary reply with **Is the action done?** unchecked leaves the action
outstanding. A completion acknowledgment is not a read receipt and does not
imply that Wathiq verified the action's substance or quality. This revision does
not define reversal or withdrawal of a completion acknowledgment. A completion
reply must reference the original delivery, never an amendment-notice delivery.

### MSG-016 — Outbox and drafts

Every authenticated human user with `messaging.user_messages.exchange` shall
have an Outbox containing the immutable user messages they previously sent. In
this specification, **Outbox** means the
user-facing sent-message collection; it is not a background delivery queue.
System-produced messages do not appear in a human user's Outbox.

An Outbox item is the original message envelope, not another recipient delivery
or a duplicate of its content. The sender may view its immutable content,
original selectors, expanded concrete recipients, read-receipt information
when requested, and per-recipient action status, subject to the sender's current
message clearance. Outbox listing and filtering shall use server-side
pagination.

A human user with `messaging.user_messages.exchange` may save an unsent private
draft. A draft may contain the same compose fields, recipient selectors, and
structured resource links as a message, but it has no sent time, delivery
copies, read state, receipts, mailbox sequence, toast, or action completion.
Only the owning user with current exchange privilege may list, read, edit,
send, or discard it.

A draft remains active for 180 days after its last update. The UI warns the
owner when 30 days remain. An expired or explicitly discarded draft moves to a
private **Recently deleted drafts** view for 30 additional days, during which
the owner may restore it. Restoration reopens the same draft but does not
restore stale recipient eligibility, clearance, or resource authorization.
After the recovery period, the subsystem permanently deletes the draft and its
draft-only selector and resource-link rows. Draft lifecycle processing creates
no message, delivery, toast, or record. The 180-day active period, 30-day
warning, and 30-day recovery period are validated deployment settings, with
these values as the defaults.

Saving a draft does not reserve recipient membership, authorization, resource
access, or security clearance. The UI may report its current validation state,
but sending must re-evaluate every rule from current authoritative data. A
successful send converts the draft to one immutable envelope atomically and
removes it from the Drafts page. A retry with the same idempotency key must not
send it twice.

### MSG-017 — Save a message as a Wathiq record

The sender or a recipient may save an ordinary human-authored message they are
currently authorized to read as a new record in an aggregation they choose.
This operation uses the existing record-draft and record-commit workflow rather
than bypassing record creation controls.

Only `message_kind = user_message` is eligible for message-to-record capture.
A `system_notification`—whether production or test—and an
`action_amendment_notice` cannot be selected or included as a linked message in
a capture. If an otherwise eligible user message has a relationship chain that
contains an ineligible kind, capture is blocked with a clear explanation rather
than silently omitting part of the chain. A feature whose business event must
itself create a record shall do so through that feature's approved backend
record-creation process, not by asking a recipient to preserve its notification.

The user must have:

- current authorization and clearance to read the selected message and every
  linked reply, forward, or follow-up message included in the capture;
- the existing `record.create` global privilege;
- `aggregation.add_record` permission on the chosen destination; and
- sufficient clearance and all ordinary destination, closure, ownership,
  numbering, and record-creation requirements.

No new messaging privilege substitutes for these existing record controls.

The record draft is initialized as follows:

- record `title` defaults to the selected message subject and remains editable
  under the ordinary record-draft rules;
- record `date_originated` defaults to the selected message's `sent_at`;
- record `security_level_id` is fixed initially to the selected message level
  and cannot be lowered below the highest level among included messages;
- the user chooses the destination aggregation and supplies or confirms every
  other required record field, including the record number; and
- the generated message PDFs are the authoritative message content preserved
  in the record; and
- separate capture-provenance metadata records the source message-envelope ID,
  the user who performed the capture, the capture time, and the resulting
  record ID. The same provenance is rendered into a human-readable PDF and
  saved as the record's final digital component. Later expiry or purging of the
  source messaging data does not alter or invalidate the captured record.

The selected message is rendered as a human-readable PDF and staged as digital
component 1. The PDF preserves the message's immutable sender, sent time,
original `To`/`Cc` selector headers, subject, priority, security level,
original action-required and due-date fields, the chronological action-
amendment history and effective state at capture time, sanitized body, and
human-readable structured resource links. Recipient-specific read receipts and other users'
delivery state are not included.

If the selected message is a reply, forward, or follow-up, every earlier
message reachable through its relationship references shall also be captured once, provided the
capturing user is currently authorized to read it. Those linked messages are
rendered as separate PDFs and staged as subsequent digital components ordered
by `sent_at` ascending with message ID as the deterministic tie-breaker. The
selected message remains component 1 as required; chronological ordering
applies to components 2 onward. A reference cycle or duplicate reference is
rejected as integrity corruption rather than producing repeated components.

After all message PDFs, Wathiq shall generate a **Message capture provenance**
PDF as the final digital component. It contains the capture ID, resulting record
ID and number, selected source envelope ID, capture date and time with timezone,
capturing user's immutable name and identifier snapshots, and an ordered list
of every included message component showing its component order, role
(`selected message` or `linked earlier message`), envelope ID, sent time, and
generated filename. This PDF contains provenance only; it does not repeat the
message bodies, recipient delivery state, or resource contents.

The provenance PDF is part of the authoritative captured record, while the
structured capture tables remain the queryable audit and referential layer.
Both representations are created from the same transaction data and must
agree. A mismatch or inability to render the provenance PDF fails the capture
without committing a partial record.

One capture may include at most 100 linked earlier messages in addition to the
selected message and final provenance PDF, and all generated PDFs combined may
not exceed 50 MiB. Both
limits are checked before record commit. Exceeding either limit blocks capture
without creating a partial record and tells the user which limit was exceeded.
The limits are validated deployment settings with these values as defaults;
raising them requires PDF-renderer, storage, request-duration, and record-view
performance testing.

If any required linked message becomes inaccessible, the message body or
stored resource-link metadata cannot be rendered faithfully, or any
authorization check fails before commit, capture fails without creating a
partial record. Loss of access to the resource itself does not prevent capture:
the PDF preserves the safe stored link description and indicates that current
access is unavailable. Ordinary message resource links remain references in
the PDF; saving a message as a record does not extract, duplicate, or grant
access to the linked resources.

PDF generation and component staging shall be deterministic and bounded. The
record and all generated components become authoritative together only when the
existing record draft commits successfully. The resulting record and component
history shall identify that they were created by the message-capture workflow.
Saving the same message more than once is permitted when the user deliberately
creates distinct records; each capture is independently authorized and audited.

Every generated component shall conform to both PDF/A-2u and PDF/UA-1. Failure
to produce or validate either required conformance blocks record commit. The
PDF shall be tagged with logical reading order, Unicode text
mapping, document title and language metadata, embedded fonts, descriptive link
text, heading and list structure, and correct LTR or RTL direction. Information
must not be conveyed by color alone. Sanitized rich text that cannot be
represented safely in this archival profile is rendered as safe text rather
than active content.

Component filenames use only stable non-sensitive values:
`message-<UTC-sent-timestamp>-<envelope-uuid>.pdf`, where the timestamp is
formatted `YYYYMMDDTHHMMSSZ`. The subject and sender name are not placed in the
filename. Filename collisions are impossible within a capture because envelope
IDs are globally unique. The final provenance component uses
`message-capture-provenance-<capture-uuid>.pdf`.

### MSG-018 — Production of system notifications

A system message may be created only by registered backend notification
producer logic. There is no public or frontend API that accepts
`sender_kind = system`, a system-producer identity, or arbitrary system-message
content. Ordinary NiceGUI, Flutter, and other client operations cannot send as
`system` or provide per-event system-message recipients, subject, body,
priority, resource links, receipt setting, or action fields. Privileged
administrative configuration is limited to MSG-019 and never directly sends an
ordinary production event. Its explicitly marked test-send operation is the
only exception and cannot create a production notification.

A client action may nevertheless cause a system notification indirectly. The
client invokes an ordinary authorized business operation, such as an approved
domain command. After independently authenticating, authorizing, and validating
that operation, backend business logic decides whether a defined notification
event has occurred. The notification is a consequence of the committed
business operation, not a client-authored messaging request. A rejected or
no-op business request must not create its success notification.

Every producer shall be registered under a stable `producer_code`. Its approved
contract defines:

- the domain event or backend condition it may report;
- the allowed static and/or named backend recipient-resolution modes;
- the allowlisted subject/body placeholder schema and renderer;
- allowed priority and resource-link behavior;
- the stable domain-event identifier used for idempotency; and
- whether durable notification creation is required for the associated business
  transaction to commit.

The feature-owned boolean `required_for_business_commit` expresses only that
transactional policy. When true, administrators cannot disable the producer and
occurrence of the registered event must create the durable envelope and all
recipient deliveries in the same transaction; failure rolls back the business
change. When false, administrators may disable the producer, in which case the
business operation may commit without a notification. If an optional producer
is enabled, an attempted notification still follows the ordinary atomic send
rules and a creation failure rolls back the transaction.

`required_for_business_commit` does not set message priority, request a read
receipt or action, require the recipient to read the message, or require a toast
or live event to reach a connected client before commit. The required outcome
is durable database creation, not user attention or real-time presentation.

This does not require the product owner to enumerate every future notification
producer before the messaging subsystem can be implemented. The initial
registry may be empty. “Registered” means that each feature which introduces a
system notification declares and tests this small contract in that feature's
approved specification and backend code before the producer is enabled. The
registry is an application allowlist: administrators configure registered
entries through MSG-019 but cannot create a producer, event trigger, resolver,
placeholder, or executable behavior.

#### Concrete backend integration

In this revision, registration and use are explicit Python application-service
integration, not REST and not an automatic event-bus subscription.

Each feature that introduces notifications provides a declarative Python
`SystemNotificationDefinition`. At minimum it contains the producer code,
event type, typed placeholder schema, allowed audience resolver names, allowed
resource-link kinds, `required_for_business_commit` policy, and contract
version. The API
application assembles these definitions into one registry explicitly during
startup; registration must not depend on an incidental module import or a
client request.

The feature's canonical catalogue seed creates its producer row for a new
deployment, while an upgrade migration advances the row for an existing
deployment when the contract changes. Seeds remain separate from schema
creation. On startup, every API instance read-only compares the database
producer row and contract version with the Python registry. A missing, unknown,
duplicate, or incompatible definition whose
`required_for_business_commit = true` fails readiness with a clear configuration
error instead of silently dropping required notifications.

Feature backend code calls one internal Python application-service operation at
the exact point where the approved business outcome is written. The conceptual
interface is:

```python
notification_service.emit_system_notification(
    transaction=db_transaction,
    producer_code="feature.approved_event",
    source_event_id=str(domain_event_id),
    context={
        "declared_text_value": bounded_text,
        "declared_date_value": domain_date,
    },
    triggered_by_user_id=current_user_id,
)
```

The actual Python module and type names may follow repository conventions, but
the operation has these mandatory semantics:

- it accepts the caller's already-open PostgreSQL transaction and never commits
  it independently;
- it accepts only producer code, stable source-event ID, schema-validated
  context values, and optional triggering-user provenance;
- it does not accept subject, body, priority, security level, arbitrary
  recipients, arbitrary resource links, or a sender identity from the caller;
- it loads and locks the producer's active administration configuration;
- it validates the context against the registered typed placeholder schema;
- it invokes only the registered static/dynamic audience resolver and permitted
  resource-link builder;
- it verifies published template coverage, renders and sanitizes every enabled-
  language variant, forces the baseline security level and prohibited
  receipt/action fields, and calls the canonical envelope/fan-out writer; and
- it returns a typed result containing the created envelope and delivery IDs,
  or a defined `disabled` result for a producer whose
  `required_for_business_commit = false` and active configuration is disabled.
  Validation or required-configuration failure raises a domain error and rolls
  back the caller's transaction.

The business feature must not insert messaging tables directly. A scheduled
backend job may call the same operation while updating its governed domain state
in the same transaction. A separately deployed service that cannot participate
in that PostgreSQL transaction cannot produce a system notification in this
revision; that topology would require the later transactional-intent extension.

The privileged REST operation used by **Send test** is deliberately separate.
It calls an internal `emit_system_notification_test` operation that enforces
MSG-019 and always sets immutable test provenance. It cannot invoke the
production operation with a fabricated domain event.

A producer has no general messaging authority beyond that contract. It cannot
accept a client-supplied producer code or use a recipient rule or template
capability outside the active validated administration configuration and
feature contract. If approved template values contain data
originally entered by a user, the values are treated as untrusted data,
strictly bounded, escaped or sanitized, and recorded as part of the resulting
message; they do not become executable markup or template instructions.

System messages always use the lowest active configured security level as
required by MSG-014. A producer may include only resource-link kinds explicitly
allowed by its registered contract, and only when backend authorization policy
permits that exact link at the baseline level. Producer status is not a general
bypass of resource authorization. A system message shall always have
`read_receipt_requested = false` and `action_required = false`; system producers
cannot request receipts, set an action due date, or receive action-completion
acknowledgments.

For this revision, production system notification creation is always atomic
with the business change that causes it. The domain change and the envelope, concrete
recipient snapshots, fan-out rows, mailbox sequences, and `NOTIFY` calls are
written in the same PostgreSQL transaction. If notification validation or
creation fails, the complete transaction rolls back. The caller may retry the
ordinary business operation using its stable idempotency key; retrying must not
create a duplicate domain change or notification.

The explicitly marked administration test in MSG-019 has no domain change. Its
test envelope, recipients, mailbox sequences, and notifications commit in one
standalone transaction or not at all.

There is no asynchronous system-notification intent queue, retry worker, or
manual notification replay operation in this revision. Adding one later would
be a separately approved extension. Backend work that cannot share the domain
transaction must not claim to have produced a system notification under this
contract.

### MSG-019 — System notification administration

System-notification configuration shall be administered from a **Notification
Administration** page under the Messages navigation category. Access requires
the new `messaging.notifications.administer` global privilege, granted by
default only to `SYS_ADMIN` and `ALL_PRIVS`. The privilege is independent of
`messaging.monitor` and `audit.view`.

The administration page operates on producer definitions registered by
application features. Feature code supplies the immutable `producer_code`,
event type, allowed template placeholders and their data types, permitted
audience modes, permitted resource-link kinds, and whether notification is
`required_for_business_commit`. Administrators cannot create a new executable event, change its
trigger, submit arbitrary production event data, or directly send a production
system message from this page.

For each registered producer, an administrator may:

- enable or disable it only when `required_for_business_commit = false`;
- author, review, and publish the bounded subject and sanitized rich-text body
  template for every enabled language using only the producer's allowlisted
  placeholders;
- select `normal`, `high`, or `very_high` priority;
- configure a static audience of eligible users, roles, and organizational
  units, or select one of the feature's declared dynamic audience resolvers;
- configure allowed baseline-level resource-link presentation when the feature
  contract permits resource links; and
- record a non-blank operational owner name or team label.

The page cannot change the mandatory lowest security level or enable read
receipts, action-required state, due dates, executable template logic, arbitrary
queries, or resource types outside the feature contract. Static audience
selectors use the same active-user, deduplication, self-exclusion where
applicable, and recipient-limit rules as ordinary sending, but do not require
`messaging.user_messages.exchange`. Dynamic resolvers are named backend
implementations, not administrator-authored expressions.

Saving configuration validates placeholder parity and previews every enabled
language in its configured direction without sending. Each successful change
creates an immutable configuration version and
an event-history entry containing the actor, producer, changed safe fields,
reason, and timestamp. Enablement, audience, template, priority, and
resource-presentation changes are also flagged as Security Operations because
they can change who receives system-authored information. Secrets and example
protected event data are not stored in configuration history.

An administrator may test the active or pending valid configuration through a
dedicated **Send test** action. A test send:

- uses the real canonical envelope, delivery, mailbox-sequence, PostgreSQL
  `NOTIFY`, real-time gateway, Inbox, unread, and toast path;
- uses the selected immutable configuration version and either feature-provided
  safe sample values or administrator-entered values limited to the declared,
  typed, bounded, escaped placeholders;
- permits only explicitly selected active individual users as test recipients,
  never a role, organizational unit, configured static audience, or dynamic
  audience resolver;
- is limited by the configured test-recipient count and per-administrator rate
  limit;
- repeats every ordinary baseline security, recipient, resource-link, rich-
  text, size, and authorization check;
- stores `is_test = true`, the initiating administrator, and a unique test-run
  ID immutably on the envelope, using `test` as the source event type and the
  test-run ID as its idempotent source-event identity; and
- creates event-history and Security Operations entries identifying the
  producer, configuration version, initiator, recipient count, result, and
  correlation ID without storing protected content in the event.

Every presentation of a test message—including toast, Inbox row, message view,
and Notification Administration test history—shall show a prominent localized
**TEST — not a production notification** label. The indicator is derived from
the immutable server field, not from editable subject text, and is not conveyed
by color alone. The rendered subject is also prefixed for clarity, but the
prefix is not the security control.

A test message cannot request receipts or action, cannot be replied to,
forwarded, or followed up, and cannot be saved as a Wathiq record. It is excluded from
production notification success/failure rates and business workflow counts but
included in separate test-send operational metrics. It expires after 30 days,
may be deleted early from a test recipient's own Inbox without record capture,
and is purged through the ordinary recovery and content-cleanup mechanism.

When the feature event occurs, the business transaction locks and uses one
active configuration version, resolves and snapshots the concrete audience,
renders and sanitizes the allowlisted template, writes the resulting envelope
with its configuration-version ID, and commits atomically as required by
MSG-018. Later administration changes never rewrite an already-sent message.
An invalid configuration for an enabled producer causes the business
transaction to fail closed with an operational error. A producer whose
`required_for_business_commit = false` and active configuration is disabled
creates no message and does not prevent the business transaction from
committing.

### MSG-020 — Sent-message retention and deletion

Sent messages expire by default three years after `sent_at`. Ninety days before
expiry, Inbox and Outbox show a localized expiry indicator. An eligible human-
authored message also provides the existing **Save as record** action; system
notifications and amendment notices do not. Reconnect and live-event processing
must not emit one warning toast per expiring message.

Saving a message as a record is the mechanism for preserving it beyond the
messaging retention period. The resulting record and PDF components follow
ordinary record retention, disposition, legal-hold, access, and deletion rules
independently of the source message.

Before automatic expiry, a sender or recipient may delete the message from
their own Outbox or Inbox only after that user has successfully saved that
message as a record. The server verifies a committed
`message_record_captures` row for that user and envelope and confirms that the
resulting record still exists under record governance at deletion time; a
client assertion, an uncommitted record draft, another user's capture, or a
record already disposed of is insufficient. Deleting one user's view does not
remove another recipient's delivery or the sender's Outbox view. Later lawful
disposition of the captured record remains governed by record rules and is not
blocked by messaging provenance.

The capture-free exceptions are every `system_notification`, whether production
or test, and every `action_amendment_notice`. Their recipients may delete their
own Inbox references without record capture because neither kind may become a
record. Deleting an amendment notice does not delete its authoritative amendment
from the retained original message.

Manual deletion and automatic expiry first move the affected mailbox reference
to **Recently deleted messages** for 30 days. During that period its owner may
restore it if the send-level message data has not yet been purged. After the
recovery period the reference is permanently hidden and cannot be restored
through the messaging interface.

Automatic expiry applies to every remaining Inbox and Outbox reference whether
or not an individual user saved the message as a record. A user who needs to
preserve the communication is responsible for saving it as a record before the
displayed expiry. This rule provides a bounded messaging store rather than
allowing uncaptured messages to grow without limit.

The send-level message data defined in section 3 is retained while any Inbox or
Outbox reference is active or recoverable. Deleting one recipient's delivery
therefore cannot remove the subject, body, or other send-level data still needed
by the sender or another recipient. An active or recoverable amendment-notice
delivery also retains its linked original envelope so **Open amended message**
cannot point to prematurely purged content. Once no active or recoverable
reference
remains, a bounded cleanup job purges the subject, body, rendered language
variants, selector and addressee details, resource-link details, receipt state,
action-amendment reasons and due-state values, and other message content. It
retains only a minimal non-content tombstone needed for UUID uniqueness,
relationship-link unavailability, record-
capture provenance, idempotency, and event-history integrity. Opening a link to
a purged earlier message shows a localized non-disclosing **This message has
expired or was deleted** placeholder.

Cleanup runs in bounded batches, is idempotent, and locks candidate rows so
multiple API or maintenance instances cannot purge the same message
concurrently. A cleanup failure leaves content retained for a later run; it
must never partially purge a still-active or recoverable message.

### MSG-021 — Localization of system-generated messages

Human-authored message subjects and bodies are displayed exactly as authored;
Wathiq does not automatically translate them. Application UI around the
message—labels, priority names, dates, buttons, status, validation, and
placeholders—uses the ordinary UI catalogue and the viewer's effective language.

Each system-notification configuration version contains a subject and body
template for every enabled Wathiq language. English is the canonical/default
template and fallback. All language templates use the same declared named
placeholders with identical types and cardinality. A configuration version
cannot be activated while any enabled language is missing, blank, unreviewed,
or placeholder-incompatible. Enabling a new Wathiq language is blocked by the
existing language release-readiness process until every active system producer
has a valid template for it.

When a system event is emitted, the internal service renders and sanitizes an
immutable subject/body variant for every currently enabled language using the
same configuration version and typed event context. Locale-sensitive values
and translated controlled/entity display values are resolved under that
language at send time and snapshotted in the rendered variant. The envelope's
ordinary `subject` and `body_rich_text` columns contain the rendered system-
default-language variant for deterministic fallback; the language-variant rows
contain every rendered version, including the default.

Each delivery snapshots the recipient's effective language at send time. Its
live toast uses that language variant. Inbox and message retrieval use the
viewer's current effective language when that immutable variant exists, then
fall back deterministically to the envelope's system-default variant and
finally English. Changing a user preference changes which already-stored
variant is presented; it never translates at read time or modifies the
envelope. A language enabled after the send may fall back because that historic
envelope could not contain a then-unknown variant.

Recipient copies still reference one envelope. Localization creates one
subject/body row per language, not one copy of the complete message per
recipient. Read state, deletion state, receipts, and mailbox sequence remain
recipient-specific and language-independent.

Notification Administration edits templates per language, validates exact
placeholder parity, previews every enabled language and direction, and follows
the governed review and fallback principles of the approved Internationalization
and User Preferences specification. These administrator-authored notification
templates are versioned message configuration data, not UI catalogue strings;
the administration screen's own labels and errors remain ordinary catalogue
keys. Test sends render all language variants and each test recipient sees the
variant selected by their effective language.

Action-amendment notices use server-owned application templates maintained as
ordinary governed UI catalogue keys rather than administrator-editable producer
templates. At amendment commit, the server renders and stores one immutable
notice variant for every enabled language. Fixed wording, controlled action
states, and date presentation are localized; the sender-authored reason is
embedded verbatim and is never machine-translated. Toast and later-read variant
selection and fallback follow the same rules as a system notification.

System notifications are never eligible for message-to-record capture. Their
localized variants remain durable messaging content only for the notification's
retention period. The underlying business object, event history, audit entry,
or feature-created record—not the notification—is the authoritative evidence of
the event being reported.

### MSG-022 — Person-to-person messaging privilege

The global privilege `messaging.user_messages.exchange` controls both sending
and receiving human-authored messages. It is a seeded immutable privilege and
is included automatically in `ALL_PRIVS`; other profiles receive it only by
explicit profile administration. System producers and system-message receipt
do not require or inherit this privilege.

A person with the privilege may use Compose, Drafts, and Outbox; send, reply,
forward, and follow up human-authored messages; be selected directly; and be included by
human-message role or organizational-unit expansion, subject to every other
clearance, lifecycle, visibility, and messaging rule.

A person without the privilege:

- retains the Messages category and Inbox, but Inbox lists and counts only
  system-generated messages, including unmistakably marked system tests;
- has no Compose action and no Outbox or Drafts navigation or API access;
- cannot send, reply to, forward, or follow up a human-authored message;
- cannot be selected directly or included by a role or organizational-unit
  expansion for a human-authored message; and
- remains eligible for system notifications independently of this privilege.

Losing the privilege does not delete envelopes, deliveries, drafts, record
captures, or history. Existing human-authored Inbox deliveries become hidden
from listing, unread counts, catch-up, and content retrieval; Outbox and Drafts
become inaccessible. Restoring the privilege restores access subject to current
security clearance, retention, deletion, and resource authorization. Draft
expiry continues while hidden.

`messaging.monitor`, `messaging.notifications.administer`, and `audit.view`
remain independent. A user lacking exchange privilege sees their privilege-
gated Monitor or Notification Administration link only if they separately hold
the applicable privilege; those administrative capabilities do not grant
person-to-person mailbox access.

### MSG-023 — Immutable action amendments

Sending never edits an existing message envelope. When an action instruction
was entered incorrectly, the original human sender may append an immutable
structured action amendment to the original envelope. The original
`action_required`, due-date fields, subject, body, sender, recipients, priority,
security level, resource links, receipt setting, and relationship references
remain unchanged.

Only these amendments are permitted for an envelope originally sent with
`action_required = true`:

- add a due date when the original/effective action has none;
- change the effective due date;
- remove the effective due date while leaving the action outstanding; or
- withdraw the action requirement for every incomplete recipient.

An informational message cannot be amended into an action request. An action
withdrawal cannot be reversed or reactivated; a new action requires a new
message. No amendment may change message content, priority, security, address
list, resource links, read-receipt behavior, or any recipient's completion
acknowledgment. Amendments apply to the complete original concrete audience and
cannot target selected recipients.

The amendment stores its own globally unique ID, monotonically increasing
sequence within the original envelope, kind, previous effective action state
and due fields, new effective state and due fields, original sender as actor,
server-assigned time, and a mandatory non-blank reason. It is append-only and
cannot be edited, replaced, reordered, or deleted through messaging operations.
The effective action state is derived from the original envelope followed by
its amendments in sequence; no mutable effective-state column is authoritative.

Fairness rules are mandatory:

- a newly added or changed due boundary must be in the future when the
  amendment commits, using the sender's validated working-timezone snapshot;
- an amendment must not make an incomplete recipient immediately or
  retroactively Late;
- it must not change a recipient from Completed to Completed late;
- extending or removing a superseded deadline immediately removes a current
  Late indicator caused by that deadline;
- the original and superseded dates remain visible in amendment history, but
  the ordinary current status must not continue to characterize a recipient as
  late against a deadline the sender corrected; and
- withdrawal changes every incomplete recipient to Withdrawn, while recipients
  already completed remain Completed or Completed late under the latest fair
  effective due date preceding withdrawal.

The sender must currently own the original envelope, retain access to its
active Outbox reference, have `messaging.user_messages.exchange`, and satisfy
the original message's current clearance. The amendment and its recipient
notices are created atomically using the original concrete recipient set. A
recipient who has since lost exchange privilege retains the delivery rows but
does not see human-authored message or amendment-notice content until the
privilege is restored; current clearance checks also continue to apply.

The authoritative amendment is a row in `message_action_amendments`. The same
transaction creates one specialized immutable notification envelope with
`message_kind = action_amendment_notice`, the original sender identity and
security level, priority, expiry, and one recipient copy for every original
recipient. It contains no resource links. The notice
uses server-owned localized templates and the ordinary durable mailbox,
PostgreSQL `NOTIFY`, real-time event, Inbox, unread, and toast path. Its `To`/`Cc`
classification follows each recipient's original classification and cannot be
edited by the sender.

An amendment notice is a delivery mechanism, not the authoritative correction.
It cannot be replied to, forwarded, followed up, used for action completion, or
independently
saved as a record. Opening it marks only that notice delivery as read and
provides **Open amended message**, which opens the original message with its
complete action-amendment timeline. Replies and completion acknowledgments
continue to reference the original recipient delivery. Forwarding the original
message exposes its current effective action state and amendment history under
the ordinary linked-message authorization rules.

For the sender, an amendment notice does not appear as an unrelated Outbox
item. The original Outbox detail displays it in the action-amendment timeline.
For recipients, the notice appears in Inbox with an unmistakable localized
**Action amended** indication, the old and new effective state/date, amendment
time, sender, and reason, subject to current authorization. Notice read state
means only that the correction notice was opened; it is not acceptance.

The amendment notice uses the original envelope's retention expiry and may be
deleted early by its recipient without record capture because it cannot itself
become a record. The authoritative amendment is retained and purged with the
original envelope's send-level message data. Purging a notice never removes the
amendment timeline from a still-retained original message.

Capturing the original message as a record includes the immutable original
action fields and a clearly separated chronological **Action amendments**
section containing every amendment committed by capture time, plus the
effective action state and language at capture. The amendment notice is not a
separate captured component. A record captured before a later amendment is not
silently rewritten; a user may perform a new capture when the later history
must also become a record.

## 5. Priority and action-required meaning

Priority is a required controlled value. The initial values are:

| Stored value | Display meaning |
| --- | --- |
| `normal` | Ordinary priority |
| `high` | Important and visually emphasized |
| `very_high` | Highest priority and strongly emphasized |

Priority affects ordering and presentation only. It must not bypass
authorization, change delivery durability, or create an external alert.

`action_required = false` means the message is informational.
`action_required = true` tells the recipient that the message calls for an
action. The optional due date, reply-based completion acknowledgment, and
derived late indicator have only the narrow meanings in MSG-015. They do not
define the action itself, validate its completion, or create escalation or a
workflow.

## 6. User experience

### 6.1 Navigation

The navigation drawer shall contain a **Messages** category immediately below
**Records Management**. For an authenticated human user it contains, in order
when applicable:

1. **Inbox**;
2. **Outbox**, only with `messaging.user_messages.exchange`;
3. **Drafts**, only with `messaging.user_messages.exchange`;
4. **Monitor**, only when the user has the new `messaging.monitor` global
   privilege; and
5. **Notification Administration**, only when the user has
   `messaging.notifications.administer`.

`messaging.monitor` is a dedicated least-privilege capability. Reusing
`audit.view` would unnecessarily grant the complete system-wide audit surface,
while monitoring messaging does not require reading message content. The
initial privilege shall be granted by default to the built-in `SYS_ADMIN` and
deliberately comprehensive `ALL_PRIVS` profiles. Other profiles receive it only
through explicit administration.

The Monitor page exposes sanitized operational information such as send and
fan-out rates, failures, PostgreSQL listener health/reconnections, connected
real-time gateways, catch-up failures, restricted-message counts, PDF-capture
failures, and oldest unresolved operational error. It shall not expose message
subjects, bodies, selector names, recipient identities, resource metadata, or
permit message impersonation, mutation, or mailbox browsing.

A Monitor user who also has `audit.view` may follow an authorized link to
relevant event-history entries. `messaging.monitor` alone does not grant that
access, and `audit.view` alone does not make the Messages Monitor navigation
item visible.

Notification Administration is the configuration surface defined in MSG-019.
Its privilege does not grant mailbox browsing, message-content access,
operational Monitor access, or general event-history access.

### 6.2 Inbox

The inbox shall show only recipient copies belonging to the authenticated user.
It shall support server-side pagination and shall not download the user's whole
mailbox. Its default order is newest `sent_at` first, with recipient-copy ID as
a deterministic tie-breaker. Read state and priority may be exposed as filters
or deliberate alternate sort choices.

The inbox shall distinguish unread messages, `To` from `Cc`, priority, and
action-required messages. For a readable action-required delivery it shall also
show the due date when present and the recipient's current Outstanding, Late,
Completed, or Completed late indicator. It shall have deliberate loading,
empty, and error states and follow Wathiq's established table/list
presentation.

Without `messaging.user_messages.exchange`, the same Inbox page and pagination
contract return only envelopes with `sender_kind = system`. Human-authored
deliveries are not returned as rows or counted as unread while the privilege is
absent.

A delivery shall remain present when the recipient no longer has sufficient
current clearance to view the message. Instead of silently omitting it, the
inbox shall show a non-disclosing **Restricted message** placeholder. The
placeholder preserves mailbox ordering, unread accounting, and awareness that a
delivery exists, while revealing no sender, subject, priority, action-required
state, headers, body, or resource information. It shall explain that the user's
current authorization no longer permits access. If clearance is later restored,
the ordinary message row becomes visible again.

For a readable message containing structured Wathiq resource links, the inbox
shall show a generic indicator when one or more links are currently unavailable,
without naming or describing an inaccessible resource. Opening the message
shows the permitted per-link status described in MSG-011.

The inbox service shall determine message-clearance and linked-resource status
for the bounded current page using set-based or bounded-batch authorization
queries. It must not issue one API or database round trip per message or per
link, and it must not scan the user's complete mailbox.

Inbox exposes **Delete** only when the authenticated recipient has a currently
retained committed record capture satisfying MSG-020, or the envelope is a
system notification or action-amendment notice that is ineligible for capture.
Inbox exposes **Save as record** only for an eligible human-authored message.
It shows the configured
expiry date and warning state. A **Recently deleted** view within Inbox lists
only that recipient's recoverable deleted deliveries and provides Restore; it
is not a separate navigation-drawer item.

### 6.3 Message view

Opening a message shall fetch the current user's copy by its globally unique ID,
re-check current message clearance, render the sanitized body, show its
immutable metadata, and mark the copy read. A delivery that the user can no
longer clear shall remain counted and identifiable only through a
non-disclosing restricted-message state; opening it must not reveal its subject,
body, headers, sender, or resource links and must not mark it read.

Reply and forward controls shall create a new compose operation with the
appropriate link; they shall not quote or embed the old content.

Replying to an incomplete action-required delivery shall show the explicit
unchecked **Is the action done?** prompt. After an acknowledgment is recorded,
later replies shall show the existing completion status and shall not offer a
second completion control.

### 6.4 Compose

The Compose route, action, and API require
`messaging.user_messages.exchange`. Hiding the UI is not authorization; the
server rejects send, reply, and forward requests without the privilege.

Recipient controls shall use the current frontend's existing shared user, role,
and organizational-unit selector components as required by MSG-005A. Those
components shall use bounded remote search and retain selected values. They must
not obtain options
through an unbounded user, role, or organizational-unit list request. Role
results shall expose whether a role is currently effective; organizational-unit
results shall expose whether the unit is active. Ineligible choices shall not
be selectable.

Only recipients visible under existing lifecycle, authorization, and
recipient-discovery rules may be selected. This specification does not create a
new privilege or broaden which users, roles, or organizational units a sender
may discover.

The compose form shall reuse the current frontend's existing shared security-
level selector, configured as a required value initialized to Wathiq's lowest
configured level. It shall offer only levels at or below the sender's current
effective clearance. Changing the selected level shall immediately revalidate
every existing recipient selector. A messaging-specific security-level
selector shall not be created.

Recipient search results that are otherwise visible but ineligible at the
selected message level shall remain understandable rather than silently
disappearing. They shall be disabled and display a localized explanation:

- a user does not have sufficient current effective clearance;
- a user is not currently permitted to exchange person-to-person messages;
- a role has no current effective user with sufficient clearance; or
- an organizational unit has no current effective user with sufficient
  clearance.

For role and organizational-unit results, an otherwise eligible selector is
also disabled when expansion contains no active user who has both sufficient
clearance and `messaging.user_messages.exchange`. The explanation shall
distinguish this from a security-level failure without disclosing users the
sender is not allowed to discover.

For an eligible role or organizational unit, the UI may show the current number
of eligible expanded users as a preview. The server's transaction-time expansion
and count remain authoritative because assignments and clearance may change
before send.

When **Action required** is selected, compose shall offer an optional action due
date using the sender's working timezone and explain that it is informational.
Clearing **Action required** clears the due date. A past local date is invalid.

The resource-link control shall use bounded authorized search. A visible
resource whose security level exceeds the selected message level shall be
disabled rather than silently omitted and shall show a localized explanation
that the message level must be at least the resource level. A resource the
sender is not permitted to discover must not be revealed as a disabled result.

If the sender lowers the message level after adding resources or recipients,
every newly invalid selection shall be visibly identified and the send action
shall remain blocked until the sender raises the message level or removes the
invalid selections. Equivalent stable validation reasons shall be returned when
the server rejects a stale or manually constructed request.

The server, not only the UI, shall enforce recipient, content, and field
validation.

### 6.5 Toast notification

When a new recipient copy has committed and the recipient has a connected
Wathiq client, the recipient shall receive a near-real-time toast. The toast
shall provide enough information to identify and open the message without
carrying the full rich-text body. Every currently connected tab and device for
that user shall receive the live event and show the toast.

The toast shall not be treated as proof that the user read the message. Toasts
may be repeated after reconnect or event redelivery; clients shall de-duplicate
them by recipient-copy ID within the current page lifetime.

On initial connection and after every reconnection, the client shall reconcile
with the server for messages newer than its last acknowledged mailbox cursor.
This catch-up is required even when the WebSocket reports a clean connection.
It ensures that a message committed while the client was offline is still
presented and cannot be lost merely because its live signal was missed.

Catch-up never produces one toast per missed message. If catch-up finds one or
more new recipient copies, the client shows at most one localized summary such
as **You have 7 new messages**, updates the unread indicator, and leaves the
individual messages in Inbox. Repeated reconciliation for the same mailbox
cursor must not repeat the summary. Live messages committed after catch-up
returns to normal per-message toast behavior.

The unread counter and inbox shall always be obtained from durable server state,
not calculated solely from toasts received by the current page.

### 6.6 Outbox

The Outbox route and API require `messaging.user_messages.exchange` and shall
list only envelopes sent by the authenticated human user. It
uses server-side pagination and defaults to newest `sent_at` first. It supports
bounded filtering by subject, sent-date range, priority, security level,
action-required state, late/outstanding action state, and recipient selector.

Opening an Outbox item shows the immutable sent message, its selector headers,
the concrete delivery result, requested read receipts, and per-recipient action
status. Current security and resource-link authorization still apply. The
Outbox does not imply that all recipients remain authorized to open the message
or its resources.

For an eligible ordinary user message, the Outbox detail provides **Forward**
and **Send follow-up** actions. Both open a new compose form linked to that
envelope and require the sender to choose and validate a new recipient list;
the original `To`/`Cc` list is not copied into the new draft. Forward uses
relationship kind `forward`; Send follow-up uses `follow_up`. Neither operation
embeds the earlier subject or body. The actions are hidden or disabled with a
clear reason for a test message, amendment notice, inaccessible or purged
message, inactive Outbox reference, inadequate clearance, or absent exchange
privilege.

Outbox shows the configured expiry date and warning state. It exposes **Delete**
only when the sender has a currently retained committed record capture
satisfying MSG-020. A **Recently deleted** view within Outbox lists the sender's
recoverable deleted references and provides Restore. Sender deletion never
deletes or hides a recipient's delivery.

### 6.7 Drafts

The Drafts route and API require `messaging.user_messages.exchange`. The page
lists only the authenticated user's unsent drafts, newest
updated first, using server-side pagination. It supports opening, editing,
sending, and explicitly discarding a draft. Each row shows last-updated time and
a non-sensitive validation summary such as **Ready to validate on send** or
**Needs attention**.

Drafts are not displayed in Inbox or Outbox and never contribute unread,
receipt, action, or Monitor delivery counts. This revision defines explicit
save and discard; it does not require automatic keystroke-by-keystroke saving.

### 6.8 Sent-message action status

For an action-required envelope, the sender's sent view shall show one status
per concrete recipient: Outstanding, Late, Completed, Completed late, or
Withdrawn. A
completion status links to the reply that recorded it. Aggregate wording may
summarize counts, but it must not conceal the per-recipient state or treat one
recipient's completion as completion for all recipients.

The original Outbox detail page contains an **Action status** panel showing the
original and current effective action state, original and effective due date,
per-recipient status, and chronological amendment history. A clearly labelled
**Amend action** button appears beside the current state/due date when the
authenticated user is the original sender, currently has
`messaging.user_messages.exchange`, retains the active Outbox reference and
clearance, the original was action-required, and the action has not been
withdrawn. On narrow layouts the same action may appear in that panel's
overflow menu; it must not be placed only in an unrelated generic message menu.

The Outbox list may show an amended indicator but does not execute an amendment
directly. The sender must open the message first. Selecting **Amend action**
opens a confirmation form showing the immutable original state, current
effective state/date, the permitted add/change/remove/withdraw choices, affected
recipient count, mandatory reason, notification consequence, and resulting
state preview. Server validation is authoritative. After commit, the panel
updates the timeline and derived recipient statuses without altering the
original message fields.

When a completion reply arrives, the sender receives the normal new-message
toast for that reply. The toast may additionally indicate **Action completed**
after the server confirms the sender may view both the reply and original
message; the transient event itself shall not carry protected message details.

### 6.9 Notification Administration

The Notification Administration page follows MSG-019 and uses bounded,
server-paginated producer search rather than loading a complete growing
catalogue. It clearly distinguishes feature-owned locked fields from editable
configuration, shows the active version and operational owner, validates
placeholders and audiences before save, requires a reason, and provides a
non-sending preview. It has deliberate loading, empty, validation-error,
concurrency-conflict, and save-failure states. Any tabular producer/version or
audience presentation uses Wathiq's standard table treatment rather than a raw
default NiceGUI table.

**Send test** opens a confirmation form showing the producer, exact
configuration version, explicit individual recipients, test values, and the
permanent TEST marking. The page also provides bounded, server-paginated test
history with initiator, configuration version, recipient count, time, and
outcome, but not protected message content in the list.

## 7. Database model

PostgreSQL is the authoritative store. UUID primary keys use PostgreSQL `uuid`
values generated by the application or an approved database UUID function.
They are globally unique and opaque to users.

### 7.0 Identifier policy

Messaging uses a deliberate hybrid identifier policy; it does not replace
Wathiq's general `BIGSERIAL` convention with UUIDs for every messaging table.
PostgreSQL sequences are safe with concurrent transactions and multiple API
instances, so horizontal scaling alone is not a reason to use UUIDs.

A UUID is used as the sole primary identifier when Wathiq intentionally exposes
and later reuses an object's ID outside the table that stores it. Examples are
an envelope, recipient delivery, draft, action amendment, capture operation, or
immutable notification-configuration version. An envelope or delivery ID may
appear in an API response, live event, reply/forward/follow-up relationship, or
capture provenance. A capture ID appears in its provenance PDF filename. A
configuration-version ID is returned to and submitted by the administration
UI.

A draft provides a concrete client example: the backend returns the new draft's
ID to WebUI, Flutter, or another client. That client retains the ID and sends it
back in later requests to retrieve, update, discard, restore, or send the same
draft. The UUID therefore provides one stable, globally unique identifier for
all of those operations. Returning an ID through an API does not itself require
a UUID—PostgreSQL `BIGSERIAL` could also identify the row—but UUID is chosen for
these externally referenced messaging objects to meet their global-identity
requirements, remain stable if data is moved or combined, and avoid exposing
adjacent sequence values. Knowledge of a UUID never grants access; every
operation must still enforce ownership and authorization.

Database-internal child or association rows whose own IDs are never returned to
clients, placed in live events or links, or written into record provenance do
not need UUIDs. They shall follow existing Wathiq conventions and use
`BIGSERIAL`, an existing entity's `BIGINT` identifier, a natural text key, or a
composite key as defined below. Examples include recipient-selector rows,
resource-link rows, localization rows, addressee mappings, and capture-component
mappings. Existing Wathiq user, role, organizational-unit, security-level,
aggregation, record, and digital-component identifiers remain unchanged.

This policy accepts the larger storage and index cost of a 16-byte UUID only
for objects that need the externally stable identity. It avoids adding both an
internal `BIGSERIAL` key and a UUID alias to the same object unless a later,
approved performance design demonstrates that the additional identifier and
mapping complexity are necessary. UUID generation shall use the repository's
approved implementation consistently; identifier format or predictability must
not be treated as a security control.

The required tables are:

| Table | Purpose |
| --- | --- |
| `message_envelopes` | Parent row for one immutable send and the fields common to every recipient |
| `message_envelope_localizations` | Immutable rendered system-message or action-amendment-notice subject/body variants by language |
| `message_recipient_selectors` | Immutable user, role, and organizational-unit choices made by the sender |
| `message_addressees` | Immutable expanded concrete-user `To` and `Cc` snapshots |
| `message_mailboxes` | Safe per-user sequence allocation for reconnect catch-up |
| `message_deliveries` | One independently readable inbox copy per recipient |
| `message_action_completions` | One immutable reply-based completion acknowledgment per recipient delivery |
| `message_action_amendments` | Append-only structured corrections to an original action requirement or due date |
| `message_resource_links` | Normalized Wathiq resource references embedded in the shared body |
| `message_drafts` | Private unsent compose state owned by one human user |
| `message_draft_recipient_selectors` | Unsaved-to-envelope user, role, and unit selections for a draft |
| `message_draft_resource_links` | Structured Wathiq resource references in a draft body |
| `message_record_captures` | Auditable link between one capture operation, its selected message, and resulting record |
| `message_record_capture_components` | Ordered mapping for captured-message PDFs and the final provenance PDF |
| `system_notification_producers` | Feature-registered system event and immutable safety contract |
| `system_notification_configuration_versions` | Immutable administrator-authored configuration versions for a registered producer |
| `system_notification_configuration_translations` | Per-language subject/body templates for one notification configuration version |
| `system_notification_configuration_audiences` | Static user, role, unit, or declared dynamic-resolver audience configuration for one version |

No table stores an active WebSocket, frontend-instance ID, or NiceGUI client
object. Those are short-lived process-local connection details.

### 7.1 `message_envelopes`

One row represents one immutable send operation.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key; globally unique envelope ID |
| `sender_user_id` | `bigint` | Nullable FK to `users(id)`; null only for a system message; deletion behavior must preserve message history |
| `sender_name` | `text` | Non-blank send-time snapshot; exactly `system` for a system message; nullable only after content purge |
| `sender_kind` | `text` | Required; `user` or `system` |
| `message_kind` | `text` | Required; `user_message`, `system_notification`, or `action_amendment_notice` |
| `action_amendment_id` | `uuid` | Nullable unique FK to `message_action_amendments(id)`; required only for an amendment notice |
| `system_producer_code` | `text` | Required only for a system message; stable registered backend producer identity |
| `system_configuration_version_id` | `uuid` | Required only for a system message; FK to the immutable configuration version used to render it |
| `source_event_type` | `text` | Required only for a system message; approved domain-event type |
| `source_event_id` | `text` | Required only for a system message; bounded stable domain-event identity |
| `triggered_by_user_id` | `bigint` | Nullable history-preserving FK to `users(id)`; records an authenticated actor whose domain action caused a system message, without making that user the sender |
| `is_test` | `boolean` | Required; defaults false and is immutable |
| `test_run_id` | `uuid` | Required and unique only when `is_test = true` |
| `test_initiated_by_user_id` | `bigint` | Required history-preserving FK to the administrator only when `is_test = true` |
| `subject` | `text` | Non-blank while retained; at most 255 Unicode characters after Unicode NFC normalization and trimming; nullable only after content purge |
| `priority` | `text` | `normal`, `high`, or `very_high` while retained; defaults to `normal`; nullable only after content purge |
| `body_rich_text` | `text` | Sanitized rich text while retained; at most 65,536 UTF-8 bytes after sanitization; nullable only after content purge |
| `security_level_id` | `bigint` | FK to `security_levels(id)` with `ON DELETE RESTRICT` while retained; defaults to the lowest configured level; nullable only after content purge |
| `action_required` | `boolean` | Required while retained; nullable only after content purge |
| `action_due_date` | `date` | Nullable informational local date; allowed only with `action_required = true` |
| `action_due_timezone` | `text` | Nullable validated IANA timezone snapshot; present exactly when a due date is present |
| `action_due_at` | `timestamptz` | Nullable exclusive late boundary; present exactly when a due date is present |
| `read_receipt_requested` | `boolean` | Required while retained; nullable only after content purge |
| `relationship_kind` | `text` | Nullable; `reply`, `forward`, or `follow_up` |
| `related_delivery_id` | `uuid` | Nullable FK to `message_deliveries(id)` for an Inbox-originated reply or forward |
| `related_envelope_id` | `uuid` | Nullable self-FK to `message_envelopes(id)` for an Outbox-originated forward or follow-up |
| `sent_at` | `timestamptz` | Required; assigned by the server/database |
| `expires_at` | `timestamptz` | Required; derived from `sent_at` and configured retention at send time |
| `sender_deleted_at` | `timestamptz` | Nullable; Outbox reference entered recovery, for a human sender only |
| `sender_purge_after` | `timestamptz` | Nullable; required with `sender_deleted_at` |
| `content_purged_at` | `timestamptz` | Nullable; set only after no active or recoverable Inbox/Outbox reference remains |
| `request_id` | `uuid` | Required idempotency key for the send request, unique within the sending principal/system producer |

Constraints shall enforce sender-kind, message-kind, amendment-link, and
system-provenance consistency. If `relationship_kind` is null, both related IDs
must be null. A `reply` requires only `related_delivery_id`; a `follow_up`
requires only `related_envelope_id`; and a `forward` requires exactly one of
the two. Relationship source and kind are immutable. The API shall reject
an over-limit subject or body before insertion and shall return a stable
validation reason. The body limit is measured after server-side sanitization so
the stored representation
is bounded; an implementation shall also impose a slightly larger bounded
request limit before sanitization to prevent oversized-input abuse.

For `sender_kind = system`, constraints shall require the configured baseline
security level, `read_receipt_requested = false`, `action_required = false`, and
all action due fields to be null.

An `action_amendment_notice` must have `sender_kind = user`, link exactly one
amendment, use the original envelope's sender, security level, expiry, and
concrete audience, inherit its priority, contain no resource links, and set
`read_receipt_requested = false` and
`action_required = false`. It cannot be a reply, forward, follow-up, or test
message.

Constraints shall permit `is_test = true` only for `sender_kind = system` with a
registered configuration version, test-run ID, and initiating administrator.
They require all test fields to be null for a production message. The test flag
and test provenance survive content purge in the minimal tombstone.

While `content_purged_at` is null, the ordinary required-content constraints
apply. When it is non-null, subject, sender-name snapshot, priority, body,
security level, action fields, and receipt flag must be null, while the minimal
identity, provenance, idempotency, sent/expiry time, and reference fields remain
immutable. Purging also removes the envelope's selector, addressee, and resource-
link child rows and clears recipient read state under MSG-020.

A constraint shall require all three action due fields to be null when
`action_required = false`, and shall require either all three to be null or all
three to be non-null when `action_required = true`. The server validates that
`action_due_at` is the start of the local date following `action_due_date` in
`action_due_timezone`, including daylight-saving transitions.

`sender_user_id` must not use cascading deletion because deleting a user must
not erase other users' messages. The stored sender name preserves attribution.

#### 7.1.1 `message_envelope_localizations`

This table is empty for an ordinary human-authored `user_message`. For a
`system_notification` or `action_amendment_notice`, it stores the immutable
rendered variants created in the send transaction:

| Column | Type | Rules |
| --- | --- | --- |
| `envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `language_tag` | `text` | Required normalized FK to the registered language |
| `subject` | `text` | Required rendered non-blank subject under the ordinary subject limit |
| `body_rich_text` | `text` | Required rendered and sanitized body under the ordinary body limit |
| `direction` | `text` | Required send-time language-direction snapshot; `ltr` or `rtl` |
| `rendered_at` | `timestamptz` | Required server-assigned send-transaction time |

The primary key is `(envelope_id, language_tag)`. Rows are immutable and are
purged with the other send-level message data under MSG-020. A constraint or
transactional validation requires the envelope's default `subject` and
`body_rich_text` to equal its system-default-language variant. A system
notification or action-amendment notice is valid only when the same transaction
inserts exactly one variant for every language enabled in the locked language-
registry snapshot; an ordinary user message must have none.

### 7.2 `message_recipient_selectors`

This table preserves what the sender selected before expansion without using a
polymorphic foreign key.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `recipient_type` | `text` | Required; `to` or `cc` |
| `selector_kind` | `text` | Required; `user`, `role`, or `org_unit` |
| `user_id` | `bigint` | Nullable FK to `users(id)` |
| `role_id` | `bigint` | Nullable FK to `roles(id)` |
| `org_unit_id` | `bigint` | Nullable FK to `org_units(id)` |
| `display_name` | `text` | Required non-blank send-time snapshot |
| `ordinal` | `integer` | Required non-negative display order within its recipient type |

A check constraint shall require exactly one of `user_id`, `role_id`, or
`org_unit_id` to be non-null and shall require it to agree with
`selector_kind`. Uniqueness constraints shall prevent the same selector from
appearing more than once in the same recipient type. Foreign-key deletion
behavior must preserve sent-message history and the immutable selector display
snapshot even if the referenced user, role, or organizational unit is later
deleted.

### 7.3 `message_addressees`

This table stores the immutable expanded concrete-user address snapshot once
per addressee.

| Column | Type | Rules |
| --- | --- | --- |
| `envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `user_id` | `bigint` | Required FK to the history-preserving user identity row; `ON DELETE RESTRICT` |
| `recipient_name` | `text` | Required non-blank name snapshot |
| `recipient_type` | `text` | Required; `to` or `cc` |
| `ordinal` | `integer` | Required non-negative display order within its recipient type |

The primary key is `(envelope_id, user_id)`. This guarantees that one user
cannot appear twice or in both recipient types. Unique ordering constraints per
envelope and recipient type shall prevent ambiguous order.

### 7.4 `message_mailboxes`

This table provides a gap-free, per-recipient ordering boundary for catch-up.

| Column | Type | Rules |
| --- | --- | --- |
| `user_id` | `bigint` | Primary key and FK to the history-preserving user identity row; `ON DELETE RESTRICT` |
| `last_sequence` | `bigint` | Required non-negative latest allocated mailbox sequence |

When a transaction creates a delivery, it locks the recipient's mailbox row,
increments `last_sequence`, and assigns that value to the delivery. For a send
to several users, mailbox rows are locked in ascending user-ID order to avoid
deadlocks. The mailbox increment and delivery commit together.

This serialization is per recipient, not global. It permits concurrent sends
to unrelated users while ensuring that a cursor `N` means every delivery for
that user with sequence `<= N` has committed. A timestamp, UUID, or ordinary
database sequence alone must not be used as this guarantee because allocation
order need not equal transaction commit order.

### 7.5 `message_deliveries`

This table is the fan-out and inbox table. Each row is one recipient's own copy.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key; globally unique recipient-copy/message ID |
| `envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `recipient_user_id` | `bigint` | Required FK to the history-preserving user identity row; `ON DELETE RESTRICT` |
| `recipient_type` | `text` | Required; `to` or `cc`; must agree with the address row |
| `mailbox_sequence` | `bigint` | Required positive per-recipient sequence allocated through `message_mailboxes` |
| `created_at` | `timestamptz` | Required; time the copy was committed |
| `language_tag_at_send` | `text` | Required normalized snapshot of the recipient's effective language used for the live toast |
| `read_at` | `timestamptz` | Nullable; immutable first-read time |
| `deleted_at` | `timestamptz` | Nullable; set by manual deletion or automatic expiry |
| `purge_after` | `timestamptz` | Nullable; required with `deleted_at` and derived from the configured recovery period |
| `deletion_reason` | `text` | Nullable; `user_deleted` or `retention_expired`, required with `deleted_at` |

There is exactly one delivery per `(envelope_id, recipient_user_id)`. A
composite foreign key including recipient type shall require the corresponding
address row and prevent an address/delivery mismatch.
`(recipient_user_id, mailbox_sequence)` is also unique.

Ordinary Inbox queries exclude deleted rows. Recently deleted message queries
include only the authenticated recipient's rows whose recovery period has not
ended. After recovery, a row may remain only as a non-readable reference
tombstone when required for mailbox cursor, relationship links, idempotency, or event-
history integrity; it must never make purged content retrievable.

Required indexes include:

- `(recipient_user_id, deleted_at, read_at, created_at DESC, id)` for inbox,
  Recently deleted, and unread work;
- `(recipient_user_id, mailbox_sequence)` for cursor-based catch-up;
- `(envelope_id, recipient_user_id)` for per-recipient send/read status.

The production DDL shall use keyset/cursor pagination indexes appropriate to
the final inbox query. Offset pagination shall not be the only large-mailbox
strategy.

### 7.6 `message_action_completions`

Each row is one recipient's immutable acknowledgment, made through a reply,
that their action is done.

| Column | Type | Rules |
| --- | --- | --- |
| `original_delivery_id` | `uuid` | Primary key; FK to the recipient's original `message_deliveries(id)` |
| `reply_envelope_id` | `uuid` | Required unique FK to the reply `message_envelopes(id)` |
| `completed_by_user_id` | `bigint` | Required FK to `users(id)`; must equal the original delivery owner at creation |
| `completed_at` | `timestamptz` | Required server-assigned completion instant |

Insertion validation shall enforce that the reply envelope's
`relationship_kind` is `reply` and `related_delivery_id` equals
`original_delivery_id`, the original envelope
requires action, and the authenticated completing user owns the original
delivery. The row and reply fan-out commit atomically. The row is immutable and
cannot be updated or deleted through ordinary messaging operations.

An index on `(reply_envelope_id)` is supplied by its uniqueness constraint. An
index on `(completed_by_user_id, completed_at DESC)` supports the recipient's
action-status queries. Sender status queries join through the original delivery
and its envelope.

#### 7.6.1 `message_action_amendments`

Each row is one immutable structured amendment to an original action-required
envelope.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key; globally unique amendment ID |
| `original_envelope_id` | `uuid` | Required FK to the original `message_envelopes(id)` |
| `sequence` | `integer` | Required positive sequence allocated under a lock on the original envelope |
| `amendment_kind` | `text` | Required; `due_date_added`, `due_date_changed`, `due_date_removed`, or `action_withdrawn` |
| `previous_action_required` | `boolean` | Required effective-state snapshot immediately before this amendment |
| `previous_due_date` | `date` | Nullable previous effective local due date |
| `previous_due_timezone` | `text` | Nullable previous validated IANA-timezone snapshot |
| `previous_due_at` | `timestamptz` | Nullable previous effective exclusive late boundary |
| `new_action_required` | `boolean` | Required effective state introduced by this amendment |
| `new_due_date` | `date` | Nullable new effective local due date |
| `new_due_timezone` | `text` | Nullable new validated IANA-timezone snapshot |
| `new_due_at` | `timestamptz` | Nullable new effective exclusive late boundary |
| `reason` | `text` | Required non-blank sender-authored reason; at most 2,000 Unicode characters after NFC normalization and trimming |
| `created_by_user_id` | `bigint` | Required history-preserving FK to the original sender |
| `created_at` | `timestamptz` | Required server-assigned commit time |
| `request_id` | `uuid` | Required amendment idempotency key, unique for the original sender |

`(original_envelope_id, sequence)` is unique. Constraints require each kind's
previous/new fields to form exactly the transition allowed by MSG-023, with due
triples either wholly null or wholly populated. The original envelope and its
latest amendment are locked while deriving the next state and sequence, so two
concurrent requests cannot create conflicting histories. Rows cannot be
updated or individually deleted through messaging operations.

Exactly one `action_amendment_notice` envelope references each committed
amendment through `message_envelopes.action_amendment_id`. The amendment and
notice are committed in the same transaction. The foreign-key arrangement may
be deferred within that transaction, but no committed amendment may exist
without its notice or vice versa.

When the original message's send-level content is finally purged under
MSG-020, its amendment reasons and due-state values are purged in the same
operation. Minimal amendment identity, sequence, kind, actor, time, and
idempotency provenance may remain as non-content tombstones needed for audit
and referential integrity.

### 7.7 `message_resource_links`

This table normalizes each Wathiq resource link embedded in the envelope body so
the server can validate it at send time and re-evaluate it without parsing rich
text on inbox-render paths.

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key |
| `envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `link_token` | `uuid` | Required opaque token referenced by the sanitized body; unique within the envelope |
| `ordinal` | `integer` | Required non-negative body order |
| `resource_kind` | `text` | Required controlled supported Wathiq resource kind |
| `target_id_snapshot` | `bigint` | Required immutable original target ID for diagnostics without granting access |
| `aggregation_id` | `bigint` | Nullable FK to `aggregations(id)` with `ON DELETE SET NULL` |
| `record_id` | `bigint` | Nullable FK to `records(id)` with `ON DELETE SET NULL` |
| `digital_component_id` | `bigint` | Nullable FK to `digital_components(id)` with `ON DELETE SET NULL` |
| `security_level_id_at_send` | `bigint` | Required FK to `security_levels(id)`; immutable validation/audit snapshot |

On insert, validation shall require exactly one target foreign key to be
non-null, to agree with `resource_kind`, and to equal `target_id_snapshot`. A
later target deletion sets the live foreign key to null while preserving the
link row as an unavailable historical reference. A digital component uses its
containing record's effective security level and authorization. Supporting
another Wathiq resource kind requires an explicit schema column, foreign key,
security-level resolution rule, and authorization rule; a generic unchecked
polymorphic target ID must not be introduced.

The current resource level and permission are authoritative when listing or
opening the message. `security_level_id_at_send` documents the successful
send-time check but is not an authorization cache. Required indexes support
lookup by `(envelope_id, ordinal)` and by each non-null target foreign key.

Ordinary sanitized external hyperlinks may remain in the rich-text body but do
not become Wathiq resource links. Internal aggregation, record, and component
URLs must use a normalized resource-link row.

### 7.8 Draft tables

`message_drafts` stores one private unsent compose document:

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key; stable draft identifier exposed through client APIs |
| `owner_user_id` | `bigint` | Required FK to `users(id)`; only this user may access the draft |
| `subject` | `text` | Nullable while saved; required for send; send-time limit applies |
| `priority` | `text` | Required; same controlled values as envelopes |
| `body_rich_text` | `text` | Nullable while saved; send-time sanitation and size limits apply |
| `security_level_id` | `bigint` | Required FK to `security_levels(id)`; defaults to the lowest configured level |
| `action_required` | `boolean` | Required |
| `action_due_date` | `date` | Nullable draft value subject to send-time validation |
| `action_due_timezone` | `text` | Nullable validated IANA working-timezone snapshot paired with a due date |
| `read_receipt_requested` | `boolean` | Required |
| `relationship_kind` | `text` | Nullable draft value; `reply`, `forward`, or `follow_up` |
| `related_delivery_id` | `uuid` | Nullable FK to `message_deliveries(id)` for an Inbox source |
| `related_envelope_id` | `uuid` | Nullable FK to `message_envelopes(id)` for an Outbox source |
| `version` | `bigint` | Required positive optimistic-concurrency version |
| `date_created` | `timestamptz` | Required |
| `date_updated` | `timestamptz` | Required |
| `expires_at` | `timestamptz` | Required; derived from the last update and configured active period |
| `deleted_at` | `timestamptz` | Nullable; set on expiry or explicit discard |
| `purge_after` | `timestamptz` | Nullable; required with `deleted_at` and derived from the configured recovery period |
| `deletion_reason` | `text` | Nullable; `expired` or `discarded`, required with `deleted_at` |

`message_draft_recipient_selectors` mirrors the selector kind, foreign-key,
recipient type, display snapshot, and ordering structure of
`message_recipient_selectors`, but belongs to a draft. It creates no concrete
addressee or delivery rows.

`message_draft_resource_links` mirrors the normalized target and body-token
structure of `message_resource_links`, but its validation status is advisory
until send. Current resource authorization and security are always rechecked.

Draft edits use optimistic concurrency. A successful draft send locks the
draft, validates its version and ownership, creates the complete envelope and
fan-out transaction, and deletes the draft rows only as part of the same
successful commit.

Ordinary Drafts queries exclude rows with `deleted_at`; Recently deleted drafts
include only the owner's unpurged deleted rows. Restoring clears the deletion
fields, advances the optimistic-concurrency version, and calculates a new
active expiry from the restoration time. Permanent purge removes child rows in
the same transaction.

### 7.9 Message-to-record capture tables

`message_record_captures` records one successful capture:

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key |
| `selected_envelope_id` | `uuid` | Required FK to `message_envelopes(id)` |
| `record_id` | `bigint` | Nullable current FK to `records(id)` with `ON DELETE SET NULL`; unique while present |
| `record_id_at_capture` | `bigint` | Required immutable record-ID snapshot used for provenance after governed record disposition |
| `captured_by_user_id` | `bigint` | Required FK to `users(id)` with history-preserving behavior |
| `captured_by_name` | `text` | Required immutable capturing-user display-name snapshot |
| `captured_at` | `timestamptz` | Required server-assigned instant |

`message_record_capture_components` records each generated PDF:

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `bigserial` | Primary key; internal capture-component mapping identifier |
| `capture_id` | `uuid` | Required FK to `message_record_captures(id)` |
| `component_kind` | `text` | Required; `message` or `provenance` |
| `envelope_id` | `uuid` | Nullable FK to the captured `message_envelopes(id)`; required only for a message component |
| `digital_component_id` | `bigint` | Nullable current FK to `digital_components(id)` with `ON DELETE SET NULL`; unique while present |
| `digital_component_id_at_capture` | `bigint` | Required immutable component-ID snapshot used for provenance after governed disposition |
| `component_order` | `integer` | Required positive order matching the committed component |
| `is_selected_message` | `boolean` | Required; true only for message component 1 |

Constraints require exactly one provenance component per capture, with null
`envelope_id`, `is_selected_message = false`, and the greatest component order.
A partial unique `(capture_id, envelope_id)` constraint for message components
prevents duplicate message PDFs. A unique `(capture_id, component_order)`
constraint preserves deterministic ordering. `record_id_at_capture` and
`digital_component_id_at_capture` remain uniquely associated with their
capture provenance even after governed deletion nulls the current foreign key.
Capture rows and the authoritative record and components are written in the
record-draft commit transaction, not when PDFs are merely staged.

### 7.10 System notification administration tables

`system_notification_producers` stores the feature-owned allowlist:

| Column | Type | Rules |
| --- | --- | --- |
| `producer_code` | `text` | Primary key; stable code registered by application feature code |
| `feature_code` | `text` | Required owning feature/module identifier |
| `event_type` | `text` | Required immutable backend event type |
| `required_for_business_commit` | `boolean` | Required immutable feature policy; true means the registered event and its durable notification must commit together |
| `contract_version` | `integer` | Required positive code-contract version |
| `contract_definition` | `jsonb` | Required code-owned, schema-validated declaration of placeholders, audience modes, and resource-link kinds; contains no executable expression |
| `active_configuration_version_id` | `uuid` | Nullable FK to an immutable version belonging to this producer |

Application startup or migration reconciliation may add or advance a producer's
feature-owned contract, but administrator requests cannot insert a producer or
alter its feature-owned fields.

`system_notification_configuration_versions` stores immutable administrator
configuration:

| Column | Type | Rules |
| --- | --- | --- |
| `id` | `uuid` | Primary key |
| `producer_code` | `text` | Required FK to `system_notification_producers` |
| `version` | `integer` | Required positive version unique within the producer |
| `enabled` | `boolean` | Required; must be true when the producer has `required_for_business_commit = true` |
| `subject_template` | `text` | Required bounded canonical English/default template using only declared placeholders |
| `body_template_rich_text` | `text` | Required bounded canonical English/default sanitized template using only declared placeholders |
| `priority` | `text` | Required; `normal`, `high`, or `very_high` |
| `audience_mode` | `text` | Required; `static` or an allowlisted dynamic resolver code |
| `resource_presentation` | `jsonb` | Required schema-validated, non-executable configuration restricted by the producer contract |
| `operational_owner` | `text` | Required non-blank team or owner label |
| `change_reason` | `text` | Required non-blank reason |
| `created_by_user_id` | `bigint` | Required history-preserving FK to the administrator |
| `created_at` | `timestamptz` | Required server-assigned time |

`system_notification_configuration_translations` stores one template pair per
configuration version and enabled language:

| Column | Type | Rules |
| --- | --- | --- |
| `configuration_version_id` | `uuid` | Required FK to the immutable configuration version |
| `language_tag` | `text` | Required normalized FK to the registered language |
| `subject_template` | `text` | Required non-blank bounded template |
| `body_template_rich_text` | `text` | Required non-blank bounded sanitized template |
| `review_status` | `text` | Required; `draft`, `reviewed`, or `published`; only `published` is activation-eligible |
| `reviewed_by_user_id` | `bigint` | Required history-preserving FK for an activation-eligible translation |
| `reviewed_at` | `timestamptz` | Required for an activation-eligible translation |

The primary key is `(configuration_version_id, language_tag)`. Exact named-
placeholder parity with the canonical template is required. The default-
language row must exactly equal the canonical columns; storing it in the child
table makes coverage and language iteration uniform.

`system_notification_configuration_audiences` stores the ordered static
audience selectors for a version using explicit nullable foreign keys for user,
role, and organizational-unit kinds, the same exactly-one-target constraint as
message selectors, and `to`/`cc` classification. It is empty for a dynamic
resolver configuration. Dynamic resolver codes come only from the producer
contract and are not stored as administrator-authored query text.

Activating a version updates the producer pointer and records its event-history
and Security Operations entry in one transaction. Versions referenced by sent
envelopes cannot be changed or deleted. Configuration APIs use optimistic
concurrency so two administrators cannot silently overwrite one another.

### 7.11 Why the model is separated

The envelope prevents one copy of a large rich-text body per recipient while
preserving one immutable send operation. A human message stores one authored
body; a system message stores one rendered body per enabled language rather
than per recipient. The selector table preserves exactly what the sender
placed in the `To` and `Cc` headers. The address table freezes the expanded
concrete users. The delivery table supplies the required globally unique copy
ID and isolates read state for each recipient. The resource-link table permits
bounded live authorization checks without duplicating or reparsing message
content. The completion table records the one permitted per-recipient action
acknowledgment without adding workflow state to the message envelope.

This is preferable to putting one `is_read` flag on a shared message row, which
cannot represent multiple recipients correctly.

## 8. Send transaction and idempotency

The server shall process a send as one database transaction:

1. authenticate the human sender, or authenticate and authorize the registered
   internal system producer; a human sender must currently have
   `messaging.user_messages.exchange`;
2. for a human sender, resolve current effective clearance and validate the
   selected message level against it; for a system producer, force the current
   lowest configured level without accepting a requested level;
3. validate and normalize the user, role, and organizational-unit selectors;
4. validate the reply, forward, or follow-up relationship, the sender's right
   to use its delivery or Outbox-envelope source, and the referenced message's
   security-level floor; when the reply marks an action
   done, also lock and validate the original recipient delivery and confirm no
   completion already exists;
5. for a human message, sanitize and validate the authored subject/body; for a
   system message, validate complete published template coverage and render and
   sanitize every enabled-language variant from the same typed context;
6. resolve every structured Wathiq resource link and verify that the resource
   exists, the sender may read it, and its current security level is not above
   the message level;
7. resolve all selectors to active, sufficiently cleared concrete users using
   one transaction snapshot; for a human message require each concrete user to
   have `messaging.user_messages.exchange`; apply `To` precedence and enforce
   post-expansion recipient limits;
8. reject any direct user below the required clearance and any role or
   organizational-unit selector having no eligible expanded user;
9. insert one envelope and, for a system message, all immutable rendered
   language variants;
10. insert all selector, expanded-address, and normalized resource-link
    snapshots;
11. lock recipient mailbox rows in stable order and allocate each recipient's
   next mailbox sequence;
12. insert one delivery copy per address with the recipient's effective-
    language snapshot;
13. when requested, insert the action-completion row linking the original
    recipient delivery to the new reply envelope;
14. issue one PostgreSQL `NOTIFY` per delivery on Wathiq's dedicated message
   notification channel, carrying only the delivery ID, recipient user ID, and
   mailbox sequence; and
15. commit once, causing PostgreSQL to release the notifications only after
    the message rows have committed.

No toast or event shall be emitted before the transaction commits.

The caller shall supply a stable idempotency key for each intended send. A
retry using the same authenticated principal and key returns the already
created result and must not create duplicate recipient copies. Reusing the key
with different content shall fail as a conflict.

For a system notification, its registered producer and domain-event identity
form this stable idempotency key. A retry of the causing business operation
does not invent a new notification key.

The send response shall identify the envelope and the recipient-copy IDs so the
result of fan-out is explicit and traceable.

An action amendment uses a separate atomic transaction:

1. authenticate the original human sender and verify current exchange
   privilege, active Outbox ownership, and clearance;
2. lock the original envelope and its latest amendment, derive the current
   effective state, and reject an informational, withdrawn, purged, expired,
   deleted, or otherwise inaccessible original;
3. validate the requested transition, reason, future boundary, and every
   fairness rule in MSG-023 against current completion rows;
4. allocate the next amendment sequence and insert the immutable amendment
   using the caller's idempotency key;
5. render and sanitize every enabled-language amendment-notice variant from
   server-owned catalogue templates; fixed labels are localized while the
   sender-authored reason is preserved verbatim;
6. create the linked amendment-notice envelope using the original sender,
   security level, expiry, concrete recipients, and `To`/`Cc` classifications;
7. allocate recipient mailbox sequences, create one delivery per original
   recipient, and issue the ordinary post-commit `NOTIFY` wake-up signals; and
8. commit the amendment, notice, variants, and deliveries together.

A retry with the same sender and amendment idempotency key returns the existing
result. Reuse with a different requested transition or reason fails as a
conflict. Failure before commit leaves neither an amendment nor a notice.

## 9. Frontend-neutral real-time architecture

### 9.1 Separation of responsibilities

The backend messaging service owns message storage, addressing, authorization,
read state, catch-up, PostgreSQL notification handling, and the real-time event
contract. It shall not depend on NiceGUI classes, page objects, Socket.IO client
IDs, or UI state.

Every frontend integrates through two backend contracts:

1. the authenticated REST API for sending, inbox queries, reading, receipts,
   and cursor-based catch-up; and
2. an authenticated real-time stream that emits small versioned events such as
   `message_available`.

The first public real-time transport shall be an authenticated WebSocket. The
same versioned event contract shall subsequently be made available over
server-sent events as the fallback transport. Clients prefer WebSocket and may
fall back to SSE when WebSocket establishment or continued operation is not
available. Authentication, authorization, cursor reconciliation, reconnect
behavior, and event meaning are identical across both transports. Because the
server only pushes availability hints, neither transport replaces ordinary
REST writes.

### 9.2 Portable live-event contract

A `message_available` event shall contain only safe routing and reconciliation
information, for example:

```json
{
  "schema_version": 1,
  "event_type": "message_available",
  "delivery_id": "e483330f-82e4-49d1-8ed0-513b1fdd84b2",
  "mailbox_cursor": 81724
}
```

It shall not contain the rich-text body or a recipient list. The authenticated
connection is bound server-side to its principal; a client cannot subscribe by
supplying another user's ID. On receipt, the client uses the REST API to fetch
authorized state and update its presentation.

Events are versioned independently of NiceGUI or Flutter. Unknown event types
or later schema versions shall not crash a client; the client shall fall back
to mailbox reconciliation.

### 9.3 Multiple API instances

All API instances point to the same authoritative PostgreSQL database. A send
accepted by API instance A commits the envelope, deliveries, mailbox sequences,
and `NOTIFY` calls in one transaction. PostgreSQL emits each notification only
after that transaction commits. API instance A does not attempt to locate
recipient connections itself.

Every API instance that hosts real-time gateway connections maintains a
dedicated PostgreSQL connection which executes `LISTEN` on Wathiq's message
notification channel. PostgreSQL broadcasts each notification to all currently
listening gateway instances. Each instance keeps only its own in-memory map from
authenticated user ID to connections. On a notification:

- an instance with one or more connections for the recipient pushes the event
  to those connections;
- an instance without such a connection ignores it; and
- no instance needs to know which load-balancer target owns the recipient.

Consequently, a sender connected through API A can reach a recipient connected
through API B, C, or any later instance.

```text
Sender
  -> API instance A
  -> PostgreSQL transaction
       envelope + addressees + per-user sequence + deliveries + NOTIFY
  -> PostgreSQL broadcasts after commit
       -> API gateway A -> connections owned by A
       -> API gateway B -> connections owned by B -> recipient
       -> API gateway C -> connections owned by C
  -> recipient fetches authorized message state from any API instance
```

### 9.4 PostgreSQL notification channel

PostgreSQL `LISTEN`/`NOTIFY` is the required internal broadcast wake-up
mechanism for this revision. Every real-time gateway instance maintains its own
`LISTEN` session, so PostgreSQL broadcasts the notification to all currently
listening instances. The notification carries only the delivery ID, recipient
user ID, and mailbox sequence; consumers read authoritative message state
through the service/database path.

This channel is needed because live connections are process-local. If API
instance A commits a message while the recipient's connection belongs to API
instance B, instance B otherwise has no immediate way to know about the commit
except repeated database polling. `NOTIFY` supplies that prompt without adding
another service.

`LISTEN`/`NOTIFY` is transient and has a listener-startup race. It shall never
replace the delivery tables or catch-up API. A gateway that starts or reconnects
first establishes its listener and then requires every client connection it
currently owns to reconcile from that client's durable mailbox cursor before
depending on new notifications. This closes both the listener-startup race and
a gap caused by a temporary database-listener disconnection while end-user
connections stayed open.

The listener shall use bounded reconnection backoff, expose its health, and
avoid holding an open transaction while waiting for notifications. The
notification channel is internal deployment infrastructure. It does not turn
messaging into an external user-delivery channel: users still receive messages
only inside authenticated Wathiq clients.

The listener connection shall be opened directly for the lifetime of the API
worker or gateway process and shall not be checked out from the ordinary
request database pool. A pooled connection cannot safely remain reserved for
`LISTEN`, and returning a listening session to the pool could leak subscription
state into unrelated requests. Each process therefore budgets one separate
listener connection, closes and recreates it on shutdown/reconnect, and includes
that connection in PostgreSQL `max_connections` capacity planning. Ordinary API
queries and send transactions continue to use the bounded request pool.

### 9.5 Multiple NiceGUI instances

A NiceGUI frontend is an adapter, not the messaging service. Each NiceGUI
instance may maintain authenticated subscriptions to the backend real-time API
for the users whose pages it currently hosts. When it receives
`message_available`, it uses supported NiceGUI APIs to show `ui.notify(...)`
through NiceGUI's existing Socket.IO/WebSocket connection.

This provides two separate hops:

```text
backend real-time API -> NiceGUI adapter -> NiceGUI browser connection
```

The first hop is the Wathiq frontend-neutral contract. The second is a NiceGUI
implementation detail. The NiceGUI instance does not need direct database
access for messaging and does not use NiceGUI's private Socket.IO internals as
a cross-service notification channel.

An alternative browser adapter may connect directly to the backend real-time
API when Wathiq's authentication and deployment topology support that choice.
Either form shall produce the same inbox and read behavior.

Existing load-balancer affinity remains necessary for NiceGUI's own live page
state. It is not used to route inter-user messages between instances.

### 9.6 Future Flutter or other clients

A Flutter client connects directly to the same authenticated REST API and
real-time stream. It maps `message_available` to a Flutter in-app presentation
and then fetches/reconciles the recipient copy through the REST API. No NiceGUI
protocol, Socket.IO event, or Python page object appears in the mobile contract.

This specification defines in-app foreground/reconnect behavior only. Mobile
operating-system push notifications while the application is suspended or
terminated would be an external delivery channel and require a separate
approved specification.

### 9.7 Reconnection and missed signals

When any client or frontend adapter connects or reconnects, it shall call a
bounded catch-up endpoint using its last durable mailbox cursor. The server
returns committed recipient copies after that cursor. The client updates its
unread indicator and, when new copies exist, displays only the single reconnect
summary defined in section 6.5 rather than individual missed-message toasts.

Therefore:

```text
PostgreSQL rows = durable messages
LISTEN/NOTIFY + real-time stream = fast availability hints
catch-up query = recovery from every missed hint
frontend adapter = presentation only
```

No correctness guarantee shall depend on one API instance, one frontend
instance, NiceGUI live page state, notification replay, or a client
acknowledging a toast.

### 9.8 Back-pressure and privacy

Connections, outbound event buffers, listener reconnect delays, and catch-up
pages shall be bounded. A slow client must not block an API event loop or cause
an unbounded per-connection queue. The gateway may disconnect a slow client,
which then recovers through catch-up.

The server shall re-check the authenticated user before returning message
content. The durable inbox remains available even when the PostgreSQL
notification listener, real-time gateway, or frontend adapter is unhealthy.

## 10. API responsibilities

Exact endpoint names may follow the repository's API conventions, but the API
shall provide these authenticated operations:

- send a human-authored message with an idempotency key only when the
  authenticated user has `messaging.user_messages.exchange`;
- validate user, role, and organizational-unit recipient selectors and return
  the committed expanded-recipient count;
- provide bounded recipient-selector search without returning complete
  tenant-grown collections;
- provide bounded, authorization-filtered Wathiq resource search and validate
  structured links against the selected message level;
- list selectable message security levels at or below the current sender's
  effective clearance;
- return stable, localized reason codes when a recipient selector is
  ineligible for the selected message security level;
- list the current user's inbox using server-side cursor pagination and
  filters, returning system messages only when exchange privilege is absent;
- get one current-user recipient copy;
- mark one current-user copy read, idempotently;
- send a reply that may atomically acknowledge completion of the authenticated
  recipient's own action-required delivery;
- start and send a forward from either an authorized Inbox delivery or an
  active, authorized Outbox envelope owned by the authenticated sender;
- start and send a follow-up linked to an active, authorized Outbox envelope
  owned by the authenticated sender;
- append one permitted action amendment to an original sent envelope, using an
  idempotency key, and return the resulting amendment and notice identities;
- return the ordered action-amendment history and effective action state as
  part of authorized original-message and Outbox-detail responses;
- obtain a bounded catch-up page after a mailbox cursor;
- return non-disclosing message and resource-link availability state for the
  bounded current inbox page using batched authorization evaluation;
- list and get the authenticated human user's Outbox with server-side
  pagination and authorized per-recipient status;
- create, list, get, update with optimistic concurrency, send, and discard only
  the authenticated user's own drafts;
- list the authenticated user's active and recently deleted Inbox and Outbox
  references, return expiry state, perform capture-gated or explicitly capture-
  free early deletion under MSG-020, and restore during the recovery period;
- initialize a message-capture record draft only for an eligible human-authored
  message whose complete relationship chain is also eligible, stage the ordered
  generated PDFs, and commit capture provenance with the ordinary record
  transaction;
- list registered notification producers and preview, version, activate, enable,
  or disable only their permitted configuration fields for callers with
  `messaging.notifications.administer`;
- create, review, publish, validate, and preview notification templates per
  enabled language with exact placeholder parity;
- send and list bounded, explicitly marked notification tests under MSG-019 for
  callers with `messaging.notifications.administer`;
- return sanitized messaging operational health only to callers with
  `messaging.monitor`;
- establish an authenticated, versioned real-time event stream;
- list the current sender's sent envelopes and per-recipient receipt status;
- return per-recipient Outstanding, Late, Completed, Completed late, or
  Withdrawn action status for the original sender and the applicable recipient;
- get a sent envelope created by the current sender; and
- resolve/open reply, forward, and follow-up links only when the requester owns
  the linking delivery or sent the linking envelope, and may read the referenced
  message under the applicable relationship grant, current clearance,
  retention, and resource rules.

There is no generic message-edit endpoint. The API shall reject reply,
forward, completion, and independent record-capture operations whose target is
an amendment notice. Opening such a notice resolves its linked original only
after ordinary ownership, exchange-privilege, clearance, retention, and
content-availability checks.

For a system envelope, Inbox, message view, toast preparation, and capture APIs
select the immutable language variant under MSG-021. They must not perform
runtime machine translation or return all variants unless an explicitly
authorized administration operation needs them.

System producers shall use the internal application-service boundary in
MSG-018, not a public request field that lets an ordinary user claim to be
`system`. The
ordinary client send endpoint always creates a user message attributed to its
authenticated human sender. Domain APIs may cause only their registered
backend notification events; they must not expose a generic client-controlled
system-send proxy.

Specifically, production feature code uses the internal Python
`emit_system_notification` application-service contract in MSG-018. It is not
mounted as a REST route. The only HTTP operation that directly initiates a
system envelope is the privilege-gated, immutable test-send route in MSG-019,
which cannot create a production envelope.

Authorization shall be derived from the authenticated principal. Inbox
requests must not accept another user's ID as a way to select mailbox
ownership.

## 11. Reliability and operations

### 11.1 Delivery guarantee

Once the send transaction commits, each recipient copy is durable and
queryable even if every real-time connection is disconnected. PostgreSQL
notifications are transient wake-up signals and can be missed during a listener
disconnect. Duplicate UI signals are also possible after reconciliation, so
consumers must be idempotent. Catch-up is the required recovery path. The
system does not claim exactly-once toast or banner display.

### 11.2 Failure behavior

- A database failure before commit returns failure and creates no partial send.
- A PostgreSQL listener or notification-routing failure after commit does not
  roll back or lose the message.
- A WebSocket, database-listener, or gateway failure does not change inbox or
  read state.
- An API or frontend restart may lose live connections or page objects, but
  reconnection catch-up restores mailbox state from PostgreSQL.
- A failed read-state request remains unread until the server commits it; the
  UI shall reconcile instead of assuming success.

### 11.3 Monitoring

Operational health shall report, without exposing message content:

- PostgreSQL notification count emitted by the send path;
- notification count received by each gateway instance;
- listener connection and reconnect count by instance;
- time of each listener's last received notification;
- active real-time connections by instance, without user-identifying labels;
- slow-client disconnect count;
- catch-up request failures;
- active listener health;
- atomic system-notification failure count and processing latency by producer
  code, without subject, body, recipient, or resource content;
- separate test-send count, failure count, rate-limit rejection count, and
  processing latency by producer code;
- messages approaching retention expiry, active/recoverable references, purge
  candidates, content purged, cleanup failures, and oldest unprocessed eligible
  purge, without message or recipient content.

Logs shall include request/correlation IDs, envelope ID, delivery ID, and safe
status metadata. They shall not include rich-text bodies or protected linked
resource data.

### 11.4 Retention and user deletion

Sent-message expiry, per-user deletion, recovery, content purge, and record
preservation follow MSG-020. Draft lifecycle follows MSG-016. The messaging
subsystem has no separate legal-hold mechanism: information requiring governed
retention must be saved as a record, after which the record copy is governed by
the existing record rules. Record disposition never deletes a still-retained
source message, and message expiry never deletes the captured record.

Permanent deletion of a user shall not cascade to envelopes, addressee
snapshots, deliveries, receipts, or messages that user sent to other people.
Historical sender and recipient names and identifiers needed to understand the
communication remain in immutable snapshots. Foreign-key handling must preserve
the message history while preventing a deleted account from authenticating or
receiving new messages. Inactive and suspended users likewise remain visible in
historical message snapshots but are not selectable for new sends.

If the current user-deletion workflow would physically remove a referenced
`users` row, it shall instead retain a minimal non-authenticating identity
tombstone for referential integrity after removing credentials, assignments,
active profile state, and other data not required by an approved historical
contract. The message snapshots—not the tombstone's mutable profile—remain the
source for historical display. Messaging foreign keys use deletion restriction
and never cascade into message history.

### 11.5 Deployment-configurable limits

The following limits are environment variables with validated startup defaults:

| Environment variable | Default | Meaning |
| --- | ---: | --- |
| `MESSAGING_MAX_SELECTORS_PER_SEND` | `100` | Combined `To` and `Cc` user, role, and organizational-unit selectors |
| `MESSAGING_MAX_RECIPIENTS_PER_SEND` | `2000` | Distinct concrete recipients after expansion |
| `MESSAGING_MAX_RESOURCE_LINKS` | `50` | Structured Wathiq resource links in one message |
| `MESSAGING_DRAFT_ACTIVE_DAYS` | `180` | Inactivity period before a draft expires |
| `MESSAGING_DRAFT_WARNING_DAYS` | `30` | Warning interval before draft expiry |
| `MESSAGING_DRAFT_RECOVERY_DAYS` | `30` | Restore period after expiry or discard |
| `MESSAGING_CAPTURE_MAX_LINKED_MESSAGES` | `100` | Earlier linked messages allowed in one record capture |
| `MESSAGING_CAPTURE_MAX_PDF_BYTES` | `52428800` | Combined generated-PDF limit of 50 MiB |
| `MESSAGING_RETENTION_DAYS` | `1095` | Sent-message retention period of three years |
| `MESSAGING_RETENTION_WARNING_DAYS` | `90` | Advance warning before automatic expiry |
| `MESSAGING_DELETION_RECOVERY_DAYS` | `30` | Recovery period before permanent mailbox-reference purge |
| `MESSAGING_CLEANUP_INTERVAL_SECONDS` | `3600` | Interval between retention/draft cleanup runs |
| `MESSAGING_CLEANUP_BATCH_SIZE` | `500` | Maximum candidate rows claimed by one cleanup batch |
| `MESSAGING_TEST_MAX_RECIPIENTS` | `10` | Explicit individual recipients allowed for one test send |
| `MESSAGING_TEST_SENDS_PER_HOUR` | `20` | Test sends allowed per initiating administrator in a rolling hour |
| `MESSAGING_TEST_RETENTION_DAYS` | `30` | Retention period for unmistakably marked test messages |

Missing variables use these defaults. Non-integer, zero, negative, internally
inconsistent, or administratively unsafe values shall fail application startup
with a clear configuration error rather than silently changing behavior.
Every API and worker instance in one deployment must use identical effective
values. Limits relevant to compose or capture are returned by an authenticated
capabilities endpoint; clients do not read environment variables directly.
Changing a value requires restarting the affected instances. An increase is a
capacity and abuse-risk change and requires performance verification rather
than being treated as an unrestricted administrator preference. Retention and
recovery values are snapshotted into new rows; changing an environment value
does not silently shorten or lengthen already stored expiry or purge dates.
Applying a retention change retrospectively requires a separate deliberate,
audited migration or administration operation.

## 12. Security requirements

- Every operation requires authentication, including live connection
  registration and reconnection catch-up.
- Inbox, Outbox, and Drafts derive ownership exclusively from the authenticated
  principal; no request parameter may select another user's mailbox or draft
  owner.
- The Monitor route and API require `messaging.monitor`; that privilege grants
  sanitized operations data only and never grants message-content access.
- Notification Administration requires
  `messaging.notifications.administer`. Server-side contract validation prevents
  that privilege from creating producer events, sending messages, expanding
  feature-declared capabilities, or accessing ordinary mailboxes. Its only
  direct-send authority is the bounded, immutable, individually addressed test
  operation in MSG-019.
- The server derives mailbox ownership and sender identity from the
  authenticated principal.
- Human-message send, reply, forward, follow-up, Compose, Drafts, and Outbox operations
  require `messaging.user_messages.exchange`. Human recipient resolution also
  requires the concrete recipient to have that privilege. System-message
  delivery and system-only Inbox access do not.
- Without exchange privilege, object-level authorization hides existing human-
  authored Inbox, Outbox, and Draft content without deleting it. UUID knowledge
  or a stale live event cannot bypass that restriction.
- No client credential or request body may select `system` as sender. System
  sender identity requires a registered in-process/service producer and its
  allowlisted event contract; a client-triggered domain action retains its
  authenticated actor in provenance.
- System producer contracts grant no general ability to choose arbitrary
  recipients, templates, resource links, security levels, or messaging fields.
- Recipient discovery follows existing user visibility and lifecycle rules.
- The server derives sender and recipient clearance from current effective
  roles; a request-supplied clearance number is never trusted.
- Secured-message content, headers, and links require a fresh clearance check
  on every retrieval, including retrieval through a reply, forward, or
  follow-up.
- A live event and restricted inbox placeholder must not disclose protected
  message metadata before the clearance check succeeds.
- Read, reply, forward, follow-up, sent-status, and receipt operations enforce
  object-level authorization server-side. An Outbox relationship source must be
  owned by the authenticated original sender and have an active Outbox
  reference; a client-supplied envelope UUID alone grants nothing.
- Delete and restore operations apply only to the authenticated user's own Inbox
  or Outbox reference. Early deletion requires that user's committed record-
  capture provenance and cannot be satisfied by another user's capture, except
  that a recipient may delete their own system-notification or amendment-notice
  delivery without record capture because those kinds cannot be captured.
- Action completion can be created only through an authenticated reply by the
  owner of the original delivery; request-supplied user, completion time, late
  state, or ownership values are never trusted.
- Rich text is sanitized server-side and rendered safely.
- Resource links run target authorization on every open.
- Resource links are permitted only when the target's current security level is
  at or below the message level, both when composed and in the send transaction.
- Authorization changes after delivery must fail closed: a restricted message
  exposes only its generic placeholder, and an unavailable resource link
  exposes no protected target metadata.
- UUIDs are identifiers, not authorization secrets.
- Message bodies and recipient lists are sensitive application data and shall
  not be placed in ordinary logs, metrics, or live-event channels.
- Rate and size controls shall bound send operations, recipient counts,
  catch-up pages, and inbox pages. Subject and body limits are fixed in section
  7.1; configurable send and capture limits are fixed by section 11.5.
- Message-to-record capture independently enforces current message access and
  the existing `record.create`, destination `aggregation.add_record`, clearance,
  and record-creation rules. A generated PDF is not an authorization bypass.

## 13. Internationalization and accessibility

All user-visible messaging UI text shall follow the Wathiq internationalization
specification and catalogue workflow. User-authored subjects and bodies are not
catalogue strings and shall be displayed as authored.

System-generated subjects and bodies follow MSG-021's versioned notification-
template and rendered-variant model. Action-amendment notices use the governed
UI-catalogue templates and immutable rendered variants specified there. They are not generated dynamically by the
UI catalogue and are never machine-translated at delivery or read time. The
administration page's labels, validation explanations, review states, TEST
indicator, and fallback notices remain ordinary UI catalogue strings.

The compose, inbox, message view, priority indicators, action-required state,
toasts, and unread counter shall work in LTR and RTL. Priority and read state
must not be communicated by color alone. Toasts and unread changes shall be
available to assistive technology without unexpectedly moving keyboard focus.

## 14. Verification and acceptance criteria

### Functional

- **AC-MSG-001:** A system producer can send a message displayed with sender
  `system`.
- **AC-MSG-001A:** No public client request can claim the `system` sender or
  directly supply arbitrary system-message content or recipients.
- **AC-MSG-001B:** An authorized client domain action may cause only the
  registered backend notification associated with its successfully committed
  business outcome; rejected and no-op actions create no success notification.
- **AC-MSG-001C:** When an enabled producer attempts a direct system
  notification, the domain transaction and durable notification commit
  together, or neither commits.
- **AC-MSG-001D:** Retrying the idempotent causing business operation after an
  atomic failure creates at most one domain change and one system envelope.
- **AC-MSG-001E:** A system producer cannot exceed its registered event,
  template, audience, field, resource-link, or baseline-security contract.
- **AC-MSG-002:** A user can send to multiple `To` and `Cc` recipients.
- **AC-MSG-003:** A send to N recipients creates N distinct globally unique
  delivery IDs and one shared immutable envelope.
- **AC-MSG-003A:** A role selector expands only to active users for whom the
  selected role is currently effective.
- **AC-MSG-003B:** An organizational-unit selector expands only to active users
  with an effective role directly owned by that active unit and does not
  implicitly include descendant units.
- **AC-MSG-003C:** Overlapping user, role, and organizational-unit selectors
  create one delivery per concrete user, with `To` taking precedence over
  `Cc`.
- **AC-MSG-003D:** Membership changes after commit do not change the selector,
  expanded-address, delivery, or receipt rows of the sent message.
- **AC-MSG-004:** Reading one copy does not change another copy.
- **AC-MSG-005:** A reply links to the earlier delivery ID without copying its
  body.
- **AC-MSG-006:** An Inbox forward links to the earlier delivery ID and an
  Outbox forward links to the earlier envelope ID, without copying its body.
- **AC-MSG-007:** Requested read receipts expose first-read status to the
  sender; unrequested receipts do not.
- **AC-MSG-008:** Resource links re-run target authorization and do not grant
  access.
- **AC-MSG-008A:** A resource above the selected message security level is
  disabled with an explanation and is rejected by the server if submitted.
- **AC-MSG-008B:** Lowering the compose message level identifies every now-
  invalid resource and recipient and blocks send until corrected.
- **AC-MSG-008C:** Raising a resource above the message level or revoking a
  recipient's target permission after delivery makes that link non-clickable
  and non-disclosing without hiding otherwise readable message content.
- **AC-MSG-008D:** A recipient who loses message clearance retains a correctly
  ordered restricted placeholder that reveals none of the protected message
  metadata; sufficient restored clearance restores the ordinary row.
- **AC-MSG-008E:** Inbox availability evaluation is bounded to the current page
  and performs no per-message or per-link network/database round trip.
- **AC-MSG-009:** Unsafe rich text cannot execute in another user's client.
- **AC-MSG-009A:** A subject longer than 255 Unicode characters after NFC
  normalization and trimming is rejected with a stable validation error.
- **AC-MSG-009B:** A sanitized rich-text body larger than 65,536 UTF-8 bytes is
  rejected with a stable validation error, and oversized unsanitized requests
  are bounded before sanitization.
- **AC-MSG-010:** Repeating a send with the same idempotency key creates no
  duplicate envelope or delivery.
- **AC-MSG-010A:** Every message has a non-null security level. A user sender
  defaults to the lowest configured level and may select a level at or below
  their greatest current effective-role level, but cannot select a higher one.
- **AC-MSG-010AA:** A system producer always creates the message at the lowest
  configured security level and cannot submit or cause a higher level.
- **AC-MSG-010B:** A secured message cannot include or expand to a user whose
  greatest current effective-role level is below the message level.
- **AC-MSG-010C:** Role and organizational-unit selectors with zero cleared
  users are disabled with the applicable explanation and are rejected by the
  server if submitted directly.
- **AC-MSG-010D:** An eligible group selector delivers only to its cleared
  expanded users, while overlap still produces one copy per concrete user.
- **AC-MSG-010E:** Losing sufficient clearance after delivery prevents content
  retrieval without deleting the delivery; restored clearance restores access.
- **AC-MSG-010F:** A reply, forward, or follow-up cannot lower the security
  level below its referenced message, and its recipients can open the complete
  linked message only while they have sufficient current clearance.
- **AC-MSG-010G:** An action-required message may have a non-past local due date;
  a non-action message cannot retain due fields, and all viewers use the same
  stored `action_due_at` boundary.
- **AC-MSG-010H:** Replying to an incomplete action-required delivery prompts
  with an unchecked completion control; checking it atomically creates the
  reply and exactly one completion acknowledgment owned by that recipient.
- **AC-MSG-010I:** A user cannot complete another recipient's action, complete
  through a non-reply message, or create a second completion for the same
  delivery.
- **AC-MSG-010J:** Before the due boundary an incomplete delivery is
  Outstanding; after it the sender and that recipient both see Late without a
  stored late boolean.
- **AC-MSG-010K:** A completion before/on the boundary displays Completed; a
  completion after it displays Completed late, and neither state completes
  another recipient's delivery.
- **AC-MSG-010L:** The original sender receives the durable reply and live toast
  and can open the reply from the corresponding per-recipient completion status.
- **AC-MSG-010M:** The Messages drawer category appears immediately below
  Records Management with Inbox always present; Outbox and Drafts gated by
  `messaging.user_messages.exchange`; and independently privilege-gated Monitor
  and Notification Administration in the specified order.
- **AC-MSG-010N:** A human user's Outbox shows each envelope they sent once,
  without duplicating content per recipient, and exposes only authorized
  recipient receipt/action status.
- **AC-MSG-010O:** A draft is private to its owner, creates no delivery or live
  event, uses optimistic concurrency, and converts atomically into exactly one
  sent envelope.
- **AC-MSG-010P:** The Monitor page/API requires `messaging.monitor`, exposes no
  message or recipient content, and does not become accessible through
  `audit.view` alone.
- **AC-MSG-010Q:** An authorized sender or recipient can initialize an ordinary
  record draft only from an eligible human-authored message; unauthorized or
  ineligible message kinds and unauthorized destination access fail without
  staged authoritative content.
- **AC-MSG-010R:** Message capture sets the record's initial title, originated
  date, and security level as specified, produces the selected message as PDF
  component 1, and produces each unique linked earlier message as a subsequent
  PDF ordered by sent time and ID, followed by exactly one provenance PDF as
  the final digital component.
- **AC-MSG-010S:** Capture is atomic at record commit, preserves structured
  resource links without granting resource access, stores matching structured
  and human-readable provenance, and rejects inaccessible linked messages,
  provenance mismatches, or corrupt reference cycles.

### Reliability and real time

- **AC-MSG-011:** A connected recipient receives a near-real-time toast without
  repeated mailbox polling.
- **AC-MSG-012:** Disconnecting a client during send and reconnecting later
  still reveals the committed message through catch-up.
- **AC-MSG-013:** Restarting any API instance, PostgreSQL listener, or frontend
  instance after commit does not lose the message.
- **AC-MSG-014:** Interrupting and restoring a gateway's PostgreSQL `LISTEN`
  connection causes its still-connected clients to reconcile without message
  loss.
- **AC-MSG-014A:** Each gateway process uses one dedicated direct PostgreSQL
  listener connection outside the request pool; listener failure or prolonged
  lifetime cannot exhaust or contaminate pooled request connections.
- **AC-MSG-015:** Duplicate live events do not create duplicate database rows
  or incorrect unread counts.
- **AC-MSG-016:** A failed fan-out creates either all recipient copies or none.
- **AC-MSG-017:** With multiple API and NiceGUI instances, a send accepted by
  one API instance notifies a recipient connected through every other eligible
  instance, without shared in-process connection state.
- **AC-MSG-018:** Starting a gateway during concurrent sends and interrupting
  its database notification subscription does not create a permanent
  notification gap;
  cursor catch-up finds every committed delivery.
- **AC-MSG-019:** The same versioned live event can be consumed by a non-NiceGUI
  test client without importing or emulating NiceGUI or Socket.IO internals.

### Security, scale, and UI

- **AC-MSG-020:** A user cannot read or mark another user's recipient copy.
- **AC-MSG-021:** A user cannot impersonate `system` or another sender.
- **AC-MSG-022:** Inbox, sent items, catch-up, and recipient lookup remain
  bounded and server-paginated with a large test dataset.
- **AC-MSG-023:** Slow or disconnected real-time clients do not create
  unbounded gateway memory growth or delay durable sends.
- **AC-MSG-024:** Toast, inbox, compose, and message view are verified in both
  LTR and RTL in a live browser.
- **AC-MSG-025:** Maintained-language catalogue coverage and required artifact
  checks pass for every new user-visible UI string.
- **AC-MSG-026:** Direct search and group expansion never select an inactive or
  suspended user, and a human sender never receives their own message through a
  direct or expanded selector.
- **AC-MSG-027:** Exceeding the configured selector, concrete-recipient, or
  structured-resource-link limit rejects the complete send without truncation;
  every instance reports and enforces the same effective configuration.
- **AC-MSG-028:** A system message cannot request a read receipt, require an
  action, carry an action due date, or create an action acknowledgment.
- **AC-MSG-029:** Every connected tab and device receives a live toast, while a
  reconnect with any number of missed messages produces at most one summary and
  never one toast per missed message.
- **AC-MSG-030:** WebSocket and subsequent SSE fallback clients consume the same
  authenticated event contract and recover through the same mailbox cursor.
- **AC-MSG-031:** A draft expires after configured inactivity, remains visible
  only to its owner during the recovery interval, restores without trusting
  stale authorization, and is permanently purged after that interval.
- **AC-MSG-032:** Message-to-record capture rejects more than the configured
  linked-message or combined-PDF limit without committing a partial record.
- **AC-MSG-033:** Every captured message and provenance component validates as
  PDF/A-2u and PDF/UA-1, preserves applicable LTR/RTL reading order and Unicode
  text, and uses its specified non-sensitive filename.
- **AC-MSG-034:** Deleting, suspending, or deactivating a user neither deletes
  historical messages nor removes immutable sender, selector, or recipient
  snapshots; the account cannot receive new messages.
- **AC-MSG-035:** Before retention expiry, a user can delete only their own
  Inbox or Outbox reference and only after their committed capture of that
  eligible human message as a record; another user's mailbox remains unchanged.
  System-notification and amendment-notice deliveries are capture-free early-
  deletion exceptions because they are ineligible for record capture.
- **AC-MSG-036:** Automatic expiry applies after the configured retention period
  whether or not each user captured the message, provides the configured warning
  and recovery periods, and never deletes a captured record.
- **AC-MSG-037:** Send-level message data remains available while any active or
  recoverable reference exists and is purged atomically only after none remains;
  relationship links then show the non-disclosing expired/deleted placeholder.
- **AC-MSG-038:** Only `messaging.notifications.administer` can change a
  registered producer's configuration, and it cannot create events, triggers,
  executable expressions, undeclared placeholders, or direct system sends.
- **AC-MSG-039:** A system notification uses exactly one immutable active
  configuration version; a later administration change does not modify its
  content, audience snapshot, or provenance.
- **AC-MSG-040:** Notification configuration changes require a reason, use
  optimistic concurrency, and create event-history and Security Operations
  entries without protected event data.
- **AC-MSG-041:** A privileged test send traverses the canonical durable send
  and real-time path, permits only bounded explicit active individual
  recipients, and cannot invoke a configured or dynamic production audience.
- **AC-MSG-042:** Test envelopes, toasts, Inbox rows, message views, and
  administration history derive an unmistakable accessible TEST label from the
  immutable `is_test` field; editing subject or placeholder data cannot remove
  it.
- **AC-MSG-043:** Test messages cannot request receipts or actions, be replied
  to, forwarded, followed up, or captured as records; they are separately metered,
  rate-limited, audited, and purged after the configured test retention period.
- **AC-MSG-044:** There is no production system-send REST route. An approved
  feature explicitly calls the internal Python application service with its
  open transaction, registered producer code, stable event ID, typed context,
  and actor provenance only.
- **AC-MSG-045:** The internal service rejects caller-supplied content,
  recipients, security level, sender, or undeclared context; it alone loads the
  locked configuration, resolves the approved audience, renders content, and
  invokes canonical fan-out.
- **AC-MSG-046:** Startup readiness detects missing, duplicate, unknown, or
  incompatible producer definitions. When
  `required_for_business_commit = true`, the producer cannot be disabled and a
  durable-notification creation failure rolls back the same domain transaction;
  when false, administrators may disable it and the business operation may then
  commit without a notification.
- **AC-MSG-047:** Activating a system-notification configuration requires one
  published, non-blank, placeholder-compatible template for every enabled
  language; adding a language fails release readiness until coverage exists.
- **AC-MSG-048:** One system send stores one immutable rendered variant per
  enabled language, not per recipient; toast uses the delivery's send-time
  language and later reads use the viewer's current language with deterministic
  fallback and no runtime machine translation.
- **AC-MSG-049:** User-authored subject/body content is never automatically
  translated, while surrounding UI remains localized through the ordinary
  catalogue.
- **AC-MSG-050:** Without `messaging.user_messages.exchange`, a person sees and
  counts only system messages in Inbox and cannot access Compose, Outbox,
  Drafts, send, reply, forward, or follow-up through UI or API.
- **AC-MSG-051:** A human-authored direct or expanded audience excludes users
  without exchange privilege, while a registered system audience may include
  them subject to all system-message rules.
- **AC-MSG-052:** Revoking exchange privilege hides rather than deletes prior
  human Inbox, Outbox, and Draft data; restoring it restores currently retained
  and otherwise authorized data.
- **AC-MSG-053:** An action amendment never updates the original envelope; it
  appends the next structured sequence row, and only add/change/remove due date
  or irreversible withdrawal is accepted for an originally action-required
  message.
- **AC-MSG-054:** An informational message cannot become action-required, a
  withdrawn action cannot be reactivated, and no amendment changes content,
  priority, security, recipients, resources, receipt settings, references, or
  completion acknowledgments.
- **AC-MSG-055:** Adding or changing a deadline requires a future boundary and
  cannot make an incomplete recipient immediately/retroactively Late or change
  Completed to Completed late; extending or removing a corrected deadline
  removes the obsolete late characterization.
- **AC-MSG-056:** The amendment, all enabled-language notice variants, the
  specialized notice envelope, original-audience deliveries, mailbox sequences,
  and wake-up notifications commit atomically and idempotently, or none do.
- **AC-MSG-057:** Every original recipient receives one amendment notice with
  their original `To`/`Cc` classification, original security level and expiry;
  the notice cannot be replied to, forwarded, followed up, completed, tested,
  or captured independently and opens the authorized original message.
- **AC-MSG-058:** Only the original sender with current exchange privilege,
  active Outbox ownership, and adequate clearance may amend, using the Outbox
  detail's Action status panel and mandatory reason form; there is no generic
  sent-message edit operation.
- **AC-MSG-059:** Concurrent amendments serialize into an unambiguous sequence,
  and retrying one amendment key creates neither a duplicate amendment nor
  duplicate recipient notices.
- **AC-MSG-060:** Original-message and Outbox views derive the same effective
  action state from ordered history; completion replies always target the
  original delivery, and withdrawal affects only incomplete recipients.
- **AC-MSG-061:** Capturing an original message includes the amendment history
  and effective state existing at capture time without a separate notice PDF;
  a later amendment never rewrites a previously committed record.
- **AC-MSG-062:** Amendment-notice fixed text is rendered for every enabled
  language at commit while its user-authored reason remains verbatim, and its
  localized UI strings pass the ordinary maintained-language catalogue checks.
- **AC-MSG-063:** An eligible Outbox detail offers Forward and Send follow-up;
  each creates a new immutable envelope linked by `related_envelope_id` and
  never embeds or copies the earlier subject or body.
- **AC-MSG-064:** Starting an Outbox forward or follow-up does not inherit the
  earlier recipients; the sender must choose a new `To`/`Cc` audience that
  passes all current recipient, clearance, and resource validations.
- **AC-MSG-065:** A reply uses only an Inbox delivery source, a follow-up uses
  only an owned active Outbox-envelope source, and a forward uses exactly one
  of those source types; malformed, foreign, deleted, restricted, test, or
  amendment-notice sources are rejected server-side.
- **AC-MSG-066:** A recipient of an Outbox-originated forward or follow-up can
  open the linked earlier message only through their own linking delivery and
  while current clearance, retention, and resource authorization permit it;
  knowing either UUID alone grants no access.
- **AC-MSG-067:** Message-to-record capture accepts only
  `message_kind = user_message`; it rejects a production or test system
  notification, an action-amendment notice, or a relationship chain containing
  either kind without staging or committing a partial record.
- **AC-MSG-068:** In each frontend, every messaging user, role, organizational-
  unit, and security-level selector is that frontend's established corresponding
  component configured for the messaging context, not a messaging-specific copy
  or fork. WebUI and Flutter are verified independently against their own
  component systems; no cross-framework UI-component sharing is required, and
  server-side messaging validation remains authoritative.
- **AC-MSG-069:** Schema verification confirms that externally referenced
  messaging domain objects use their specified UUID identities, internal child
  and association rows retain the specified `BIGSERIAL`, existing `BIGINT`,
  text, or composite keys, and no duplicate UUID alias is added without a
  separately approved performance design.

Database-backed verification shall use a new uniquely named disposable
PostgreSQL database for each run, initialize it from the required canonical
schema or migration path, point the complete test process only at that
database, and drop it after the run whether tests pass or fail.

## 15. Comparison with email and chat messaging

This section is explanatory rather than a source of additional functional
requirements. Wathiq messaging is a governed internal communication channel;
it is not intended to reproduce every capability of email or conversational
chat.

| Consideration | Wathiq messaging | Email | Chat messaging |
| --- | --- | --- | --- |
| Primary purpose | Governed internal notifications and durable person-to-person messages connected to Wathiq work | Universal asynchronous correspondence within and outside an organization | Rapid, conversational collaboration |
| Reach | Active Wathiq users; external delivery belongs to the separate email extension | Nearly universal across organizations and platforms | Usually members or guests of the same chat service or workspace |
| Identity | Authenticated Wathiq identity with immutable sender and recipient snapshots | Address-based identity whose assurance depends on mail-domain and authentication controls | Service/workspace identity, often strong within one tenant |
| Authorization after delivery | Message clearance and resource authorization are checked again whenever content or a linked resource is opened | A delivered copy is normally outside the sender application's continuing control | Varies by product; copied, exported, or downloaded content may escape later access changes |
| Security classification | Mandatory message security level enforced against senders, recipients, groups, and linked resources | Classification may be expressed through labels or gateway policy but is not universally enforced end to end | Often workspace-policy driven, with capabilities varying by service |
| Delivery durability | PostgreSQL is authoritative; live events are hints and reconnect catch-up recovers missed events | Store-and-forward delivery is mature but crosses independently administered servers | Usually durable within the service, although retention may be channel- or workspace-specific |
| Immediacy | Near real time for connected clients, without repeated polling | Asynchronous; push speed depends on mail servers and clients | Typically the strongest option for immediate conversation, presence, and rapid exchanges |
| Conversation model | Individual immutable envelopes linked by reply, forward, or follow-up relationships | Mature reply, forwarding, and thread conventions, with inconsistent behavior between clients | Channels, group threads, direct messages, reactions, presence, and typing indicators are common |
| Changes after sending | Original messages are immutable; narrowly defined action amendments preserve correction history | Recall and replacement are unreliable across systems; recipients usually retain the original | Many products permit editing or deletion, sometimes with limited history visibility |
| Actions and receipts | Governed read receipts, informational due dates, per-recipient completion acknowledgments, and fairness-preserving amendments | Delivery/read receipts are inconsistent and may be rejected or disabled | Read indicators and lightweight tasks vary by product and are often less formal |
| Wathiq resources | Structured links preserve identity and re-run Wathiq authorization on every open | Links or attachments can be copied externally and may become stale or overexposed | Links can be convenient but are generally not part of the target system's governed message model |
| Attachments | Core subsystem intentionally has no arbitrary file attachments; Wathiq resources remain controlled links | Strong support for attachments, although copies become difficult to govern | Strong support for files and media, subject to the chat service's controls |
| Records Management | A message chain and provenance can become a governed Wathiq record with archival PDFs | Emails can be captured, but reliable classification and preservation commonly require a separate integration | Chat capture is often difficult because relevant context is distributed across channels, edits, reactions, and threads |
| System notifications | A business change and its required durable notification can commit atomically in the same database transaction | Delivery requires an external mail system and cannot normally share the business transaction | Usually requires an external chat API and service availability |
| Offline and external access | Requires an authorized Wathiq client and eventual connection to Wathiq | Excellent offline-client support and external reach | Depends on the chat client and service; often good on mobile devices |
| Portability | Frontend-neutral Wathiq APIs support NiceGUI, Flutter, and future clients, but the protocol is application-specific | Open, widely interoperable standards and a broad client ecosystem | Commonly proprietary APIs and service-specific clients |

### 15.1 Advantages of Wathiq messaging

Compared with ordinary email or chat, Wathiq messaging provides:

- one authoritative authenticated identity and permission model;
- mandatory security classification enforced at selection, send, list, and
  open time;
- continuing authorization checks for linked Wathiq resources instead of
  distributing uncontrolled resource copies;
- immutable messages, recipient snapshots, amendment history, and capture
  provenance suitable for later audit;
- atomic system notifications tied to successful backend business changes;
- independent delivery, read, and action status for every concrete recipient;
- direct conversion into a governed Wathiq record using accessible archival
  PDFs; and
- durable delivery without requiring an external mail or chat provider.

These characteristics make it particularly suitable for internal notices and
communications whose meaning depends on Wathiq permissions, security levels,
resources, business events, or records-management obligations.

### 15.2 Disadvantages and deliberate limitations

Compared with email, Wathiq messaging:

- does not reach a person who lacks an active Wathiq account in the core
  subsystem;
- does not provide universal addressing, federation, or access through ordinary
  mail clients;
- cannot provide an out-of-band alert when a user is not using a Wathiq client;
- does not support arbitrary attachments; and
- requires Wathiq to operate and monitor the database, APIs, live gateways,
  clients, retention jobs, and PDF-capture path.

Compared with chat, Wathiq messaging:

- is less suitable for rapid back-and-forth conversation;
- deliberately omits rooms, group conversations, presence, typing indicators,
  reactions, calls, and informal media sharing;
- makes corrections more formal because a sent envelope is immutable; and
- may feel heavier when the participants need temporary collaboration rather
  than a durable, attributable communication.

Near-real-time delivery also depends on a connected client. A disconnected
user receives the message durably on their next connection but receives no
external notification from the core subsystem. PostgreSQL `LISTEN`/`NOTIFY`
and cursor catch-up keep the initial operational design simple, but a future
deployment with exceptionally large fan-out or connection volume may need a
dedicated event-distribution service without changing PostgreSQL's role as the
authoritative message store.

### 15.3 Appropriate channel selection

Wathiq messaging should be preferred for governed internal notifications,
security-sensitive communication, messages linked to Wathiq resources,
action-required correspondence, and communication that may need to become a
Wathiq record.

Email remains more appropriate when the recipient is outside Wathiq, universal
interoperability is required, or the recipient needs delivery through an
ordinary mail client. Such delivery belongs to the separately specified
external-email extension and carries different security risks and controls.

Chat remains more appropriate for informal, high-frequency team discussion,
presence-aware coordination, and collaborative conversation that does not need
each contribution to function as an individually governed message. Important
decisions or evidence arising in chat may still need deliberate capture into
Wathiq through a separately governed process.

The channels are therefore complementary. Wathiq messaging should not be
presented as a universal replacement for either email or chat.

## 16. Phased implementation and verification plan

Implementation shall use the following five phases. The phases follow the
architecture's dependency order and create independently testable boundaries;
they are not permission to expose incomplete behavior. A phase is complete only
when its assigned requirements have implementation and verification evidence.

```text
Durable kernel -> Human messaging -> Real-time distribution
                                      |
                                      v
                            System notifications
                                      |
                                      v
                    Records and production hardening
```

### 16.1 Phase 1 — Durable messaging kernel

This phase establishes the PostgreSQL and backend foundation used by every
sender and frontend.

It shall implement:

- the complete canonical schema and corresponding upgrade migration, including
  the hybrid identifier policy in section 7.0;
- the canonical transactional envelope and fan-out service;
- immutable envelopes, selectors, expanded addressees, deliveries, mailbox
  sequences, resource links, drafts, completions, and amendments;
- recipient expansion, deduplication, `To` precedence, eligibility, clearance,
  security-level, resource-link, and message-size validation;
- rich-text sanitization, idempotency, snapshotting, stable mailbox ordering,
  and complete transactional rollback; and
- bounded frontend-neutral APIs for recipient/resource lookup, send, Inbox,
  Outbox, message retrieval, read state, and cursor catch-up.

The validation gate shall initialize a new disposable database from
`database/schema.sql`, separately upgrade a disposable database through the
migration, compare the resulting structures, and test concurrency, mailbox
ordering, idempotency, fan-out rollback, selector expansion, authorization,
sanitization, resource security, and bounded pagination. Every database-backed
run shall use and subsequently drop a uniquely named disposable database.

The exit condition is that a human message can be committed, fanned out exactly
once per eligible recipient, retrieved after process restart, and reconciled by
cursor without relying on WebSocket, NiceGUI, or other process memory.

### 16.2 Phase 2 — Complete human messaging

This phase builds the human-facing workflows on the durable kernel. It shall
implement the Messages navigation, Compose, Inbox, Outbox, Drafts, privilege
enforcement, read receipts, reply, Inbox and Outbox forwarding, Outbox follow-
up, structured resource links, priorities, security levels, action-required
messages, due dates, completion replies, immutable action amendments, and
amendment notices.

Each frontend shall reuse its own established user, role, organizational-unit,
and security-level selectors under MSG-005A. The UI shall include deliberate
loading, empty, restricted, validation, concurrency-conflict, and failure
states. It shall not use unbounded tenant collection requests.

The validation gate shall cover object-level API authorization, drafts and
optimistic concurrency, all relationship kinds, security floors, independent
recipient state, receipts, action status, due boundaries, completion,
amendment fairness, withdrawal, amendment concurrency, and idempotency. WebUI
shall be verified in a live browser in both LTR and RTL, including shared-
selector regression checks, repeated navigation, background-task abandonment,
and freshness after mutation. Translation catalogue coverage, ordering,
placeholder, provenance, and hash checks shall pass.

The exit condition is that every human workflow assigned to this phase behaves
correctly through the frontend and remains correct after refresh or process
restart. This is a validation milestone, not authorization for production
release: Phase 3 must supply live delivery and reconnect behavior, and Phase 5
must complete the human message's records and retention lifecycle.

### 16.3 Phase 3 — Real-time and multi-instance distribution

This phase adds low-latency presentation without moving correctness out of
PostgreSQL. It shall implement post-commit `NOTIFY`, one dedicated direct
listener connection outside each gateway's request pool, the versioned
frontend-neutral event contract, authenticated WebSocket delivery, subsequent
SSE support using the same contract, delivery to every connected tab/device,
cursor reconciliation, reconnect-summary behavior, and bounded slow-client
handling. NiceGUI shall adapt this contract rather than become the durable
messaging transport.

The validation environment shall contain multiple API/gateway and frontend
instances using the same PostgreSQL database, with clients attached through
different instances. Tests shall verify cross-instance delivery, all-tab/device
notification, no pre-commit event, no event after rollback, duplicate-event
idempotence, listener interruption, startup-race recovery, API/frontend
restart, bounded queues, slow-client isolation, and equivalent WebSocket/SSE
catch-up without NiceGUI-specific protocol assumptions.

The exit condition is that human messaging meets both durable and near-real-
time requirements across multiple instances, including recovery after every
connection gap.

### 16.4 Phase 4 — System notifications and administration

This phase shall implement the code-owned `SystemNotificationDefinition`
registry, database reconciliation and readiness checks, the internal Python
notification service, `required_for_business_commit`, immutable configuration
versions and translations, Notification Administration, reviewed/published
templates for every enabled language, controlled test sends, and system-only
Inbox access for users without person-to-person exchange privilege. There shall
be no production system-send REST endpoint, and system notifications shall
remain ineligible for record capture.

The validation gate shall verify registry consistency, required-producer
readiness failure, optional disablement, atomic business-change/notification
commit, rollback on enabled-notification failure, lowest security level, the
prohibition on receipts and actions, rejection of undeclared context or
audiences, complete published language coverage, immutable historic variants,
test marking and limits, and system-only Inbox behavior without exchange
privilege.

The exit condition is that approved backend features can emit localized,
durable system notifications without granting clients or administrators
arbitrary system-message authority.

### 16.5 Phase 5 — Records, retention, monitoring, and production hardening

This phase shall implement human-message-only record capture, deterministic
message PDFs, the final provenance PDF, embedded or subset-embedded Changa,
PDF/A-2u and PDF/UA-1 validation, atomic record/component/provenance commit,
expiry warnings, capture-gated and capture-free deletion rules, Recently
deleted restoration, final content purge, tombstones, draft cleanup, bounded
multi-instance cleanup, the privilege-gated Monitor page/API, operational
metrics, and alerts.

The validation gate shall use independent PDF conformance tooling and visual
inspection of English and Arabic output. It shall verify embedded fonts,
Unicode extraction, tags, reading order, links, filenames, provenance agreement,
rollback at every capture boundary, record independence after message expiry,
non-rewriting of earlier captures after amendments, retention/recovery
boundaries, concurrent cleanup, configured capacity limits, and the complete
requirement-to-test traceability matrix.

The exit condition is that the subsystem satisfies its records-management,
retention, accessibility, security, scale, monitoring, and operational
requirements in addition to its messaging behavior.

### 16.6 Controls applying to every phase

Every phase shall:

- maintain requirement-to-implementation-to-test traceability and remain
  incomplete while an assigned requirement lacks evidence;
- use disposable databases for database-backed tests;
- keep `database/schema.sql` self-contained and repeat upgrade DDL in the
  migration without `psql` meta-commands;
- preserve frontend-neutral backend contracts and authoritative server-side
  authorization;
- reuse each frontend's established selector and table patterns;
- keep growing collections server-paginated or bounded by remote search;
- treat real-time events only as hints to durable state; and
- keep unfinished later-phase behavior inaccessible rather than presenting it
  as complete.

## 17. Resolved design decisions

The former implementation decisions are resolved normatively in this revision:

- section 11.5 defines configurable selector, recipient, resource-link, draft,
  linked-message, and generated-PDF limits;
- section 7.0 defines a hybrid identifier policy: UUIDs are limited to
  externally referenced messaging domain objects, while internal rows retain
  Wathiq's established `BIGSERIAL`, `BIGINT`, text, or composite-key
  conventions;
- MSG-004 and MSG-005 exclude self-addressing and inactive or suspended users;
- MSG-005A requires each frontend's messaging user, role, organizational-unit,
  and security-level controls to reuse and, where necessary, generically extend
  the corresponding selectors already established in that frontend rather than
  creating messaging-specific implementations;
- MSG-020 and sections 11.4–11.5 define three-year sent-message retention,
  capture-gated early deletion, warning and recovery periods, bounded purge,
  record independence, and preservation of required history after user
  deletion;
- section 6.5 sends live toasts to every connected tab/device and collapses all
  reconnect discoveries into at most one summary;
- MSG-018 prohibits system-message read receipts and action-required state;
- section 9.1 makes WebSocket the first transport and SSE the subsequent
  fallback using the same frontend-neutral event contract;
- MSG-016 defines draft expiry, recovery, restoration, and purge;
- MSG-017 permits only human-authored message chains to be captured, using
  bounded PDF/A-2u and PDF/UA-1 output, the specified safe filename convention,
  and a matching human-readable provenance PDF as the final digital component;
- features register immutable system-producer safety contracts, while
  privileged administrators manage versioned templates, audiences, priority,
  enablement, resource presentation, and operational ownership through
  Notification Administration, including bounded and unmistakably marked
  end-to-end test sends; and
- `system_notification_producers.required_for_business_commit` states whether
  a producer may be disabled and whether its registered event is forbidden from
  committing without durable notification creation; it does not express
  priority, acknowledgment, action, reading, or live-delivery semantics;
- system templates require published coverage for every enabled language and
  sends store immutable rendered language variants under MSG-021;
- `messaging.user_messages.exchange` controls person-to-person sending,
  receiving, Compose, Outbox, Drafts, replies, forwards, and follow-ups without
  restricting
  system-message Inbox delivery;
- MSG-023 preserves the immutable original while permitting only append-only,
  fairness-constrained due-date correction or action withdrawal, with an
  atomic specialized notice to the original audience;
- MSG-007 and MSG-008 permit Outbox forwarding and explicitly named follow-ups
  through an immutable envelope relationship without copying content or
  recipients; and
- system notification envelopes are created atomically with their causing
  business changes. This revision has no notification-intent queue, retry
  worker, manual intent retry, or intent-retention policy.

## 18. Architecture conclusion

NiceGUI is suitable for Wathiq's current near-real-time presentation. Its
established Socket.IO/WebSocket connection lets a NiceGUI adapter update a
connected page and show a toast without repeated mailbox polling. NiceGUI is
not, however, the messaging transport or the durable inter-user message queue.

The reliable and scalable design is frontend-neutral and PostgreSQL-based.
PostgreSQL atomically stores envelopes, mailbox sequences, recipient copies,
and read state. The same transaction issues `NOTIFY`, which PostgreSQL releases
after commit to every listening API gateway instance. Each gateway pushes the
availability hint to the authenticated connections it owns. NiceGUI, Flutter,
and future clients adapt the same versioned event contract to their own in-app
presentation and reconcile from the REST API after every connection gap.

This lets API and frontend instances scale horizontally without shared process
memory, sticky routing between users, or a dependency on a particular UI
framework. Correctness remains anchored in the database and catch-up API.

## 19. Technical references

- [NiceGUI project architecture](https://github.com/zauberzeug/nicegui#architecture)
  documents its FastAPI, Vue/Quasar, Socket.IO, WebSocket, and server-to-client
  update architecture.
- [NiceGUI page documentation](https://nicegui.io/documentation/page) explains
  that page execution can await the established client WebSocket connection.
- [FastAPI WebSocket documentation](https://fastapi.tiangolo.com/advanced/websockets/)
  documents a frontend-neutral backend WebSocket endpoint and JSON/text event
  exchange.
- [PostgreSQL `LISTEN`](https://www.postgresql.org/docs/current/sql-listen.html)
  documents broadcast to every currently listening session and the required
  initial state-reconciliation step that closes the listener-startup race.
- Wathiq's existing [deployment guidance](../docs/deployment.md#nicegui-instances)
  defines instance affinity, WebSocket upgrade, and shared-storage constraints
  for this repository.
