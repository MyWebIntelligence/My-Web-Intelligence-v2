"""R01 - every relative link in the READMEs must resolve to a versioned file.

The commit `c60246c` (2026-06-24, "drop legacy docs") moved eight user guides
under `.claude/docs/`, which `.gitignore` excludes: `git ls-tree -r HEAD docs/`
listed two files while the READMEs pointed at guides nobody cloning the
repository — or downloading the Zenodo archive — could ever open. 13 of 17
relative links were dead. No test covered it.

Scope: the two READMEs only. They are the entry point, the JOSS reviewer's
first read, and the one place where a dead link costs credibility.

Two rules, both of which have bitten this project:

1. the target must exist **by exact name**. APFS is case-insensitive, so a
   `Docs/Guide.md` link resolves happily here and 404s for a reviewer on Linux;
2. no path segment may start with a dot. The `.gitignore` rule is encoded
   statically rather than shelled out to `git check-ignore`, so this test still
   means something inside a Zenodo tarball that has no `.git/` at all.
"""

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
READMES = ['README.md', 'README_fr.md']

# [label](target) — the label may itself contain brackets (badges).
LINK_RE = re.compile(r'\[[^\]]*\]\(([^)\s]+)\)')
SKIP_PREFIXES = ('http://', 'https://', 'mailto:', '#', 'data:')


def _relative_links(path):
    text = path.read_text(encoding='utf-8')
    for target in LINK_RE.findall(text):
        if target.startswith(SKIP_PREFIXES) or '://' in target:
            continue
        yield target.split('#', 1)[0]


def _cases():
    out = []
    for name in READMES:
        path = REPO_ROOT / name
        if not path.is_file():
            continue
        for target in _relative_links(path):
            if target:
                out.append(pytest.param(name, target,
                                        id="%s::%s" % (name, target)))
    return out


CASES = _cases()


def test_there_is_something_to_check():
    """Guard: a regex that silently matches nothing would make this file green."""
    assert len(CASES) >= 10


@pytest.mark.parametrize('readme,target', CASES)
def test_relative_link_points_at_a_versioned_file(readme, target):
    resolved = (REPO_ROOT / target).resolve()

    parts = Path(target).parts
    hidden = [p for p in parts if p.startswith('.') and p not in ('.', '..')]
    assert not hidden, (
        "%s links to %s, under a dot-directory that .gitignore excludes: a "
        "reader who clones the repo or downloads the Zenodo archive cannot "
        "open it" % (readme, target))

    parent = resolved.parent
    assert parent.is_dir(), "%s links to %s: no such directory" % (readme,
                                                                   target)
    # Exact-name check: APFS is case-insensitive, a Linux reviewer is not.
    assert resolved.name in os.listdir(parent), (
        "%s links to %s, which does not exist under that exact name"
        % (readme, target))
