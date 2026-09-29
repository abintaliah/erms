# Aggregations: Browse classification

## Approved interaction

The second Aggregations tab centers on one full-width classification,
aggregation and record tree. The adjacent summary pane and its secondary
Open buttons are removed. Existing aggregation and record detail pages remain
the navigation destinations; their content, actions and authorization rules
are unchanged.

- Classification chevrons and titles expand or collapse their branch.
- Aggregation chevrons expand or collapse child aggregations and records.
  Aggregation titles open the existing aggregation detail page directly.
- Record titles open the existing record detail page directly.
- Back restores the selected scheme, expanded branches, loaded page lengths,
  branch filters, selected node and tree/page scroll position. Returning reloads
  metadata so mutations made in the detail view are reflected.
- Rows retain real titles, identifiers and type icons. Record rows use the
  same primary-blue outlined document icon as the rest of the tree icon system.
  Aggregation rows display record counts and open/closed status. No summary-only
  retention or location requests occur during tree selection.
- The scheme selector, refresh, branch-specific filtering/pagination,
  loading/error/empty states and recent-activity section remain available.
- Collapsed chevrons point right in English and left in Arabic; expanded
  chevrons point down. Title controls align to the reading start and are
  keyboard-operable independently of disclosure controls.

## Performance and localization

Keep each branch server-paginated; never fetch a complete hierarchy. Independent
branch reloads run concurrently, with continuation pages fetched sequentially
within each branch. Ignore responses belonging to abandoned browser instances,
changed schemes or superseded filters. Tree data is isolated to the authenticated
page session, cleared at sign-out and refreshed on return. Existing server-side
permissions and ordering continue to apply.

Reuse existing translation keys. Retire summary-only keys using the normal
catalogue synchronization/deprecation lifecycle; retain immutable translation
history and preserve all surviving Arabic entries and provenance.

## Verification traceability

`frontend/webui/interaction/tests/test_aggregation_browser.py` verifies:

- Direct record navigation and independent chevrons in LTR/RTL:
  `test_titles_navigate_and_disclosures_only_expand`.
- Direct aggregation navigation, loaded page lengths, fresh metadata and
  expansion on return: `test_return_reloads_pages_and_preserves_expansion`.
- Abandoned branch responses: `test_abandoned_branch_response_does_not_update_browser`.

Live browser verification covers full-width rendering, LTR/RTL alignment,
aggregation/record details and Back navigation, plus a narrow viewport.

The existing aggregation and record detail-page metadata and operations remain
unchanged. Their identity headers follow the same direction-aware convention:
the entity icon stays beside its title, while Favourite and Back—and Preview
for eligible records—occupy the opposite side. Arabic Back arrows point right.
