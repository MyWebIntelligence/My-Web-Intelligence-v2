"""Unit tests for the unified markdown link parser (sprint EXTRACTLINKS-2026-06).

Locks the contract of ``mwi.link_context.iter_markdown_link_tokens`` /
``extract_markdown_links`` (and the ``core.extract_md_links`` wrapper) against
the two bug families found by the airegulation audits:

- Family A — URL corruption: A1 greedy overflow, A2 paren truncation,
  A3 autolink blindness, A4 image contamination.
- Family B — relative-link blindness ([text](/path) silently lost).

Plus the hardened ``core.is_crawlable`` (extension tested on the path, not the
whole URL). All 18 cases come from the sprint Annexe B (real audit data).
"""

import pytest

from mwi import link_context
from mwi.core import extract_md_links, is_crawlable


SAFELINK = ("https://gcc02.safelinks.protection.outlook.com/?url=https%3A%2F%2F"
            "nist.gov%2Fai&data=05%7C01%7C&reserved=0")


# --- Annexe B: the 18 reference cases (md, base_url, expected) ---------------
ANNEXE_B = [
    # 1 — A1 simple: trailing bare "(2020)" must not be swallowed
    ("[ArXiv](http://arxiv.org/abs/2011.02395)(2020)", None,
     ["http://arxiv.org/abs/2011.02395"]),
    # 2 — A1 multi: only the bracketed DOI link, no overflow merge
    ("...PMC6963795/)[[DOI](https://doi.org/10.3390/jintelligence7040023)]",
     None, ["https://doi.org/10.3390/jintelligence7040023"]),
    # 3 — A2: balanced wikipedia parens preserved
    ("[x](https://en.wikipedia.org/wiki/Runaround_(story))", None,
     ["https://en.wikipedia.org/wiki/Runaround_(story)"]),
    # 4 — A2: IPOL_STU(2020) balanced parens preserved
    ("[x](https://www.europarl.europa.eu/thinktank/en/document/IPOL_STU(2020))",
     None, ["https://www.europarl.europa.eu/thinktank/en/document/IPOL_STU(2020)"]),
    # 5 — A3: autolink <url>
    ("final <https://perma.cc/54M5-V8YB>, see above", None,
     ["https://perma.cc/54M5-V8YB"]),
    # 6 — A4: image excluded
    ("![logo](https://site.org/img/logo.png)", None, []),
    # 7 — title with double quote
    ('[doc](https://a.org/p "Titre")', None, ["https://a.org/p"]),
    # 8 — nominal
    ("[clean](https://example.org/article)", None,
     ["https://example.org/article"]),
    # 9 — Family B: relative link resolved against base
    ("[Article 57](/en/ai-act/article-57)",
     "https://ai-act-service-desk.ec.europa.eu/en/ai-act-explorer",
     ["https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-57"]),
    # 10 — Family B retro-compat: relative dropped without base
    ("[Article 57](/en/ai-act/article-57)", None, []),
    # 11 — case-sensitive path preserved
    ("[x](https://site.com/Runaround_CamelCase)", None,
     ["https://site.com/Runaround_CamelCase"]),
    # 14 — mixed image + real link
    ("![img](https://a.org/x.png) then [real](https://b.org/y)", None,
     ["https://b.org/y"]),
    # 15 — A1 monster: long single token (no space) kept whole
    (f"[x]({SAFELINK})", None, [SAFELINK]),
    # 16 — A4 empty alt image excluded
    ("![](https://a.org/logo.png)", None, []),
    # 17 — Family B relative "../"
    ("[r](../article/5)", "https://artificialintelligenceact.eu/article/1",
     ["https://artificialintelligenceact.eu/article/5"]),
    # 18 — adjacent links
    ("[a](https://a.org/1)[b](https://b.org/2)", None,
     ["https://a.org/1", "https://b.org/2"]),
]


