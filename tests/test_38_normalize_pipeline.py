"""land normalize: id mapping, deterministic plan order, --limit semantics.

Sprint body-links, T1'. This ticket is NEUTRAL on the benchmark by design: it
merges duplicate NODES, which the resolution ladder already absorbed at lookup
time. Its deliverables are graph quality and a migration mapping for consumers
who reference internal ids.

The module had no direct unit test before this file: its seven private
functions were only exercised through the controller and a real database.
"""
import csv

import pytest

from mwi import normalize_pipeline


def _land_with_variants(fresh_db, urls, rules=None):
    """A land holding one expression per URL, plus the dedup rules."""
    model = fresh_db['model']
    core = fresh_db['core']
    controller = fresh_db['controller']
    controller.LandController.create(
        core.Namespace(name='L', desc='d', lang=['fr']))
    land = model.Land.get(model.Land.name == 'L')
    domain, _ = model.Domain.get_or_create(name='a.eu')
    made = []
    for url in urls:
        made.append(model.Expression.create(land=land, domain=domain, url=url,
                                            depth=0, relevance=1))
    return land, made


@pytest.fixture
def dedup_rules(monkeypatch):
    """force_https + strip_www + strip: the classic collision configuration."""
    from mwi import url_normalizer
    monkeypatch.setattr(url_normalizer.settings, 'url_normalization',
                        {'force_https': True, 'strip_www': True,
                         'trailing_slash': 'strip'}, raising=False)


class TestMappingExport:

    def test_merges_are_reported_to_the_sink(self, fresh_db, dedup_rules):
        land, made = _land_with_variants(
            fresh_db, ['https://a.eu/p', 'http://www.a.eu/p'])
        rows = []

        normalize_pipeline.normalize_land(land, mapping_sink=rows.append)

        assert rows, 'no mapping row emitted'
        old_ids = {r[0] for r in rows}
        assert made[1].id in old_ids or made[0].id in old_ids

    def test_a_rename_is_reported_with_equal_ids(self, fresh_db, dedup_rules):
        """old_id == new_id marks a renaming, not a merge."""
        land, made = _land_with_variants(fresh_db, ['http://www.a.eu/solo'])
        rows = []

        normalize_pipeline.normalize_land(land, mapping_sink=rows.append)

        assert rows == [(made[0].id, made[0].id, 'http://www.a.eu/solo',
                         'https://a.eu/solo')]

    def test_the_mapping_is_produced_in_dry_run(self, fresh_db, dedup_rules):
        """Its highest-value use: deciding whether to apply at all."""
        land, _ = _land_with_variants(
            fresh_db, ['https://a.eu/p', 'http://www.a.eu/p'])
        rows = []

        normalize_pipeline.normalize_land(land, dry_run=True,
                                          mapping_sink=rows.append)

        assert rows

    def test_the_return_type_is_unchanged(self, fresh_db, dedup_rules):
        """Callers read counters by name; the signature must stay Dict[str,int]."""
        land, _ = _land_with_variants(fresh_db, ['http://www.a.eu/p'])

        totals = normalize_pipeline.normalize_land(land)

        assert isinstance(totals, dict)
        assert all(isinstance(v, int) for v in totals.values())

    def test_merge_rows_are_transitively_closed(self, fresh_db, dedup_rules):
        """A -> B -> C must be flattened to A -> C, never A -> B."""
        land, _ = _land_with_variants(
            fresh_db, ['https://a.eu/p', 'http://www.a.eu/p', 'http://a.eu/p'])
        rows = []

        normalize_pipeline.normalize_land(land, mapping_sink=rows.append)

        merges = [r for r in rows if r[0] != r[1]]
        merged_away = {r[0] for r in merges}
        assert not merged_away & {r[1] for r in merges}


