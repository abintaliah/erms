from dataclasses import dataclass


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    kind: str = "text"
    required: bool = False
    lookup_resource: str | None = None
    lookup_label_fields: tuple[str, ...] = ()


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
        (FieldSpec("parent_aggregation_id", "Parent aggregation", "lookup", lookup_resource="aggregations", lookup_label_fields=("aggregation_number", "title")), FieldSpec("classification_id", "Classification", "classification", lookup_resource="classifications", lookup_label_fields=("code", "title")), FieldSpec("aggregation_number", "Aggregation number", required=True), FieldSpec("title", "Title", required=True), FieldSpec("description", "Description", "textarea"), FieldSpec("date_opened", "Date opened", "datetime"), FieldSpec("date_closed", "Date closed", "datetime")),
        True, ("aggregation_number", "title", "description"),
    ),
    "records": EntitySpec(
        "records", "Records", "record",
        (("record_number", "Number"), ("title", "Title"), ("aggregation_display", "Aggregation"), ("date_originated", "Originated")),
        (FieldSpec("aggregation_id", "Aggregation", "lookup", True, "aggregations", ("aggregation_number", "title")), FieldSpec("record_number", "Record number", required=True), FieldSpec("title", "Title", required=True), FieldSpec("description", "Description", "textarea"), FieldSpec("date_originated", "Date originated", "datetime")),
        True, ("record_number", "title", "description"),
    ),
    "classification-schemes": EntitySpec(
        "classification-schemes", "Classification schemes", "classification scheme",
        (("code", "Code"), ("title", "Title"), ("date_published", "Published"), ("date_deactivated", "Deactivated")),
        (FieldSpec("code", "Code", required=True), FieldSpec("title", "Title", required=True), FieldSpec("description", "Description", "textarea"), FieldSpec("authority", "Authority"), FieldSpec("scope_note", "Scope note", "textarea"), FieldSpec("edition", "Edition"), FieldSpec("date_published", "Date published", "datetime")),
        False, ("code", "title", "description"),
    ),
    "classifications": EntitySpec(
        "classifications", "Classifications", "classification",
        (("code", "Code"), ("title", "Title"), ("type_display", "Type"), ("scheme_display", "Scheme")),
        (
            FieldSpec("classification_scheme_id", "Classification scheme", "lookup", True, "classification-schemes", ("code", "title")),
            FieldSpec("parent_classification_id", "Parent classification", "lookup", False, "classifications", ("code", "title")),
            FieldSpec("code", "Code", required=True), FieldSpec("title", "Title", required=True),
            FieldSpec("description", "Description", "textarea"), FieldSpec("authority", "Authority"),
            FieldSpec("scope_note", "Scope note", "textarea"), FieldSpec("keywords", "Keywords"),
            FieldSpec("is_terminal", "Classification type", "classification_type", True),
            FieldSpec("current_period_years", "Current retention (years)", "int"),
            FieldSpec("intermediate_period_years", "Intermediate retention (years)", "int"),
            FieldSpec("final_disposition", "Final disposition", "disposition"),
            FieldSpec("instructions", "Retention and disposal instructions", "textarea"),
        ),
        True, ("code", "title", "description", "keywords"),
    ),
    "org-units": EntitySpec(
        "org-units", "Organization units", "organization unit",
        (("code", "Code"), ("name", "Name"), ("effective_status", "Status"), ("parent_org_unit_display", "Parent")),
        (FieldSpec("parent_org_unit_id", "Parent organization unit", "lookup", lookup_resource="org-units", lookup_label_fields=("code", "name")), FieldSpec("code", "Code", required=True), FieldSpec("name", "Name", required=True), FieldSpec("description", "Description", "textarea")),
    ),
    "users": EntitySpec(
        "users", "Users", "user",
        (("_avatar", ""), ("name", "Name"), ("email", "Email"), ("account_type", "Account type"), ("effective_status", "Status")),
        (FieldSpec("name", "Name", required=True), FieldSpec("email", "Email"), FieldSpec("external_id", "External ID"), FieldSpec("account_type", "Account type", "account_type", True)),
    ),
    "roles": EntitySpec(
        "roles", "Roles", "role",
        (("code", "Code"), ("name", "Name"), ("org_unit_display", "Organization unit"), ("effective_status", "Status")),
        (FieldSpec("org_unit_id", "Organization unit", "lookup", True, "org-units", ("code", "name")), FieldSpec("supervisor_role_id", "Supervising role", "lookup", False, "roles", ("code", "name")), FieldSpec("code", "Code", required=True), FieldSpec("name", "Name", required=True), FieldSpec("description", "Description", "textarea")),
    ),
}
