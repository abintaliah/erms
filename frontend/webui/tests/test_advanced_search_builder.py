import pytest
from pathlib import Path

from frontend.webui.app import (
    advanced_search_depth, advanced_search_has_positive_full_text,
    advanced_search_leaf_count, advanced_search_node_from_expression,
    advanced_search_operators, advanced_search_field_options,
    advanced_search_empty_value, advanced_search_has_component_field,
    compile_advanced_search_node,
)


APP_SOURCE = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")


def test_nested_builder_compiles_existing_boolean_and_full_text_grammar():
    tree = {"type": "group", "operator": "and", "children": [
        {"type": "condition", "kind": "structured", "field": "date_originated", "operator": "between", "value": ["2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z"]},
        {"type": "group", "operator": "or", "children": [
            {"type": "condition", "kind": "structured", "field": "title", "operator": "contains_ci", "value": "budget"},
            {"type": "group", "operator": "not", "children": [
                {"type": "condition", "kind": "full_text", "query": "draft", "sources": ["metadata", "components"]},
            ]},
        ]},
    ]}
    assert compile_advanced_search_node(tree, "records") == {"and": [
        {"field": "date_originated", "operator": "between", "value": ["2026-01-01T00:00:00Z", "2026-12-31T23:59:59Z"]},
        {"or": [
            {"field": "title", "operator": "contains_ci", "value": "budget"},
            {"not": {"full_text": {"query": "draft", "sources": ["metadata", "components"]}}},
        ]},
    ]}
    assert advanced_search_leaf_count(tree) == 3
    assert advanced_search_depth(tree) == 4
    assert not advanced_search_has_positive_full_text(tree)
    tree["children"].append({"type": "condition", "kind": "full_text", "query": "approved"})
    assert advanced_search_has_positive_full_text(tree)


def test_builder_rejects_incomplete_nodes_and_filters_operators_by_type():
    with pytest.raises(ValueError, match="full-text"):
        compile_advanced_search_node({"type": "condition", "kind": "full_text", "query": ""}, "records")
    with pytest.raises(ValueError, match="Boolean group"):
        compile_advanced_search_node({"type": "group", "operator": "and", "children": []}, "records")
    assert "contains_ci" in advanced_search_operators("text", False)
    assert "contains_ci" not in advanced_search_operators("datetime", False)
    assert "is_null" in advanced_search_operators("text", True)


def test_canonical_saved_expression_round_trips_into_builder_tree():
    expression = {"and": [
        {"field": "title", "operator": "contains_ci", "value": "budget"},
        {"not": {"full_text": {"query": "draft", "sources": ["metadata"]}}},
    ]}
    tree = advanced_search_node_from_expression(expression)
    assert compile_advanced_search_node(tree, "records") == expression


def test_component_metadata_fields_use_the_existing_leaf_shape_and_are_grouped():
    tree = {"type": "group", "operator": "and", "children": [
        {"type": "condition", "kind": "structured", "field": "component.file_name", "operator": "starts_with_ci", "value": "A"},
        {"type": "condition", "kind": "structured", "field": "component.size_in_bytes", "operator": "lt", "value": 100},
    ]}
    assert compile_advanced_search_node(tree, "records") == {"and": [
        {"field": "component.file_name", "operator": "starts_with_ci", "value": "A"},
        {"field": "component.size_in_bytes", "operator": "lt", "value": 100},
    ]}
    options = advanced_search_field_options("records")
    assert options["title"] == "Record — Title"
    assert options["component.file_name"] == "Digital component — File name"


def test_component_metadata_fields_are_not_available_for_aggregations():
    with pytest.raises(ValueError, match="Choose a field"):
        compile_advanced_search_node({
            "type": "condition", "kind": "structured",
            "field": "component.file_name", "operator": "eq", "value": "a.pdf",
        }, "aggregations")


def test_typed_controls_use_valid_empty_values_before_user_selection():
    assert advanced_search_empty_value("security_level_id", "eq", "integer") is None
    assert advanced_search_empty_value("component.size_in_bytes", "gt", "integer") is None
    assert advanced_search_empty_value("is_vital", "eq", "boolean") is None
    assert advanced_search_empty_value("description", "contains_ci", "text") == ""
    assert advanced_search_empty_value("component.size_in_bytes", "between", "integer") == []


