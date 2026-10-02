"""Offline tests for the query guard (no database or API key needed)."""

import pytest

from src.agent.guard import UnsafeQuery, validate_select

MAX = 100


@pytest.mark.parametrize("sql", [
    "SELECT TOP 5 Name FROM SalesLT.Product",
    "select top 1 count(*) from SalesLT.Customer;",
    "SELECT DISTINCT TOP (10) Color FROM SalesLT.Product",
    "SELECT Name FROM SalesLT.Product ORDER BY Name OFFSET 0 ROWS FETCH NEXT 20 ROWS ONLY",
    "SELECT TOP 3 [Update] FROM t",                         # keyword inside [identifier]
    "SELECT TOP 3 Name FROM t WHERE Name = 'drop; table'",  # keyword/; inside a string
    "SELECT TOP 3 Name /* DELETE */ FROM t -- DROP",        # keywords inside comments
])
def test_allows_limited_select(sql):
    assert validate_select(sql, MAX) == sql.strip()


@pytest.mark.parametrize("sql", [
    "DELETE FROM SalesLT.Customer",
    "UPDATE SalesLT.Product SET ListPrice = 0",
    "INSERT INTO SalesLT.Product (Name) VALUES ('x')",
    "DROP TABLE SalesLT.Customer",
    "TRUNCATE TABLE SalesLT.Customer",
    "ALTER TABLE SalesLT.Customer ADD x int",
    "CREATE TABLE t (id int)",
    "MERGE t USING s ON 1=1 WHEN MATCHED THEN DELETE",
    "EXEC sp_who",
    "GRANT SELECT ON t TO public",
    "",
    "-- just a comment",
])
def test_rejects_non_select(sql):
    with pytest.raises(UnsafeQuery):
        validate_select(sql, MAX)


@pytest.mark.parametrize("sql", [
    "SELECT TOP 1 1; DROP TABLE t",                  # second statement
    "SELECT TOP 1 1; SELECT TOP 1 2",                # two SELECTs
    "SELECT TOP 1 * INTO newtable FROM t",           # SELECT INTO writes a table
    "SELECT TOP 1 * FROM OPENROWSET('x','y','z')",   # reaches outside the database
    "SELECT TOP 1 1 /* unterminated",                # unbalanced comment
    "SELECT TOP 1 'unterminated",                    # unbalanced string
    "SELECT TOP 1 1 WHERE 1=1 EXEC('DROP TABLE t')", # exec hidden mid-query
])
def test_rejects_smuggled_statements(sql):
    with pytest.raises(UnsafeQuery):
        validate_select(sql, MAX)


@pytest.mark.parametrize("sql", [
    "SELECT Name FROM SalesLT.Product",              # no limit
    "SELECT TOP 101 Name FROM SalesLT.Product",      # above MAX_ROWS
    "SELECT TOP 50 PERCENT Name FROM SalesLT.Product",
    "SELECT Name FROM t OFFSET 0 ROWS FETCH NEXT 500 ROWS ONLY",
])
def test_requires_row_limit(sql):
    with pytest.raises(UnsafeQuery):
        validate_select(sql, MAX)
