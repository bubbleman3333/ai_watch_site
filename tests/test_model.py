import json
from datetime import date

from aiwatch.model import load_all, parse_note, pick_for_notes, topic_stats, week_key
from aiwatch.feeds import Feed
from aiwatch.sources import first_sentences, parse_feed, save_items
from aiwatch.topics import TOPICS, classify


def test_classify_picks_topics_by_keywords():
    assert classify("Retrieval-Augmented Generation for enterprise search")[0] == "rag"
    assert "agents" in classify("An agentic framework for computer use")
    assert "speech" in classify("音声認識で議事録を自動作成")
    assert classify("") == []


def test_every_topic_has_query_and_keywords():
    slugs = [t.slug for t in TOPICS]
    assert len(slugs) == len(set(slugs))
    for t in TOPICS:
        assert t.keywords and t.arxiv and t.color.startswith("#")


def test_parse_note_reads_front_matter():
    n = parse_note("---\nheadline: 見出し\npoint: 要点\n---\n### 何が起きた\n本文")
    assert n["headline"] == "見出し" and n["point"] == "要点" and n["body"].startswith("### 何が起きた")
    assert parse_note("本文だけ")["body"] == "本文だけ"


def test_first_sentences_cuts_at_sentence():
    s = first_sentences("First sentence. Second one is here. Third." * 5, 40)
    assert s.startswith("First sentence.") and len(s) <= 40


def test_parse_feed_rss_and_atom():
    rss = b"""<rss><channel><item><title>Introducing X</title><link>https://ex.com/a</link>
      <pubDate>Tue, 29 Sep 2026 10:00:00 GMT</pubDate></item></channel></rss>"""
    rows = parse_feed(rss, Feed("openai", "OpenAI", "", "news"))
    assert rows[0]["date"] == "2026-09-29" and rows[0]["url"] == "https://ex.com/a"
    atom = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Y</title>
      <link rel="alternate" href="https://ex.com/b"/><updated>2026-09-30T01:00:00Z</updated></entry></feed>"""
    assert parse_feed(atom, Feed("x", "X", "", "media"))[0]["url"] == "https://ex.com/b"
    rdf = """<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/"
      xmlns:dc="http://purl.org/dc/elements/1.1/"><item><title>生成AIの新機能</title><link>https://ex.com/c</link>
      <dc:date>2026-10-01T09:00:00+09:00</dc:date></item><item><title>決算発表</title><link>https://ex.com/d</link>
      <dc:date>2026-10-01T09:00:00+09:00</dc:date></item></rdf:RDF>""".encode("utf-8")
    rows = parse_feed(rdf, Feed("x", "X", "", "media", "ja", filter=True))
    assert [r["url"] for r in rows] == ["https://ex.com/c"]   # AI と関係ない記事は落とす


def _item(i, source="hn", kind="discussion", day="2026-09-30", score=10, title="LLM agents"):
    return {"id": f"{source}-{i}", "source": source, "kind": kind, "title": title, "url": f"https://ex.com/{i}",
            "date": day, "summary": "", "score": score, "extra": {}}


def test_save_items_keeps_first_and_updates_score(tmp_path):
    assert save_items(tmp_path, "hn", [_item(1, score=5)]) == 1
    assert save_items(tmp_path, "hn", [_item(1, score=50, title="changed")]) == 0
    raw = json.loads((tmp_path / "items" / "hn" / "2026-09.json").read_text(encoding="utf-8"))
    assert raw["hn-1"]["score"] == 50 and raw["hn-1"]["title"] == "LLM agents"


def test_corpus_heat_stats_and_notes(tmp_path):
    data = tmp_path / "data"
    save_items(data, "hn", [_item(i, score=i * 10) for i in range(1, 6)])
    save_items(data, "news", [_item(9, source="news", kind="news", title="Introducing RAG search") | {"extra": {"feed": "openai", "publisher": "OpenAI"}}])
    (data / "arxiv_weekly.json").write_text(json.dumps({
        "_all": {f"2026-{m:02d}-{d:02d}": 1000 for m, d in [(7, 6), (7, 13), (7, 20), (7, 27), (8, 3), (8, 10), (8, 17), (8, 24), (8, 31), (9, 7), (9, 14), (9, 21)]},
        "agents": {"2026-09-21": 300, "2026-07-06": 100},
    }), encoding="utf-8")
    (data / "models").mkdir()
    (data / "models" / "2026-10-01.json").write_text(json.dumps([
        {"id": "a/ok", "task": "text-to-speech", "tags": []}, {"id": "b/x-Uncensored", "task": "text-generation", "tags": []}]),
        encoding="utf-8")
    notes = tmp_path / "content" / "notes"
    notes.mkdir(parents=True)
    (notes / "hn-5.md").write_text("---\nheadline: 見出し\n---\n本文", encoding="utf-8")

    c = load_all(data, notes, today=date(2026, 10, 2))
    hot = c.hot(days=7, n=3)
    assert hot[0].id in ("hn-5", "news-9")
    assert c.by_id["hn-5"].headline == "見出し"
    assert [m.id for m in c.models] == ["a/ok"]            # 検閲外しのモデルは載せない
    assert c.models[0].topics[0] == "speech"
    st = {s.slug: s for s in topic_stats(c)}
    assert st["agents"].momentum > 1
    picks = pick_for_notes(c, notes)
    assert "hn-5" not in [getattr(p, "id", None) for p in picks]


def test_week_key():
    assert week_key(date(2026, 10, 4)) == "2026-W40"


def test_scrape_anthropic():
    from aiwatch.sources import scrape_anthropic
    html = '<a href="/news/x-y"><time class="d">Oct 2, 2026</time><span>Announcements</span><h3>Long title of the news</h3></a>'
    rows = scrape_anthropic(html, "anthropic", "Anthropic", "news")
    assert rows[0]["date"] == "2026-10-02" and rows[0]["title"] == "Long title of the news"
