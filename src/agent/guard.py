"""Agent-side query guard: the last check before SQL reaches the MCP server.

Rule: only a single SELECT with a row limit may pass. This is one of three
layers (the others: a db_datareader-only database user, and a read-only MCP
server), so it must never be loosened to make a feature work.
"""

from __future__ import annotations

import re

class UnsafeQuery(ValueError):
    """The query is not a single, row-limited SELECT."""


# Things that may hide keywords or statements: string literals, "quoted" and
# [bracketed] identifiers, and comments. We blank them out before checking.
_MASK = re.compile(r"'(?:[^']|'')*'|\"[^\"]*\"|\[[^\]]*\]|--[^\n]*|/\*.*?\*/", re.S)

# Anything that changes data/schema, runs code, or reaches outside the database.
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC|EXECUTE|"
    r"GRANT|REVOKE|DENY|INTO|BACKUP|RESTORE|SHUTDOWN|WAITFOR|"
    r"OPENROWSET|OPENQUERY|OPENDATASOURCE|BULK|XP_\w+|SP_\w+)\b",
    re.I,
)

# The outer query must start with TOP n, or end with OFFSET .. FETCH NEXT n.
_TOP = re.compile(r"^SELECT\s+(?:DISTINCT\s+)?TOP\s*\(?\s*(\d+)(?!\d)\s*\)?(?!\s*PERCENT)", re.I)
_FETCH = re.compile(r"\bFETCH\s+(?:NEXT|FIRST)\s+(\d+)\s+ROWS?\s+ONLY\s*$", re.I)


def validate_select(sql: str, max_rows: int) -> str:
    """Return the cleaned SQL if it is a single limited SELECT, else raise UnsafeQuery."""
    # Blank out literals/comments so they can't smuggle in keywords or ';'.
    masked = _MASK.sub(" ", sql).strip()
    if "'" in masked or "/*" in masked or '"' in masked:
        raise UnsafeQuery("Unbalanced quote or comment in query.")
    if masked.endswith(";"):
        masked = masked[:-1].rstrip()
    if ";" in masked:
        raise UnsafeQuery("Only one statement is allowed.")
    if not re.match(r"SELECT\b", masked, re.I):
        raise UnsafeQuery("Only SELECT statements are allowed.")
    bad = _FORBIDDEN.search(masked)
    if bad:
        raise UnsafeQuery(f"Keyword not allowed: {bad.group(1).upper()}.")

    limit = _TOP.match(masked) or _FETCH.search(masked)
    if not limit:
        raise UnsafeQuery(f"Add a row limit: SELECT TOP n (n <= {max_rows}).")
    if int(limit.group(1)) > max_rows:
        raise UnsafeQuery(f"Row limit too large: use at most {max_rows} rows.")
    return sql.strip()
