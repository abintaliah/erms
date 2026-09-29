# ERMS mobile application — requirements and specification

Status: Draft for review; phased delivery plan included.
Prepared: 23 September 2026.
Repository baseline reviewed: `06208904a914b88d7afa1413077db7c930de354f`.

## 1. Purpose and scope

Build a Flutter application that makes ERMS easy to use on iPhone and Android
phones, with adaptive tablet layouts. Every interactive user must be able to
complete the tasks available to them in the current web application, including
records management, governance and administration. Adapt the interface for touch
and available screen space while preserving existing terminology and behavior.

This document specifies mobile-specific requirements. Shared business rules
and API contracts are incorporated by reference in Section 2, not redefined
here. Existing APIs are the trusted, tested baseline; mobile verification
focuses on the new client and its integration.

The scope is the current web application's implemented capabilities. API-only
operations and unimplemented proposals do not automatically enter scope. No
backend, database or permission changes are included. For a concrete gap,
inspect existing routes, contracts, the [web API adapter](../frontend/webui/api_client.py)
and [policy inventory](../security/operation-policy-registry.json) first.
Document the missing capability and proposed solution. **Explicit project-owner
permission is required before implementing any new endpoint, even when no
suitable endpoint exists.** Other backend scope changes likewise require agreement.

## 2. Shared specifications and coverage

The following references govern mobile behavior for the corresponding existing
web features. Their data models, validation, authorization, reasons, previews,
lifecycle rules, audit events and error contracts are inherited unchanged.
Desktop-specific layout prescriptions may be adapted under Section 3.

