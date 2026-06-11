"""Add expressionlink.context/dom/dom_html columns (sprint link-context)."""

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
    """Ensure expressionlink.context, .dom and .dom_html exist."""
    _add_column('expressionlink', 'context TEXT DEFAULT NULL')
    _add_column('expressionlink', 'dom TEXT DEFAULT NULL')
    _add_column('expressionlink', 'dom_html TEXT DEFAULT NULL')
