"""
Tests for database setup, migrations, and installation verification.
"""
import os
import pytest


class TestDatabaseSetup:
    """Tests for database setup functionality."""

    def test_db_setup_creates_database(self, fresh_db):
        """Vérifie que db setup crée mwi.db."""
        db_path = os.path.join(fresh_db["data_dir"], "mwi.db")
        assert os.path.exists(db_path), "Database file should exist"

    def test_db_setup_creates_required_tables(self, fresh_db):
        """Vérifie la présence de toutes les tables requises."""
        model = fresh_db["model"]
        expected_tables = [
            "land", "domain", "expression", "expressionlink",
            "word", "landdictionary", "media",
            "paragraph", "paragraph_embedding", "paragraph_similarity",
            "tag", "taggedcontent"
        ]

        # Query sqlite_master pour obtenir la liste des tables
        cursor = model.DB.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        actual_tables = [row[0] for row in cursor.fetchall()]

        # Vérifier que toutes les tables attendues existent
        for table in expected_tables:
            assert table in actual_tables, f"Table '{table}' should exist"

    def test_db_setup_idempotent(self, fresh_db):
        """Exécuter db setup deux fois ne cause pas d'erreur."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        # Exécuter setup une deuxième fois
        ret = controller.DbController.setup(core.Namespace())
        assert ret == 1, "Second setup should succeed"

        # Vérifier que les tables existent toujours
        model = fresh_db["model"]
        cursor = model.DB.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = [row[0] for row in cursor.fetchall()]
        assert len(tables) >= 12, "Tables should still exist after second setup"


class TestDatabaseMigrate:
    """Tests for database migration functionality."""

    def test_db_migrate_on_fresh_db(self, fresh_db):
        """migrate sur DB fraîche ne cause pas d'erreur."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        # Exécuter migrate
        ret = controller.DbController.migrate(core.Namespace())
        assert ret == 1, "Migration should succeed on fresh database"

    def test_db_migrate_is_idempotent(self, fresh_db):
        """Exécuter migrate plusieurs fois ne cause pas d'erreur."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        # Exécuter migrate deux fois
        ret1 = controller.DbController.migrate(core.Namespace())
        ret2 = controller.DbController.migrate(core.Namespace())

        assert ret1 == 1, "First migration should succeed"
        assert ret2 == 1, "Second migration should succeed"


class TestDatabaseIntegrity:
    """Tests for database integrity and structure."""

    def test_expression_table_has_validllm_column(self, fresh_db):
        """Vérifie que la table expression a la colonne validllm."""
        model = fresh_db["model"]

        # Query pour obtenir les colonnes de la table expression
        cursor = model.DB.execute_sql("PRAGMA table_info(expression)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "validllm" in columns, "Expression table should have validllm column"
        assert "validmodel" in columns, "Expression table should have validmodel column"

    def test_expression_table_has_seorank_column(self, fresh_db):
        """Vérifie que la table expression a la colonne seorank."""
        model = fresh_db["model"]

        cursor = model.DB.execute_sql("PRAGMA table_info(expression)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "seorank" in columns, "Expression table should have seorank column"

    def test_media_table_has_analysis_columns(self, fresh_db):
        """Vérifie que la table media a les colonnes d'analyse."""
        model = fresh_db["model"]

        cursor = model.DB.execute_sql("PRAGMA table_info(media)")
        columns = [row[1] for row in cursor.fetchall()]

        expected_columns = [
            "width", "height", "file_size", "format",
            "dominant_colors", "exif_data", "image_hash", "analyzed_at"
        ]

        for col in expected_columns:
            assert col in columns, f"Media table should have {col} column"

    def test_paragraph_tables_exist(self, fresh_db):
        """Vérifie que les tables de paragraphes existent."""
        model = fresh_db["model"]

        cursor = model.DB.execute_sql(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'paragraph%'"
        )
        para_tables = [row[0] for row in cursor.fetchall()]

        assert "paragraph" in para_tables, "paragraph table should exist"
        assert "paragraph_embedding" in para_tables, "paragraph_embedding table should exist"
        assert "paragraph_similarity" in para_tables, "paragraph_similarity table should exist"


class TestEmbeddingCheck:
    """Tests for embedding environment check."""

    def test_embedding_check_runs(self, fresh_db, capsys):
        """embedding check retourne succès et affiche le statut."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        # Exécuter embedding check
        ret = controller.EmbeddingController.check(core.Namespace())

        # Le check peut retourner 0 si des clés API manquent, mais ne devrait pas crasher
        assert ret in [0, 1], "Embedding check should return 0 or 1"

        # Vérifier l'output
        output = capsys.readouterr().out
        assert "Embedding" in output or "provider" in output.lower(), \
            "Output should mention embedding provider"


class TestDatabasePragmas:
    """Tests for database configuration and pragmas."""

    def test_database_has_wal_mode(self, fresh_db):
        """Vérifie que la base de données utilise le mode WAL."""
        model = fresh_db["model"]

        cursor = model.DB.execute_sql("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]

        assert journal_mode.upper() == "WAL", "Database should use WAL journal mode"

    def test_database_has_foreign_keys_enabled(self, fresh_db):
        """Vérifie que les foreign keys sont activées."""
        model = fresh_db["model"]

        cursor = model.DB.execute_sql("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]

        assert fk_enabled == 1, "Foreign keys should be enabled"
