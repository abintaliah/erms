import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_untouched_translation_fields_do_not_block_unrelated_metadata_save():
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    state_node = next(node for node in ast.walk(tree) if isinstance(node, ast.AnnAssign)
                      and isinstance(node.target, ast.Name) and node.target.id == 'translation_state')
    pending = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                   and node.name == 'pending_entity_translation')
    state = eval(compile(ast.Expression(state_node.value), 'state', 'eval'), {
        'multilingual_fields': {'roles': ('name', 'description')}, 'spec': SimpleNamespace(key='roles'),
    })
    controls = {field: SimpleNamespace(value=None) for field in ('name', 'description')}
    namespace = {'translation_state': state, 'translation_controls': controls,
                 'language_control': SimpleNamespace(value=None), 'render_message': lambda key: key}
    exec(compile(ast.Module(body=[pending], type_ignores=[]), 'pending', 'exec'), namespace)
    assert namespace['pending_entity_translation']() is None
    controls['name'].value = 'Actual translation edit'
    with pytest.raises(ValueError, match='load_the_selected_language'):
        namespace['pending_entity_translation']()
