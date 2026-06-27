"""
Sprint-multilang test suite (P1, P2, P3).

Covers:
- stem_word(word, lang) multilingual Snowball stemming + retro-compat
- unicode fallback tokenizer
- Word.lang schema + multilingual addterm
- language-aware expression_relevance (_resolve_text_lang)
- migration 011 (word.lang + ltr/rtl cleanup) idempotence
- Mercury pipeline no longer writes direction into Expression.lang
- land relemm retro-fit verb
"""

import importlib.util
import os
from types import SimpleNamespace

import peewee
import pytest


def _load_migration_011():
    """Load migrations/011_word_lang.py the same way MigrationManager does."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    module_path = os.path.join(here, 'migrations', '011_word_lang.py')
    spec = importlib.util.spec_from_file_location('011_word_lang', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStemWord:
    """D1 — multilingual Snowball stemming."""

    def test_stem_word_english_and_french(self, test_env):
        core = test_env["core"]
        assert core.stem_word('working', 'en') == 'work'
        # NB: 'mangeons' stems to 'mangeon' with the French Snowball stemmer,
        # hence the verified pair 'manger' -> 'mang'.
        assert core.stem_word('manger', 'fr') == 'mang'

    def test_stem_word_unsupported_language_is_lowercase_identity(self, test_env):
        core = test_env["core"]
        assert core.stem_word('Working', 'zz') == 'working'
        assert core.stem_word('Mangeons', 'xx-XX') == 'mangeons'

    def test_stem_word_default_is_french_retrocompat(self, test_env):
        core = test_env["core"]
        for word in ('manger', 'enfants', 'working'):
            assert core.stem_word(word) == core.stem_word(word, 'fr')

    def test_stem_word_regional_variant_reduced_to_base(self, test_env):
        core = test_env["core"]
        assert core.stem_word('working', 'en-US') == 'work'


class TestTokenizers:
    """D2 — unicode fallback tokenizer + punkt table."""

    def test_simple_word_tokenize_keeps_cyrillic_and_arabic(self, test_env):
        core = test_env["core"]
        tokens = core._simple_word_tokenize("Привет мир — مرحبا بالعالم!")
        assert 'привет' in tokens
        assert 'мир' in tokens
        assert 'مرحبا' in tokens

    def test_punkt_langs_are_available_in_nltk_data(self, test_env):
        core = test_env["core"]
        if not core._NLTK_OK:
            pytest.skip("NLTK punkt data unavailable")
        import nltk
        for iso, name in core._PUNKT_LANGS.items():
            nltk.data.find(f'tokenizers/punkt_tab/{name}')


class TestAddtermMultilang:
    """D3 — Word.lang + multilingual addterm."""

    def test_addterm_english_land_creates_english_lemma(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        m.Land.create(name="ml_en", description="t", lang="en")
        ret = controller.LandController.addterm(
            core.Namespace(land="ml_en", terms="working"))
        assert ret == 1
        word = m.Word.get(m.Word.term == "working")
        assert word.lang == "en"
        assert word.lemma == "work"

    def test_addterm_bilingual_land_creates_one_word_per_lang(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        land = m.Land.create(name="ml_fren", description="t", lang="fr,en")
        ret = controller.LandController.addterm(
            core.Namespace(land="ml_fren", terms="working"))
        assert ret == 1
        words = list(m.Word.select().where(m.Word.term == "working"))
        assert sorted(str(w.lang) for w in words) == ["en", "fr"]
        linked = (m.Word.select()
                  .join(m.LandDictionary)
                  .where(m.LandDictionary.land == land))
        assert linked.count() == 2

    def test_schema_has_word_lang_column(self, fresh_db):
        m = fresh_db["model"]
        cols = [row[1] for row in
                m.DB.execute_sql("PRAGMA table_info('word')").fetchall()]
        assert 'lang' in cols


class TestExpressionRelevance:
    """D4 — language-aware relevance. Discriminating case verified on
    master @1308306: term 'work' vs page titled 'Working from home
    policies' scores 0 with French-only stemming, >= 10 with English."""

    def test_english_land_matches_english_morphology(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        land = m.Land.create(name="ml_rel", description="t", lang="en")
        domain = m.Domain.create(name="ml-rel.example")
        expr = m.Expression.create(
            land=land, domain=domain, url="https://ml-rel.example/1",
            title="Working from home policies",
            readable="Working from home policies are evolving fast.",
            lang="en")
        controller.LandController.addterm(
            core.Namespace(land="ml_rel", terms="work"))
        dictionary = core.get_land_dictionary(land)
        score = core.expression_relevance(dictionary, expr)
        assert score >= 10  # title hit alone is worth 10

    def test_resolve_text_lang_variants(self, test_env):
        core = test_env["core"]
        expr = SimpleNamespace(land=SimpleNamespace(lang="fr,en"), lang="en-US")
        assert core._resolve_text_lang(expr) == "en"
        expr_empty = SimpleNamespace(land=SimpleNamespace(lang="fr,en"), lang="")
        assert core._resolve_text_lang(expr_empty) == "fr"
        expr_foreign = SimpleNamespace(land=SimpleNamespace(lang="fr,en"), lang="de")
        assert core._resolve_text_lang(expr_foreign) == "fr"
        expr_nolang = SimpleNamespace(land=SimpleNamespace(lang=None), lang=None)
        assert core._resolve_text_lang(expr_nolang) == "fr"


class TestMigration011:
    """A5/D6 — migration adds word.lang and cleans ltr/rtl, idempotent."""

    def test_migration_011_on_old_db_idempotent(self, fresh_db, tmp_path, monkeypatch):
        m = fresh_db["model"]
        old_db = peewee.SqliteDatabase(str(tmp_path / "old.db"))
        old_db.execute_sql(
            "CREATE TABLE word (id INTEGER PRIMARY KEY, "
            "term VARCHAR(30), lemma VARCHAR(30))")
        old_db.execute_sql(
            "CREATE TABLE expression (id INTEGER PRIMARY KEY, "
            "url TEXT, lang VARCHAR(100))")
        old_db.execute_sql(
            "INSERT INTO word (term, lemma) VALUES ('manger', 'mang')")
        old_db.execute_sql(
            "INSERT INTO expression (url, lang) VALUES "
            "('https://a.example/1', 'ltr'), "
            "('https://a.example/2', 'rtl'), "
            "('https://a.example/3', 'en')")

        migration = _load_migration_011()
        # Point the migration's `model.DB` at the old database
        monkeypatch.setattr(m, "DB", old_db)

        migration.upgrade()
        migration.upgrade()  # idempotence: second run must not raise

        cols = [row[1] for row in
                old_db.execute_sql("PRAGMA table_info('word')").fetchall()]
        assert 'lang' in cols
        row = old_db.execute_sql(
            "SELECT lang FROM word WHERE term='manger'").fetchone()
        assert row[0] == 'fr'  # backfill: legacy rows were stemmed in French

    def test_migration_011_cleans_ltr_rtl(self, fresh_db, tmp_path, monkeypatch):
        m = fresh_db["model"]
        old_db = peewee.SqliteDatabase(str(tmp_path / "old2.db"))
        old_db.execute_sql(
            "CREATE TABLE word (id INTEGER PRIMARY KEY, "
            "term VARCHAR(30), lemma VARCHAR(30))")
        old_db.execute_sql(
            "CREATE TABLE expression (id INTEGER PRIMARY KEY, "
            "url TEXT, lang VARCHAR(100))")
        old_db.execute_sql(
            "INSERT INTO expression (url, lang) VALUES "
            "('https://a.example/1', 'ltr'), "
            "('https://a.example/2', 'rtl'), "
            "('https://a.example/3', 'en')")

        migration = _load_migration_011()
        monkeypatch.setattr(m, "DB", old_db)
        migration.upgrade()

        rows = old_db.execute_sql(
            "SELECT url, lang FROM expression ORDER BY id").fetchall()
        assert rows[0][1] == ''   # ltr cleaned
        assert rows[1][1] == ''   # rtl cleaned
        assert rows[2][1] == 'en'  # genuine language preserved


class TestMercuryLangFix:
    """A3 — _prepare_expression_update no longer writes Expression.lang."""

    def test_prepare_expression_update_ignores_direction(self, fresh_db):
        m = fresh_db["model"]
        from mwi.readable_pipeline import MercuryReadablePipeline, MercuryResult

        land = m.Land.create(name="ml_merc", description="t", lang="fr")
        domain = m.Domain.create(name="ml-merc.example")
        expr = m.Expression.create(
            land=land, domain=domain, url="https://ml-merc.example/1",
            title="Ancien titre", readable="Ancien contenu", lang="fr")

        pipeline = MercuryReadablePipeline()
        mercury_result = MercuryResult(
            title="Un titre nettement plus long et informatif",
            markdown="Nouveau contenu markdown extrait par Mercury.",
            excerpt="Nouvel extrait",
            direction="ltr",
        )
        update = pipeline._prepare_expression_update(expr, mercury_result)
        assert 'lang' not in update.field_updates


class TestRelemm:
    """D5 — land relemm retro-fits pre-sprint lands."""

    def test_relemm_restems_english_land(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]

        land = m.Land.create(name="ml_relemm", description="t", lang="en")
        domain = m.Domain.create(name="ml-relemm.example")
        m.Expression.create(
            land=land, domain=domain, url="https://ml-relemm.example/1",
            title="Working from home policies",
            readable="Working from home policies are evolving.",
            lang="en")
        # Simulate a pre-sprint dictionary: term lemmatized in French
        # ('working' is left unchanged by the French stemmer).
        legacy_word = m.Word.create(term="working", lemma="working", lang="fr")
        m.LandDictionary.create(land=land, word=legacy_word)
        core.land_relevance(land)
        expr_before = m.Expression.get(m.Expression.url == "https://ml-relemm.example/1")
        assert expr_before.relevance == 0  # French lemma misses English morphology

        ret = controller.LandController.relemm(core.Namespace(name="ml_relemm"))
        assert ret == 1

        word = m.Word.get(m.Word.term == "working")
        assert word.lang == "en"
        assert word.lemma == "work"
        # Old French word was orphaned and purged
        assert m.Word.select().where(
            (m.Word.term == "working") & (m.Word.lang == "fr")).count() == 0
        expr_after = m.Expression.get(m.Expression.url == "https://ml-relemm.example/1")
        assert expr_after.relevance >= 10

    def test_relemm_is_idempotent(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        m.Land.create(name="ml_idem", description="t", lang="en")
        controller.LandController.addterm(
            core.Namespace(land="ml_idem", terms="working"))
        assert controller.LandController.relemm(core.Namespace(name="ml_idem")) == 1
        snapshot1 = sorted((str(w.term), str(w.lang), str(w.lemma))
                           for w in m.Word.select())
        assert controller.LandController.relemm(core.Namespace(name="ml_idem")) == 1
        snapshot2 = sorted((str(w.term), str(w.lang), str(w.lemma))
                           for w in m.Word.select())
        assert snapshot1 == snapshot2

    def test_relemm_unknown_land_returns_zero(self, fresh_db):
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        assert controller.LandController.relemm(
            core.Namespace(name="nope_does_not_exist")) == 0


class TestLlmPromptLanguage:
    """D7 — prompt by land language + yes/no parser robustness."""

    def test_normalize_yesno_accepts_english_variants(self, test_env):
        from mwi import llm_openrouter
        assert llm_openrouter._normalize_yesno("Yes.") == "oui"
        assert llm_openrouter._normalize_yesno("No, it is not relevant.") == "non"
        assert llm_openrouter._normalize_yesno("oui") == "oui"
        assert llm_openrouter._normalize_yesno("Non.") == "non"
        assert llm_openrouter._normalize_yesno("maybe") == "?"
        assert llm_openrouter._normalize_yesno("") == "?"

    def test_prompt_language_follows_land_primary_lang(self, fresh_db):
        m = fresh_db["model"]
        from mwi import llm_openrouter
        land_fr = m.Land.create(name="ml_prompt_fr", description="d", lang="fr,en")
        land_en = m.Land.create(name="ml_prompt_en", description="d", lang="en")
        expr = SimpleNamespace(title="T", description="D", url="https://x.example")
        prompt_fr = llm_openrouter.build_relevance_prompt(land_fr, expr, "texte")
        prompt_en = llm_openrouter.build_relevance_prompt(land_en, expr, "text")
        # sprint validate-update: prompts are now English wrappers that state the
        # project's working language (supersedes the FR/EN split of D7).
        assert '"yes" or "no"' in prompt_fr
        assert '"yes" or "no"' in prompt_en
        assert 'French' in prompt_fr
        assert 'English' in prompt_en


class TestLanguageInheritance:
    """A7 — search run / land create language defaults."""

    def test_land_create_without_lang_defaults_to_fr(self, fresh_db):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        ret = controller.LandController.create(
            core.Namespace(name="ml_nolang", desc="d"))
        assert ret == 1
        assert str(m.Land.get(m.Land.name == "ml_nolang").lang) == "fr"

    def test_search_run_inherits_land_primary_language(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        m.Land.create(name="ml_inherit", description="d", lang="en,fr")

        captured = {}

        class StubRouter:
            providers = [object()]
            provider_names = ['stub']

            async def search(self, query, strategy=None, num=20,
                             language='fr', providers=None):
                captured['language'] = language
                return []

            def usage_report(self):
                return {}

        monkeypatch.setattr(controller.SearchController, "_build_router",
                            staticmethod(lambda: StubRouter()))
        ret = controller.SearchController.run(
            core.Namespace(land="ml_inherit", query="q"))
        assert ret == 1
        assert captured['language'] == 'en'  # land primary, not 'fr'
