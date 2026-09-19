"""R02 lot B - a real perceptual fingerprint (dHash 64 bits), migration 016.

What this buys, and what it does not: `image_hash` (SHA-256) answers "is this
the SAME FILE?". It cannot see that a photo has been reprinted by another
outlet after a recompression or a resize — which is exactly the circulation a
web-corpus study wants to measure. `perceptual_hash` answers "is this the SAME
IMAGE?". It does not replace `image_hash`: byte identity remains the only
proof of an untouched file.

No new dependency (decision recorded in the sprint): `imagehash` was dropped
from the project in June 2026 as a pip-freeze leftover nothing imported, and
dHash is fifteen lines of Pillow, which is already a base dependency.

Definition under test: grayscale -> resize to (9, 8) LANCZOS -> for each row,
8 comparisons of neighbouring pixels -> 64 bits -> 16 hex characters. Two
images are alike when the HAMMING DISTANCE of their fingerprints is small.

The file number was reassigned: 40 was reserved for a TLS test that decision
D-3 cancelled.
"""

import hashlib
import importlib.util
import io
import os
from datetime import datetime

import peewee
import pytest
from PIL import Image

from mwi.media_analyzer import hamming_distance, perceptual_hash


# --------------------------------------------------------------------------
# synthetic images, generated in memory (no versioned binary)
# --------------------------------------------------------------------------

def _gradient(size=(160, 120), seed=0):
    """Gradient plus a few shapes: enough structure for dHash to be stable."""
    img = Image.new("RGB", size)
    w, h = size
    img.putdata([
        ((x * 3 + seed * 40) % 256,
         (y * 5 + seed * 17) % 256,
         ((x + y) * 2 + seed * 90) % 256)
        for y in range(h) for x in range(w)
    ])
    return img


def _encode(img, **kwargs):
    buf = io.BytesIO()
    img.save(buf, **kwargs)
    return buf.getvalue()


def _open(payload):
    return Image.open(io.BytesIO(payload))


