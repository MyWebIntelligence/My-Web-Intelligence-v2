"""
Sprint-multilang, Sprint D fixes (P8, P9, P10, P11/D-5).

Covers:
- D-1: `embedding reset --name=X` asks for confirmation, `--force` bypasses
- D-2: `domain crawl --http=ERR` matches every failure status
- D-3: `_maybe_truncate_html` caps in UTF-8 bytes, not characters
- D-5: `core.get_dryrun` accepts both --dryrun and --dry-run spellings
"""

from datetime import datetime


class TestEmbeddingResetConfirm:
    """D-1 — land-scoped reset requires confirmation; --force bypasses."""

    def _make_land_with_paragraph(self, fresh_db):
        m = fresh_db["model"]
        land = m.Land.create(name="reset_land", description="t", lang="fr")
        domain = m.Domain.create(name="reset.example")
        expr = m.Expression.create(
            land=land, domain=domain, url="https://reset.example/1",
            readable="Contenu.", fetched_at=datetime.now())
        m.Paragraph.create(expression=expr, domain=domain, para_index=0,
                           text="Contenu.", text_hash="hash_reset_1")
        return land

    def test_reset_land_aborts_without_confirmation(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        self._make_land_with_paragraph(fresh_db)
        monkeypatch.setattr(controller.core, "confirm", lambda msg: False)
        ret = controller.EmbeddingController.reset(core.Namespace(name="reset_land"))
        assert ret == 0
        m = fresh_db["model"]
        assert m.Paragraph.select().count() == 1  # nothing deleted

    def test_reset_land_force_bypasses_confirmation(self, fresh_db, monkeypatch):
        core = fresh_db["core"]
        controller = fresh_db["controller"]
        self._make_land_with_paragraph(fresh_db)

        def _refuse(msg):
            raise AssertionError("confirm() must not be called with --force")

        monkeypatch.setattr(controller.core, "confirm", _refuse)
        ret = controller.EmbeddingController.reset(
            core.Namespace(name="reset_land", force=True))
        assert ret == 1
        m = fresh_db["model"]
        assert m.Paragraph.select().count() == 0


class TestDomainCrawlErrFilter:
    """D-2 — --http=ERR matches all failure statuses."""

    def test_err_filter_matches_all_failure_codes(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        core = fresh_db["core"]
        statuses = ['ERR_TRAFI', 'ERR_ARCHIVE', 'ERR_UNKNOWN', 'ERR_ALL_FAILED',
                    'ARC_NO_HTML', 'REQ_NO_HTML', '000', '200', '404']
        for i, status in enumerate(statuses):
            m.Domain.create(name=f"err{i}.example", http_status=status,
                            fetched_at=datetime.now())

        crawled = []

        def fake_fetch(url, timeout=None):
            crawled.append(url)
            return None  # every fetch "fails": domain keeps an ERR status

        monkeypatch.setattr(core, "_fetch_url_with_retry_and_timeout", fake_fetch)
        # Avoid hitting archive.org / direct requests fallbacks
        monkeypatch.setattr(core.requests, "get",
                            lambda *a, **k: (_ for _ in ()).throw(
                                core.requests.RequestException("offline")))

        core.crawl_domains(limit=0, http='ERR')

        # 7 failure domains -> 2 fetch attempts each (https then http);
        # '200' and '404' domains must NOT be selected.
        touched = {u.split('//')[1].split('/')[0] for u in crawled}
        assert len(touched) == 7
        assert 'err7.example' not in touched  # status 200
        assert 'err8.example' not in touched  # status 404

    def test_exact_status_filter_still_works(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        core = fresh_db["core"]
        m.Domain.create(name="only404.example", http_status='404',
                        fetched_at=datetime.now())
        m.Domain.create(name="err.example", http_status='ERR_TRAFI',
                        fetched_at=datetime.now())

        crawled = []

        def fake_fetch(url, timeout=None):
            crawled.append(url)
            return None

        monkeypatch.setattr(core, "_fetch_url_with_retry_and_timeout", fake_fetch)
        monkeypatch.setattr(core.requests, "get",
                            lambda *a, **k: (_ for _ in ()).throw(
                                core.requests.RequestException("offline")))

        core.crawl_domains(limit=0, http='404')
        touched = {u.split('//')[1].split('/')[0] for u in crawled}
        assert touched == {'only404.example'}


class TestTruncateHtmlBytes:
    """D-3 — truncation cap enforced in UTF-8 bytes."""

    def test_multibyte_page_is_truncated_to_byte_cap(self, test_env, monkeypatch):
        core = test_env["core"]
        # Patch the settings module *as seen by core* (module reloads in
        # test_env make `import settings` resolve to a different object).
        monkeypatch.setattr(core.settings, "fullhtml_max_size_kb", 1, raising=False)
        # 1000 chars of 'é' = 2000 UTF-8 bytes > 1024-byte cap,
        # but only 1000 characters (under the old char-based cap).
        raw = "é" * 1000
        result = core._maybe_truncate_html(raw)
        assert len(result.encode('utf-8')) <= 1024
        # Lower bound: truncation must cut at the cap, not collapse the page
        # (a multi-byte char split at the boundary may drop at most 3 bytes).
        assert len(result.encode('utf-8')) >= 1024 - 3
        assert result  # decodable, non-empty

    def test_ascii_page_under_cap_untouched(self, test_env, monkeypatch):
        core = test_env["core"]
        monkeypatch.setattr(core.settings, "fullhtml_max_size_kb", 1, raising=False)
        raw = "a" * 500
        assert core._maybe_truncate_html(raw) == raw

    def test_no_cap_returns_original(self, test_env, monkeypatch):
        core = test_env["core"]
        monkeypatch.setattr(core.settings, "fullhtml_max_size_kb", 0, raising=False)
        raw = "é" * 100000
        assert core._maybe_truncate_html(raw) is raw


class TestGetDryrun:
    """D-5 — both --dryrun and --dry-run spellings are honoured."""

    def test_get_dryrun_variants(self, test_env):
        core = test_env["core"]
        assert core.get_dryrun(core.Namespace(dryrun=True)) is True
        assert core.get_dryrun(core.Namespace(dryrun=False)) is False
        assert core.get_dryrun(core.Namespace(dry_run='TRUE')) is True
        assert core.get_dryrun(core.Namespace(dry_run='FALSE')) is False
        assert core.get_dryrun(core.Namespace(dry_run=None)) is False
        assert core.get_dryrun(core.Namespace()) is False
        # store_true flag absent but --dry-run present
        assert core.get_dryrun(core.Namespace(dryrun=False, dry_run='TRUE')) is True


class TestDomainCrawlErrCaseInsensitive:
    """D-2 — --http=err (lowercase) matches too."""

    def test_err_filter_is_case_insensitive(self, fresh_db, monkeypatch):
        m = fresh_db["model"]
        core = fresh_db["core"]
        m.Domain.create(name="errlow.example", http_status='ERR_TRAFI',
                        fetched_at=datetime.now())
        m.Domain.create(name="ok.example", http_status='200',
                        fetched_at=datetime.now())

        crawled = []

        def fake_fetch(url, timeout=None):
            crawled.append(url)
            return None

        monkeypatch.setattr(core, "_fetch_url_with_retry_and_timeout", fake_fetch)
        monkeypatch.setattr(core.requests, "get",
                            lambda *a, **k: (_ for _ in ()).throw(
                                core.requests.RequestException("offline")))

        core.crawl_domains(limit=0, http='err')
        touched = {u.split('//')[1].split('/')[0] for u in crawled}
        assert touched == {'errlow.example'}


class TestUrlistKeyResolution:
    """D-4 — urlist reads the same key cascade as the search router."""

    def _clear_keys(self, controller, monkeypatch):
        monkeypatch.setattr(controller.settings, "SERPAPI_API_KEY", "", raising=False)
        monkeypatch.setattr(controller.settings, "serpapi_api_key", "", raising=False)
        monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
        monkeypatch.delenv("MWI_SERPAPI_API_KEY", raising=False)

    def test_urlist_without_any_key_aborts(self, fresh_db, monkeypatch, capsys):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        self._clear_keys(controller, monkeypatch)
        ret = controller.LandController.urlist(
            core.Namespace(name="missing_land_x", query="q"))
        assert ret == 0
        assert 'key missing' in capsys.readouterr().out

    def test_urlist_reads_upper_env_key(self, fresh_db, monkeypatch, capsys):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        self._clear_keys(controller, monkeypatch)
        monkeypatch.setenv("SERPAPI_API_KEY", "k-upper")
        ret = controller.LandController.urlist(
            core.Namespace(name="missing_land_x", query="q"))
        # Key accepted -> fails later at land lookup, not at the key check
        assert ret == 0
        out = capsys.readouterr().out
        assert 'key missing' not in out
        assert 'not found' in out

    def test_urlist_reads_upper_settings_key(self, fresh_db, monkeypatch, capsys):
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        self._clear_keys(controller, monkeypatch)
        monkeypatch.setattr(controller.settings, "SERPAPI_API_KEY", "k-settings",
                            raising=False)
        ret = controller.LandController.urlist(
            core.Namespace(name="missing_land_x", query="q"))
        assert ret == 0
        out = capsys.readouterr().out
        assert 'key missing' not in out
        assert 'not found' in out


class TestUrlistPersistence:
    """Window-by-window persistence keeps the legacy patched-fetch seam."""

    def test_urlist_persists_patched_fetch_results(self, fresh_db, monkeypatch, capsys):
        """Callers that patch fetch_serpapi_url_list to return a plain list
        (legacy tests, external scripts) still get their results persisted
        even though real runs insert window by window via the hook."""
        controller = fresh_db["controller"]
        core = fresh_db["core"]
        m = fresh_db["model"]
        m.Land.create(name="urlist_land", description="d", lang="en")
        monkeypatch.setattr(controller.settings, "SERPAPI_API_KEY", "k",
                            raising=False)
        monkeypatch.setattr(
            controller.core, "fetch_serpapi_url_list",
            lambda **kwargs: [
                {"position": 1, "title": "T1",
                 "link": "https://example.com/a", "date": None},
                {"position": 2, "title": "T2",
                 "link": "https://example.com/b", "date": None},
            ],
        )
        ret = controller.LandController.urlist(
            core.Namespace(name="urlist_land", query="q"))
        assert ret == 1
        assert "Added 2 new URLs" in capsys.readouterr().out
        land = m.Land.get(m.Land.name == "urlist_land")
        assert m.Expression.select().where(m.Expression.land == land).count() == 2
