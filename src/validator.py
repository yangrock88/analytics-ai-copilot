"""SQL validator: the guardrail between composed SQL and the warehouse.

Rules:
- single read-only statement (SELECT/WITH), nothing else -- ever
- no DDL/DML/pragma/attach/copy, no multiple statements, no comments tricks
- every table referenced must be in the registry allowlist
- a LIMIT is always present (inject the policy default if missing)
- dry-run EXPLAIN against the real engine before execution
"""

from __future__ import annotations

import re

import duckdb

FORBIDDEN = re.compile(
    r"\b(drop|delete|update|insert|alter|create|attach|detach|pragma|copy|"
    r"export|import|grant|revoke|truncate|replace|call|execute\s+immediate|"
    r"set|use|vacuum|install|load)\b",
    re.IGNORECASE,
)
TABLE_RE = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", re.IGNORECASE)


class ValidationError(ValueError):
    pass


def validate(sql: str, allowed_tables: set[str], default_limit: int,
             max_limit: int) -> str:
    text = sql.strip().rstrip(";")
    if ";" in text:
        raise ValidationError("multiple statements are not allowed")
    if not re.match(r"^(select|with)\b", text, re.IGNORECASE):
        raise ValidationError("only SELECT statements are allowed")
    if FORBIDDEN.search(text):
        raise ValidationError("statement contains a forbidden keyword")
    if "--" in text or "/*" in text:
        raise ValidationError("comments are not allowed in generated SQL")

    referenced = {t.lower() for t in TABLE_RE.findall(text)}
    unknown = referenced - {t.lower() for t in allowed_tables}
    if unknown:
        raise ValidationError(f"tables outside the governed registry: {sorted(unknown)}")

    limit_match = re.search(r"\blimit\s+(\d+)", text, re.IGNORECASE)
    if limit_match:
        n = int(limit_match.group(1))
        if n > max_limit:
            text = text[:limit_match.start()] + f"LIMIT {max_limit}" + text[limit_match.end():]
    else:
        text += f" LIMIT {default_limit}"
    return text


def dry_run(sql: str, warehouse: str) -> None:
    with duckdb.connect(warehouse, read_only=True) as con:
        try:
            con.execute(f"explain {sql}")
        except Exception as exc:
            raise ValidationError(f"SQL failed dry-run: {exc}") from exc
