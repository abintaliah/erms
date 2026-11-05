# Phase 2 existing API contract map

Reviewed 5 November 2026 on `MobileFlutterv0.4.2`.
Status: source mapping complete; mobile implementation and runtime verification
have not started. This document approves no new API, UI workflow or scope change.

## Authority and boundary

Mobile specification §§8.3, 12, 16–19, 26 Phase 2 and 27.7 govern this work.
Domain references: `specs/record-detail-page.md`, `specs/user-favourites.md`,
`specs/aggregation-classification-browser.md`,
`specs/security-and-authorization-subsystem.md` and
`specs/records-management-subsystem.md`. Web record-detail mutation controls do
not extend mobile Phase 2: only favourites mutate here; viewing is Phase 4.
All routes below already exist. No backend, WebUI, database, settings or catalogue
changes were made during mapping. No network or database tests were run.

Paths below are relative to `/api/v1`. IDs are existing resource IDs, not new
mobile identifiers. Reuse Phase 1 authenticated transport, mobile audit headers,
locale and session-generation isolation; no role-based authorization reconstruction.

## Route and response map

| Mobile requirement | Existing method and path | Response and boundary | Source |
| --- | --- | --- | --- |
| Full aggregation metadata | GET `/aggregations/{id}` | `AggregationRead`; hidden and absent both 404; parent relationship has explicit none/visible/redacted state | `backend/services/api/main.py`: `get_aggregation`; `crud.py`: `get_or_404`, `redact_hidden_relationships` |
| Full record metadata | GET `/records/{id}` | `RecordRead`; hidden and absent both 404; containing aggregation may be redacted | `main.py`: `get_record`; `crud.py` |
| Resource capabilities | GET `/aggregations/{id}/capabilities`, `/records/{id}/capabilities` | `ResourceCapabilitiesRead`: resource type/ID, capabilities, reason codes; record separates `list_components` and `view_component`; no dedicated history/favourite key | `main.py`: `get_aggregation_capabilities`, `get_record_capabilities` |
| Child aggregations | GET `/browse/aggregations/{id}/children?limit=25` | `BrowsePage[BrowseAggregationNode]`: items, next_cursor, total | `browse.py`: `browse_aggregation_children`, `_page` |
| Child records | GET `/browse/aggregations/{id}/records?limit=25` | `BrowsePage[BrowseRecordNode]`; independent cursor and loading/error state | `browse.py`: `browse_aggregation_records` |
| Shared card context | GET `/browse/aggregations/{id}/summary`, `/browse/records/{id}/summary` | One browse node, counts and contextual fields; not a substitute for complete detail metadata | `browse.py`: summary handlers; `schemas.py`: browse nodes |
| Visible digital-component metadata | GET `/digital-components?record_id={id}&limit={n}&offset={n}` | `list[DigitalComponentRead]`; limit 1–500, default 100; no total/cursor; order record_id, component_order; visibility enforced by `current_user_can_list_record_components` | `main.py`: `list_digital_components`; `crud.py`: `READ_VISIBILITY` |
| Current user's favourite state | GET `/favourites` | `FavouritesPageRead`: aggregations, records, application_configuration; complete authorized personal collection, no paging/per-item status | `favourites.py`: `list_favourites` |
| Add favourite | PUT `/favourites/aggregations/{id}`, `/favourites/records/{id}` | 204, no body; idempotent; missing/hidden target 404; owner comes from session | `favourites.py`: favourite handlers |
| Remove favourite | DELETE same favourite paths | 204, no body; idempotent even if absent; does not modify target version or history | `favourites.py`: unfavourite handlers |
| Resource event history | GET `/aggregations/{id}/history`, `/records/{id}/history` | `list[EventHistoryRead]`; limit 1–500, default 100, offset >=0; newest occurred_at/id first; authorized event-history projection; no total/cursor | `main.py`: history handlers, `_entity_history`; `crud.py`: `list_rows` |
| Effective retention context | GET `/aggregations/{id}/effective-retention-rule` | `EffectiveRetentionRuleRead`; server-derived source, periods, action, instructions, acceleration; 404 also means no effective rule | `classification_management.py`: `effective_aggregation_rule` |
| Direct retention override | GET `/aggregations/{id}/retention-rule` | `AggregationRetentionRuleRead` or null; does not replace effective rule | `classification_management.py`: `get_aggregation_rule` |
| Effective closure context | GET `/aggregations/{id}/effective-closure` | `{closure: null or {id, aggregation_number, title, date_closed}}`; server computes nearest closure | `main.py`: `get_effective_aggregation_closure` |
| Authorized hold context | GET `/aggregations/{id}/effective-holds`, `/records/{id}/effective-holds` | `list[EffectiveHoldResponse]`; may return restricted markers without hold identity; do not reconstruct hidden holds | `holds.py`: `_effective_holds` |
| Individual reference labels | GET `/classifications/{id}`, `/org-units/{id}`, `/security-levels/{id}` | Existing individual read contracts, subject to their own access rules; never enumerate whole collections to resolve one label | `classification_management.py`, `user_management.py`, `security_levels.py` |