class TestExtractMarkdownLinks:
    """link_context.extract_markdown_links — the resolving public API."""

    @pytest.mark.parametrize("md,base,expected", ANNEXE_B)
    def test_annexe_b_cases(self, md, base, expected):
        assert link_context.extract_markdown_links(md, base) == expected

    # 12 — legacy compat: bracketed link kept, bare paren ignored
    def test_legacy_bracketed_kept_bare_paren_dropped(self):
        out = link_context.extract_markdown_links(
            "See [link](https://example.com/path) and (https://foo.com/path)")
        assert "https://example.com/path" in out
        assert "https://foo.com/path" not in out

    # 13 — robustness: None / empty
    @pytest.mark.parametrize("bad", [None, "", "   ", 123, []])
    def test_empty_or_none_returns_empty(self, bad):
        assert link_context.extract_markdown_links(bad) == []

    def test_mailto_token_filtered_out(self):
        # iter yields the raw token, but the http(s)/ftp gate drops mailto.
        assert link_context.extract_markdown_links(
            "[mail](mailto:foo@bar.com)") == []

    def test_ftp_autolink_accepted_by_parser(self):
        # ftp passes the parser gate (filtered later by is_crawlable; §12 n.3).
        assert link_context.extract_markdown_links(
            "<ftp://ftp.x.org/pub/file>") == ["ftp://ftp.x.org/pub/file"]

    def test_deeply_nested_parens_balanced(self):
        url = "https://x.org/a(b(c)d)e"
        assert link_context.extract_markdown_links(f"[k]({url})") == [url]

    def test_no_link_returns_empty(self):
        assert link_context.extract_markdown_links(
            "Plain text, no links here at all.") == []

    def test_bare_quote_in_url_not_truncated(self):
        # Regression (review BLOCKER): a literal quote inside the destination
        # is a legal URL char, not a title marker — must NOT truncate.
        assert link_context.extract_markdown_links(
            '[s](https://a.org/find?q="cats")') == ['https://a.org/find?q="cats"']
        assert link_context.extract_markdown_links(
            "[s](https://a.org/find?q='cats')") == ["https://a.org/find?q='cats'"]

    def test_title_with_preceding_space_still_stripped(self):
        # A real CommonMark title (space-separated) is still dropped.
        assert link_context.extract_markdown_links(
            '[d](https://a.org/p "A Title")') == ['https://a.org/p']
        assert link_context.extract_markdown_links(
            "[d](https://a.org/p 'A Title')") == ['https://a.org/p']

    def test_duplicates_preserved(self):
        md = "[a](https://x.org/1)[b](https://x.org/1)"
        assert link_context.extract_markdown_links(md) == [
            "https://x.org/1", "https://x.org/1"]


class TestIterMarkdownLinkTokens:
    """Raw token iterator — keeps the literal (relative) href for raw_url."""

    def test_relative_token_preserved_literally(self):
        assert list(link_context.iter_markdown_link_tokens(
            "[r](/en/ai-act/article-57)")) == ["/en/ai-act/article-57"]

    def test_image_excluded_at_token_level(self):
        assert list(link_context.iter_markdown_link_tokens(
            "![a](https://x.org/i.png)")) == []

    def test_autolink_token(self):
        assert list(link_context.iter_markdown_link_tokens(
            "<https://perma.cc/x>")) == ["https://perma.cc/x"]

    def test_none_yields_nothing(self):
        assert list(link_context.iter_markdown_link_tokens(None)) == []


class TestExtractMdLinksWrapper:
    """core.extract_md_links delegates to the unified parser."""

    def test_wrapper_resolves_relative_with_base(self):
        out = extract_md_links("[r](/p)", "https://x.org/dir/page")
        assert out == ["https://x.org/p"]

    def test_wrapper_drops_relative_without_base(self):
        assert extract_md_links("[r](/p)") == []

    def test_wrapper_handles_none(self):
        assert extract_md_links(None) == []


class TestIsCrawlableHardened:
    """is_crawlable tests the extension on urlparse(url).path, not the URL."""

    @pytest.mark.parametrize("url,expected", [
        ("https://x.org/a.pdf?dl=1", False),   # query no longer smuggles binary
        ("https://x.org/article", True),
        ("https://x.org/page#sec", True),      # fragment no longer fakes binary
        ("https://x.org/img.png", False),
        ("https://x.org/doc.PDF", False),      # case-insensitive on the path
        ("https://x.org/data.zip", False),
        ("https://x.org/clip.mp4", False),
        ("https://x.org/pic.svg", False),
        ("ftp://x.org/file", False),           # http(s) only
        ("http://x.org/ok", True),
        (None, False),
        ("", False),
    ])
    def test_is_crawlable(self, url, expected):
        assert is_crawlable(url) is expected
