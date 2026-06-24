"""Add composite/secondary indexes on `expression` for the client read paths.

Sprint-indexing (2026-06). `expression` is the hot table for MyWebClient /
MyWebAPI: listing a land filtered by relevance / http_status / depth and
sorted by relevance, plus the per-land aggregations (status / fetch_method /
relevance distributions, domain rollups). On databases imported from the
legacy My Web Intelligence system, the `expression` table was created
WITHOUT the Peewee foreign-key / url indexes, so those queries fell back to
full table scans + temp b-tree sorts — catastrophic past ~100k rows.

Idempotent and defensive:
- every index uses `CREATE INDEX IF NOT EXISTS` (re-run = no-op);
- an index is skipped if one of its columns does not exist (legacy bases
  missing e.g. `fetch_method` are not broken — migration 009 adds it first
  in the normal in-order run);
- the single-column heal indexes (url, domain_id) are created only when no
  existing index already leads with that column, so a fresh `db setup`
  (which already has Peewee's `expression_url` / `expression_domain_id`) is
  not duplicated.

`(land_id, relevance, id)` also covers any bare `WHERE land_id = ?` via its
leftmost prefix, so no standalone land_id index is created here.
"""

from mwi import model


# Composite indexes (new names, never pre-exist on any base).
_COMPOSITE_INDEXES = (
    ("idx_expression_land_relevance", ["land_id", "relevance", "id"]),
    ("idx_expression_land_status",    ["land_id", "http_status"]),
    ("idx_expression_land_depth",     ["land_id", "depth"]),
    ("idx_expression_land_domain",    ["land_id", "domain_id"]),
    ("idx_expression_land_fetchm",    ["land_id", "fetch_method"]),
)

# Single-column heal indexes for legacy-imported bases.
_HEAL_INDEXES = (
    ("idx_expression_url",       "url"),
    ("idx_expression_domain_id", "domain_id"),
)


def _table_columns(table: str) -> set:
    """Return the set of column names of `table`."""
    return {row[1] for row in
            model.DB.execute_sql(f"PRAGMA table_info('{table}')").fetchall()}


def _leading_columns(table: str) -> set:
    """Return the set of columns that already lead an index on `table`."""
    cols = set()
    rows = model.DB.execute_sql(f"PRAGMA index_list('{table}')").fetchall()
    for row in rows:
        index_name = row[1]
        info = model.DB.execute_sql(
            f"PRAGMA index_info('{index_name}')").fetchall()
        if info:
            cols.add(info[0][2])  # column name at the first index position
    return cols


def upgrade() -> None:
    """Create the expression read-path indexes (idempotent)."""
    columns = _table_columns('expression')
    with model.DB.atomic():
        for name, index_cols in _COMPOSITE_INDEXES:
            missing = [c for c in index_cols if c not in columns]
            if missing:
                print(f"Skipping {name}: missing column(s) {missing}")
                continue
            cols_sql = ', '.join(index_cols)
            model.DB.execute_sql(
                f"CREATE INDEX IF NOT EXISTS {name} ON expression({cols_sql})")
            print(f"Ensured index {name} ON expression({cols_sql})")

        leading = _leading_columns('expression')
        for name, column in _HEAL_INDEXES:
            if column not in columns:
                print(f"Skipping {name}: column {column} absent")
                continue
            if column in leading:
                print(f"Column {column} already indexed — skipping {name}")
                continue
            model.DB.execute_sql(
                f"CREATE INDEX IF NOT EXISTS {name} ON expression({column})")
            print(f"Ensured heal index {name} ON expression({column})")

    # Refresh the query-planner statistics so the new indexes are picked up.
    model.DB.execute_sql("ANALYZE")
    print("ANALYZE done")
