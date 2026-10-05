"""An export keeps the readable identity of the generated scheme snapshot."""
import ast
from pathlib import Path
from typing import Any


def test_export_identity_prefers_export_snapshot_to_renamed_current_entity():
    tree = ast.parse((Path(__file__).parents[1]/'app.py').read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='event_entity_identity')
    namespace = {'Any':Any,'render_message':lambda key,**params:params['title']}
    exec(compile(ast.Module(body=[function],type_ignores=[]),'app.py','exec'),namespace)
    event = dict(entity_type='classification_scheme',entity_id=42,operation='EXPORT',metadata={'scheme':{'id':42,'code':'ORIGINAL','title':'Exported title'}},_current_entity={'code':'RENAMED','title':'Current title'})
    assert namespace['event_entity_identity'](event)[1] == 'ORIGINAL — Exported title'
    event.pop('_current_entity')
    assert namespace['event_entity_identity'](event)[1] == 'ORIGINAL — Exported title'
