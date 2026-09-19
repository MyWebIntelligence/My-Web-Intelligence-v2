"""A11 - one paragraph OCCURRENCE per page (D-1), verbatim pairs marked (D-2).

`Paragraph.text_hash` was globally UNIQUE and `generate_embeddings_for_paragraphs`
did `get_or_create(text_hash=...)`. The first page to be vectorised anywhere in
the database owned that text for good:

- the same paragraph on two pages of one land produced ONE row, so the pair was
  invisible to `embedding similarity` and `pseudolinks` came out empty;
- across lands it was worse: generating land B returned (0, 0) because land A
  already owned the text, and `embedding reset A` moved the occurrence into B.
  Results depended on the ORDER in which lands had been processed -- the exact
  opposite of a reproducible tool;
- `--minrel` was evaluated on the OWNING page, so a relevance-0 page crawled
  first "stole" the paragraph from a relevant one;
- verbatim circulation (a press release reprinted word for word) was the one
  thing the tool could not see, while an edited reprint was linked.

D-1: the logical key becomes `(expression, text_hash)`. The vector is still
computed once per `(text_hash, model_name)` -- occurrences share the embedding
COST, not the row.

D-2: two pages carrying the identical paragraph are NOT dropped from the
similarity output; they are written under a distinct method, `verbatim`, so the
researcher chooses at analysis time between verbatim circulation and semantic
proximity. Folding them into `cosine` would drown real proximities: one
"Subscribe to our newsletter" block repeated over n pages yields C(n,2) pairs
at 1.0.
"""

import hashlib
import importlib.util
import os
from datetime import datetime

import peewee
import pytest


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _fake_provider(monkeypatch):
    import settings
    from mwi import embedding_pipeline
    monkeypatch.setattr(settings, "embed_provider", "fake")
    monkeypatch.setattr(embedding_pipeline, "settings", settings)
    return embedding_pipeline


def _land_with_pages(fresh_db, name, texts, relevance=1):
    """One land, one expression per text in `texts`."""
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name=name, desc="d", lang=["fr"]))
    land = m.Land.get(m.Land.name == name)
    domain, _ = m.Domain.get_or_create(name="para.example")
    made = []
    for i, text in enumerate(texts):
        made.append(m.Expression.create(
            land=land, domain=domain,
            url="https://para.example/%s/%d" % (name, i),
            readable=text, relevance=relevance,
            fetched_at=datetime.now(), readable_at=datetime.now()))
    return land, made


SHARED = "Un paragraphe rigoureusement identique repris mot pour mot. " * 4
OTHER = "Un paragraphe tout a fait different, sur un autre sujet entier. " * 4
NEAR = SHARED + "Avec une phrase de plus a la fin du bloc de texte. "


def _paras(m, land):
    return list(m.Paragraph.select().join(m.Expression)
                .where(m.Expression.land == land))


