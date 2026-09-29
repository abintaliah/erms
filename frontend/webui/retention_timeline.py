"""Shared, direction-aware three-stage retention presentation."""
from typing import Any, Callable

from nicegui import ui

from .i18n_catalogue import render_message


def render_retention_stages(rule: dict[str, Any], disposition_label: Callable) -> None:
    # Reuse the aggregation page's established stage layout and RTL rules.
    stages = (
        (render_message("entity_metadata.field.current_retention_years"),
         render_message("common.duration.years", count=rule["current_period_years"]),
         render_message("webui.open_aggregation.retention.business_unit")),
        (render_message("entity_metadata.field.intermediate_retention_years"),
         render_message("common.duration.years", count=rule["intermediate_period_years"]),
         render_message("webui.open_aggregation.retention.records_storage")),
        (render_message("entity_metadata.field.final_disposition"),
         disposition_label(rule["final_disposition"]),
         render_message("entity_metadata.field.final_disposition")),
    )
    with ui.element("div").classes("aggregation-retention-stages w-full"):
        for label, value, help_text in stages:
            with ui.column().classes("aggregation-retention-stage gap-0"):
                ui.label(render_message(
                    "webui.open_aggregation.label.stage_label_stage_value_026d5c3a",
                    stage_label=label, stage_value=value,
                )).classes("w-full text-sm font-semibold text-slate-800")
                ui.label(help_text).classes("w-full text-xs text-slate-500")
