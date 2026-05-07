"""Add expression.fetch_method column for cascade audit (sprint-403 Sprint 4).

Records which fetch strategy provided the HTML for each expression
('aiohttp', 'curl_cffi', 'playwright', 'archive_org'). NULL when the
expression has not been crawled yet or pre-dates this migration.
"""

from mwi import model


def _add_column(table: str, definition: str) -> None:
    """Defensive ALTER TABLE, ignoring duplicate-column errors."""
    with model.DB.atomic():
        try:
            model.DB.execute_sql(f"ALTER TABLE {table} ADD COLUMN {definition}")
            print(f"Added column on {table}: {definition}")
        except Exception as exc:
            msg = str(exc).lower()
            if 'duplicate column name' in msg or 'already exists' in msg:
                print(f"Column already exists for {table}: {definition} — skipping")
            else:
                raise


def upgrade() -> None:
    """Ensure expression.fetch_method exists."""
    _add_column('expression', 'fetch_method TEXT DEFAULT NULL')
