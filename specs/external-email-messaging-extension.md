# External Email Messaging Extension — Exploratory Companion Specification

**Status:** Exploratory proposal  
**Project:** ERMS / Wathiq  
**Prepared:** 1 October 2026  
**Revision:** 0.1

## 1. Relationship to the core specification

This document is a companion to
[Notifications and In-App Messaging](notifications-and-messaging.md). It
explores external email recipients, SMTP delivery, controlled external resource
access, revocation, inbound reply proxying, and security monitoring.

It does not change the core subsystem's in-app-only contract unless this
extension is separately approved and enabled. Core PostgreSQL envelopes,
internal recipient deliveries, security levels, drafts, Outbox, record capture,
and authorization rules remain authoritative.

## 2. Goals and boundaries

When the extension is enabled, a human sender may include one or more validated
external email addresses in `To` or `Cc`. The same send may contain internal
Wathiq selectors and external addresses.

External delivery requires configured SMTP submission. Receiving external
replies through generated reply addresses additionally requires an inbound
mail service or SMTP receiver; an outbound SMTP server alone is insufficient.

This extension does not promise that Wathiq can recall an email, revoke an
attachment already delivered, prevent a recipient from forwarding an email, or
prevent screenshots or capture of content rendered for viewing.

## 3. Proposed privileges

Two new global privileges are recommended:

| Privilege | Purpose |
| --- | --- |
| `messaging.external.send` | Address and send Wathiq messages to validated external email addresses |
| `messaging.external.resource_share` | Create attachment or controlled-link releases of Wathiq resources for external recipients |

`messaging.external.resource_share` depends on `messaging.external.send`. It
does not replace current resource authorization. The sender must still be
authorized to view the linked aggregation or record and, for digital-component
content, must have the applicable resource permission and
`record.component.share`. Original-file attachment also requires
`record.component.download` because it releases downloadable bytes.

Neither privilege is granted to ordinary profiles by default. The initial
proposal grants both only to `ALL_PRIVS`; an administrator may explicitly add
them to a purpose-specific profile after organizational approval. Granting them
to `SYS_ADMIN` by default requires a separate decision because administrative
authority should not silently confer external-release authority.

## 4. External recipients

An external recipient selector contains a normalized valid email address and a
display name when supplied. Validation shall reject control characters,
multiple-address injection, invalid syntax, local-only domains, and addresses
exceeding supported length limits. Address comparison and deduplication follow
the application's approved email-normalization rules; Wathiq must not invent
provider-specific transformations such as removing dots.

If an address belongs to an active Wathiq person account, the UI shall identify
the internal account and require the sender to choose the internal user rather
than bypassing in-app clearance through external delivery, unless a later
approved exception explicitly permits both.

External recipients have no Wathiq effective roles or clearance. Sending to
them is an explicit release outside the ordinary recipient-clearance model and
therefore requires the privileges and security controls in this extension.

Each external recipient receives a separately rendered email and a separate
external-delivery row. Other recipients' email addresses shall not be exposed
through SMTP envelope headers merely because they shared a Wathiq send.

## 5. Compose behavior

External email entry is available only with `messaging.external.send`. Resource
release controls appear only when at least one external email recipient is
present.

For each Wathiq resource link, the sender chooses one approved external mode:

- **Do not include externally:** omit the resource from the external rendering
  while retaining it for authorized internal recipients.
- **Controlled view link:** issue a revocable, expiring, view-count-limited
  external preview capability.
- **Email attachment:** extract and attach an authorized snapshot to each
  external email. This mode is irrevocable after SMTP acceptance.

The form shall display the external-recipient count, every externally released
resource, release mode, expiration, view limit, current resource security
level, and whether the release will create a monitored security operation.

If the message or any externally released resource has a security level above
Wathiq's lowest configured level, the UI shall show a prominent warning before
confirmation. It shall identify the affected resources the sender is permitted
to see, explain that users without Wathiq clearance will receive access, require
an explicit confirmation and non-blank reason, and state whether access is
revocable or irrevocable.

Changing recipients, message level, resource selection, release mode,
expiration, or view count revalidates the complete external-release plan. The
server repeats all checks in the final send transaction.

## 6. Controlled external view links

### 6.1 Configuration

A controlled link shall have values chosen within administrator-configured
bounds:

- expiration after a positive number of days, or an explicit expiry instant;
- maximum successful views, when limited;
- recipient email address;
- resource and permitted preview representation; and
- optional recipient-verification requirement.