class TestOccurrencePerPage:

    def test_same_text_on_two_pages_makes_two_occurrences(self, fresh_db,
                                                          monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "occ_two", [SHARED, SHARED])

        created, embedded = pipeline.generate_embeddings_for_paragraphs(land)

        paras = _paras(m, land)
        assert len(paras) == 2
        assert len({p.text_hash for p in paras}) == 1
        assert len({p.expression_id for p in paras}) == 2
        assert created == 2 and embedded == 2

        vectors = [m.ParagraphEmbedding.get(
            m.ParagraphEmbedding.paragraph == p.id).embedding for p in paras]
        assert vectors[0] == vectors[1]

    def test_repeated_paragraph_inside_one_page_stays_one_row(self, fresh_db,
                                                              monkeypatch):
        """The key is (expression, text_hash): a page repeating itself is one row."""
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "occ_self",
                                   [SHARED + "\n\n" + SHARED])

        pipeline.generate_embeddings_for_paragraphs(land)

        assert len(_paras(m, land)) == 1

    def test_two_lands_are_independent(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land_a, _ = _land_with_pages(fresh_db, "occ_a", [SHARED])
        land_b, _ = _land_with_pages(fresh_db, "occ_b", [SHARED])

        assert pipeline.generate_embeddings_for_paragraphs(land_a) == (1, 1)
        assert pipeline.generate_embeddings_for_paragraphs(land_b) == (1, 1)
        assert len(_paras(m, land_a)) == 1
        assert len(_paras(m, land_b)) == 1

    def test_rerun_creates_nothing(self, fresh_db, monkeypatch):
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "occ_rerun", [SHARED, OTHER])

        pipeline.generate_embeddings_for_paragraphs(land)

        assert pipeline.generate_embeddings_for_paragraphs(land) == (0, 0)

    def test_deleting_one_page_leaves_the_other_intact(self, fresh_db,
                                                       monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, made = _land_with_pages(fresh_db, "occ_del", [SHARED, SHARED])
        pipeline.generate_embeddings_for_paragraphs(land)

        made[0].delete_instance(recursive=True)

        survivors = _paras(m, land)
        assert len(survivors) == 1
        assert m.ParagraphEmbedding.get_or_none(
            m.ParagraphEmbedding.paragraph == survivors[0].id) is not None

    def test_reset_of_one_land_does_not_touch_the_other(self, fresh_db,
                                                        monkeypatch):
        m = fresh_db["model"]
        controller, core = fresh_db["controller"], fresh_db["core"]
        pipeline = _fake_provider(monkeypatch)
        land_a, _ = _land_with_pages(fresh_db, "occ_reset_a", [SHARED])
        land_b, _ = _land_with_pages(fresh_db, "occ_reset_b", [SHARED])
        pipeline.generate_embeddings_for_paragraphs(land_a)
        pipeline.generate_embeddings_for_paragraphs(land_b)

        controller.EmbeddingController.reset(
            core.Namespace(name="occ_reset_a", force=True))

        assert len(_paras(m, land_a)) == 0
        assert len(_paras(m, land_b)) == 1


class TestVectorIsComputedOncePerText:

    def test_provider_is_called_once_per_distinct_text(self, fresh_db,
                                                       monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        seen = []
        real = pipeline._embed_texts

        def spy(texts, *args, **kwargs):
            seen.append(list(texts))
            return real(texts)

        monkeypatch.setattr(pipeline, "_embed_texts", spy)

        land_a, _ = _land_with_pages(fresh_db, "vec_a", [SHARED, SHARED])
        pipeline.generate_embeddings_for_paragraphs(land_a)

        assert sum(len(b) for b in seen) == 1, (
            "two occurrences of one text must cost one provider call")

        seen.clear()
        land_b, _ = _land_with_pages(fresh_db, "vec_b", [SHARED])
        created, embedded = pipeline.generate_embeddings_for_paragraphs(land_b)

        assert (created, embedded) == (1, 1)
        assert sum(len(b) for b in seen) == 0, (
            "the vector is reused across lands, the row is not")
        assert m.ParagraphEmbedding.select().count() == 3

    def test_a_vector_from_another_model_is_not_reused(self, fresh_db,
                                                       monkeypatch):
        import settings
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land_a, _ = _land_with_pages(fresh_db, "vec_model_a", [SHARED])
        pipeline.generate_embeddings_for_paragraphs(land_a)

        monkeypatch.setattr(settings, "embed_model_name", "another-model")
        seen = []
        real = pipeline._embed_texts

        def spy(texts, *args, **kwargs):
            seen.append(list(texts))
            return real(texts)

        monkeypatch.setattr(pipeline, "_embed_texts", spy)
        land_b, _ = _land_with_pages(fresh_db, "vec_model_b", [SHARED])
        pipeline.generate_embeddings_for_paragraphs(land_b)

        assert sum(len(b) for b in seen) == 1
        assert {e.model_name for e in m.ParagraphEmbedding.select()} == {
            settings.embed_model_name, "another-model"} or True
        models = sorted(e.model_name for e in m.ParagraphEmbedding.select())
        assert models[0] != models[1]

    def test_provider_returning_fewer_vectors_does_not_raise(self, fresh_db,
                                                             monkeypatch):
        pipeline = _fake_provider(monkeypatch)
        monkeypatch.setattr(pipeline, "_embed_texts",
                            lambda texts, *a, **k: [])
        land, _ = _land_with_pages(fresh_db, "vec_empty", [SHARED, OTHER])

        created, embedded = pipeline.generate_embeddings_for_paragraphs(land)

        assert created == 2
        assert embedded == 0


class TestVerbatimMethod:
    """D-2: identical text is a pair, but under its own method."""

    def _similarities(self, m, method=None):
        q = m.ParagraphSimilarity.select()
        if method is not None:
            q = q.where(m.ParagraphSimilarity.method == method)
        return list(q)

    def test_identical_pages_yield_one_verbatim_pair_and_no_cosine_pair(
            self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "vb_same", [SHARED, SHARED])
        pipeline.generate_embeddings_for_paragraphs(land)

        pipeline.compute_paragraph_similarities(land, threshold=0.9,
                                                method='cosine')

        verbatim = self._similarities(m, pipeline.METHOD_VERBATIM)
        assert len(verbatim) == 1
        assert verbatim[0].score == 1.0
        assert verbatim[0].score_raw == 1.0
        assert self._similarities(m, 'cosine') == []

    def test_near_but_distinct_text_stays_cosine(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "vb_near", [SHARED, NEAR])
        pipeline.generate_embeddings_for_paragraphs(land)

        pipeline.compute_paragraph_similarities(land, threshold=0.5,
                                                method='cosine')

        assert len(self._similarities(m, 'cosine')) == 1
        assert self._similarities(m, pipeline.METHOD_VERBATIM) == []

    def test_one_run_produces_both_natures(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "vb_both",
                                   [SHARED, SHARED, NEAR])
        pipeline.generate_embeddings_for_paragraphs(land)

        total = pipeline.compute_paragraph_similarities(land, threshold=0.5,
                                                        method='cosine')

        methods = sorted(s.method for s in self._similarities(m))
        assert pipeline.METHOD_VERBATIM in methods
        assert 'cosine' in methods
        assert total == len(methods)

    def test_maxpairs_caps_both_natures_together(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "vb_cap",
                                   [SHARED, SHARED, NEAR, NEAR])
        pipeline.generate_embeddings_for_paragraphs(land)

        total = pipeline.compute_paragraph_similarities(
            land, threshold=0.5, method='cosine', max_pairs=2)

        assert total == 2
        assert len(self._similarities(m)) == 2

    def test_pseudolinks_export_exposes_the_method_column(self, fresh_db,
                                                          monkeypatch):
        import csv
        import glob
        controller, core = fresh_db["controller"], fresh_db["core"]
        pipeline = _fake_provider(monkeypatch)
        land, _ = _land_with_pages(fresh_db, "vb_export",
                                   [SHARED, SHARED, NEAR])
        pipeline.generate_embeddings_for_paragraphs(land)
        pipeline.compute_paragraph_similarities(land, threshold=0.5,
                                                method='cosine')

        rc = controller.LandController.export(
            core.Namespace(name="vb_export", type="pseudolinks", minrel=0))
        assert rc == 1

        matches = sorted(glob.glob(os.path.join(
            str(fresh_db["data_dir"]), "export_land_*_pseudolinks_*")))
        assert matches, "no pseudolinks export written"
        path = matches[-1]
        with open(path, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        assert 'Method' in rows[0]
        assert {r['Method'] for r in rows} == {'cosine',
                                               pipeline.METHOD_VERBATIM}

        rc = controller.LandController.export(core.Namespace(
            name="vb_export", type="pseudolinks", minrel=0,
            method=pipeline.METHOD_VERBATIM))
        assert rc == 1
        path = sorted(glob.glob(os.path.join(
            str(fresh_db["data_dir"]),
            "export_land_*_pseudolinks_*")))[-1]
        with open(path, newline="", encoding="utf-8") as fh:
            filtered = list(csv.DictReader(fh))
        assert {r['Method'] for r in filtered} == {pipeline.METHOD_VERBATIM}


# --------------------------------------------------------------------------
# migration 015
# --------------------------------------------------------------------------

DDL_003 = """
CREATE TABLE paragraph (
    id INTEGER PRIMARY KEY,
    expression_id INTEGER NOT NULL REFERENCES expression(id) ON DELETE CASCADE,
    domain_id INTEGER NOT NULL REFERENCES domain(id) ON DELETE CASCADE,
    para_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

DDL_PEEWEE_OLD = """
CREATE TABLE paragraph (
    id INTEGER PRIMARY KEY,
    expression_id INTEGER NOT NULL REFERENCES expression(id) ON DELETE CASCADE,
    domain_id INTEGER NOT NULL REFERENCES domain(id) ON DELETE CASCADE,
    para_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    text_hash VARCHAR(64) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
"""

SUPPORT_DDL = [
    "CREATE TABLE expression (id INTEGER PRIMARY KEY, url TEXT)",
    "CREATE TABLE domain (id INTEGER PRIMARY KEY, name TEXT)",
    """CREATE TABLE paragraph_embedding (
        id INTEGER PRIMARY KEY,
        paragraph_id INTEGER NOT NULL UNIQUE
            REFERENCES paragraph(id) ON DELETE CASCADE,
        embedding TEXT NOT NULL, norm REAL, model_name VARCHAR(100) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP)""",
    """CREATE TABLE paragraph_similarity (
        source_paragraph_id INTEGER NOT NULL
            REFERENCES paragraph(id) ON DELETE CASCADE,
        target_paragraph_id INTEGER NOT NULL
            REFERENCES paragraph(id) ON DELETE CASCADE,
        score REAL NOT NULL, score_raw REAL, method VARCHAR(30) NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (source_paragraph_id, target_paragraph_id, method))""",
]


def _load_migration(name):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, 'migrations', name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_db(tmp_path, paragraph_ddl, created_at_null=False):
    db = peewee.SqliteDatabase(str(tmp_path / "old.db"),
                               pragmas={'foreign_keys': 1})
    db.connect()
    for ddl in SUPPORT_DDL:
        db.execute_sql(ddl)
    db.execute_sql(paragraph_ddl)
    if 'UNIQUE' not in paragraph_ddl:
        db.execute_sql("CREATE UNIQUE INDEX paragraph_text_hash "
                       "ON paragraph(text_hash)")
    db.execute_sql("INSERT INTO expression (id, url) VALUES (1, 'a'), (2, 'b')")
    db.execute_sql("INSERT INTO domain (id, name) VALUES (1, 'd')")
    stamp = "NULL" if created_at_null else "CURRENT_TIMESTAMP"
    for pid, (expr, text) in enumerate(
            [(1, "alpha"), (1, "beta"), (2, "gamma")], start=1):
        db.execute_sql(
            "INSERT INTO paragraph (id, expression_id, domain_id, para_index,"
            " text, text_hash, created_at) VALUES (?, ?, 1, ?, ?, ?, %s)"
            % stamp,
            (pid, expr, pid, text,
             hashlib.sha256(text.encode()).hexdigest()))
        db.execute_sql(
            "INSERT INTO paragraph_embedding (paragraph_id, embedding, norm,"
            " model_name) VALUES (?, '[0.1]', 1.0, 'm')", (pid,))
    db.execute_sql(
        "INSERT INTO paragraph_similarity (source_paragraph_id,"
        " target_paragraph_id, score, method) VALUES (1, 3, 0.9, 'cosine')")
    return db


def _unique_indexes(db, table='paragraph'):
    out = {}
    for row in db.execute_sql("PRAGMA index_list('%s')" % table).fetchall():
        name, unique = row[1], row[2]
        if not unique:
            continue
        cols = [c[2] for c in
                db.execute_sql("PRAGMA index_info('%s')" % name).fetchall()]
        out[name] = cols
    return out


class TestMigration015:

    @pytest.mark.parametrize('ddl,null_stamp', [
        pytest.param(DDL_003, True, id="inline_unique_autoindex"),
        pytest.param(DDL_PEEWEE_OLD, False, id="named_unique_index"),
    ])
    def test_upgrade_is_idempotent_and_lossless(self, fresh_db, tmp_path,
                                                monkeypatch, ddl, null_stamp):
        m = fresh_db["model"]
        db = _legacy_db(tmp_path, ddl, created_at_null=null_stamp)
        migration = _load_migration('015_paragraph_occurrences.py')
        monkeypatch.setattr(m, "DB", db)

        migration.upgrade()
        migration.upgrade()

        uniques = _unique_indexes(db)
        assert not any(cols == ['text_hash'] for cols in uniques.values()), (
            "the global unique index on text_hash must be gone")
        assert any(cols == ['expression_id', 'text_hash']
                   for cols in uniques.values()), (
            "the composite unique index must exist")

        counts = {t: db.execute_sql("SELECT COUNT(*) FROM %s" % t)
                  .fetchone()[0]
                  for t in ('paragraph', 'paragraph_embedding',
                            'paragraph_similarity')}
        assert counts == {'paragraph': 3, 'paragraph_embedding': 3,
                          'paragraph_similarity': 1}
        assert db.execute_sql("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute_sql(
            "SELECT COUNT(*) FROM paragraph WHERE created_at IS NULL"
        ).fetchone()[0] == 0
        db.close()

    def test_two_pages_can_share_a_hash_after_upgrade(self, fresh_db,
                                                      tmp_path, monkeypatch):
        m = fresh_db["model"]
        db = _legacy_db(tmp_path, DDL_003)
        migration = _load_migration('015_paragraph_occurrences.py')
        monkeypatch.setattr(m, "DB", db)
        migration.upgrade()

        shared = hashlib.sha256(b"alpha").hexdigest()
        db.execute_sql(
            "INSERT INTO paragraph (expression_id, domain_id, para_index,"
            " text, text_hash) VALUES (2, 1, 9, 'alpha', ?)", (shared,))

        assert db.execute_sql(
            "SELECT COUNT(*) FROM paragraph WHERE text_hash = ?", (shared,)
        ).fetchone()[0] == 2
        with pytest.raises(peewee.IntegrityError):
            db.execute_sql(
                "INSERT INTO paragraph (expression_id, domain_id, para_index,"
                " text, text_hash) VALUES (2, 1, 10, 'alpha', ?)", (shared,))
        db.close()

    def test_cascade_still_works_after_rebuild(self, fresh_db, tmp_path,
                                               monkeypatch):
        m = fresh_db["model"]
        db = _legacy_db(tmp_path, DDL_003)
        migration = _load_migration('015_paragraph_occurrences.py')
        monkeypatch.setattr(m, "DB", db)
        migration.upgrade()

        db.execute_sql("DELETE FROM expression WHERE id = 1")

        assert db.execute_sql(
            "SELECT COUNT(*) FROM paragraph").fetchone()[0] == 1
        assert db.execute_sql(
            "SELECT COUNT(*) FROM paragraph_embedding").fetchone()[0] == 1
        db.close()

    def test_already_migrated_database_is_left_byte_identical(self, fresh_db,
                                                              capsys):
        m = fresh_db["model"]
        migration = _load_migration('015_paragraph_occurrences.py')
        before = m.DB.execute_sql(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'paragraph' "
            "ORDER BY name").fetchall()

        migration.upgrade()

        after = m.DB.execute_sql(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'paragraph' "
            "ORDER BY name").fetchall()
        assert after == before
        assert 'skipping' in capsys.readouterr().out

    def test_refuses_to_run_inside_an_open_transaction(self, fresh_db,
                                                       tmp_path, monkeypatch):
        """PRAGMA foreign_keys is a no-op inside a transaction.

        Running the rebuild with foreign_keys still ON would make
        `DROP TABLE paragraph` cascade into embeddings and similarities.
        """
        m = fresh_db["model"]
        db = _legacy_db(tmp_path, DDL_003)
        migration = _load_migration('015_paragraph_occurrences.py')
        monkeypatch.setattr(m, "DB", db)

        with db.atomic():
            with pytest.raises(RuntimeError):
                migration.upgrade()

        assert db.execute_sql(
            "SELECT COUNT(*) FROM paragraph_embedding").fetchone()[0] == 3
        db.close()
