from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.services.loader import CsvFormatError, parse_created_date, parse_rubrics, read_csv

DATASET = Path(__file__).resolve().parents[2] / "data" / "posts.csv"


def test_parse_rubrics() -> None:
    assert parse_rubrics("['VK-1', 'VK-2']") == ["VK-1", "VK-2"]
    assert parse_rubrics("[]") == []
    assert parse_rubrics("") == []


@pytest.mark.parametrize("raw", ["VK-1", "[1, 2]", "{'a': 1}", "__import__('os')"])
def test_parse_rubrics_rejects_garbage(raw: str) -> None:
    with pytest.raises(CsvFormatError):
        parse_rubrics(raw)


def test_parse_created_date_is_utc() -> None:
    assert parse_created_date("2019-07-25 12:42:13") == datetime(
        2019, 7, 25, 12, 42, 13, tzinfo=UTC
    )


def test_parse_created_date_rejects_garbage() -> None:
    with pytest.raises(CsvFormatError):
        parse_created_date("yesterday")


def test_reads_the_whole_dataset() -> None:
    docs = list(read_csv(DATASET))

    assert len(docs) == 1500
    assert all(d.text and d.rubrics and d.created_date.tzinfo for d in docs)


def test_reports_line_number_on_error(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("text,created_date,rubrics\nok,2019-01-01 00:00:00,[]\nbad,oops,[]\n")

    with pytest.raises(CsvFormatError, match=r"bad\.csv:3"):
        list(read_csv(path))


def test_reports_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("text,rubrics\n")

    with pytest.raises(CsvFormatError, match="created_date"):
        list(read_csv(path))
