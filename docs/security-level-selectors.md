# Security-level choices in ordinary resource forms

Aggregation creation, record draft creation, and ordinary aggregation/record
editing use `bind_resource_security_select` in `frontend/webui/app.py`.
The separate governed Change security level action keeps its existing behavior.

The existing `/api/v1/security-levels/page` endpoint accepts `assignable=true`
and optional `parent_aggregation_id` and `aggregation_id`. It evaluates current
effective-role clearance, checks referenced aggregation visibility, caps choices
at the parent level, and applies the aggregation's content minimum before search,
counting and pagination. No effective clearance yields no choices. The existing
mutation authorization checks and database hierarchy triggers remain authoritative.

The selector requests at most 25 matching choices. It fetches a selected ID
separately when necessary, retaining it only if it remains within the returned
bounds. It refreshes on opening and parent changes, debounces text search, ignores
superseded responses and abandoned controls, and clears invalid selections.
There is no new cache: every request evaluates the current authenticated user
and language. Errors clear the choices rather than exposing unfiltered options.

The explanation uses one new key, `security_level.selection.constraints`, in
English and the maintained Arabic artifact. Existing Arabic entries and provenance
are preserved. The new Arabic wording is a generated draft requiring normal
review/publication; no administrator export was replaced. No schema migration or
demo database update is part of this change.

The native select hint was inspected in a live NiceGUI preview and overlapped the
next field at a 360px width. A standard NiceGUI column and label now reserve space
for the explanation; no custom CSS override is needed. English and Arabic previews
were checked at narrow and desktop widths. The preview uses the actual binding
with a bounded fake API; the full signed-in forms were not replayed.

Verification links requirements to implementation:

| Requirement | Evidence |
| --- | --- |
| Effective-role ceiling, parent ceiling, filtering before pagination/search, expired assignments | `test_assignable_levels_follow_clearance_and_parent` |
| Aggregation content minimum | `test_assignable_aggregation_update_respects_contents` |
| Parent changes, fresh clearance, invalid selection clearing, English/Arabic guidance | `test_constraints_refresh_and_clear_invalid_selection` |
| Superseded response and abandoned control protection | `test_old_response_cannot_restore_previous_parent_choices` |

Database tests use a uniquely named disposable database initialized from
`database/schema.sql`, then dropped. Persistent databases are not used for tests.
