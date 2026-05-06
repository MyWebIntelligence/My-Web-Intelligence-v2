"""Add land.fullhtml and expression.html columns for HTML storage feature."""

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
    """Ensure land.fullhtml and expression.html exist."""
    _add_column('land', 'fullhtml INTEGER DEFAULT 0')
    _add_column('expression', 'html TEXT DEFAULT NULL')
