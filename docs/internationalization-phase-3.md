# Internationalization Phase 3 implementation contract

This document records the implemented RTL infrastructure for the approved
`specs/internationalization-and-user-preferences.md`. The approved specification
remains authoritative.

## Language and direction lifecycle

The authenticated bootstrap is the authority for language and direction. The
WebUI keeps the last verified bootstrap metadata and compiled catalogue in the
browser's private NiceGUI user storage so that subsequent page construction can
set `html.lang` and `html.dir` before rendering the application shell. When the
authoritative language, direction, or catalogue revision changes, the WebUI
updates the private cache and performs one controlled rebuild. The default for
an uncached browser remains English LTR.

Runtime catalogues are isolated by NiceGUI client id. Event callbacks therefore
resolve messages for their own browser page instead of process-global state;
client entries are removed on disconnect.

## RTL component behavior

Arabic sets `lang="ar"`, `dir="rtl"`, an RTL body direction, and the Arabic font
stack. The navigation drawer moves to the right, directional controls mirror,
rows and action groups flow from the right, and form values, selectors, menus,
dialogs, notifications, tooltips, and listboxes inherit RTL. A mutation observer
applies language and direction to dynamically portalled content.

Directional spacing, indentation, borders, and sticky tree positions use CSS
logical properties. Intrinsically LTR content—including codes, email addresses,
URLs, numbers, monospace values, and preformatted content—is directionally
isolated. The message renderer continues to HTML-escape and Unicode-isolate all
named-placeholder values.

## Preferences

The signed-in user menu exposes a compact Preferences dialog for selecting an
enabled interface language and an IANA working timezone. Saving uses the
optimistic-concurrency preference API, clears the cached presentation context,
and rebuilds the page from the returned authoritative preference.

## Verification

Controlled, manually published Arabic test translations were used only in a
disposable browser-test database. Desktop and 390×844 browser checks verified
root language/direction, right-side drawer placement, dynamic menu/dialog RTL,
Arabic field labels, Arabic typography, no horizontal overflow, and restoration
to English LTR with the drawer on the left. Semantic DOM inspection confirmed
dialog, menu, form, button, and accessible-name exposure. Automated tests cover
direction normalization, dynamic-portal scripting, the catalogue contract, and
the existing WebUI behavior.
