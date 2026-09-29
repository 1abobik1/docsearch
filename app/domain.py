from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class NewDocument:
    rubrics: list[str]
    text: str
    created_date: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class Document(NewDocument):
    id: int
