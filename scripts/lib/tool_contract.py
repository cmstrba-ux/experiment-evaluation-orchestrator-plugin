"""Tool-contract guards for the experiment-evaluation-orchestrator plugin.

Enforces:
 - BigQuery is read-only (SELECT / WITH only).
 - URL paths never touch mds.groupondev.com (Okta-headless requirement).
 - BigQuery never goes through MCP.
"""
import re

_FORBIDDEN_DML_DDL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE|REPLACE)\b",
    re.IGNORECASE,
)


def assert_select_only(sql: str) -> None:
    stripped = sql.strip()
    if not stripped:
        raise ValueError("Empty SQL")
    head = stripped.lstrip("(").lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise ValueError(f"Refusing non-SELECT statement: {stripped[:80]!r}")
    if _FORBIDDEN_DML_DDL.search(sql):
        raise ValueError(f"Refusing non-SELECT statement (DML/DDL keyword found): {stripped[:80]!r}")


def assert_no_mds(url: str) -> None:
    if "mds.groupondev.com" in url:
        raise ValueError(f"Refusing MDS URL (Okta dependency, not cloud-friendly): {url}")


def assert_no_bq_mcp(tool_name: str) -> None:
    lower = tool_name.lower()
    if "mcp" in lower and ("bigquery" in lower or "bq" in lower):
        raise ValueError(f"Refusing BigQuery MCP tool: {tool_name}. Use the bq CLI instead.")
