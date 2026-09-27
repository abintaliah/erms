"""Browser direction helpers shared by the Wathiq WebUI."""
from __future__ import annotations

import json


def normalize_direction(value: object) -> str:
    return "rtl" if str(value).lower() == "rtl" else "ltr"


def document_direction_script(language_tag: str, direction: str) -> str:
    """Return the script that applies direction to the root and portal content."""
    language = json.dumps(language_tag)
    normalized = json.dumps(normalize_direction(direction))
    return f"""
(() => {{
  const language = {language};
  const direction = {normalized};
  const apply = (node) => {{
    if (!(node instanceof Element)) return;
    if (node.matches('.q-menu, .q-dialog, .q-notifications, [role="dialog"], [role="menu"], [role="listbox"]')) {{
      node.setAttribute('lang', language);
      node.setAttribute('dir', direction);
    }}
    node.querySelectorAll?.('.q-menu, .q-dialog, .q-notifications, [role="dialog"], [role="menu"], [role="listbox"]').forEach(apply);
  }};
  document.documentElement.lang = language;
  document.documentElement.dir = direction;
  document.body?.setAttribute('dir', direction);
  document.body?.classList.toggle('wathiq-rtl', direction === 'rtl');
  apply(document.body);
  window.__wathiqDirectionObserver?.disconnect();
  window.__wathiqDirectionObserver = new MutationObserver(records =>
    records.forEach(record => record.addedNodes.forEach(apply))
  );
  if (document.body) window.__wathiqDirectionObserver.observe(document.body, {{childList:true, subtree:true}});
  localStorage.setItem('wathiq.language', language);
  localStorage.setItem('wathiq.direction', direction);
  return {{language, direction}};
}})()
""".strip()
