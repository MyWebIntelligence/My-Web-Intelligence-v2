"""Add expressionlink.kind/kind_rule/origin columns (sprint body-links)."""

from mwi import model


def _add_column(table: str, definition: str) -> None:
    """Run a defensive ALTER TABLE, ignoring the duplicate column error."""
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
    """Ensure expressionlink.kind, .kind_rule and .origin exist.

    No backfill: NULL means `body` everywhere it is read, so rewriting
    hundreds of thousands of rows would buy nothing.
    """
    _add_column('expressionlink', 'kind TEXT DEFAULT NULL')
    _add_column('expressionlink', 'kind_rule TEXT DEFAULT NULL')
    _add_column('expressionlink', 'origin TEXT DEFAULT NULL')
