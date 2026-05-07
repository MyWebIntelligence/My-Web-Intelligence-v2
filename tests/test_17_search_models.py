"""Tests for the search router data models (J2 of sprint-searchrouter).

Covers:
- Persistent Peewee classes ``SearchQuery`` and ``SearchResultLog``: insertion,
  FK cascade, unique constraint on (search_query, url), JSON round-trip on
  ``usage_report``.
- In-memory dataclasses (``SearchResult``, ``ProviderUsage``,
  ``ProviderStatus``): default values and JSON-friendly representation.
- Migration 010 idempotence (two consecutive ``upgrade()`` calls).
"""

from __future__ import annotations

import json

import pytest

from mwi.search.models import ProviderStatus, ProviderUsage, SearchResult


# ---------------------------------------------------------------------------
# Persistent Peewee models
# ---------------------------------------------------------------------------

def test_search_query_insertion(fresh_db):
    """SearchQuery rows are inserted with the expected defaults."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-sq", description="d", lang="fr")

    sq = m.SearchQuery.create(
        land=land,
        query="humanités numériques",
        strategy="parallel",
        language="fr",
        num_requested=20,
    )

    fetched = m.SearchQuery.get_by_id(sq.id)
    assert fetched.query == "humanités numériques"
    assert fetched.strategy == "parallel"
    assert fetched.num_collected == 0
    assert fetched.completed_at is None
    assert fetched.usage_report is None


def test_search_result_log_unique_constraint(fresh_db):
    """Same (search_query, url) cannot be inserted twice."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-uniq", description="d", lang="fr")
    sq = m.SearchQuery.create(land=land, query="q", strategy="fallback")

    m.SearchResultLog.create(
        search_query=sq, url="https://a.com/x", providers="searxng", rank_min=1
    )
    with pytest.raises(Exception):
        m.SearchResultLog.create(
            search_query=sq, url="https://a.com/x", providers="brave", rank_min=2
        )


def test_search_result_log_two_queries_same_url(fresh_db):
    """The same URL CAN be logged for two distinct SearchQueries."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-2q", description="d", lang="fr")
    sq1 = m.SearchQuery.create(land=land, query="q1", strategy="fallback")
    sq2 = m.SearchQuery.create(land=land, query="q2", strategy="parallel")

    m.SearchResultLog.create(search_query=sq1, url="https://a.com/x", providers="s")
    m.SearchResultLog.create(search_query=sq2, url="https://a.com/x", providers="s")

    assert m.SearchResultLog.select().count() == 2


def test_cascade_delete_search_query(fresh_db):
    """Deleting a SearchQuery cascades to its SearchResultLog rows."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-cas", description="d", lang="fr")
    sq = m.SearchQuery.create(land=land, query="q", strategy="fallback")
    m.SearchResultLog.create(search_query=sq, url="https://a.com/1", providers="s")
    m.SearchResultLog.create(search_query=sq, url="https://a.com/2", providers="s")
    assert m.SearchResultLog.select().count() == 2
    sq.delete_instance(recursive=False)
    assert m.SearchResultLog.select().count() == 0


def test_cascade_delete_land(fresh_db):
    """Deleting a Land cascades to its SearchQuery rows (and their logs)."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-cas-land", description="d", lang="fr")
    sq = m.SearchQuery.create(land=land, query="q", strategy="parallel")
    m.SearchResultLog.create(search_query=sq, url="https://a.com/x", providers="s")
    assert m.SearchQuery.select().count() == 1
    assert m.SearchResultLog.select().count() == 1
    land.delete_instance(recursive=True)
    assert m.SearchQuery.select().count() == 0
    assert m.SearchResultLog.select().count() == 0


def test_usage_report_json_roundtrip(fresh_db):
    """The TextField ``usage_report`` round-trips through JSON correctly."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-json", description="d", lang="fr")

    report = {
        "searxng": {"calls": 1, "errors": 0, "status": "ok",
                    "monthly_quota": None},
        "brave":   {"calls": 1, "errors": 1, "status": "quota_exceeded",
                    "monthly_quota": 1000},
    }
    sq = m.SearchQuery.create(
        land=land, query="q", strategy="parallel",
        usage_report=json.dumps(report),
    )
    fetched = m.SearchQuery.get_by_id(sq.id)
    decoded = json.loads(fetched.usage_report)
    assert decoded == report


def test_search_result_log_expression_set_null_on_delete(fresh_db):
    """When the linked Expression is deleted, the log's FK becomes NULL."""
    m = fresh_db["model"]
    land = m.Land.create(name="t-setnull", description="d", lang="fr")
    domain = m.Domain.create(name="example.com")
    expr = m.Expression.create(land=land, domain=domain, url="https://example.com/p")
    sq = m.SearchQuery.create(land=land, query="q", strategy="fallback")
    log = m.SearchResultLog.create(
        search_query=sq, url=expr.url, providers="searxng", expression=expr,
    )
    expr.delete_instance(recursive=False)
    fetched = m.SearchResultLog.get_by_id(log.id)
    assert fetched.expression is None


# ---------------------------------------------------------------------------
# In-memory dataclasses
# ---------------------------------------------------------------------------

def test_provider_status_values_are_stable():
    """Enum values are part of the public API — they must not change silently."""
    assert ProviderStatus.OK.value == "ok"
    assert ProviderStatus.QUOTA_EXCEEDED.value == "quota_exceeded"
    assert ProviderStatus.ERROR.value == "error"
    assert ProviderStatus.NOT_CONFIGURED.value == "not_configured"


def test_search_result_to_dict_drops_raw():
    """``raw`` is debug-only and must not appear in serialised output."""
    r = SearchResult(
        url="https://x", title="t", snippet="s", rank=1,
        providers="searxng", raw={"junk": True},
    )
    d = r.to_dict()
    assert "raw" not in d
    assert d["url"] == "https://x"
    assert d["providers"] == "searxng"


def test_provider_usage_to_dict_serialises_status():
    """``ProviderUsage.to_dict()`` returns the status as its string value."""
    u = ProviderUsage(
        name="searxng", calls=3, errors=1,
        status=ProviderStatus.QUOTA_EXCEEDED, monthly_quota=1000,
    )
    d = u.to_dict()
    assert d == {
        "name": "searxng", "calls": 3, "errors": 1,
        "status": "quota_exceeded", "monthly_quota": 1000,
    }
    # Round-trips cleanly through json.
    assert json.loads(json.dumps(d)) == d


# ---------------------------------------------------------------------------
# Migration idempotence
# ---------------------------------------------------------------------------

def test_migration_010_is_idempotent(fresh_db):
    """Running migration 010 twice does not raise (safe=True semantics)."""
    import importlib
    spec = importlib.util.find_spec  # noqa: F401 — sanity import path

    # Load the migration module by file path (matches MigrationManager).
    import importlib.util
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mig_path = os.path.join(here, "migrations", "010_add_search_tables.py")
    spec = importlib.util.spec_from_file_location("_mig010", mig_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.upgrade()  # tables already exist (fresh_db ran setup)
    mod.upgrade()  # second run still works
