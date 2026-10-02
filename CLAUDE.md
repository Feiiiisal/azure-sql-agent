# Project Rules

This project is an AI agent that answers plain-English questions about data by
querying an Azure SQL Database through an MCP server. Follow these rules for
every change.

## 1. Database access is read-only

- The agent may only run `SELECT` queries. Never write, generate or run
  `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`,
  `EXEC`, `GRANT` or any other statement that changes data or schema.
- Enforce this in layers:
  1. **Database:** connect as a dedicated user that has only the
     `db_datareader` role.
  2. **MCP server:** expose only read and schema-inspection tools.
  3. **Agent code:** before sending a query to the server, reject it unless
     it is a single `SELECT` statement.
- Put a row limit (`TOP n`) and a query timeout on every query.
- Never weaken these checks to make a feature work.

## 2. Never hardcode credentials

- No connection strings, passwords, API keys, tenant IDs or server names in
  source code, tests, docs or commit messages.
- Do not print or log secrets, and do not include them in error messages.

## 3. Use a `.env` file for configuration

- Load settings with `python-dotenv` and read them from environment variables.
- `.env` is listed in `.gitignore` and must never be committed.
- `.env.example` lists every required variable, with placeholder values only.
  When you add a new setting, add it to `.env.example` too.
- If a required variable is missing, fail early with a clear message that
  names the variable but never shows its value.

## 4. General conventions

- Python 3.10 or newer.
- Use the official `anthropic` SDK for Claude, and the `mcp` package for the
  MCP client. Default model: `claude-sonnet-5-5`, set through `ANTHROPIC_MODEL`.
- Show the user the SQL that produced each answer.
- Keep functions small and typed, and add tests for the query-validation logic.
