from __future__ import annotations


PERMISSION_DEPENDENCIES = {
    "aggregation.modify_metadata": {"aggregation.view"},
    "aggregation.delete": {"aggregation.view"},
    "aggregation.close": {"aggregation.view"},
    "aggregation.reopen": {"aggregation.view"},
    "aggregation.add_child": {"aggregation.view"},
    "aggregation.add_record": {"aggregation.view"},
    "aggregation.move": {"aggregation.view"},
    "aggregation.receive_child": {"aggregation.view"},
    "aggregation.receive_record": {"aggregation.view"},
    "aggregation.reclassify": {"aggregation.view"},
    "aggregation.security_level.change": {"aggregation.view"},
    "aggregation.acl.manage": {"aggregation.view"},
    "aggregation.history.view": {"aggregation.view"},
    "record.modify_metadata": {"record.view"},
    "record.delete": {"record.view"},
    "record.move": {"record.view"},
    "record.security_level.change": {"record.view"},
    "record.acl.manage": {"record.view"},
    "record.history.view": {"record.view"},
    "record.component.list": {"record.view"},
    "record.component.view": {"record.component.list", "record.view"},
    "record.component.download": {"record.component.list", "record.view"},
    "record.component.add": {"record.component.list", "record.view"},
    "record.component.replace": {"record.component.list", "record.view"},
    "record.component.remove": {"record.component.list", "record.view"},
    "record.component.reorder": {"record.component.list", "record.view"},
    "record.component.share": {"record.component.view", "record.component.list", "record.view"},
    "record.component.print": {"record.component.view", "record.component.list", "record.view"},
}


def permission_closure(selected: set[str]) -> set[str]:
    closed = set(selected)
    while True:
        expanded = closed | {required for code in closed for required in PERMISSION_DEPENDENCIES.get(code, set())}
        if expanded == closed:
            return closed
        closed = expanded


def dependents_of(permission: str, selected: set[str]) -> set[str]:
    return {code for code in selected if permission in permission_closure({code}) and code != permission}


def acl_grants_payload(principals: list[dict]) -> list[dict]:
    """Convert ACL read rows into the API's strict grant write contract."""
    return [
        {
            "principal_type": principal["principal_type"],
            "role_id": principal.get("role_id"),
            "permission_codes": list(principal.get("permission_codes", [])),
        }
        for principal in principals
    ]
