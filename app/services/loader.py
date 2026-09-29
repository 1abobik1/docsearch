"""Import of the test dataset (CSV) into the database."""

import ast
import csv
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import batched
from pathlib import Path

from app.domain import NewDocument
from app.repositories.documents import UnitOfWork

logger = logging.getLogger(__name__)

CSV_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class CsvFormatError(ValueError):
    pass


def parse_rubrics(raw: str) -> list[str]:
    """Rubrics are stored as a Python list literal, e.g. "['VK-1', 'VK-2']"."""
    if not raw.strip():
        return []
    try:
        value = ast.literal_eval(raw)  # safe: evaluates literals only
    except (ValueError, SyntaxError) as exc:
        raise CsvFormatError(f"Invalid rubrics value: {raw!r}") from exc
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise CsvFormatError(f"Rubrics must be a list of strings: {raw!r}")
    return value


def parse_created_date(raw: str) -> datetime:
    # The dataset has no timezone information; we treat timestamps as UTC.
    try:
        return datetime.strptime(raw.strip(), CSV_DATE_FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise CsvFormatError(f"Invalid created_date: {raw!r}") from exc


def read_csv(path: Path) -> Iterator[NewDocument]:
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"text", "created_date", "rubrics"} - set(reader.fieldnames or [])
        if missing:
            raise CsvFormatError(f"CSV is missing columns: {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            try:
                yield NewDocument(
                    rubrics=parse_rubrics(row["rubrics"]),
                    text=row["text"],
                    created_date=parse_created_date(row["created_date"]),
                )
            except CsvFormatError as exc:
                raise CsvFormatError(f"{path}:{line_no}: {exc}") from exc


async def load_csv(uow: UnitOfWork, path: Path, batch_size: int = 500) -> int:
    """Insert all rows in a single transaction: the import is all-or-nothing."""
    total = 0
    async with uow:
        for batch in batched(read_csv(path), batch_size, strict=False):
            total += len(await uow.documents.add_many(batch))
        await uow.commit()
    logger.info("Imported %d documents from %s", total, path)
    return total
