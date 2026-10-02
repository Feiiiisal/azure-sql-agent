"""Launch the read-only mcp-mssql server with settings loaded from .env.

Builds the connection string at runtime so no credentials ever appear in
.mcp.json or any other committed file. Write access stays disabled.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIRED_VARS = (
    "AZURE_SQL_SERVER",
    "AZURE_SQL_DATABASE",
    "AZURE_SQL_USERNAME",
    "AZURE_SQL_PASSWORD",
)
# mcp-mssql hard ceilings for the query tool.
MAX_ROWS_CEILING = 1000
TIMEOUT_CEILING_SECONDS = 300


def require_env(name: str) -> str:
    """Return a required variable or exit, naming it without showing any value."""
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Missing required environment variable: {name} (set it in .env)")
    return value


def quote_value(value: str) -> str:
    """Quote a connection-string value if it contains special characters."""
    if any(ch in value for ch in ";'\"=") or value != value.strip():
        return '"' + value.replace('"', '""') + '"'
    return value


def bounded_int(name: str, default: int, ceiling: int) -> int:
    """Read a positive integer setting, clamped to the server's ceiling."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        sys.exit(f"Environment variable {name} must be an integer")
    if value < 1:
        sys.exit(f"Environment variable {name} must be at least 1")
    return min(value, ceiling)


def build_connection_string() -> str:
    """Build an encrypted SQL-authentication connection string."""
    server, database, user, password = (require_env(n) for n in REQUIRED_VARS)
    parts = {
        "Server": f"tcp:{server},1433",
        "Database": database,
        "User ID": user,
        "Password": password,
        "Encrypt": "True",
        "TrustServerCertificate": "False",
        # Allow time for a paused serverless database to resume.
        "Connect Timeout": "60",
        "Application Name": "azure-sql-agent-mcp",
    }
    return ";".join(f"{k}={quote_value(v)}" for k, v in parts.items()) + ";"


def find_server_executable() -> str:
    """Locate the mcp-mssql .NET global tool."""
    found = shutil.which("mcp-mssql")
    if found:
        return found
    fallback = Path.home() / ".dotnet" / "tools" / "mcp-mssql.exe"
    if fallback.exists():
        return str(fallback)
    sys.exit("mcp-mssql not found; install it with: "
             "dotnet tool install --global Alyio.McpMssql --prerelease")


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    env = os.environ.copy()
    env["MCPMSSQL_CONNECTION_STRING"] = build_connection_string()
    max_rows = str(bounded_int("MAX_ROWS", 100, MAX_ROWS_CEILING))
    timeout = str(bounded_int("QUERY_TIMEOUT_SECONDS", 30, TIMEOUT_CEILING_SECONDS))
    # Apply the same limits to every query path, including snapshots and plans.
    env["MCPMSSQL_QUERY_MAX_ROWS"] = max_rows
    env["MCPMSSQL_QUERY_SNAPSHOT_MAX_ROWS"] = max_rows
    env["MCPMSSQL_QUERY_COMMAND_TIMEOUT_SECONDS"] = timeout
    env["MCPMSSQL_QUERY_SNAPSHOT_COMMAND_TIMEOUT_SECONDS"] = timeout
    env["MCPMSSQL_ANALYZE_COMMAND_TIMEOUT_SECONDS"] = timeout
    # Never allow the write tool, even if set elsewhere in the environment.
    env["MCPMSSQL_ALLOW_WRITE"] = "false"
    return subprocess.call([find_server_executable()], env=env)


if __name__ == "__main__":
    sys.exit(main())