## Pagination, errors and authorization

- Children: always explicitly request 25; carry `next_cursor` unchanged. Server
  accepts 1–100 (default 50). Cursor is scoped to branch, query and filters;
  mismatch/malformed cursor is 400. Sort is number in C collation then ID.
  End is null cursor. Do not decode cursor or merge branches.
- Component/history lists are offset-based arrays. A bounded page can be
  requested; a short page ends traversal, while an exact full page can require
  one further empty request. Neither endpoint provides a total. Their page-size
  and presentation choices are not specified here as new requirements.
- Do not use unfiltered `/aggregations` or `/records` list downloads for children.
- 401 follows current session clearing and protected-route removal. 403 is a
  permission denial, not proof of session expiry. Resource 404 must not reveal
  whether deleted, hidden or absent. A contextual retention 404 is not itself
  proof that the already loaded resource was deleted.
- Components can return an empty array for a metadata-only reader; use server
  `list_components` capability so denied access is not described as no uploads.
- History routes first check live visibility or permitted deleted-resource audit
  access, then query `authorized_event_history`. They do not use the global
  `/event-history` route's `audit.view` dependency. Do not gate resource history
  by a guessed global privilege. An empty authorized history page is not a denial.
- Network/service errors use the existing safe offline/retry boundary. Do not
  silently replay favourite mutations after reconnect. Late responses must not
  restore state after sign-out, revocation, resource change or account change.
- Back/scroll preservation and request cancellation are Flutter responsibilities,
  not new server endpoints. No external deep links are approved.

## Contract limitations and decisions to review before implementation

1. Favourite state is absent from detail/browse responses. The existing complete
   personal collection is expressly allowed by mobile §13; there is no per-item
   check. No new endpoint is proposed. Any future in-memory reuse needs explicit
   identity scope, freshness, invalidation and failure rules before implementation.
2. Resource history has no dedicated visibility capability and does not call the
   global history route's `enrich_audit_page`. `EventHistoryRead` therefore does
   not guarantee populated display_presentation/display_references on these
   routes. Do not assume identical enriched display across the two contracts or
   substitute global audit access. Recommendation awaiting user decision: use
   resource history with existing localized event terminology and only authorized
   response fields, without adding enrichment to the backend.
3. Record metadata can be visible while its containing aggregation is redacted.
   There is no record-specific effective-retention endpoint in this mapping.
   Recommendation awaiting user decision: in that case retain the redacted
   relationship and show only returned record context; do not resolve a hidden
   parent or invent retention/closure values. Full record retention enrichment
   would require separate review if expected.
4. Phase 2 details have no implemented discovery source yet: Dashboard/search/
   classification workflows are later phases. Recommendation awaiting user
   decision: verify internal typed detail navigation through a test-only harness
   using controlled existing IDs, without adding a production ID-entry screen,
   external deep links or bringing later discovery work forward.
5. Digital-component metadata includes storage and checksum fields. Mobile §12
   requires all returned authorized metadata to remain reachable, while download,
   sharing, printing and external opening remain deferred. Do not turn storage
   metadata into an actionable URL or silently omit fields for a shorter layout.

These recommendations are not implementation approvals. No mockups or Flutter
feature code have been changed; obtain the user's decisions first.

## Existing verification evidence to reuse

These are source-inspected tests, not tests executed during this mapping.

