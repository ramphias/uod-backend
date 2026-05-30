"""Pydantic v2 request/response shapes for the API.

These are deliberately a superset of the Git `instance_schema.json`: the
backend stores additional bookkeeping fields (audit timestamps) that the
demo files don't carry. Conversion happens at the router boundary.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

InstanceStatus = Literal["candidate", "accepted", "rejected", "archived"]
InstanceSource = Literal[
    "manual",
    "wikidata",
    "dbpedia",
    "sec_edgar",
    "openalex",
    "llm_extracted",
    "other",
]


class InstanceBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    type: Annotated[str, Field(pattern=r"^[A-Z][a-zA-Z0-9]*$")]
    layer: str
    label_en: str | None = None
    label_zh: str | None = None
    data: dict = Field(default_factory=dict)
    schema_version: str
    source: InstanceSource
    source_url: str | None = None
    source_id: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    status: InstanceStatus = "candidate"

    @field_validator("label_en", "label_zh", mode="after")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class InstanceCreate(InstanceBase):
    id: Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", min_length=2)]


class InstanceUpdate(BaseModel):
    """Partial update payload — all fields optional."""

    model_config = ConfigDict(populate_by_name=True)

    label_en: str | None = None
    label_zh: str | None = None
    data: dict | None = None
    source_url: str | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    status: InstanceStatus | None = None


class InstanceRead(InstanceBase):
    id: str
    harvested_at: AwareDatetime
    verified_by: str | None = None
    verified_at: AwareDatetime | None = None


class InstanceList(BaseModel):
    items: list[InstanceRead]
    total: int
    limit: int
    offset: int


class VerifyRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RejectRequest(BaseModel):
    reason: Annotated[str, Field(min_length=1, max_length=500)]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: Literal["up", "down"]
    timestamp: datetime
