"""Add expression.original_url column for URL provenance tracking.

Sprint 'normalise' — populated by add_expression when url_normalizer
transforms the input URL. NULL when the input was already canonical.
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
    """Ensure expression.original_url exists."""
    _add_column('expression', 'original_url TEXT DEFAULT NULL')