| Coverage | Governing references |
| --- | --- |
| Sign-in, password changes, account states and session administration | [Authentication](../docs/authentication.md), [session lifecycle](authentication-and-login-session-lifecycle.md) |
| Dashboard, personal recent records/aggregations and favourites | [Dashboard contract](../docs/dashboard.md), [favourites](user-favourites.md) |
| Search, classification-led aggregation browsing and record details | [Search grammar](../docs/search-grammar.md), [aggregation browser](aggregation-classification-browser.md), [record details](record-detail-page.md) |
| Classification schemes, classifications and retention rules | [Classification subsystem](classification-scheme-subsystem.md), [implementation guide](../docs/classification-schemes.md) |
| Record creation and staged components | [Record drafts](../docs/record-drafts.md) |
| Medium, vital status, review dates, locations and closure interactions | [Resource-medium specification](resource-medium-vital-status-review-and-location.md), [implemented Phase 6 behavior](../docs/resource-medium-phase-6.md) |
| Ownership, creation-role selection, moves and ACL defaults | [Ownership and default ACLs](organizational-ownership-and-default-acls.md), [implemented ownership behavior](../docs/organizational-ownership-phase-7.md) |
| Privileges, capabilities, ACL management, security levels, access explanations and governance custody | [Authorization specification](security-and-authorization-subsystem.md), [implemented UI](../docs/security-authorization-phase-10.md), [API policy rules](../docs/api-policy-inventory.md) |
| Organization browsing, users, roles, assignments and lifecycle/deletion | [Organization browser](organization-structure-browser.md), [user management](../docs/user-management.md), [deletion specification](user-role-org-unit-deletion.md) |
| Digital-component operations, preview, download and content storage | [Document viewing](../docs/document-viewing.md), [content storage](../docs/content-storage.md), [implemented storage baseline](segmented-postgresql-content-storage.md#11-implemented-baseline), [component authorization](../docs/security-authorization-phase-8.md) |
| Entity history, Audit Trail and Security Operations | [Event history](../docs/event-history.md), [security operations](../docs/security-authorization-phase-11.md) |
| Version conflicts and navigation state | [Optimistic concurrency](../docs/optimistic-concurrency.md), [navigation semantics](persistent-navigation-breadcrumbs.md) |

Use the current [web interface](../frontend/webui/app.py),
[entity definitions](../frontend/webui/entities.py) and
[capability mapping](../frontend/webui/capabilities.py) to determine exposed
features and labels. Historical phase documents and draft proposals are not
additional mobile scope. In particular:

- The current Dashboard contract supersedes the older separate favourites-read
  guidance for assembling the Dashboard.
- Current authorization and governed-resource commands supersede older claims
  that authorization is absent or that reopening is the only permitted change
  to a closed resource.
- The resource-medium specification has a historical draft status; its Phase 6
  implementation guide and current API identify the implemented behavior.
- The content-storage specification's implemented baseline governs transfer
  support; its proposed resumable-upload endpoints are not available features.

If a remaining documentation discrepancy affects a mobile task, record it
against the current implementation rather than inventing a new policy.

## 3. Flutter project and presentation

**PROJECT-01 — Location.** All Flutter project resources must reside under
`frontend/mobile/<resources>`, relative to the repository root. This includes
Dart source, assets, translations, tests, iOS/Android project files, dependency
manifests/lockfiles, mobile build configuration, scripts and client-specific
documentation. Examples are `frontend/mobile/lib/`, `assets/`, `test/`,
`integration_test/`, `ios/` and `android/`, all beneath that project root.
Do not scatter Flutter resources under the web client, backend or repository
root. This shared specification remains in `specs/`. Runtime device data is
stored in the app's platform storage, not in the repository.

**MOB-01 — Adaptive layout.** Use one Flutter codebase for small/large phones
and tablets. Adapt navigation, forms, lists and detail panes to available window
space, portrait/landscape orientation and resized/split-screen windows without
clipping content or losing actions. Support text scaling and accessible touch
controls; status must remain understandable without colour alone.

**MOB-02 — Language.** English is the initial language. Externalize text and
use direction-aware layouts ready for a future right-to-left translation.

**MOB-03 — Names and interaction.** Match screen, section, entity, field,
action and status names in the current web interface. Use touch-friendly
layouts and selectors without renaming existing features. Mobile Back navigation
may replace desktop history breadcrumbs while preserving the referenced
navigation semantics and understandable structural ancestry.

## 4. Dashboard customization

**HOME-01 — Data loading.** Populate all Dashboard information with one
`GET /api/v1/dashboard/summary` call per initial load or refresh, following the
[Dashboard contract](../docs/dashboard.md). Do not assemble sections through
additional reads or overlap refreshes. Explicit actions and navigation to
Details or View all use their existing endpoints separately. “Home” refers to
the landing screen; its displayed name remains **Dashboard**.

**HOME-02 — Local layout.** Start with a common permission-filtered layout,
without role-based defaults. Allow every user to hide, restore and reorder
sections. Persist preferences on that device, isolated by user and server
environment. Layout changes do not fetch data or change access. Recent activity
and favourites use the shared definitions in Section 2 without new categories.

## 5. Mobile session and connection behavior

**AUTH-02 — Process lifetime.** Use the existing credentials and session API,
but keep the token only for the running app process. Require sign-in after
process termination or server session expiry/revocation, whichever occurs first.
Backgrounding or screen locking alone does not end a valid session. Remember
the username, not the password; do not restore a token from persistent storage.
Explicit sign-out uses the existing logout API. Process termination cannot
promise a server logout call, so the server session follows its normal lifecycle.
Avoid background polling that keeps an otherwise idle session alive.

**NET-01 — Connection loss.** No offline browsing, editing or queued writes.
When API connectivity fails, display a centred blocking reconnect message over
the existing content; the content remains visible but non-interactive. Retain
unfinished work only within the valid running session. Revalidate authentication
and relevant resource state before unblocking. If validity cannot be established,
remain blocked; an authentication rejection invokes the cleanup below.

**NET-02 — Session end and discard.** Sign-out, detected expiry/revocation and
process termination discard unfinished local work and clear protected screen
state. Confirm deliberate discard when navigating away from unfinished work.
Saved server drafts retain their shared lifecycle; local cleanup does not
implicitly delete them. Explicit server-draft discard requires a successful
existing API operation. Persistent local recovery is deferred in Section 11.

**NET-03 — Uncertain submissions.** Prevent overlapping submissions. After a
network failure with an unknown mutation outcome, reconcile using existing read
or draft operations before retrying; do not blindly resubmit. If the outcome
cannot be established, explain the uncertainty rather than claiming success or
starting a duplicate operation. Do not assume resumable-upload support.

For access denials and version conflicts, use the referenced authorization,
navigation and optimistic-concurrency behavior. An action-only denial must not
be treated as loss of all record access. Distinguish these responses from
connectivity failures and present safe server messages.

## 6. Mobile capture and digitization

**REC-03 — Device-produced PDF.** Users can choose existing files or scan paper
with the camera. Support multiple pages, cropping, rotation, reordering and page
deletion. The device assembles a PDF locally before upload and lets the user
preview it. On confirmation, upload that completed PDF through the existing
upload operation. Server-side assembly or a new endpoint is not needed.

**REC-04 — Existing physical record.** Offer a guided workflow to attach scanned
or selected digital content to the same physical record entry. Confirm the
change to `mixed`, collect the existing required reason, save the medium change,
then upload the component. Preserve the record identity and history. Apply the
referenced medium/parent restrictions and permissions; do not automatically
convert its parent or bypass a blocked change.

These are separate existing operations. If the medium changes but the upload
is not confirmed, show that partial outcome and apply NET-03 before retrying;
do not silently revert the medium. This workflow does not promise an atomic
conversion. Both capture flows follow Section 5's online-session requirements.

## 7. Temporary files and exported downloads

**DOC-03 — Temporary processing.** Scanning and rendering may require private
temporary files, but no reusable offline cache is provided. Delete temporary
files on discard or session cleanup; remove abandoned files on the next launch
if process termination prevented cleanup. Never restore abandoned scans as
drafts or automatically save them to the gallery.

**DOC-04 — Explicit export.** A permitted original download saved outside
app-managed storage is an exported copy, not a temporary preview file. It
remains after sign-out and is not deleted by app cleanup. Provide a platform
save-file interaction without exposing Share or Print actions in ERMS. Once
exported, ERMS cannot control sharing or printing through other applications.
Platform save-file behavior must be verified before declaring this flow complete.

## 8. Verification and outstanding setup

Verify mobile requirements in Sections 3–7 with client tests and device checks.
Use a web-action coverage checklist under `frontend/mobile/` to map each current
web action to a mobile screen, existing API operation and verification scenario.
This establishes functional parity without copying the backend specifications
or re-certifying their tested implementation.

Exercise layout/window changes, RTL readiness, accessibility, per-user preference
isolation, process death, background/resume, session expiry, connection loss,
uncertain uploads, scan preview, digitization partial failure and exported-file
cleanup boundaries. Include integration scenarios for changed access and
concurrent edits using their existing contracts. Database-backed checks must
follow [AGENTS.md](../AGENTS.md).

Before Phase 1, confirm the development toolchain, initial demonstration device,
reachable API environment and demo account/data. Select supported OS versions
and the wider test-device matrix during setup; settle signing and distribution
before the delivery method requires them.
Flutter communicates with the existing HTTP API; no direct database access or
new deployment infrastructure is implied by this specification.

## 9. Exclusions

Outside current scope: approval/request inboxes, push notifications and their
deep links, opened-item activity tracking, native sharing/printing workflows,
offline operation, OCR, barcode/QR scanning and Arabic translation. Unimplemented
warehouse/custody, organizational-workspace, break-glass, bulk-transfer and
resumable-upload proposals remain excluded. Section 1 governs any future scope
change.

## 10. Implementation phases and prerequisites

The first cut comprises Phases 1–3: a complete browse-to-document demonstration
followed by record declaration. Deliver working increments in this order.

| Phase | Scope | Completion criterion |
| --- | --- | --- |
| 1. Foundation, login and Dashboard | Create the Flutter project under `frontend/mobile/`; establish adaptive navigation, API integration, authentication and session handling; display Dashboard summaries and recent records/aggregations through the summary endpoint. | A user signs in, sees their authorized Dashboard and recents, and signs out. |
| 2. Browse-to-document demonstration | Browse classification schemes and hierarchy; open aggregations and metadata; select records; show record details and digital components; preview documents through existing APIs. Recent entries open the same detail screens. | **Demo 1:** Login → Dashboard → classification → aggregation → record → document preview. |
| 3. Record declaration demonstration | From an eligible aggregation, create a draft, enter metadata, select permitted medium/security values, attach existing files, review and submit using the existing draft/commit flow. | **Demo 2:** Open aggregation → declare record → attach PDF → review → submit → open the saved record and preview its document. Also declare a physical record without an attachment. |
| 4. Camera capture and mobile polish | Multi-page scanning and page adjustments, on-device PDF generation/preview, permitted digitization of existing physical records, Dashboard customization, and further navigation/layout refinement. | Declare a record from scanned paper and add scanned content to an eligible existing record using REC-04. Local layout preferences persist correctly. |
| 5. Remaining web-feature coverage | Search, favourites, remaining edits/component operations, aggregation management, governed metadata, classification/access/identity administration and audit/security views. | The web-to-mobile action checklist accounts for every in-scope web feature. |
| 6. Pilot and release readiness | Complete device, tablet, RTL, accessibility, interrupted-operation and performance checks; prepare packaging and the selected distribution method. | A pilot build passes the agreed acceptance checks on the selected devices. |

Permissions, applicable concurrency, session/connection behavior, error handling
and verification are part of every phase as its features are introduced.
Adaptive layout and localization foundations start in Phase 1; later polish
does not defer them. Existing-file upload makes the declaration demo possible
before camera integration. The first cut is not full feature parity, and no
phase activates Section 11 or relaxes the endpoint-approval rule in Section 1.

Prerequisites for starting the first cut:

- **Toolchain:** Locate or install Flutter/Dart and the selected platform's
  build tools; confirm a basic app can run on the demonstration target.
- **Target:** Choose the first simulator/emulator or physical phone. Maintain
  iOS/Android support even if the first demonstration uses only one platform.
- **API connectivity:** Choose the existing ERMS environment and a base URL
  reachable from that target. Confirm device-to-API connectivity without
  treating setup as backend re-certification.
- **Demo access/data:** Identify an account with browsing and document-preview
  access plus declaration rights in an eligible aggregation. Provide populated
  classification/aggregation paths, a viewable document, a PDF for upload and
  suitable physical-record data. Separate accounts may demonstrate different
  permissions. Do not embed credentials in source or this specification.
- **Delivery:** Decide whether the first demonstration runs from the development
  machine or needs an installable build on another person's phone. Configure
  device signing/distribution when required by that choice.

## 11. Deferred: recoverable local record drafts

Deferred until further instruction; not an active implementation requirement.

A future feature could automatically preserve unfinished metadata, scanned
pages/PDFs and pending attachments across connection failure, logout, expiry and
process termination. Use encrypted app-private persistent storage rather than
disposable OS cache. Isolate by user/environment and restore only after the same
user authenticates online; do not enable offline editing.

Recovery must recheck current access, destination eligibility, versions and
server-draft state, reconcile uncertain outcomes, and associate existing server
drafts to avoid duplicate submissions. Delete recovery copies after confirmed
submission or explicit discard. Retention, size limits, key lifecycle and
expired-server-draft handling remain undecided.

Activation requires revising NET-02 and DOC-03 consistently. Until then, their
local-discard behavior remains authoritative. Endpoint changes remain subject
to Section 1.
