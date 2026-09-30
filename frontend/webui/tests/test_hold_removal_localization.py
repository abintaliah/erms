"""Hold-removal callbacks localize their indirectly rendered dialog strings."""
import ast
import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

from frontend.webui.i18n_catalogue import render_message, set_active_messages


def test_record_and_aggregation_hold_removal_dialogs_use_arabic():
    root = Path(__file__).parents[1]
    arabic = {i['message_key']: i['translated_text'] for i in
              json.loads((root / 'i18n/messages.ar.generated.json').read_text())['items']}
    tree = ast.parse((root / 'app.py').read_text())
    set_active_messages(arabic)
    try:
        for name in ('remove_record_from_all_holds', 'remove_aggregation_from_all_holds'):
            function = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
            dialog = AsyncMock()
            scope = dict(render_message=render_message, hold_reason_dialog=dialog)
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<hold-removal>', 'exec'), scope)
            asyncio.run(scope[name]())
            title, action, _ = dialog.call_args.args
            assert title == arabic['webui.hold_reason_dialog.remove_all_confirmation']
            assert action == arabic['webui.open_aggregation.button.remove_direct_holds_d5ecb7ae']
    finally:
        set_active_messages({})
