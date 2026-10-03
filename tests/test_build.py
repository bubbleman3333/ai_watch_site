from datetime import date

from aiwatch.build import Builder, ROOT, bars, sparkline


def test_sparkline_and_bars_are_svg():
    assert sparkline([1, 3, 2]).startswith("<svg")
    assert sparkline([]).startswith("<svg")
    assert "<rect" in bars([1, 2, 3], ["a", "b", "c"], "#000")


def test_build_whole_site(tmp_path):
    """手元にあるデータでサイト全体を作り、主なページが出ることだけ確かめる。"""
    out = tmp_path / "dist"
    n = Builder(out, "https://example.com", root=ROOT, today=date.today()).build()
    assert n > 20
    for p in ("index.html", "topic/rag/index.html", "industry/retail/index.html", "models/index.html",
              "start/index.html", "sitemap.xml", "feed.xml", "404.html"):
        assert (out / p).exists(), p
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "https://example.com/topic/agents/" in html
    # Markdown のサイト内リンクが URL になっている
    assert "](topic:" not in (out / "start" / "index.html").read_text(encoding="utf-8")
