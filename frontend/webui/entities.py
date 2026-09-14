from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str = "text"
    required: bool = False


@dataclass(frozen=True)
class EntitySpec:
    key: str
    label: str
    singular: str
    columns: tuple[tuple[str, str], ...]
    fields: tuple[FieldSpec, ...]
    search_first: bool = False
    search_fields: tuple[str, ...] = ()


ENTITIES = {
    "aggregations": EntitySpec(
        "aggregations", "Aggregations", "aggregation",
        (("aggregation_number", "Number"), ("title", "Title"), ("date_opened", "Opened"), ("date_closed", "Closed")),
        (FieldSpec("parent_aggregation_id", "Parent aggregation ID", "int"), FieldSpec("aggregation_number", "Aggregation number", required=True), FieldSpec("title", "Title", required=True), FieldSpec("description", "Description", "textarea"), FieldSpec("date_opened", "Date opened", "datetime"), FieldSpec("date_closed", "Date closed", "datetime")),
        True, ("aggregation_number", "title", "description"),
    ),
    "records": EntitySpec(
        "records", "Records", "record",
        (("record_number", "Number"), ("title", "Title"), ("aggregation_id", "Aggregation"), ("date_originated", "Originated")),
        (FieldSpec("aggregation_id", "Aggregation ID", "int", True), FieldSpec("record_number", "Record number", required=True), FieldSpec("title", "Title", required=True), FieldSpec("description", "Description", "textarea"), FieldSpec("date_originated", "Date originated", "datetime")),
        True, ("record_number", "title", "description"),
    ),
    "org-units": EntitySpec(
        "org-units", "Organization units", "organization unit",
        (("code", "Code"), ("name", "Name"), ("status", "Status"), ("parent_org_unit_id", "Parent")),
        (FieldSpec("parent_org_unit_id", "Parent unit ID", "int"), FieldSpec("code", "Code", required=True), FieldSpec("name", "Name", required=True), FieldSpec("description", "Description", "textarea")),
    ),
    "users": EntitySpec(
        "users", "Users", "user",
        (("name", "Name"), ("email", "Email"), ("external_id", "External ID"), ("status", "Status")),
        (FieldSpec("name", "Name", required=True), FieldSpec("email", "Email"), FieldSpec("external_id", "External ID")),
    ),
    "roles": EntitySpec(
        "roles", "Roles", "role",
        (("code", "Code"), ("name", "Name"), ("org_unit_id", "Organization unit"), ("status", "Status")),
        (FieldSpec("org_unit_id", "Organization unit ID", "int", True), FieldSpec("supervisor_role_id", "Supervisor role ID", "int"), FieldSpec("code", "Code", required=True), FieldSpec("name", "Name", required=True), FieldSpec("description", "Description", "textarea")),
    ),
}
