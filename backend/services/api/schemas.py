from datetime import datetime
from typing import Annotated, Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AggregationCreate(ApiModel):
    parent_aggregation_id: int | None = None
    aggregation_number: NonBlankString
    title: NonBlankString
    description: str | None = None
    date_opened: datetime | None = None
    date_closed: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.date_opened is not None
            and self.date_closed is not None
            and self.date_closed < self.date_opened
        ):
            raise ValueError("date_closed cannot be earlier than date_opened")
        return self


class AggregationUpdate(ApiModel):
    parent_aggregation_id: int | None = None
    aggregation_number: NonBlankString | None = None
    title: NonBlankString | None = None
    description: str | None = None
    date_opened: datetime | None = None
    date_closed: datetime | None = None


class AggregationRead(ApiModel):
    id: int
    parent_aggregation_id: int | None
    aggregation_number: str
    title: str
    description: str | None
    date_created: datetime
    date_opened: datetime
    date_closed: datetime | None
    version: int


class RecordCreate(ApiModel):
    aggregation_id: int
    record_number: NonBlankString
    title: NonBlankString
    description: str | None = None
    date_originated: datetime | None = None


class RecordUpdate(ApiModel):
    aggregation_id: int | None = None
    record_number: NonBlankString | None = None
    title: NonBlankString | None = None
    description: str | None = None
    date_originated: datetime | None = None


class RecordRead(ApiModel):
    id: int
    aggregation_id: int
    record_number: str
    title: str
    description: str | None
    date_created: datetime
    date_originated: datetime
    version: int


class RecordDraftCreate(ApiModel):
    aggregation_id: int | None = None
    record_number: NonBlankString | None = None
    title: NonBlankString | None = None
    description: str | None = None
    date_originated: datetime | None = None


class RecordDraftUpdate(RecordDraftCreate):
    pass


class RecordDraftRead(ApiModel):
    id: int
    owner_user_id: int | None
    aggregation_id: int | None
    record_number: str | None
    title: str | None
    description: str | None
    date_originated: datetime | None
    date_created: datetime
    date_updated: datetime
    expires_at: datetime
    status: Literal["open", "committed"]
    version: int


class RecordDraftComponentRead(ApiModel):
    id: int
    draft_id: int
    component_order: int
    file_name: str
    date_created: datetime
    date_originated: datetime
    mime_type: str
    size_in_bytes: int
    checksum_algo: str
    checksum_value: str
    content_status: Literal["staged"] = "staged"
    storage_backend: Literal["temporary"] = "temporary"


class ComponentOrderItem(ApiModel):
    id: int
    component_order: int = Field(gt=0)


class ComponentReorderRequest(ApiModel):
    components: list[ComponentOrderItem]


class DigitalComponentCreate(ApiModel):
    record_id: int
    component_order: int = Field(gt=0)
    file_name: NonBlankString
    date_originated: datetime | None = None
    mime_type: NonBlankString
    size_in_bytes: int = Field(ge=0)
    checksum_algo: NonBlankString
    checksum_value: NonBlankString


class DigitalComponentUpdate(ApiModel):
    record_id: int | None = None
    component_order: int | None = Field(default=None, gt=0)
    file_name: NonBlankString | None = None
    date_originated: datetime | None = None
    mime_type: NonBlankString | None = None
    size_in_bytes: int | None = Field(default=None, ge=0)
    checksum_algo: NonBlankString | None = None
    checksum_value: NonBlankString | None = None


class DigitalComponentRead(ApiModel):
    id: int
    record_id: int
    component_order: int
    file_name: str
    date_created: datetime
    date_originated: datetime
    mime_type: str
    size_in_bytes: int
    checksum_algo: str
    checksum_value: str
    storage_backend: Literal["postgresql", "s3"]
    storage_key: str | None
    content_status: Literal["pending", "available", "failed", "quarantined", "deleted"]
    version: int


class EventHistoryRead(ApiModel):
    id: int
    occurred_at: datetime
    transaction_id: int
    entity_type: str
    entity_id: int
    operation: str
    actor_user_id: int | None
    actor_type: str
    source: str
    request_id: UUID | None
    correlation_id: UUID | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    changed_fields: list[str]
    reason: str | None
    metadata: dict[str, Any]


class OrgUnitCreate(ApiModel):
    parent_org_unit_id: int | None = None
    code: NonBlankString
    name: NonBlankString
    description: str | None = None


