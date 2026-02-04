"""
Tests for land management: CRUD operations, terms, URLs management.
"""
import os
import random
import string
import pytest
from unittest.mock import patch


def rand_name(prefix="land"):
    """Generate random land name for tests."""
    letters = string.ascii_lowercase
    return f"{prefix}_" + "".join(random.choice(letters) for _ in range(8))


class TestLandCreate:
    """Tests for land creation."""

    def test_create_land_minimal(self, fresh_db):
        """land create --name=TestLand crée un land."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        ret = controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        assert ret == 1, "Land creation should succeed"
        land = model.Land.get_or_none(model.Land.name == name)
        assert land is not None, "Land should exist in database"
        assert land.name == name

    def test_create_land_with_description(self, fresh_db):
        """land create avec description stocke la description."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        desc = "Test land description"

        ret = controller.LandController.create(
            core.Namespace(name=name, desc=desc, lang=["fr"])
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        assert land.description == desc

    def test_create_land_with_lang(self, fresh_db):
        """land create avec --lang=en définit la langue."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")

        ret = controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["en"])
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        assert "en" in land.lang

    def test_create_land_with_multiple_langs(self, fresh_db):
        """land create avec --lang=fr,en stocke les deux langues."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")

        ret = controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr", "en"])
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        # Les langues sont stockées comme string comma-separated
        assert "fr" in land.lang
        assert "en" in land.lang

    def test_create_duplicate_land_fails(self, fresh_db):
        """Créer deux lands avec le même nom échoue."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        import peewee

        name = rand_name("test")

        # Première création
        ret1 = controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        assert ret1 == 1

        # Deuxième création avec le même nom devrait lever IntegrityError
        with pytest.raises(peewee.IntegrityError):
            controller.LandController.create(
                core.Namespace(name=name, desc="Test land", lang=["fr"])
            )


class TestLandList:
    """Tests for land listing."""

    def test_list_empty(self, fresh_db, capsys):
        """land list sur DB vide retourne liste vide."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        ret = controller.LandController.list(core.Namespace(name=None))

        # Return 0 when no lands (expected behavior)
        assert ret == 0, "List should return 0 when no lands exist"
        output = capsys.readouterr().out
        assert "No land" in output or len(output.strip()) == 0

    def test_list_shows_created_lands(self, fresh_db, capsys):
        """Après création, land list affiche le land."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test", lang=["fr"])
        )

        ret = controller.LandController.list(core.Namespace(name=None))

        assert ret == 1
        output = capsys.readouterr().out
        assert name in output, "Created land should appear in list"

    def test_list_specific_land(self, fresh_db, capsys):
        """land list --name=X affiche les détails de X."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        name = rand_name("test")
        desc = "Test land description"
        controller.LandController.create(
            core.Namespace(name=name, desc=desc, lang=["fr"])
        )

        ret = controller.LandController.list(core.Namespace(name=name))

        assert ret == 1
        output = capsys.readouterr().out
        assert name in output
        # La description devrait aussi apparaître
        assert desc in output or "description" in output.lower()


