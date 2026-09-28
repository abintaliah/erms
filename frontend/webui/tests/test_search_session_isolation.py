"""Search state must not survive an authentication boundary (no database needed)."""
import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

SOURCE = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())


def load(name, namespace):
    node = next(n for n in ast.walk(SOURCE)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'app.py', 'exec'), namespace)
    return namespace[name]


def test_logout_discards_query_results_and_diagnostics():
    state = dict(global_search_revision=4, global_search_query='private query',
                 global_search_items=[{'record': {'id': 42}}], search_diagnostics_sent={'private': True})
    control = SimpleNamespace(value='private query', update=lambda: None)
    load('clear_global_search_session', {'state': state, 'global_search_input': control})()
    assert control.value == state['global_search_query'] == ''
    assert state['global_search_items'] == []
    assert state['search_diagnostics_sent'] is None
    assert state['global_search_revision'] == 5


def test_old_search_response_cannot_repopulate_new_session():
    async def scenario():
        state = dict(resource='full-text-search', global_search_revision=0,
                     search_diagnostics_enabled=False, global_search_items=[])
        principal = {'principal': {'id': 1}}
        started, release = asyncio.Event(), asyncio.Event()
        renders = []
        async def search(payload):
            started.set()
            await release.wait()
            return {'items': [{'type': 'aggregation', 'id': 42}]}
        control = SimpleNamespace(value='private query', update=lambda: None)
        namespace = dict(state=state, auth_state=principal, Any=Any, json=json, asyncio=asyncio,
                         global_search_input=control, ApiError=RuntimeError,
                         global_search_payload=lambda *a, **k: {},
                         render_message=lambda *a: '', show_authenticated_view=lambda: None,
                         render_global_search_results=lambda: renders.append(True),
                         api=SimpleNamespace(full_text_search=search),
                         title=SimpleNamespace(text=''), subtitle=SimpleNamespace(text=''))
        for name in ('search_bar', 'aggregation_mode_bar', 'add_button', 'add_record_button'):
            namespace[name] = SimpleNamespace(set_visibility=lambda v: None)
        run = load('run_global_search', namespace)
        clear = load('clear_global_search_session', namespace)
        task = asyncio.create_task(run('private query', load_more=True))
        await started.wait()
        clear()
        principal['principal'] = {'id': 2}
        release.set()
        await task
        assert state['global_search_items'] == []
        assert state['global_search_query'] == ''
        assert len(renders) == 1  # only the original loading render
    asyncio.run(scenario())
