from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": 42,
                "rubrics": ["VK-1603736028819866", "VK-11879320040"],
                "text": "Конкурс на новый скин!",
                "created_date": "2019-07-25T12:42:13Z",
            }
        },
    )

    id: int = Field(description="Unique document id")
    rubrics: list[str] = Field(description="Rubrics the document belongs to")
    text: str = Field(description="Document text")
    created_date: datetime = Field(description="Creation date (UTC)")


class SearchResponse(BaseModel):
    items: list[DocumentOut] = Field(
        description="Up to 20 most relevant documents, ordered by `created_date` (newest first)"
    )


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str
    checks: dict[str, bool] = Field(default_factory=dict)
