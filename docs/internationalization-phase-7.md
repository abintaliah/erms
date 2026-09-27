# Internationalization Phase 7 implementation contract

Phase 7 provides the privileged Translation Inspector required by the approved
internationalization specification. It is a diagnostic aid for system
administrators; it is not an authoring surface and it never exposes draft
translations to ordinary users.

## Access and lifetime

The inspector is available only when the current identity has the
`localization.administer` privilege. Its compact switch appears in an
administrator-only **Diagnostics** section of the account menu. The inspector
is off by default, and its enabled state is stored in browser session storage,
not in user preferences. Identity clearing, sign-out, session expiry, and
privilege loss disable it and remove the session value. Authorization is
rechecked whenever identity privileges are refreshed.

The account-menu trigger and the Diagnostics section are deliberately exempt
from action interception so an administrator can always reach the switch and
turn the inspector off. This exemption does not apply to application actions.

## Rendering and interaction

The centralized catalogue renderer emits short-lived diagnostic metadata only
for the authorized page client. A single delegated browser interaction layer
decodes that metadata, annotates translated DOM nodes, watches dynamic and
portal-rendered content, and handles pointer, focus, click, and Escape events.
This avoids per-component inspector wiring and covers labels, buttons, fields,
tooltips, menus, and dynamically rendered content that use the catalogue.

The delegated DOM observer is connected only while an authorized administrator
has enabled the inspector. When disabled it is disconnected and performs no
ordinary page-mutation work. Enabling performs one document scan before
observing subsequent mutations. The normative performance and cache contract
is documented in [WebUI performance](webui-performance.md).

Hover or keyboard focus highlights the current translated element. Clicking an
inspectable element may pin it for inspection, but never cancels, delays, or
changes its ordinary navigation, form, or application action. Escape clears the
pin. Disabling the inspector removes the panel and all delegated listeners.
User-authored values and multilingual entity metadata are not assigned
synthetic UI-message keys.

## Inspector panel

The fixed compact panel shows the contextual key in monospace, effective
language, rendered translation, and whether English fallback was used. Its two
icon actions have localized accessible names and tooltips:

- copy the contextual key;
- open Translation Administration with an exact-key filter.

Opening administration uses the normal guarded navigation path and therefore
preserves Wathiq's page-history and unsaved-change behavior. The inspector is
read-only: editing, review, and publication remain exclusively in Translation
Administration under the existing governance rules.

The panel inherits the document direction, uses logical positioning and text
alignment, and keeps the contextual key explicitly left-to-right. It therefore
works in both LTR English and RTL Arabic without changing business tooltips or
the application layout.

## Bulk review and publication

Translation Administration provides one compact action for all valid drafts
and an equivalent action within each actual context group. Draft origin is
shown for audit and filtering only; it does not decide whether a draft may be
published.
The former non-actionable wall of blue context-summary badges is removed;
counts and actions live with the grouped results they describe.

Opening a bulk action first obtains an exact key-and-version preview. The
confirmation dialog shows the scope and count, explains the all-or-nothing
behavior, requires one audit reason, and lists invalid keys before publication.
The API locks and revalidates the exact selection, rejects stale or changed
rows, and publishes nothing if any selected value is blank, malformed, has a
placeholder mismatch, contains disallowed markup, or retains a quality flag. A
successful transaction records review and publication identity
on every key, produces immutable per-key event history, and increments the
language catalogue revision and clears its cache once for the complete batch.

Source-copy, generated, imported, and manual drafts use the same preview,
validation, atomic review, audit, and publication contract. Import itself does
not count as review and cannot publish a translation. The supported-language
cards select the language being administered. Key filters never select an
action target. Page-level and context actions use the selected card, while an
import always uses the language declared by its JSON file.

## Runtime data boundary

The published catalogue response includes a compact `fallback_keys` list so
the client can distinguish an effective English fallback from a published
translation. It does not include draft text, reviewer metadata, or unpublished
translation state. Diagnostic markers are enabled only for the current
authorized page client and are removed before the user sees the rendered text.

## Verification evidence

- focused inspector tests cover the contextual catalogue contract, privilege
  gate, session-only lifetime, centralized delegated handler, dynamic DOM
  observer, action interception, Escape handling, exact-key administration
  navigation, non-UI value boundary, and always-reachable disable controls;
- API tests prove `fallback_keys` is returned without draft metadata and is
  updated when a translation is published;
- all 208 WebUI tests and all 326 API/database tests passed, with database tests
  run only against unique disposable PostgreSQL databases that were removed;
- the catalogue checker, JavaScript syntax check, Python compilation, and
  `git diff --check` passed;
- a live browser pass against an isolated disposable stack verified the
  administrator-only switch, 60 annotated elements on the dashboard, hover/
  pin panel data, consumed Refresh action, Escape clearing, copying, exact-key
  navigation, disabling through the exempt Diagnostics controls, English LTR,
  and Arabic RTL with localized panel labels and an LTR key value.