class TestDeterministicOrder:

    def test_the_plan_is_sorted_by_id(self, fresh_db, dedup_rules):
        """_collect_pairs iterates dicts; without a sort the order is a plan
        detail of SQLite, which the sprint forbids as an output dependency."""
        land, _ = _land_with_variants(
            fresh_db, ['http://www.a.eu/p{}'.format(i) for i in range(6)])

        to_rename, to_merge, _ = normalize_pipeline._collect_pairs(land)

        assert [r[0] for r in to_rename] == sorted(r[0] for r in to_rename)
        assert [m[0] for m in to_merge] == sorted(m[0] for m in to_merge)

    def test_two_runs_emit_the_same_mapping(self, fresh_db, dedup_rules):
        land, _ = _land_with_variants(
            fresh_db, ['http://www.a.eu/p{}'.format(i) for i in range(5)])
        first = []
        normalize_pipeline.normalize_land(land, dry_run=True,
                                          mapping_sink=first.append)
        second = []
        normalize_pipeline.normalize_land(land, dry_run=True,
                                          mapping_sink=second.append)

        assert first == second


class TestLimitSemantics:

    def test_limit_caps_groups_not_operations(self, fresh_db, dedup_rules):
        """Two collision groups, limit=1 -> one group fully handled."""
        land, _ = _land_with_variants(
            fresh_db, ['https://a.eu/x', 'http://www.a.eu/x',
                       'https://a.eu/y', 'http://www.a.eu/y'])

        totals = normalize_pipeline.normalize_land(land, limit=1)

        assert totals['merged'] == 1

    def test_limit_reaches_merges_even_when_renames_are_pending(
            self, fresh_db, dedup_rules):
        """The defect: renames consumed the whole budget, so the risky half of
        the pipeline -- edge remapping, backfill, cascading delete -- was
        unreachable on a slice."""
        land, _ = _land_with_variants(
            fresh_db, ['http://www.a.eu/r1', 'http://www.a.eu/r2',
                       'http://www.a.eu/r3',
                       'https://a.eu/m', 'http://www.a.eu/m'])

        totals = normalize_pipeline.normalize_land(land, limit=4)

        assert totals['merged'] >= 1

    def test_limit_zero_processes_everything(self, fresh_db, dedup_rules):
        land, _ = _land_with_variants(
            fresh_db, ['https://a.eu/p', 'http://www.a.eu/p',
                       'http://www.a.eu/q'])

        totals = normalize_pipeline.normalize_land(land, limit=0)

        assert totals['merged'] + totals['renamed'] + totals['promoted'] >= 2


class TestControllerWiring:

    def test_mapping_out_writes_a_csv(self, fresh_db, dedup_rules, tmp_path):
        controller = fresh_db['controller']
        core = fresh_db['core']
        _land_with_variants(fresh_db, ['https://a.eu/p', 'http://www.a.eu/p'])
        out = str(tmp_path / 'mapping.csv')

        ret = controller.LandController.normalize(core.Namespace(
            name='L', dry_run=None, reset_status=None, verbose=None,
            limit=0, mapping_out=out))

        assert ret == 1
        with open(out, encoding='utf-8') as handle:
            rows = list(csv.reader(handle))
        assert rows[0] == ['old_id', 'new_id', 'old_url', 'canonical_url']
        assert len(rows) > 1

    def test_an_unwritable_path_fails_before_touching_the_database(
            self, fresh_db, dedup_rules, tmp_path):
        """A typo must cost a second, not forty minutes of merges."""
        controller = fresh_db['controller']
        core = fresh_db['core']
        model = fresh_db['model']
        _land_with_variants(fresh_db, ['https://a.eu/p', 'http://www.a.eu/p'])
        before = model.Expression.select().count()

        ret = controller.LandController.normalize(core.Namespace(
            name='L', dry_run=None, reset_status=None, verbose=None,
            limit=0, mapping_out=str(tmp_path / 'nope' / 'x.csv')))

        assert ret == 0
        assert model.Expression.select().count() == before

    def test_absent_flag_keeps_the_previous_behaviour(self, fresh_db,
                                                      dedup_rules):
        """Namespaces built without mapping_out must keep working."""
        controller = fresh_db['controller']
        core = fresh_db['core']
        _land_with_variants(fresh_db, ['http://www.a.eu/p'])

        ret = controller.LandController.normalize(core.Namespace(
            name='L', dry_run=None, reset_status=None, verbose=None, limit=0))

        assert ret == 1
