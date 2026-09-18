"""Link profiles at export: the `kind` column and `--link-profile`.

Sprint body-links, T4. Two contracts matter here:

* `kind` is appended at the END of every link header, so a consumer selecting
  columns by name is unaffected;
* the whole-page network (`*pageslinksfullhtml.csv`) is NEVER filtered by a
  profile. It is the comparator that validates the whole sprint -- filtering it
  would destroy the only measurement that says whether the body network is
  getting better.
"""
import csv
import os

import pytest

from mwi import export as export_module


def _rows(path):
    with open(path, encoding='utf-8') as handle:
        return list(csv.reader(handle))


@pytest.fixture
def linked_land(fresh_db):
    """A land with one edge of each structural kind."""
    model = fresh_db['model']
    core = fresh_db['core']
    controller = fresh_db['controller']
    controller.LandController.create(
        core.Namespace(name='L', desc='d', lang=['fr']))
    land = model.Land.get(model.Land.name == 'L')
    domain, _ = model.Domain.get_or_create(name='site.test')
    # Targets live on a second domain so the domain-level graph is non-empty.
    other, _ = model.Domain.get_or_create(name='cible.test')

    source = model.Expression.create(land=land, domain=domain, depth=0,
                                     relevance=5, url='https://site.test/a',
                                     readable='texte')
    targets = {}
    for kind in ('body', 'ref', 'reco', 'toc', 'nav', None):
        name = kind or 'legacy'
        target = model.Expression.create(
            land=land, domain=other, depth=1, relevance=5,
            url='https://site.test/t-{}'.format(name))
        model.ExpressionLink.create(source=source, target=target, kind=kind)
        targets[name] = target
    fresh_db['land'] = land
    fresh_db['targets'] = targets
    return fresh_db


def _export(land, tmp_path, name, profile=None):
    kwargs = {} if profile is None else {'link_profile': profile}
    exporter = export_module.Export('nodelinkcsv', land, 1, **kwargs)
    out = str(tmp_path / name)
    exporter.write('nodelinkcsv', out)
    return out


class TestKindColumn:

    def test_kind_is_the_last_column_of_pageslinks(self, linked_land, tmp_path):
        _export(linked_land['land'], tmp_path, 'e')

        header = _rows(str(tmp_path / 'e_pageslinks.csv'))[0]
        assert header[-1] == 'kind'

    def test_null_kind_is_exported_as_body(self, linked_land, tmp_path):
        _export(linked_land['land'], tmp_path, 'e')

        rows = _rows(str(tmp_path / 'e_pageslinks.csv'))
        header, data = rows[0], rows[1:]
        kinds = {r[header.index('target_url')]: r[header.index('kind')]
                 for r in data}
        assert kinds['https://site.test/t-legacy'] == 'body'


class TestProfileFiltering:

    def test_default_profile_keeps_body_and_ref(self, linked_land, tmp_path):
        _export(linked_land['land'], tmp_path, 'e')

        rows = _rows(str(tmp_path / 'e_pageslinks.csv'))
        header = rows[0]
        kinds = sorted(r[header.index('kind')] for r in rows[1:])
        assert kinds == ['body', 'body', 'ref']

    def test_all_profile_keeps_every_kind(self, linked_land, tmp_path):
        _export(linked_land['land'], tmp_path, 'e', profile='all')

        rows = _rows(str(tmp_path / 'e_pageslinks.csv'))
        header = rows[0]
        kinds = sorted(r[header.index('kind')] for r in rows[1:])
        assert kinds == ['body', 'body', 'nav', 'reco', 'ref', 'toc']

    def test_citation_plus_reco_adds_reco_only(self, linked_land, tmp_path):
        _export(linked_land['land'], tmp_path, 'e', profile='citation+reco')

        rows = _rows(str(tmp_path / 'e_pageslinks.csv'))
        header = rows[0]
        kinds = sorted(r[header.index('kind')] for r in rows[1:])
        assert kinds == ['body', 'body', 'reco', 'ref']

    def test_unknown_profile_falls_back_without_raising(self, linked_land,
                                                        tmp_path):
        _export(linked_land['land'], tmp_path, 'e', profile='nonexistent')

        rows = _rows(str(tmp_path / 'e_pageslinks.csv'))
        header = rows[0]
        kinds = sorted(r[header.index('kind')] for r in rows[1:])
        assert kinds == ['body', 'body', 'ref']

    def test_domain_links_follow_the_same_profile(self, linked_land, tmp_path):
        """Otherwise pageslinks and domainlinks describe two different graphs."""
        _export(linked_land['land'], tmp_path, 'strict')
        _export(linked_land['land'], tmp_path, 'wide', profile='all')

        strict = _rows(str(tmp_path / 'strict_domainlinks.csv'))
        wide = _rows(str(tmp_path / 'wide_domainlinks.csv'))
        assert strict != wide


