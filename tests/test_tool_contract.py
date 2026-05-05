import pytest
from scripts.lib.tool_contract import assert_select_only, assert_no_mds, assert_no_bq_mcp

def test_select_only_allows_select():
    assert_select_only("SELECT * FROM foo")  # no raise

def test_select_only_rejects_insert():
    with pytest.raises(ValueError, match="non-SELECT"):
        assert_select_only("INSERT INTO foo VALUES (1)")

def test_select_only_rejects_create():
    with pytest.raises(ValueError, match="non-SELECT"):
        assert_select_only("CREATE OR REPLACE TABLE foo AS SELECT 1")

def test_select_only_rejects_delete():
    with pytest.raises(ValueError, match="non-SELECT"):
        assert_select_only("DELETE FROM foo WHERE 1=1")

def test_select_only_rejects_merge():
    with pytest.raises(ValueError, match="non-SELECT"):
        assert_select_only("MERGE INTO foo USING bar ON x")

def test_select_only_allows_with_cte():
    assert_select_only("WITH x AS (SELECT 1) SELECT * FROM x")  # no raise

def test_select_only_case_insensitive():
    with pytest.raises(ValueError):
        assert_select_only("insert into foo values (1)")

def test_no_mds_rejects_mds_url():
    with pytest.raises(ValueError, match="MDS"):
        assert_no_mds("https://mds.groupondev.com/deals/abc")

def test_no_mds_allows_other_url():
    assert_no_mds("https://www.groupon.com/deals/abc")  # no raise

def test_no_bq_mcp_rejects_mcp_tool_name():
    with pytest.raises(ValueError, match="BigQuery MCP"):
        assert_no_bq_mcp("mcp__bigquery__execute_sql")

def test_no_bq_mcp_allows_bq_cli():
    assert_no_bq_mcp("bq query --use_legacy_sql=false ...")  # no raise
