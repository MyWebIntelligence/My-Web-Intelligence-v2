"""Add search_query and search_result_log tables for the multi-API router.

Sprint: search-router (J2). Idempotent: ``safe=True`` skips tables that
already exist. Auto-discovered by ``migrations/migrate.py`` — nothing to
register manually.
"""

from mwi import model


def upgrade() -> None:
    """Create SearchQuery and SearchResultLog tables (safe / idempotent)."""
    tables = [model.SearchQuery, model.SearchResultLog]
    existing = set(model.DB.get_tables())
    fresh = [t for t in tables if t._meta.table_name not in existing]
    model.DB.create_tables(tables, safe=True)
    for t in tables:
        if t._meta.table_name in existing:
            print(f"Table {t._meta.table_name} already exists — skipping create")
        else:
            print(f"Created table {t._meta.table_name}")
    if not fresh:
        print("[migrate 010] no new search tables to create")