class TestWholePageNetworkIsNeverFiltered:

    def test_fullhtml_output_is_identical_under_every_profile(self, linked_land,
                                                              tmp_path):
        """The comparator that validates the sprint must not move."""
        land = linked_land['land']
        for expression in linked_land['model'].Expression.select():
            expression.html = ('<html><body><p>'
                               '<a href="https://site.test/t-nav">x</a>'
                               '</p></body></html>')
            expression.save()

        strict = export_module.Export('nodelinkcsv', land, 1, fullhtml=True,
                                      link_profile='citation')
        strict.write('nodelinkcsv', str(tmp_path / 'strict'))
        wide = export_module.Export('nodelinkcsv', land, 1, fullhtml=True,
                                    link_profile='all')
        wide.write('nodelinkcsv', str(tmp_path / 'wide'))

        left = open(str(tmp_path / 'strict_pageslinksfullhtml.csv'), 'rb').read()
        right = open(str(tmp_path / 'wide_pageslinksfullhtml.csv'), 'rb').read()
        assert left == right

    def test_raw_only_edges_carry_no_kind(self, linked_land, tmp_path):
        """A link absent from the body has no structural zone to report."""
        land = linked_land['land']
        source = (linked_land['model'].Expression
                  .get(linked_land['model'].Expression.url == 'https://site.test/a'))
        source.html = ('<html><body><p>'
                       '<a href="https://site.test/t-rawonly">x</a>'
                       '</p></body></html>')
        source.save()
        linked_land['model'].Expression.create(
            land=land, domain=source.domain, depth=1, relevance=5,
            url='https://site.test/t-rawonly')

        exporter = export_module.Export('nodelinkcsv', land, 1, fullhtml=True)
        exporter.write('nodelinkcsv', str(tmp_path / 'e'))

        rows = _rows(str(tmp_path / 'e_pageslinksfullhtml.csv'))
        header = rows[0]
        raw = [r for r in rows[1:] if r[header.index('weightbody')] == '0']
        assert raw and all(r[header.index('kind')] == '' for r in raw)


class TestCliPlumbing:

    def test_controller_passes_the_profile_through(self, linked_land,
                                                   monkeypatch):
        core = linked_land['core']
        controller = linked_land['controller']
        seen = {}

        # **kwargs: production keeps adding optional export arguments
        # (`method=` landed with A11). A rigid signature would raise TypeError
        # here and the test would stop asserting anything useful.
        def fake_export(land, export_type, minrel, fullhtml=False,
                        link_profile=None, **kwargs):
            seen['profile'] = link_profile

        monkeypatch.setattr(core, 'export_land', fake_export)
        monkeypatch.setattr(controller.core, 'export_land', fake_export)

        controller.LandController.export(core.Namespace(
            name='L', type='pagecsv', minrel=1, link_profile='all'))

        assert seen['profile'] == 'all'

    def test_default_profile_is_used_when_the_flag_is_absent(self, linked_land,
                                                             tmp_path):
        land = linked_land['land']
        exporter = export_module.Export('nodelinkcsv', land, 1)

        assert exporter.link_profile == export_module.DEFAULT_LINK_PROFILE
        assert os.path.basename(str(tmp_path))  # tmp_path used, keeps lint quiet
