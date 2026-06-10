"""Add word.lang for multilingual lemmatization + clean ltr/rtl pollution.

Sprint-multilang (2026-06). Two concerns:

1. `word.lang` (VARCHAR(10) DEFAULT 'fr') — the lemma now depends on the
   stemming language, so the logical key of `word` becomes (term, lang).
   Backfilling with 'fr' is CORRECT (not a stopgap): every pre-migration
   row was stemmed with the French Snowball stemmer.

2. Expressions polluted by the Mercury pipeline bug (P2): the text
   direction ('ltr'/'rtl') used to be written into `expression.lang`.
   Reset those values to '' (neutral for the language gate, see
   `core.is_language_compatible`). The code fix in readable_pipeline
   prevents repollution.
"""

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
    """Ensure word.lang exists and clean ltr/rtl values in expression.lang."""
    _add_column('word', "lang VARCHAR(10) DEFAULT 'fr'")
    with model.DB.atomic():
        # SQLite applies the column DEFAULT to existing rows, but stay
        # defensive for engines/paths where it would not.
        model.DB.execute_sql("UPDATE word SET lang = 'fr' WHERE lang IS NULL")
        cursor = model.DB.execute_sql(
            "UPDATE expression SET lang = '' WHERE lang IN ('ltr', 'rtl')")
        cleaned = getattr(cursor, 'rowcount', 0)
        if cleaned:
            print(f"Cleaned {cleaned} expression.lang value(s) polluted with ltr/rtl")