| Contract | Existing test evidence | Mobile verification still required |
| --- | --- | --- |
| Details and metadata semantics | `backend/services/api/tests/test_api.py`: aggregation/record CRUD, governed location inheritance, closure, vital status and review dates | Complete-field parsing/rendering, wrapped values, explicit empty/redacted state, en/ar phone/tablet layouts |
| Non-disclosure and relationships | `tests/test_phase6_read_authorization.py`: `test_hidden_resources_are_non_disclosing_across_read_surfaces`, bounded redaction query test | 404 handling, hidden-parent navigation suppression, stale-generation clearing |
| Children and cursors | `tests/test_browse.py`: hierarchy/counts, stable/scoped cursor, immediate collection filtering | 25-item requests, independent cursors, no overlap/duplicates, local append retry, retained Back/scroll |
| Favourites | `tests/test_favourites.py`: idempotence/hydration, missing targets, per-user isolation, cascade, no event history | Correct initial heart, PUT/DELETE 204, failure reconciliation and account isolation |
| Components | `tests/test_phase8_content_authorization.py`: `test_metadata_only_record_viewer_cannot_enumerate_or_read_components`; `test_api.py`: component ordering | List/view capability separation, bounded traversal, denied versus empty, Phase 4 preview boundary |
| History | `tests/test_api.py`: `test_event_history_is_read_only_and_searchable`; `test_phase6_read_authorization.py`: redacted audit response | Authorized resource route use, offset termination, localized safe presentation, denied/unavailable state |

Backend test paths abbreviated with `tests/` above are under
`backend/services/api/`. Any future database-backed run must use a uniquely named
disposable database initialized from the canonical schema and dropped afterward.

## Exact detail-field inventory

Snapshot of the declared response fields in `backend/services/api/schemas.py`.
This is a coverage checklist, not a new schema. Effective context from separate
routes is listed above. Future implementation must reconcile schema changes.

### AggregationRead

`id`, `parent_aggregation_id`, `parent_aggregation_state`, `classification_id`, `aggregation_number`, `title`, `description`, `date_created`, `date_opened`, `date_closed`, `medium`, `is_vital`, `has_vital_descendants`, `date_of_next_review`, `assigned_location`, `current_location`, `effective_assigned_location`, `effective_current_location`, `effective_assigned_location_source_aggregation_id`, `effective_current_location_source_aggregation_id`, `security_level_id`, `owning_org_unit_id`, `owning_org_unit_code`, `owning_org_unit_name`, `inherit_acl_from_parent`, `default_child_aggregation_acl_mode`, `resource_acl_version`, `child_aggregation_acl_version`, `child_record_acl_version`, `version`, `disposition_status`, `final_disposition_at`, `final_disposition_by_user_id`, `disposition_job_id`, `destruction_number`, `transfer_number`, `final_disposition_event_id`.

### EffectiveRetentionRuleRead

`governing_root_aggregation_id`, `classification_id`, `rule_source`, `rule_id`, `defined_by_classification_id`, `inheritance_depth`, `current_period_years`, `intermediate_period_years`, `final_disposition`, `instructions`, `justification`, `acceleration`.

### RecordRead

`id`, `aggregation_id`, `aggregation_state`, `record_number`, `title`, `description`, `date_created`, `date_originated`, `medium`, `is_vital`, `date_of_next_review`, `effective_assigned_location`, `effective_current_location`, `effective_assigned_location_source_aggregation_id`, `effective_current_location_source_aggregation_id`, `security_level_id`, `owning_org_unit_id`, `owning_org_unit_code`, `owning_org_unit_name`, `inherit_acl_from_parent`, `resource_acl_version`, `version`, `disposition_status`, `final_disposition_at`, `final_disposition_by_user_id`, `disposition_job_id`, `destruction_number`, `transfer_number`, `final_disposition_event_id`.

### DigitalComponentRead

`id`, `record_id`, `component_order`, `file_name`, `date_created`, `date_originated`, `mime_type`, `size_in_bytes`, `checksum_algo`, `checksum_value`, `storage_backend`, `storage_key`, `content_status`, `active_content_set_id`, `upload_completed_at`, `version`.

### EventHistoryRead

`display_presentation`, `display_references`, `can_view_technical_details`, `id`, `occurred_at`, `transaction_id`, `entity_type`, `entity_id`, `operation`, `actor_user_id`, `actor_name`, `actor_email`, `actor_type`, `source`, `request_id`, `correlation_id`, `before_state`, `after_state`, `changed_fields`, `reason`, `metadata`.

