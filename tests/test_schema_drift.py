import pytest
from scripts.lib.schema_drift import validate_required_columns

REQUIRED_TEST_DEFS = [
    "alternate_name", "experiment_name", "start_date", "end_date",
    "use_deal_category_split", "use_misc_split", "evaluate_automatically",
]
REQUIRED_REVIEW_EXP = [
    "event_date", "experimentname", "variantname", "country", "region",
    "clientPlatform", "groupon_version", "log_status", "active_visitor_flag",
    "UDV", "ue_orders", "margin_1_vfm", "distinct_bcookie_count",
]

def test_test_definitions_schema_has_required():
    validate_required_columns("fixtures/test_definitions.schema.json", REQUIRED_TEST_DEFS)

def test_review_experiments_schema_has_required():
    validate_required_columns("fixtures/review_experiments.schema.json", REQUIRED_REVIEW_EXP)

def test_missing_column_raises(tmp_path):
    f = tmp_path / "broken.json"
    f.write_text('[{"name":"foo","type":"STRING"}]')
    with pytest.raises(ValueError, match="Missing required columns"):
        validate_required_columns(str(f), ["foo", "bar"])