def test_component_guidance_is_contextual_to_component_conditions():
    assert not advanced_search_has_component_field({
        "type": "condition", "kind": "structured", "field": "title",
    })
    assert advanced_search_has_component_field({
        "type": "group", "operator": "and", "children": [
            {"type": "condition", "kind": "structured", "field": "title"},
            {"type": "condition", "kind": "structured", "field": "component.file_name"},
        ],
    })


def test_advanced_search_restores_the_workspace_across_result_drill_down():
    assert 'restored_workspace = state.get("advanced_search_workspace")' in APP_SOURCE
    assert 'workspace["last_result"] = copy.deepcopy(result)' in APP_SOURCE
    assert 'state["advanced_search_workspace"] = copy.deepcopy(workspace)' in APP_SOURCE
    assert APP_SOURCE.count('state.pop("discard_navigation_guard", None)') >= 4
    assert 'render_results(workspace["last_result"])' in APP_SOURCE


def test_search_builder_precedes_secondary_saved_search_actions():
    advanced_search = APP_SOURCE[APP_SOURCE.index("async def select_advanced_search"):]
    assert advanced_search.index('ui.label("Criteria")') < advanced_search.index('ui.button("Save search"')
    assert advanced_search.index('ui.button("Open saved search"') < advanced_search.index('results_host = ui.column()')
    assert 'ui.input("Search name")' not in advanced_search[:advanced_search.index("async def save_search")]
    assert 'advanced-search-workspace-layout' in advanced_search
    assert 'advanced-search-saved-panel' in advanced_search
    assert 'This query has not been saved.' in advanced_search


def test_saved_search_browser_warns_only_when_a_replacement_is_selected():
    advanced_search = APP_SOURCE[APP_SOURCE.index("async def open_saved_search_dialog"):]
    before_selector = advanced_search[:advanced_search.index("async def select_saved_search")]
    selector = advanced_search[
        advanced_search.index("async def select_saved_search"):
        advanced_search.index("async def load_saved_page")
    ]
    assert "confirm_discard_changes" not in before_selector
    assert 'confirm_discard_changes("open another saved search")' in selector


def test_save_as_is_available_only_for_an_opened_saved_search():
    assert 'save_as_button.set_visibility(has_save and saved is not None)' in APP_SOURCE


def test_saved_search_category_is_committed_and_can_be_updated_reliably():
    assert 'autocomplete=list(workspace.get("category_suggestions") or [])' in APP_SOURCE
    assert 'new-value-mode=add-unique' not in APP_SOURCE
    assert 'save_button.text = "Update saved search" if saved is not None else "Save search"' in APP_SOURCE
    assert 'f"Category: {saved.get(\'category\') or \'Uncategorized\'}"' in APP_SOURCE
    assert '"category": str(workspace.get("search_category") or "").strip() or None' in APP_SOURCE
    assert 'workspace["search_category"] = str(category_control.value or "").strip() or None' in APP_SOURCE
    assert 'workspace["search_category"] = search_category.value' not in APP_SOURCE
    assert 'search_category = ui.select([], value=workspace["search_category"])' not in APP_SOURCE
    assert 'search_category = ui.input(value=str(workspace.get("search_category") or ""))' in APP_SOURCE


def test_restored_advanced_search_selectors_reject_stale_values_before_rendering():
    assert 'if workspace.get("sort_direction") not in {"asc", "desc"}:' in APP_SOURCE
    assert 'if workspace.get("limit") not in {25, 50, 100}:' in APP_SOURCE
    assert 'if int(value) in role_options' in APP_SOURCE
    assert 'if int(value) in unit_options' in APP_SOURCE
    assert 'value=selected_role_ids' in APP_SOURCE
    assert 'value=selected_unit_ids' in APP_SOURCE


def test_open_saved_search_uses_the_approved_search_first_layout():
    dialog = APP_SOURCE[APP_SOURCE.index("async def open_saved_search_dialog"):]
    assert 'ui.input("Search saved searches")' in dialog
    assert 'ui.button("Filters", icon="tune")' in dialog
    assert 'with ui.tabs(value="all")' in dialog
    assert 'ui.tab("owned", label="Mine")' in dialog
    assert 'ui.tab("shared_with_me", label="Shared with me")' in dialog
    assert 'advanced_filters.set_visibility(False)' in dialog
    assert 'for item in page["items"]:' in dialog
    assert 'for category_name, items in categories.items()' not in dialog


