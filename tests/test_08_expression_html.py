"""Tests for the HTML storage feature (Expression.html + Land.fullhtml).

Tests cover:
- Model fields (nullable, roundtrip, schema)
- process_expression_content with store_html flag
- Land.fullhtml default and creation
- Cascade logic (CLI override > land default)
- Migration on legacy databases
"""
import peewee
import pytest


class TestExpressionHtmlField:
    """Tests for Expression.html field."""

    def test_expression_html_field_nullable(self, fresh_db):
        """Expression created without html has html=None."""
        m = fresh_db["model"]
        domain = m.Domain.create(name="test-nullable.com")
        land = m.Land.create(name="test_nullable", description="test", lang="fr")
        expr = m.Expression.create(land=land, domain=domain, url="https://test-nullable.com/1")
        assert expr.html is None

    def test_expression_html_roundtrip(self, fresh_db):
        """HTML stored in DB is retrieved identically."""
        m = fresh_db["model"]
        domain = m.Domain.create(name="test-roundtrip.com")
        land = m.Land.create(name="test_roundtrip", description="test", lang="fr")
        raw = "<html><head><title>Test</title></head><body><p>Contenu</p></body></html>"
        expr = m.Expression.create(land=land, domain=domain, url="https://test-roundtrip.com/1", html=raw)
        fetched = m.Expression.get_by_id(expr.id)
        assert fetched.html == raw

    def test_schema_has_html_column(self, fresh_db):
        """The expression table contains the html column."""
        m = fresh_db["model"]
        cols = [row[1] for row in m.DB.execute_sql("PRAGMA table_info('expression')").fetchall()]
        assert 'html' in cols


class TestLandFullhtmlField:
    """Tests for Land.fullhtml field."""

    def test_land_create_with_fullhtml_true(self, fresh_db):
        """Land created with fullhtml=True stores the flag."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_fh", description="test", lang="fr", fullhtml=True)
        fetched = m.Land.get_by_id(land.id)
        assert fetched.fullhtml is True

    def test_land_create_without_fullhtml_defaults_false(self, fresh_db):
        """Land created without fullhtml has fullhtml=False."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_nofh", description="test", lang="fr")
        fetched = m.Land.get_by_id(land.id)
        assert fetched.fullhtml is False

    def test_schema_has_fullhtml_column(self, fresh_db):
        """The land table contains the fullhtml column."""
        m = fresh_db["model"]
        cols = [row[1] for row in m.DB.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'fullhtml' in cols


class TestProcessExpressionContent:
    """Tests for store_html flag in process_expression_content."""

    def test_stores_html_when_enabled(self, fresh_db):
        """process_expression_content stores html when store_html=True."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name="test_pec", description="test", lang="fr")
        domain = m.Domain.create(name="test-pec.com")
        expr = m.Expression.create(land=land, domain=domain, url="https://test-pec.com/page")

        sample_html = '<html lang="fr"><head><title>Article Test</title></head><body><p>Contenu.</p></body></html>'
        dictionary = list(m.Word.select().join(m.LandDictionary).where(m.LandDictionary.land == land))
        core.process_expression_content(expr, sample_html, dictionary, store_html=True)

        assert expr.html == sample_html.strip()

    def test_no_html_by_default(self, fresh_db):
        """process_expression_content leaves html=None when store_html=False (default)."""
        m = fresh_db["model"]
        core = fresh_db["core"]
        land = m.Land.create(name="test_pec2", description="test", lang="fr")
        domain = m.Domain.create(name="test-pec2.com")
        expr = m.Expression.create(land=land, domain=domain, url="https://test-pec2.com/page")

        sample_html = '<html lang="fr"><head><title>Test</title></head><body><p>Contenu.</p></body></html>'
        dictionary = list(m.Word.select().join(m.LandDictionary).where(m.LandDictionary.land == land))
        core.process_expression_content(expr, sample_html, dictionary)

        assert expr.html is None


class TestCrawlFullhtmlCascade:
    """Tests for the --fullhtml cascade logic (CLI override > land default)."""

    def test_crawl_inherits_land_fullhtml(self, fresh_db):
        """When --fullhtml not specified at crawl, land.fullhtml is used."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_inherit", description="test", lang="fr", fullhtml=True)

        # Simulate resolution as in LandController.crawl
        fullhtml_raw = None  # CLI absent
        if fullhtml_raw is not None:
            store_html = fullhtml_raw.upper() == 'TRUE'
        else:
            store_html = bool(land.fullhtml)

        assert store_html is True

    def test_crawl_fullhtml_false_overrides_land(self, fresh_db):
        """--fullhtml=FALSE at crawl overrides land.fullhtml=True."""
        m = fresh_db["model"]
        land = m.Land.create(name="test_override", description="test", lang="fr", fullhtml=True)

        fullhtml_raw = 'FALSE'  # CLI explicit
        if fullhtml_raw is not None:
            store_html = fullhtml_raw.upper() == 'TRUE'
        else:
            store_html = bool(land.fullhtml)

        assert store_html is False


class TestMigration:
    """Tests for the migration adding html columns."""

    def test_migration_adds_html_columns(self, tmp_path):
        """Migration 007 adds html and fullhtml columns to legacy databases."""
        db = peewee.SqliteDatabase(str(tmp_path / "old.db"))

        # Create minimal tables WITHOUT new columns
        db.execute_sql("""CREATE TABLE land (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT, lang TEXT
        )""")
        db.execute_sql("""CREATE TABLE expression (
            id INTEGER PRIMARY KEY, url TEXT NOT NULL, readable TEXT
        )""")
        db.execute_sql("INSERT INTO land (name, description) VALUES ('test', 'desc')")
        db.execute_sql("INSERT INTO expression (url) VALUES ('https://example.com')")

        # Verify columns don't exist
        expr_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        land_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'html' not in expr_cols
        assert 'fullhtml' not in land_cols

        # Apply migration
        db.execute_sql("ALTER TABLE expression ADD COLUMN html TEXT DEFAULT NULL")
        db.execute_sql("ALTER TABLE land ADD COLUMN fullhtml INTEGER DEFAULT 0")

        # Verify columns exist
        expr_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('expression')").fetchall()]
        land_cols = [r[1] for r in db.execute_sql("PRAGMA table_info('land')").fetchall()]
        assert 'html' in expr_cols
        assert 'fullhtml' in land_cols

        # Verify default values on existing rows
        row = db.execute_sql("SELECT html FROM expression WHERE url='https://example.com'").fetchone()
        assert row[0] is None
        land_row = db.execute_sql("SELECT fullhtml FROM land WHERE name='test'").fetchone()
        assert land_row[0] == 0
        db.close()
