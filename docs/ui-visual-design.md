# Web UI visual design

The ERMS web interface uses a calm, light enterprise visual system. These rules
are cosmetic: they do not change navigation, permissions, API behavior, entity
semantics, or application workflows.

## Foundation

- The application canvas and content pane use a clean white background. The
  header and navigation drawer are separated from it with fine borders rather
  than a darker canvas or shadow.
- Light blue is the primary accent. Strong blue is reserved for primary
  actions, links, selected items, and focus. Pale blue is used for selection
  backgrounds and informational emphasis.
- Green, amber, and red remain semantic colors for positive/open, warning or
  closed, and destructive states respectively.
- Typography uses the platform UI font stack, preferring Inter when available.
  Headings use weight and spacing rather than decorative treatments.
- Cards use fine neutral borders and 14-pixel corner radii. Page content uses a
  flat treatment without elevation; dialogs retain overlay separation. Inputs,
  buttons, and tables use related radii and restrained borders.

## Application shell

The header, navigation drawer, and canvas use the same light background and are
separated by fine borders rather than shadows.
Navigation remains in its established order and continues to support the
compact clickable icon rail. Hover states use pale blue, and labels remain on a
single line in the expanded drawer.
The drawer uses a white surface and near-black navigation labels so it is
lighter and more distinct from the application canvas. Section headings use the
product blue to make the hierarchy easier to scan. The current destination uses
a pale-yellow background, dark-blue text, and a slim blue rail. Its active state
remains visible in collapsed icon-rail mode and is exposed with
`aria-current="page"`.
Drawer icons use the unfilled Material Symbols treatment at weight 300 for a
light outline. This icon treatment is scoped to navigation and does not alter action,
status, or metadata icons elsewhere in the application.

## Detail pages

Entity details use a consistent hierarchy:

1. A compact section heading identifies the entity type.
2. The entity title and reference are visually dominant.
3. Actions remain in the page header and retain their existing behavior.
4. Long descriptions appear on a quiet neutral inset surface.
5. Metadata is arranged in a two-column field grid. Each field has a small
   uppercase label and a darker, readable value.
6. Status is represented by a semantic outlined badge.

Record details retain the embedded Digital Components interface immediately
below the metadata surface.

The Dashboard and main list pages for Aggregations, Records, Classification
Schemes, Organization Units, Roles, and Users place the corresponding lightweight
outlined navigation icon immediately before the page title. Other pages hide
this title icon rather than inheriting a stale icon from prior navigation.

## Page tables

Full-width entity tables must be visually inset from their containing card.
Use the shared `erms-page-table` treatment so a table has consistent space on
its left, right, and lower edges, plus separation from favourites, filters, or
other content above it. Do not place a page table flush against the boundary of
its card. This convention applies to aggregation contents and to entity-list
pages such as Users, Roles, and Organization Units. Compact tables nested
inside an already padded dialog or detail card do not add a second outer inset.

Search-result tables and tables that list records contained by an aggregation
must provide a compact text filter and sortable data columns. Action columns
are never sortable. Filtering applies to the rows already loaded into the
table; it supplements rather than replaces the page's API search controls.
Page-table headers use the product's pale-blue accent surface and dark blue-grey
type rather than generic grey table chrome. Body typography uses the same ink
and scale as the surrounding metadata surfaces, with a subtle blue hover state.

Related page-header actions must occupy one non-wrapping action group. Long
titles may truncate or yield space, but must not push one action onto a separate
line while leaving another action behind.

## Effective retention rule

Aggregation details present the effective rule as a three-stage lifecycle:

1. **Current (active)** — the period kept with the responsible business unit.
2. **Intermediate (semi-active)** — the period retained in intermediate
   storage.
3. **Final disposition** — the configured action after both periods complete.

A vertical blue line and stage markers express the sequence without changing
the underlying rule. Provenance, governing classification, instructions, and
the existing local-override action remain visible. Retention information uses a
pale-blue panel but final-disposition and status semantics are unchanged. On
the Aggregation Details page, this panel sits beside the primary metadata card
and wraps beneath it on narrower viewports. Child-aggregation and record totals
appear once in the metadata field named **Contains**; they are not repeated as
oversized statistic cards.

## Accessibility and behavior

- Text and action contrast must remain readable on light surfaces.
- Color supplements labels and icons; it is not the only status indicator.
- Existing keyboard, click, double-click, paging, filtering, and navigation
  behavior must not be removed by visual changes.
- Responsive layouts may wrap actions or metadata but must not hide them.