def test_relevance_sort_refreshes_when_full_text_becomes_valid():
    assert 'node.__setitem__("query", event.value or ""),' in APP_SOURCE
    query_handler = APP_SOURCE[APP_SOURCE.index('node.__setitem__("query", event.value or ""),'):]
    assert 'update_search_enabled(), refresh_sort_options(), persist_workspace(),' in query_handler[:300]
    sources_handler = APP_SOURCE[APP_SOURCE.index('node.__setitem__("sources", event.value or []),'):]
    assert 'update_search_enabled(), refresh_sort_options(), persist_workspace(),' in sources_handler[:300]


def test_saved_search_administrator_sees_system_inventory_under_all():
    advanced_search = APP_SOURCE[APP_SOURCE.index("async def select_advanced_search"):]
    dialog = advanced_search[advanced_search.index("async def open_saved_search_dialog"):]
    assert 'administrator = "search.saved_search.administrator" in privileges' in dialog
    assert 'administrative_all = administrator and scope_control.value == "all"' in dialog
    assert 'api.saved_search_administration(**params) if administrative_all' in dialog
    assert 'ui.button("Administration"' not in advanced_search
    assert 'Saved-search administration' not in dialog


def test_advanced_search_uses_clearable_catalogues_and_classification_aggregation_browser():
    assert '"medium": {"digital": "Digital", "physical": "Physical", "mixed": "Mixed"}' in APP_SOURCE
    assert '"component.content_status": {' in APP_SOURCE
    assert 'and advanced_search_has_component_field(workspace["root"])' in APP_SOURCE
    assert 'Browse classification and aggregation hierarchy' in APP_SOURCE
    assert 'f"classification-schemes/{scheme_id}/roots"' in APP_SOURCE
    assert ').props("outlined dense clearable")' in APP_SOURCE
    assert 'if selected_value not in controlled_options:' in APP_SOURCE
    assert 'one file you are allowed "' in APP_SOURCE
    assert 'style_status_chip_select(value_control)' in APP_SOURCE
    assert '<q-chip outline color="primary" icon="task_alt"' in APP_SOURCE


def test_record_component_attributions_open_the_governed_viewer():
    assert "aria-label='Preview digital component'" in APP_SOURCE
    assert 'preview_record_components(record, component_id)' in APP_SOURCE
    assert 'workspace["record_component_details"] = dict(component_details)' in APP_SOURCE
    assert 'for component in search_meta.get("matching_components", [])' in APP_SOURCE
    assert '{**authorized_component_details.get(int(component["id"]), {}), **component}' in APP_SOURCE
    assert 'Preview is unavailable for this component' in APP_SOURCE


def test_advanced_search_builder_and_results_use_compact_aligned_layouts():
    assert 'advanced-search-condition w-full p-2' in APP_SOURCE
    assert 'advanced-search-group w-full p-2' in APP_SOURCE
    assert 'advanced-search-condition-actions items-center gap-0 self-end' in APP_SOURCE
    assert 'global-search-card-header w-full items-center gap-2 px-3 py-2' in APP_SOURCE
    assert 'advanced-search-result-actions items-center gap-0' in APP_SOURCE
    assert 'with ui.column().classes("w-full gap-1 px-3 py-2")' in APP_SOURCE


def test_each_advanced_search_preview_is_attributed_to_its_component():
    result_renderer = APP_SOURCE[
        APP_SOURCE.index("def render_results(result:"):
        APP_SOURCE.index("async def open_advanced_record")
    ]
    component_section = result_renderer[result_renderer.index("for component in matching_components:"):]
    assert 'ui.label(component.get("file_name") or "Digital component")' in component_section
    assert "aria-label='Preview digital component'" in component_section
    header_actions = result_renderer[
        result_renderer.index('advanced-search-result-actions items-center gap-0'):
        result_renderer.index('with ui.column().classes("w-full gap-1 px-3 py-2")')
    ]
    assert "visibility" not in header_actions


def test_global_and_advanced_search_open_actions_are_icon_only():
    assert 'aria-label=\'Open record\'' in APP_SOURCE
    assert 'aria-label=\'Open aggregation\'' in APP_SOURCE
    assert 'ui.button("Open record", icon="open_in_new"' not in APP_SOURCE
    assert 'ui.button("Open aggregation", icon="open_in_new"' not in APP_SOURCE
    assert "aria-label='Open result'" in APP_SOURCE
