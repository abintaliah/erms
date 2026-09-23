from pathlib import Path


APP = Path(__file__).parents[1] / "app.py"
CLIENT = Path(__file__).parents[1] / "api_client.py"


def test_holds_workspace_and_navigation_are_wired():
    source = APP.read_text(encoding="utf-8")
    assert '"Holds", "gavel", navigation_key="holds"' in source
    assert 'async def select_holds()' in source
    assert 'async def select_hold_details(hold_id: int)' in source
    assert 'async def open_hold_editor(' in source
    assert '"Create hold"' in source
    assert 'ui.label("Filter holds").classes("text-lg font-semibold text-slate-800")' in source
    assert 'with ui.row().classes("w-full items-center"):' in source
    assert '"Add held items"' in source
    assert '"Search number, title or description"' in source
    assert 'first_page=ui.button("First"' in source
    assert 'last_page=ui.button("Last"' in source
    assert '.tooltip("Open resource")' in source
    assert '.tooltip("Remove from this hold")' in source
    assert '"Remove from all holds"' in source
    assert 'color="positive" if hold["state"]=="active" else "blue-grey"' in source
    assert 'render_user_avatar(contributor, size="25px").style(' in source
    assert '"margin-right:5px !important"' in source
    assert 'held_item_assigned_from=ui.input("Assignment date from")' in source
    assert 'held_item_assigned_before=ui.input("Assignment date before")' in source
    assert '"hold-command-layout w-full"' in source
    assert 'ui.label("Hold actions")' in source
    assert 'ui.button("Edit hold"' in source
    assert 'ui.button("Manage contributors"' in source
    assert 'ui.button("View history"' in source
    assert source.count('await show_entity_history("holds", hold)') == 2
    assert 'ui.label("Hold history").classes("text-2xl font-bold")' not in source
    assert 'ui.button("Delete hold"' in source
    assert 'control.add_slot("selected-item"' in source
    assert 'control._props["hide-selected"] = False' in source
    assert 'control._props["fill-input"] = False' in source
    assert 'value=(hold or {}).get("owner_user_id"), label="Owner", with_input=True' in source
    assert 'control._props["display-value"]' not in source
    assert '"hold-held-item-filter-primary w-full"' in source
    assert '"hold-held-item-filter-secondary w-full"' in source
    assert 'with ui.row().classes("w-full items-center justify-end gap-2")' in source
    assert '"width:1280px;max-width:calc(100vw - 48px)"' in source
    assert 'update_held_item_selection(row: dict[str, Any], selected: bool)' in source
    assert 'update_candidate_selection(row: dict[str, Any], selected: bool)' in source
    assert source.count('with ui.element("div").classes("governance-card-list w-full")') >= 3
    assert 'selected = ui.checkbox(value=row["selection_key"] in held_item_selection)' in source
    assert 'selected = ui.checkbox(value=row["selection_key"] in picker["selected"])' in source
    assert 'on_click=lambda: select_user_details(hold["owner"]["id"])' in source
    assert '"folder" if row["resource_type"] == "aggregation" else "description"' in source
    assert 'row["assigned_at_display"] = format_timestamp(row["assigned_at"])' in source
    assert 'props.row.security_level_code' not in source  # composed once in Python
    assert 'row["security_level_display"] = f"{row[\'security_level_code\']} — {row[\'security_level_name\']}"' in source
    assert 'select_user_details(user_id)' in source


def test_hold_mutations_collect_reasons_and_refresh_live_state():
    source = APP.read_text(encoding="utf-8")
    assert 'async def hold_reason_dialog(' in source
    assert 'Reason for updating this hold' in source
    assert 'Reason for removing this direct assignment' in source
    assert 'Remove from all holds? Inherited protection from parent aggregations will remain.' in source
    assert 'Remove from all holds? Inherited protection from its aggregation hierarchy will remain.' in source
    assert 'await api.effective_holds("record", record_id)' in source
    assert 'await api.effective_holds("aggregation", current["id"])' in source
    assert 'effective_holds, "record", record_id' in source
    assert 'effective_holds, "aggregation", current["id"]' in source
    assert 'Remove from this hold' in source


