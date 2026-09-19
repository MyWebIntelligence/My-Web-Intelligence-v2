"""Migration 016 — perceptual fingerprint on media (R02 lot B, decision D-6).

Adds `media.perceptual_hash`: a 64-bit dHash stored as 16 hex characters.
`media.image_hash` (SHA-256 of the bytes) is NOT replaced — it stays the proof
of byte identity. The new column answers the other question: "is this the same
IMAGE?", so a photo reprinted by another outlet after a recompression or a
resize becomes measurable.

Plain ALTER TABLE ADD COLUMN, with the canonical idempotent guard: no table
rebuild is needed for a nullable column with no constraint.

The column is NULL for every media analysed before this migration — it cannot
be backfilled from the database, the bytes are not stored. `land reanalyze`
re-downloads and fills it (one GET per media).
"""
from mwi import model


def _add_column(table: str, definition: str) -> None:
    """Run a defensive ALTER TABLE, ignoring the duplicate column error."""
    with model.DB.atomic():
        try:
            model.DB.execute_sql(f"ALTER TABLE {table} ADD COLUMN {definition}")
        except Exception as exc:
            msg = str(exc).lower()
            if 'duplicate column name' in msg or 'already exists' in msg:
                print(f"Column already exists for {table}: {definition} — skipping")
            else:
                raise


def upgrade():
    print("Starting media perceptual hash migration (016)…")
    _add_column('media', 'perceptual_hash VARCHAR(16)')
    model.DB.execute_sql(
        "CREATE INDEX IF NOT EXISTS media_perceptual_hash "
        "ON media(perceptual_hash)")
    print("  media.perceptual_hash ready (NULL until `land reanalyze`)")
