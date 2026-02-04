"""
Tests for land export functionality: CSV, GEXF, corpus.
"""
import os
import glob
import csv
import xml.etree.ElementTree as ET
import zipfile
import pytest


class TestLandExportCSV:
    """Tests for CSV export formats."""

    def test_export_pagecsv(self, populated_land):
        """land export --type=pagecsv génère un CSV valide."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]
        data_dir = str(populated_land["data_dir"])

        # Count existing export files before
        before_count = len(glob.glob(os.path.join(data_dir, "export_land_*pagecsv*")))

        ret = controller.LandController.export(
            core.Namespace(name=name, type="pagecsv", minrel=0)
        )

        assert ret == 1

        # Find newly created file
        after_files = glob.glob(os.path.join(data_dir, "export_land_*pagecsv*"))
        assert len(after_files) > before_count, "New CSV file should be created"

        # Validate CSV content
        csv_file = after_files[-1]  # Most recent
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 20, "Should have 20 expressions"
        assert "id" in rows[0]
        assert "url" in rows[0]

    def test_export_fullpagecsv(self, populated_land):
        """--type=fullpagecsv inclut le contenu complet."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="fullpagecsv", minrel=0)
        )

        assert ret == 1

    def test_export_nodecsv(self, populated_land):
        """--type=nodecsv génère les nœuds (domains)."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="nodecsv", minrel=0)
        )

        assert ret == 1

    def test_export_mediacsv(self, populated_land):
        """--type=mediacsv exporte les médias."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="mediacsv", minrel=0)
        )

        assert ret == 1

    def test_export_corpus(self, populated_land):
        """--type=corpus génère le corpus texte."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="corpus", minrel=0)
        )

        assert ret == 1

    def test_export_nodelinkcsv(self, populated_land):
        """--type=nodelinkcsv crée des fichiers CSV."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="nodelinkcsv", minrel=0)
        )

        assert ret == 1

    def test_export_minrel_filter(self, populated_land):
        """--minrel=X filtre les expressions."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]
        data_dir = str(populated_land["data_dir"])

        # Export avec minrel=10
        ret = controller.LandController.export(
            core.Namespace(name=name, type="pagecsv", minrel=10)
        )

        assert ret == 1

        # Find the CSV file
        csv_files = glob.glob(os.path.join(data_dir, "export_land_*pagecsv*"))
        csv_file = csv_files[-1]  # Most recent

        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Should filter to expressions with relevance >= 10 (0-19 in fixture)
        assert len(rows) == 10, f"Should have 10 filtered expressions, got {len(rows)}"


class TestLandExportGEXF:
    """Tests for GEXF export formats."""

    def test_export_pagegexf(self, populated_land):
        """--type=pagegexf génère un GEXF valide."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="pagegexf", minrel=0)
        )

        assert ret == 1

    def test_export_nodegexf(self, populated_land):
        """--type=nodegexf génère un GEXF de nœuds (domains)."""
        controller = populated_land["controller"]
        core = populated_land["core"]
        name = populated_land["name"]

        ret = controller.LandController.export(
            core.Namespace(name=name, type="nodegexf", minrel=0)
        )

        assert ret == 1


class TestTagExport:
    """Tests for tag export."""

    @pytest.fixture
    def land_with_tags(self, fresh_db):
        """Land avec tags et TaggedContent."""
        controller = fresh_db["controller"]
        model = fresh_db["model"]
        core = fresh_db["core"]
        from datetime import datetime

        # Créer land
        name = "test_tags_land"
        controller.LandController.create(
            core.Namespace(name=name, desc="Test land with tags", lang=["fr"])
        )
        land = model.Land.get(model.Land.name == name)

        # Ajouter terms
        controller.LandController.addterm(
            core.Namespace(land=name, terms="test, keyword")
        )

        # Créer expressions
        domain = model.Domain.create(name="example.com")
        expressions = []
        for i in range(5):
            expr = model.Expression.create(
                land=land,
                domain=domain,
                url=f"https://example.com/page{i}",
                title=f"Page {i}",
                readable=f"Content with test keyword {i}. " * 20,
                relevance=i + 1,
                fetched_at=datetime.now()
            )
            expressions.append(expr)

        # Créer tags avec le champ sorting requis
        tag1 = model.Tag.create(land=land, name="Topic1", parent=None, sorting=1, color="#FF0000")
        tag2 = model.Tag.create(land=land, name="Subtopic1", parent=tag1, sorting=2, color="#00FF00")
        tag3 = model.Tag.create(land=land, name="Topic2", parent=None, sorting=3, color="#0000FF")

        # Créer TaggedContent
        model.TaggedContent.create(
            tag=tag1,
            expression=expressions[0],
            text="Tagged snippet 1",
            from_char=0,
            to_char=15
        )
        model.TaggedContent.create(
            tag=tag2,
            expression=expressions[1],
            text="Tagged snippet 2",
            from_char=10,
            to_char=25
        )
        model.TaggedContent.create(
            tag=tag1,
            expression=expressions[2],
            text="Tagged snippet 3",
            from_char=5,
            to_char=40
        )

        return {
            "land": land,
            "tags": [tag1, tag2, tag3],
            "expressions": expressions,
            "name": name,
            "controller": controller,
            "core": core,
            "data_dir": fresh_db["data_dir"]
        }

    def test_tag_export_content(self, land_with_tags):
        """tag export --type=content exporte le contenu taggé."""
        controller = land_with_tags["controller"]
        core = land_with_tags["core"]
        name = land_with_tags["name"]

        ret = controller.TagController.export(
            core.Namespace(name=name, type="content", minrel=0)
        )

        assert ret == 1

    def test_tag_export_matrix(self, land_with_tags):
        """tag export --type=matrix génère la matrice de co-occurrence."""
        controller = land_with_tags["controller"]
        core = land_with_tags["core"]
        name = land_with_tags["name"]

        ret = controller.TagController.export(
            core.Namespace(name=name, type="matrix", minrel=0)
        )

        assert ret == 1

    def test_tag_export_minrel(self, land_with_tags):
        """--minrel filtre le contenu exporté."""
        controller = land_with_tags["controller"]
        core = land_with_tags["core"]
        name = land_with_tags["name"]

        # Export avec minrel=3
        ret = controller.TagController.export(
            core.Namespace(name=name, type="content", minrel=3)
        )

        assert ret == 1
