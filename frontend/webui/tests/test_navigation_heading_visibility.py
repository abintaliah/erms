import ast
from pathlib import Path
from types import SimpleNamespace


def test_heading_tracks_async_link_visibility_and_collapsed_drawer():
    tree = ast.parse((Path(__file__).parents[1] / 'app.py').read_text())
    function = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
                    and n.name == 'refresh_drawer_headings')
    heading = SimpleNamespace()
    heading.set_visibility = lambda value: setattr(heading, 'visible', value)
    holds = SimpleNamespace(visible=False)
    namespace = {'drawer_links': [(holds, None, 'holds')],
                 'drawer_sections': [(heading, ('holds', 'profiles'))],
                 'drawer_collapsed': False}
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'heading', 'exec'), namespace)
    refresh = namespace['refresh_drawer_headings']
    refresh()
    assert not heading.visible
    holds.visible = True
    refresh()
    assert heading.visible
    namespace['drawer_collapsed'] = True
    refresh()
    assert not heading.visible
    namespace['drawer_collapsed'] = False
    holds.visible = False
    refresh()
    assert not heading.visible
