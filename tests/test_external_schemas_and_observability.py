import pytest

from UK_news_scraper.errors import ValidationError
from UK_news_scraper.external_schemas import validate_parliament_api_payload
from UK_news_scraper.observability import evaluate_observability_budget


def test_parliament_schema_rejects_missing_items():
    with pytest.raises(ValidationError):
        validate_parliament_api_payload({"result": {}})


def test_observability_budget_reports_excesses():
    assert set(evaluate_observability_budget(success_rate=0.8, p95_seconds=100, zero_item_ratio=0.5, peak_memory_mb=90)) == {
        "source_success_rate", "source_p95_seconds", "zero_item_ratio", "peak_memory_mb_100k"
    }