class OrgUnitUpdate(ApiModel):
    parent_org_unit_id: int | None = None
    code: NonBlankString | None = None
    name: NonBlankString | None = None
    description: str | None = None
    status: Literal["active", "inactive"] | None = None
    date_closed: datetime | None = None


class OrgUnitRead(ApiModel):
    id: int
    parent_org_unit_id: int | None
    code: str
    name: str
    description: str | None
    status: Literal["active", "inactive"]
    date_created: datetime
    date_closed: datetime | None
    version: int


class UserCreate(ApiModel):
    name: NonBlankString
    email: NonBlankString | None = None
    external_id: NonBlankString | None = None


class UserUpdate(ApiModel):
    name: NonBlankString | None = None
    email: NonBlankString | None = None
    external_id: NonBlankString | None = None
    status: Literal["active", "inactive", "suspended"] | None = None
    date_deactivated: datetime | None = None


class UserRead(ApiModel):
    id: int
    name: str
    email: str | None
    external_id: str | None
    status: Literal["active", "inactive", "suspended"]
    date_created: datetime
    date_deactivated: datetime | None
    version: int


class RoleCreate(ApiModel):
    org_unit_id: int
    supervisor_role_id: int | None = None
    code: NonBlankString
    name: NonBlankString
    description: str | None = None


class RoleUpdate(ApiModel):
    org_unit_id: int | None = None
    supervisor_role_id: int | None = None
    code: NonBlankString | None = None
    name: NonBlankString | None = None
    description: str | None = None
    status: Literal["active", "inactive"] | None = None
    date_deactivated: datetime | None = None


class RoleRead(ApiModel):
    id: int
    org_unit_id: int
    supervisor_role_id: int | None
    code: str
    name: str
    description: str | None
    status: Literal["active", "inactive"]
    date_created: datetime
    date_deactivated: datetime | None
    version: int


class UserRoleAssignmentCreate(ApiModel):
    user_id: int
    role_id: int
    assigned_by: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if (
            self.valid_from is not None
            and self.valid_until is not None
            and self.valid_until < self.valid_from
        ):
            raise ValueError("valid_until cannot be earlier than valid_from")
        return self


class UserRoleAssignmentUpdate(ApiModel):
    user_id: int | None = None
    role_id: int | None = None
    assigned_by: int | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class UserRoleAssignmentRead(ApiModel):
    id: int
    user_id: int
    role_id: int
    assigned_by: int | None
    date_assigned: datetime
    valid_from: datetime
    valid_until: datetime | None
    version: int


SearchOperator = Literal[
    "eq",
    "ne",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "not_in",
    "between",
    "is_null",
    "is_not_null",
    "contains_ci",
    "starts_with_ci",
    "ends_with_ci",
]


class SearchExpression(ApiModel):
    field: str | None = None
    operator: SearchOperator | None = None
    value: Any = None
    and_: list["SearchExpression"] | None = Field(default=None, alias="and", min_length=1)
    or_: list["SearchExpression"] | None = Field(default=None, alias="or", min_length=1)
    not_: "SearchExpression | None" = Field(default=None, alias="not")

    @model_validator(mode="after")
    def validate_expression_shape(self):
        comparison_keys = self.model_fields_set & {"field", "operator", "value"}
        logical_nodes = sum(
            node is not None for node in (self.and_, self.or_, self.not_)
        )
        is_comparison = self.field is not None or self.operator is not None

        if logical_nodes + int(is_comparison) != 1:
            raise ValueError("use exactly one comparison, and, or, or not expression")
        if logical_nodes and comparison_keys:
            raise ValueError("logical expressions cannot contain field, operator, or value")
        if is_comparison and (self.field is None or self.operator is None):
            raise ValueError("comparison expressions require field and operator")

        has_value = "value" in self.model_fields_set
        if is_comparison and self.operator in {"is_null", "is_not_null"} and has_value:
            raise ValueError(f"{self.operator} does not accept a value")
        if is_comparison and self.operator not in {"is_null", "is_not_null"}:
            if not has_value or self.value is None:
                raise ValueError(f"{self.operator} requires a non-null value")
        return self


class SearchSort(ApiModel):
    field: str
    direction: Literal["asc", "desc"] = "asc"


class SearchRequest(ApiModel):
    where: SearchExpression | None = None
    sort: list[SearchSort] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


SearchItem = TypeVar("SearchItem")


class SearchResponse(ApiModel, Generic[SearchItem]):
    items: list[SearchItem]
    total: int
    limit: int
    offset: int
    returned: int
