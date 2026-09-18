"""Migration 015 — one paragraph OCCURRENCE per page (A11 / decision D-1).

`paragraph.text_hash` was UNIQUE across the whole database, so the first page
vectorised anywhere owned that text: the same paragraph on two pages produced
one row, the pair was invisible to `embedding similarity`, and results depended
on the order in which lands had been processed. The logical key becomes
`(expression_id, text_hash)`.

Two shapes exist in the wild and they are NOT repaired the same way:

- **named unique index** (`origin='c'`, database built by `db setup`): the
  index is droppable, so a DROP + two CREATE INDEX are enough;
- **inline UNIQUE column constraint** (`origin='u'`, database built by
  migration 003): SQLite implements it as an *autoindex*, which cannot be
  dropped. The table has to be rebuilt.

Detection is STRUCTURAL (`PRAGMA index_list` + `PRAGMA index_info`), never by
version number: a database can have gone through either path.

Idempotent: a database already keyed per expression prints "skipping" and is
left byte-identical.
"""
from mwi import model

TARGET_UNIQUE = ['expression_id', 'text_hash']
UNIQUE_INDEX_NAME = 'paragraph_expression_id_text_hash'
PLAIN_INDEX_NAME = 'paragraph_text_hash'

PARAGRAPH_DDL = """
CREATE TABLE paragraph_new (
    id INTEGER PRIMARY KEY,
    expression_id INTEGER NOT NULL REFERENCES expression(id) ON DELETE CASCADE,
    domain_id INTEGER NOT NULL REFERENCES domain(id) ON DELETE CASCADE,
    para_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash VARCHAR(64) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

COUNTED_TABLES = ('paragraph', 'paragraph_embedding', 'paragraph_similarity')


def _index_columns(name):
    return [row[2] for row in
            model.DB.execute_sql("PRAGMA index_info('%s')" % name).fetchall()]


def _global_unique_index():
    """Return (name, origin) of a UNIQUE index on text_hash alone, or None."""
    for row in model.DB.execute_sql(
            "PRAGMA index_list('paragraph')").fetchall():
        name, unique, origin = row[1], row[2], row[3]
        if not unique:
            continue
        if _index_columns(name) == ['text_hash']:
            return name, origin
    return None


def _has_target_unique():
    for row in model.DB.execute_sql(
            "PRAGMA index_list('paragraph')").fetchall():
        if row[2] and _index_columns(row[1]) == TARGET_UNIQUE:
            return True
    return False


def _counts():
    out = {}
    for table in COUNTED_TABLES:
        out[table] = model.DB.execute_sql(
            "SELECT COUNT(*) FROM %s" % table).fetchone()[0]
    return out


def _create_target_indexes():
    model.DB.execute_sql(
        "CREATE INDEX IF NOT EXISTS %s ON paragraph(text_hash)"
        % PLAIN_INDEX_NAME)
    model.DB.execute_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS %s ON paragraph(%s)"
        % (UNIQUE_INDEX_NAME, ', '.join(TARGET_UNIQUE)))


def _rebuild_table():
    """Rebuild `paragraph` to drop an undroppable autoindex (origin 'u')."""
    # PRAGMA foreign_keys is a NO-OP inside a transaction. If it does not take
    # effect, DROP TABLE paragraph would cascade into paragraph_embedding and
    # paragraph_similarity and silently destroy them. Check BEFORE any DDL.
    model.DB.execute_sql("PRAGMA foreign_keys=OFF")
    still_on = model.DB.execute_sql("PRAGMA foreign_keys").fetchone()[0]
    if still_on:
        raise RuntimeError(
            "foreign_keys still ON — migration 015 cannot run inside an open "
            "transaction (DROP TABLE paragraph would cascade)")

    try:
        before = _counts()
        with model.DB.atomic():
            model.DB.execute_sql(PARAGRAPH_DDL)
            model.DB.execute_sql(
                "INSERT INTO paragraph_new (id, expression_id, domain_id,"
                " para_index, text, text_hash, created_at)"
                " SELECT id, expression_id, domain_id, para_index, text,"
                " text_hash, COALESCE(created_at, CURRENT_TIMESTAMP)"
                " FROM paragraph")
            model.DB.execute_sql("DROP TABLE paragraph")
            model.DB.execute_sql(
                "ALTER TABLE paragraph_new RENAME TO paragraph")
            model.DB.execute_sql(
                "CREATE INDEX IF NOT EXISTS idx_paragraph_expr"
                " ON paragraph(expression_id)")
            model.DB.execute_sql(
                "CREATE INDEX IF NOT EXISTS idx_paragraph_domain"
                " ON paragraph(domain_id)")
            model.DB.execute_sql(
                "CREATE INDEX IF NOT EXISTS idx_paragraph_pidx"
                " ON paragraph(para_index)")
            _create_target_indexes()

            after = _counts()
            if after != before:
                raise RuntimeError(
                    "migration 015 would lose rows: %s -> %s" % (before, after))
    finally:
        model.DB.execute_sql("PRAGMA foreign_keys=ON")

    orphans = model.DB.execute_sql("PRAGMA foreign_key_check").fetchall()
    if orphans:
        raise RuntimeError(
            "migration 015 left %d orphan row(s): %s"
            % (len(orphans), orphans[:5]))
    print("  rebuilt table, rows kept: %s" % before)


def upgrade():
    print("Starting paragraph occurrences migration (015)…")
    found = _global_unique_index()

    if found is None:
        if not _has_target_unique():
            # Nothing globally unique, nothing composite: a database created
            # before the index existed at all. Just add the target indexes.
            _create_target_indexes()
            print("  added the (expression_id, text_hash) unique index")
            return
        print("  paragraph is already keyed per expression — skipping")
        return

    name, origin = found
    if origin == 'c':
        print("  dropping named unique index %s (origin=c)" % name)
        with model.DB.atomic():
            model.DB.execute_sql("DROP INDEX %s" % name)
            _create_target_indexes()
    else:
        print("  inline UNIQUE constraint (origin=%s): rebuilding the table"
              % origin)
        _rebuild_table()

    print("  paragraph.text_hash is now unique per expression")