class TestPerceptualHashIsStableUnderReEncoding:
    """The whole point: survive what SHA-256 cannot."""

    @pytest.mark.parametrize('label,make', [
        pytest.param('png_compress_0',
                     lambda img: _encode(img, format="PNG", compress_level=0),
                     id="png_compress_0"),
        pytest.param('png_compress_9',
                     lambda img: _encode(img, format="PNG", compress_level=9),
                     id="png_compress_9"),
        pytest.param('jpeg_q90',
                     lambda img: _encode(img, format="JPEG", quality=90),
                     id="jpeg_q90"),
        pytest.param('resized_50pct',
                     lambda img: _encode(img.resize((80, 60)), format="PNG"),
                     id="resized_50pct"),
    ])
    def test_re_encoding_keeps_the_fingerprint_close(self, label, make):
        original = _gradient()
        reference_bytes = _encode(original, format="PNG")
        variant_bytes = make(original)

        reference = perceptual_hash(_open(reference_bytes))
        variant = perceptual_hash(_open(variant_bytes))

        assert hamming_distance(reference, variant) <= 5, (
            "%s: distance %s" % (label,
                                 hamming_distance(reference, variant)))
        # The twin assertion is what proves the added value: the cryptographic
        # hash is unrelated for every one of these variants.
        if label != 'png_compress_0':
            assert (hashlib.sha256(reference_bytes).hexdigest()
                    != hashlib.sha256(variant_bytes).hexdigest())

    def test_two_distinct_images_are_far_apart(self):
        """A property, not a constant: never assert an exact distance."""
        a = perceptual_hash(_gradient(seed=0))
        b = perceptual_hash(Image.new("RGB", (160, 120)).copy())
        checker = Image.new("RGB", (160, 120))
        checker.putdata([(255, 255, 255) if (x // 8 + y // 8) % 2 else (0, 0, 0)
                         for y in range(120) for x in range(160)])
        c = perceptual_hash(checker)

        assert hamming_distance(a, c) >= 20
        assert b is not None

    def test_is_deterministic(self):
        payload = _encode(_gradient(), format="PNG")

        first = perceptual_hash(_open(payload))
        second = perceptual_hash(_open(payload))

        assert first == second
        assert len(first) == 16
        assert all(ch in '0123456789abcdef' for ch in first)


class TestPerceptualHashDegradations:

    def test_one_pixel_image_does_not_divide_by_zero(self):
        assert perceptual_hash(Image.new("RGB", (1, 1))) is not None

    def test_unreadable_bytes_give_none_without_raising(self):
        assert perceptual_hash(None) is None
        assert perceptual_hash(b"not an image") is None

    def test_analysis_keeps_image_hash_when_pillow_fails(self):
        """SHA-256 is computed before Image.open, so it survives a bad file."""
        import asyncio

        from mwi.media_analyzer import MediaAnalyzer

        payload = b"<svg xmlns='http://www.w3.org/2000/svg'></svg>"

        class _Resp:
            content_length = len(payload)

            async def read(self):
                return payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class _Session:
            def get(self, url):
                return _Resp()

        result = asyncio.new_event_loop().run_until_complete(
            MediaAnalyzer(_Session(), {}).analyze_image("https://x/i.svg"))

        assert result['image_hash'] == hashlib.sha256(payload).hexdigest()
        assert result.get('perceptual_hash') is None

    def test_analysis_fills_both_fingerprints_on_a_real_image(self):
        import asyncio

        from mwi.media_analyzer import MediaAnalyzer

        payload = _encode(_gradient(), format="PNG")

        class _Resp:
            content_length = len(payload)

            async def read(self):
                return payload

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

        class _Session:
            def get(self, url):
                return _Resp()

        result = asyncio.new_event_loop().run_until_complete(
            MediaAnalyzer(_Session(), {}).analyze_image("https://x/i.png"))

        assert result['image_hash'] == hashlib.sha256(payload).hexdigest()
        assert result['perceptual_hash'] == perceptual_hash(_open(payload))


class TestHammingDistance:

    @pytest.mark.parametrize('a,b,expected', [
        pytest.param('0000000000000000', '0000000000000000', 0, id="identical"),
        pytest.param('0000000000000000', '0000000000000001', 1, id="one_bit"),
        pytest.param('0000000000000000', 'ffffffffffffffff', 64, id="all_bits"),
    ])
    def test_distance(self, a, b, expected):
        assert hamming_distance(a, b) == expected

    def test_none_is_infinitely_far(self):
        """A media with no fingerprint is never a near-duplicate of anything."""
        assert hamming_distance(None, '0000000000000000') > 64
        assert hamming_distance('0000000000000000', None) > 64


# --------------------------------------------------------------------------
# migration 016
# --------------------------------------------------------------------------

OLD_MEDIA_DDL = """
CREATE TABLE media (
    id INTEGER PRIMARY KEY,
    expression_id INTEGER NOT NULL REFERENCES expression(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    type VARCHAR(30) NOT NULL,
    width INTEGER, height INTEGER, file_size INTEGER,
    format VARCHAR(10), color_mode VARCHAR(10),
    image_hash VARCHAR(64), analyzed_at DATETIME
)
"""


def _load_migration(name):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, 'migrations', name)
    spec = importlib.util.spec_from_file_location(name[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_media_db(tmp_path):
    db = peewee.SqliteDatabase(str(tmp_path / "old.db"),
                               pragmas={'foreign_keys': 1})
    db.connect()
    db.execute_sql("CREATE TABLE expression (id INTEGER PRIMARY KEY, url TEXT)")
    db.execute_sql(OLD_MEDIA_DDL)
    db.execute_sql("INSERT INTO expression (id, url) VALUES (1, 'a')")
    for i in range(3):
        db.execute_sql(
            "INSERT INTO media (expression_id, url, type, image_hash)"
            " VALUES (1, ?, 'img', ?)", ("https://x/%d.jpg" % i, "h%d" % i))
    return db


class TestMigration016:

    def test_adds_the_column_and_is_idempotent(self, fresh_db, tmp_path,
                                               monkeypatch):
        m = fresh_db["model"]
        db = _legacy_media_db(tmp_path)
        migration = _load_migration('016_media_perceptual_hash.py')
        monkeypatch.setattr(m, "DB", db)

        migration.upgrade()
        migration.upgrade()

        cols = [row[1] for row in
                db.execute_sql("PRAGMA table_info('media')").fetchall()]
        assert 'perceptual_hash' in cols
        assert db.execute_sql("SELECT COUNT(*) FROM media").fetchone()[0] == 3
        assert db.execute_sql(
            "SELECT COUNT(*) FROM media WHERE perceptual_hash IS NULL"
        ).fetchone()[0] == 3
        assert db.execute_sql("PRAGMA foreign_key_check").fetchall() == []
        db.close()

    def test_runs_on_the_current_schema_without_complaining(self, fresh_db):
        migration = _load_migration('016_media_perceptual_hash.py')

        migration.upgrade()

        cols = [row[1] for row in fresh_db["model"].DB.execute_sql(
            "PRAGMA table_info('media')").fetchall()]
        assert 'perceptual_hash' in cols


# --------------------------------------------------------------------------
# media_stats
# --------------------------------------------------------------------------

def _land_with_media(fresh_db, specs):
    m = fresh_db["model"]
    controller = fresh_db["controller"]
    core = fresh_db["core"]
    controller.LandController.create(
        core.Namespace(name="ph_land", desc="d", lang=["fr"]))
    land = m.Land.get(m.Land.name == "ph_land")
    domain, _ = m.Domain.get_or_create(name="ph.example")
    expr = m.Expression.create(land=land, domain=domain,
                               url="https://ph.example/a", depth=0)
    for i, spec in enumerate(specs):
        m.Media.create(expression=expr, url="https://ph.example/%d.jpg" % i,
                       type='img', analyzed_at=datetime.now(), **spec)
    return land


class TestMediaStatsReportsBothKinds:

    def test_exact_and_near_duplicates_are_counted_separately(self, fresh_db,
                                                              capsys):
        controller, core = fresh_db["controller"], fresh_db["core"]
        _land_with_media(fresh_db, [
            # Same image recompressed: different bytes, same fingerprint.
            {'image_hash': 'sha_a', 'perceptual_hash': 'ffff0000ffff0000'},
            {'image_hash': 'sha_b', 'perceptual_hash': 'ffff0000ffff0000'},
            # A true exact duplicate.
            {'image_hash': 'sha_c', 'perceptual_hash': '0f0f0f0f0f0f0f0f'},
            {'image_hash': 'sha_c', 'perceptual_hash': '0f0f0f0f0f0f0f0f'},
        ])

        assert controller.LandController.media_stats(
            core.Namespace(name="ph_land")) == 1

        out = capsys.readouterr().out
        assert 'Exact duplicates (SHA-256): 1 group(s), 2 media' in out
        assert 'Near-duplicates (dHash): 2 group(s)' in out

    def test_media_without_a_fingerprint_are_ignored_not_grouped(self,
                                                                 fresh_db,
                                                                 capsys):
        """Every existing database is in this state before a re-analysis."""
        controller, core = fresh_db["controller"], fresh_db["core"]
        _land_with_media(fresh_db, [
            {'image_hash': 'sha_a', 'perceptual_hash': None},
            {'image_hash': 'sha_b', 'perceptual_hash': None},
        ])

        assert controller.LandController.media_stats(
            core.Namespace(name="ph_land")) == 1

        out = capsys.readouterr().out
        assert 'Near-duplicates (dHash): 0 group(s)' in out

    def test_near_search_is_explicit_and_bounded(self, fresh_db, capsys,
                                                 monkeypatch):
        """--near=N is quadratic, so it is opt-in and it refuses to run wild."""
        controller, core = fresh_db["controller"], fresh_db["core"]
        _land_with_media(fresh_db, [
            {'image_hash': 'sha_a', 'perceptual_hash': 'ffff0000ffff0000'},
            # One bit away: same image, one pixel comparison flipped.
            {'image_hash': 'sha_b', 'perceptual_hash': 'ffff0000ffff0001'},
            {'image_hash': 'sha_c', 'perceptual_hash': '0f0f0f0f0f0f0f0f'},
        ])

        controller.LandController.media_stats(
            core.Namespace(name="ph_land", near=5))
        out = capsys.readouterr().out
        assert 'distance <= 5' in out
        assert '3 media compared' in out

        monkeypatch.setattr(core.settings, 'media_near_duplicate_max', 2,
                            raising=False)
        assert controller.LandController.media_stats(
            core.Namespace(name="ph_land", near=5)) == 1
        refused = capsys.readouterr().out
        assert 'too many media' in refused
        assert '--minrel' in refused