def test_hold_editor_datetime_conversion_uses_application_timezone_without_javascript():
    source = APP.read_text(encoding="utf-8")
    hold_editor = source[source.index("async def open_hold_editor("):source.index("async def add_resource_to_hold_dialog(")]
    assert "ui.run_javascript" not in hold_editor
    assert 'return parsed.astimezone().strftime("%Y-%m-%dT%H:%M")' in hold_editor
    assert "parsed.replace(tzinfo=local_timezone).astimezone(timezone.utc).isoformat()" in source
    assert "Dates currently use the application timezone." in source


def test_aggregation_command_centre_matches_the_approved_two_column_layout():
    source = APP.read_text(encoding="utf-8")
    assert '"aggregation-command-layout w-full p-5"' in source
    assert '"Aggregation overview"' in source
    assert '"detail-surface aggregation-actions-panel shadow-none p-4 gap-3"' in source
    assert '"Metadata and review"' in source
    assert '"Lifecycle"' in source
    assert '"Security, access and audit"' in source
    assert '"detail-surface aggregation-hold-controls shadow-none p-4 gap-3"' in source
    assert '"Hold controls"' in source
    assert '"Remove direct holds"' in source
    assert '"aggregation-child-preview-grid mx-5 mb-3"' in source
    assert 'for child in children:' in source
    assert 'f"{child[\'aggregation_number\']} · {child_status}"' in source
    assert '"aggregation-retention-stages w-full"' in source
    assert '"aggregation-retention-footer w-full"' in source
    assert 'grid-column: 1 / -1; grid-row: 2' in source
    assert '"w-full text-sm font-semibold text-slate-800"' in source
    assert '("Permanent Transfer", "External archive")' in source
    assert '("Selective Transfer", "Appraise and transfer")' in source
    assert '("Destruction", "Destroy after retention")' in source
    assert '.aggregation-retention-stage:not(:last-child)::after' in source
    assert '.aggregation-overview-actions .q-btn' in source


def test_access_explainer_renders_redaction_safe_hold_constraints():
    source = APP.read_text(encoding="utf-8")
    assert 'result.get("resource_state_constraints", [])' in source
    assert 'details restricted' in source
    assert 'An effective legal hold prevents this' in source


def test_security_level_change_remains_separate_from_hold_frozen_metadata():
    source = APP.read_text(encoding="utf-8")
    assert 'async def show_security_level_change(' in source
    assert 'if capabilities.get("change_security_level"):' in source
    assert 'await api.preview_security_level_change({' in source
    assert 'await api.apply_security_level_change({' in source
    assert '"Reason *"' in source
    assert '"security_level_id",' in source
    assert '"Level action for a reviewed security-level change."' in source
    assert '"none": "Change only this resource"' in source
    assert '"raise_ancestors": "Also raise parent aggregations as needed"' in source
    assert '"downgrade_subtree": "Also lower contained resources as needed"' in source
    assert "props.opt.value === 0" in source
    assert 'popup-content-style="width:572px;max-width:calc(100vw - 64px)"' in source
    assert "white-space:normal; overflow-wrap:anywhere" in source


def test_api_client_exposes_complete_hold_workflow():
    source = CLIENT.read_text(encoding="utf-8")
    for method in (
        "holds", "hold", "create_hold", "update_hold", "delete_hold",
        "hold_held_items", "hold_contributors", "replace_hold_contributors",
        "add_hold_held_item", "hold_held_item_candidates", "add_hold_held_items_bulk",
        "remove_hold_held_item", "effective_holds",
        "add_resource_to_hold", "remove_resource_from_hold",
        "remove_all_direct_holds", "hold_history",
    ):
        assert f"async def {method}(" in source