class TestLandAddTerm:
    """Tests for adding terms to lands."""

    def test_addterm_single(self, fresh_db):
        """land addterm ajoute un terme au dictionnaire."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        ret = controller.LandController.addterm(
            core.Namespace(land=name, terms="keyword")
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        # Vérifier qu'un mot a été ajouté au dictionnaire
        dict_count = model.LandDictionary.select().where(
            model.LandDictionary.land == land
        ).count()
        assert dict_count >= 1, "At least one term should be added"

    def test_addterm_multiple(self, fresh_db):
        """land addterm avec virgules ajoute plusieurs termes."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        ret = controller.LandController.addterm(
            core.Namespace(land=name, terms="keyword1, keyword2, keyword3")
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        dict_count = model.LandDictionary.select().where(
            model.LandDictionary.land == land
        ).count()
        assert dict_count >= 3, "Multiple terms should be added"

    def test_addterm_to_nonexistent_land_fails(self, fresh_db):
        """Ajouter terme à land inexistant échoue."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        nonexistent_land = "land_that_does_not_exist_xyz"

        ret = controller.LandController.addterm(
            core.Namespace(land=nonexistent_land, terms="keyword")
        )

        assert ret == 0, "Adding term to non-existent land should fail"


class TestLandAddUrl:
    """Tests for adding URLs to lands."""

    def test_addurl_direct(self, fresh_db):
        """land addurl --urls ajoute l'URL."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        url = "https://example.com/test"
        ret = controller.LandController.addurl(
            core.Namespace(land=name, urls=url, path=None)
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        expr = model.Expression.get_or_none(
            (model.Expression.land == land) & (model.Expression.url == url)
        )
        assert expr is not None, "URL should be added as expression"

    def test_addurl_multiple(self, fresh_db):
        """land addurl --urls="url1, url2" ajoute les deux."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        urls = "https://example.com/test1, https://example.com/test2"
        ret = controller.LandController.addurl(
            core.Namespace(land=name, urls=urls, path=None)
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        expr_count = model.Expression.select().where(
            model.Expression.land == land
        ).count()
        assert expr_count == 2, "Two URLs should be added"

    def test_addurl_from_file(self, fresh_db, tmp_path):
        """land addurl --path lit les URLs du fichier."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        # Créer un fichier avec des URLs
        url_file = tmp_path / "urls.txt"
        url_file.write_text(
            "https://example.com/1\nhttps://example.com/2\nhttps://example.com/3",
            encoding="utf-8"
        )

        ret = controller.LandController.addurl(
            core.Namespace(land=name, urls=None, path=str(url_file))
        )

        assert ret == 1
        land = model.Land.get(model.Land.name == name)
        expr_count = model.Expression.select().where(
            model.Expression.land == land
        ).count()
        assert expr_count == 3, "Three URLs from file should be added"

    def test_addurl_deduplication(self, fresh_db):
        """Ajouter la même URL deux fois ne crée pas de doublon."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        url = "https://example.com/test"

        # Ajouter la première fois
        controller.LandController.addurl(
            core.Namespace(land=name, urls=url, path=None)
        )

        # Ajouter la deuxième fois
        controller.LandController.addurl(
            core.Namespace(land=name, urls=url, path=None)
        )

        land = model.Land.get(model.Land.name == name)
        expr_count = model.Expression.select().where(
            (model.Expression.land == land) & (model.Expression.url == url)
        ).count()
        assert expr_count == 1, "URL should not be duplicated"

    def test_addurl_creates_domain(self, fresh_db):
        """Ajouter URL crée le Domain associé."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        url = "https://example.com/test"
        controller.LandController.addurl(
            core.Namespace(land=name, urls=url, path=None)
        )

        domain = model.Domain.get_or_none(model.Domain.name == "example.com")
        assert domain is not None, "Domain should be created"


class TestLandDelete:
    """Tests for land deletion."""

    def test_delete_land(self, fresh_db, monkeypatch):
        """land delete supprime le land et cascade."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )

        # Auto-confirm delete
        monkeypatch.setattr(core, "confirm", lambda msg: True, raising=True)

        ret = controller.LandController.delete(
            core.Namespace(name=name, maxrel=None)
        )

        assert ret == 1
        land = model.Land.get_or_none(model.Land.name == name)
        assert land is None, "Land should be deleted"

    def test_delete_with_maxrel(self, fresh_db, monkeypatch):
        """land delete --maxrel=5 ne supprime que relevance < 5."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        from datetime import datetime

        name = rand_name("test")
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Créer des expressions avec différentes relevances ET fetched_at (requis pour maxrel)
        # Note: maxrel est traité comme int par le controller, donc on utilise des entiers
        domain = model.Domain.create(name="example.com")
        model.Expression.create(
            land=land, domain=domain, url="https://example.com/1",
            relevance=3, fetched_at=datetime.now()
        )
        model.Expression.create(
            land=land, domain=domain, url="https://example.com/2",
            relevance=7, fetched_at=datetime.now()
        )

        # Auto-confirm delete
        monkeypatch.setattr(core, "confirm", lambda msg: True, raising=True)

        ret = controller.LandController.delete(
            core.Namespace(name=name, maxrel=5)
        )

        assert ret == 1
        # Le land devrait toujours exister
        land = model.Land.get_or_none(model.Land.name == name)
        assert land is not None, "Land should still exist when using maxrel"

        # Seule l'expression avec relevance < 5 devrait être supprimée
        expr_count = model.Expression.select().where(
            model.Expression.land == land
        ).count()
        assert expr_count == 1, "Only low relevance expression should be deleted"

    def test_delete_nonexistent_land(self, fresh_db):
        """Supprimer un land inexistant échoue proprement."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]

        nonexistent_land = "land_that_does_not_exist_xyz"

        ret = controller.LandController.delete(
            core.Namespace(name=nonexistent_land, maxrel=None)
        )

        assert ret == 0, "Deleting non-existent land should fail gracefully"


# Note: Tests SerpAPI et autres tests avec API keys sont volontairement omis
# car ils nécessitent des clés API réelles et sont testés dans les tests legacy