The initial recommendation is to require email verification for every
controlled link and to require it unconditionally for resources above the
lowest security level. Verification uses a short-lived one-time code sent only
to the intended external address. The share URL itself remains an opaque
high-entropy capability and must not contain a database ID, email address, or
resource identifier.

Only a hash of the capability token is stored. Tokens and verification codes
must never appear in application logs, event history, analytics, referrers, or
URLs loaded from third-party resources.

### 6.2 View-only meaning

The external page may present a bounded server-generated preview without an
original-file download, print, or export control. It shall send restrictive
cache, framing, content-security, and referrer headers and may watermark the
preview with the external address and access time.

“View only” means Wathiq does not provide the original file or a download
operation. It cannot technically prevent screenshots, photography, browser
capture, or reconstruction of information already delivered to a device. The
confirmation UI and policy documentation must state this limitation.

### 6.3 Validation on every access

Every access attempt re-evaluates, atomically where applicable:

1. token validity and revocation;
2. expiry;
3. recipient verification;
4. remaining successful-view count;
5. resource existence and preview availability;
6. the original sender's current active status, effective role authorization,
   clearance, ACL access, and applicable component permission;
7. the resource's current lifecycle and security level; and
8. any current external-sharing policy restriction.

The link fails closed if the original sender's authorization has been revoked
or become ineffective after email delivery. It also fails if the resource's
security level or policy changes so the approved release is no longer valid.

A successful view consumes one view only after the server has authorized and
begun returning the preview. Concurrent attempts shall lock or atomically
increment the counter so the configured maximum cannot be exceeded.

Denied and expired pages show useful generic explanations such as **This link
has expired**, **This link was revoked**, **The permitted number of views has
been used**, or **This resource is no longer available**. They must not reveal
protected resource metadata, authorization structure, the sender's roles, or
whether an undisclosed resource exists.

### 6.4 Revocation

The original sender may open the Outbox message and revoke any controlled link
at any time. Revocation is immediate, permanent for that issued capability, and
idempotent. It does not retract an attachment or information already viewed.

An authorized security administrator may need emergency revocation; whether
`messaging.external.resource_share`, `audit.view`, or a separate emergency
privilege should permit this is an approval decision in section 13.

## 7. Email attachments

An attachment is generated from the authorized resource representation at send
time, scanned and size-limited, and queued with the external email. Once the
SMTP server accepts it, Wathiq cannot revoke it, validate later authorization,
limit views, or prevent redistribution.

For that reason, the recommended initial release is controlled links only.
Attachment delivery should remain disabled until explicit policy approval
defines permitted resource types, formats, maximum total size, malware
scanning, encryption, security-level ceiling, and retention of generated
staging files.

If attachments are approved, above-baseline resources require the same warning,
reason, explicit confirmation, event-history record, and Security Operations
flag as controlled links, with stronger wording that the release is
irrevocable.

## 8. Durable SMTP delivery

The in-app send transaction stores the envelope, internal deliveries, external
recipient snapshots, security-event metadata, and one durable outbound email
job per external recipient. It does not wait for the SMTP network call.

A PostgreSQL-backed worker claims due jobs with leases and `SKIP LOCKED`, renders
the recipient-specific MIME message, submits it to the configured SMTP server,
and records attempts and terminal status. Temporary failures retry with bounded
backoff; permanent failures and exhausted retries are shown in the sender's
Outbox. Idempotency prevents a retried Wathiq send from creating duplicate jobs,
although SMTP's protocol boundary cannot provide a universal exactly-once
delivery guarantee.

SMTP credentials are deployment secrets. TLS and certificate verification are
required. Sender addresses, bounce handling, message-size limits, rate limits,
and retention of SMTP diagnostics require explicit configuration.

## 9. Reply-to proxy into Wathiq

Each externally delivered email may use a random, non-guessable reply alias at
a Wathiq-controlled mail domain. The alias maps to the original envelope and
original human sender without exposing an internal user ID.

Inbound processing requires a configured receiving service. It validates the
alias, applies mail-size and rate limits, performs malware and content checks,
prevents auto-reply loops, sanitizes supported body content, and creates a
lowest-security-level in-app reply delivered to the original sender. The
displayed external sender is the validated envelope/header address according to
the approved inbound-mail policy.

The inbound reply links to the original envelope but does not cause an external
address to become a Wathiq user. Attachments on inbound replies are rejected in
the initial proposal; supporting them requires a malware-scanned record or
message-attachment specification. Invalid, expired, revoked, or abused aliases
fail safely and create bounded diagnostics without generating backscatter.

