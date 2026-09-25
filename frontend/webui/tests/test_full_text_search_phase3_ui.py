from __future__ import annotations

import inspect

from frontend.webui import api_client
from frontend.webui.app import render_component_cards


def test_component_cards_offer_authorized_reindex_and_truthful_index_state():
    source=inspect.getsource(render_component_cards)
    assert 'capability_allowed(capabilities, "reindex_components")' in source
    assert 'icon="manage_search"' in source
    assert 'Index: {index_status' in source
    assert "Last indexed" in source


def test_api_client_exposes_component_record_and_status_operations():
    source=inspect.getsource(api_client.ErmsApiClient)
    assert 'f"/api/v1/digital-components/{component_id}/reindex"' in source
    assert 'f"/api/v1/records/{record_id}/reindex"' in source
    assert 'f"/api/v1/digital-components/{component_id}/indexing-status"' in source
