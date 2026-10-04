"""Shared Select variant whose options have already been filtered by the server.

NiceGUI's standard Select re-filters multiple options by their display label on
updates. That discards server matches on descriptions, email or other languages.
The public constructor has no switch to disable this second filtering pass.
Keep its Python value/selection API and render the bounded server options directly.
"""
from nicegui.elements.select import Select


class RemoteSelect(Select, component="remote_select.js"):
    def __init__(self, *args, **kwargs):
        self.option_details = {}
        super().__init__(*args, **kwargs)

    def _update_options(self):
        super()._update_options()
        # NiceGUI rebuilds ordinal option values on every update. Attach display
        # metadata by stable entity ID so retained selections keep their details.
        self.option_details = {
            key: details for key, details in self.option_details.items()
            if key in self._values
        }
        for option, key in zip(self._props['options'], self._values):
            option.update(self.option_details.get(key, {}))