An ordinary SMTP submission server cannot implement this behavior alone. The
deployment must provide inbound routing to a Wathiq worker or an approved mail
gateway webhook.

## 10. Event history and Security Operations

The following immutable operations are proposed:

- `EXTERNAL_MESSAGE_QUEUED`;
- `EXTERNAL_MESSAGE_SUBMITTED`;
- `EXTERNAL_MESSAGE_FAILED`;
- `EXTERNAL_RESOURCE_SHARE_CREATED`;
- `EXTERNAL_RESOURCE_SHARE_ACCESSED`;
- `EXTERNAL_RESOURCE_SHARE_DENIED`;
- `EXTERNAL_RESOURCE_SHARE_REVOKED`; and
- `EXTERNAL_EMAIL_REPLY_ACCEPTED`.

Events store actor, sender snapshot, message/envelope ID, external recipient
address in an access-restricted field, resource type/ID and security-level
snapshots when applicable, release mode, reason, expiry/view policy, outcome,
request/correlation ID, and safe denial code. They never store capability
tokens, verification codes, SMTP credentials, complete message bodies, or
resource content.

Every external release of an above-baseline message or resource and every
access, denial, revocation, or attachment release is classified as a monitored
security operation. The existing Security Operations page shall expose
sanitized counts and recent safe envelopes under `audit.view`; protected
details remain subject to current clearance and resource authorization.

## 11. Proposed database tables

### `message_external_recipients`

Stores envelope, normalized email, display-name snapshot, `to`/`cc`, and
ordinal. It is unique by `(envelope_id, normalized_email)`.

### `external_email_deliveries`

Stores globally unique delivery ID, envelope/external-recipient identity,
status (`pending`, `leased`, `submitted`, `failed`), attempt count, next attempt,
lease owner/expiry, SMTP message ID when safe, submitted time, and bounded last
error. It contains no SMTP credential.

### `external_resource_shares`

Stores share ID, envelope, external recipient, normalized resource foreign key,
sender, release mode, security-level snapshot, token hash, expiry, maximum and
successful views, verification policy, created time, revoked time/actor/reason,
and current terminal state. Resource types use explicit foreign keys rather
than an unchecked polymorphic ID.

### `external_resource_share_accesses`

Stores one bounded security audit row per attempt: share, attempted time,
outcome/reason code, whether a successful view was consumed, privacy-safe
network/client context, and request/correlation ID. It stores no token or
resource content.

### `external_reply_aliases`

Stores alias-token hash, envelope, original sender, creation/expiry/revocation,
and bounded abuse-control state. The plaintext alias is never recoverable from
the table.

## 12. Acceptance themes

Approval and implementation shall verify at minimum:

- external addressing is impossible without `messaging.external.send`;
- resource release is impossible without all new and existing required
  privileges and live resource authorization;
- internal-account emails cannot silently bypass in-app clearance;
- SMTP failure never rolls back or loses the committed in-app message;
- external jobs survive worker/API restarts and do not send twice on ordinary
  idempotent request retries;
- above-baseline releases require warning, reason, confirmation, immutable
  history, and Security Operations visibility;
- revoked, expired, exhausted, sender-deauthorized, resource-deauthorized, and
  deleted-resource links all fail closed with safe useful explanations;
- concurrent last-view attempts cannot exceed the limit;
- Outbox shows per-recipient SMTP and controlled-link state and supports sender
  revocation;
- inbound aliases cannot be guessed, reused outside policy, or cause mail loops;
  and
- no token, verification code, credential, protected content, or unrestricted
  external email address leaks into logs or sanitized monitoring.

## 13. Decisions required before approval

1. Whether the initial release supports controlled links only or also permits
   irrevocable attachments.
2. Allowed resource kinds and preview formats.
3. Minimum/maximum expiry and view-count values and whether unlimited views are
   ever permitted.
4. Whether recipient email verification is mandatory for all links or only
   above-baseline resources.
5. Which profiles receive the proposed privileges and whether an emergency
   revocation privilege is needed.
6. Maximum external recipients, attachment bytes, resources, SMTP retries, and
   inbound email size.
7. Approved SMTP submission, bounce, inbound routing, malware-scanning, and
   domain-authentication architecture.
8. External-address retention, masking, privacy-access, and data-subject rules.
9. Reply-alias lifetime and behavior after sender deactivation or message
   retention expiry.
10. Whether an external reply may contain attachments or rich HTML in a later
    phase.

