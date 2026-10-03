"""取り込み。キー不要の公開 API と RSS だけを使う。

保存するのは「題名・リンク・日付・数字（いいね数など）・短い抜粋」だけ。記事本文は保存しない。
各社ブログ・ニュースは題名とリンクだけ（本文は元のページで読んでもらう）。

保存先:
  data/items/<source>/<YYYY-MM>.json   1 か月分を {id: item} で
  data/models/<YYYY-MM-DD>.json         その日の Hugging Face トレンド上位
  data/arxiv_weekly.json                テーマごと・週ごとの arXiv の論文数
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from .feeds import AI_WORDS, FEEDS, SCRAPED, Feed
from .topics import TOPICS

UA = "ai-watch/1.0 (+https://ai-watch.rakunowa.workers.dev/about/)"
ARXIV_CATS = "(cat:cs.AI OR cat:cs.CL OR cat:cs.LG OR cat:cs.CV OR cat:cs.RO)"
KEEP_DAYS = 400

HN_QUERIES = ("AI", "LLM", "GPT", "Claude", "Gemini", "OpenAI", "Anthropic", "agent", "model", "DeepSeek", "Qwen", "Llama")
GITHUB_TOPICS = ("llm", "ai-agents", "agents", "mcp", "rag", "generative-ai", "large-language-models",
                 "diffusion", "speech", "computer-vision", "ai")


class Http:
    def __init__(self, sleep: float = 0.5):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.sleep = sleep
        self._last: dict[str, float] = {}

    def get(self, url: str, *, params=None, headers=None, min_gap: float | None = None, tries: int = 4):
        host = url.split("/")[2]
        gap = self.sleep if min_gap is None else min_gap
        for i in range(tries):
            wait = self._last.get(host, 0) + gap - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()
            try:
                r = self.s.get(url, params=params, headers=headers, timeout=40)
            except requests.RequestException as e:
                print(f"  ! {host}: {e}")
                time.sleep(3 * (i + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(60, 5 * (i + 1) ** 2))
                continue
            return r
        return None


# ---------- 保存 ----------

def month_path(root: Path, source: str, day: str) -> Path:
    return root / "items" / source / f"{day[:7]}.json"


def save_items(root: Path, source: str, items: list[dict]) -> int:
    """新しいものを足し、既にあるものは数字だけ新しくする。新規の件数を返す。"""
    by_month: dict[str, list[dict]] = {}
    for it in items:
        by_month.setdefault(it["date"][:7], []).append(it)
    added = 0
    for month, rows in by_month.items():
        path = root / "items" / source / f"{month}.json"
        cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        for it in rows:
            old = cur.get(it["id"])
            if old is None:
                added += 1
                cur[it["id"]] = it
            else:
                # 日付と題名は最初のものを残し、数字（いいね・スター）は新しいほうにする
                for k in ("score", "extra"):
                    if k in it:
                        old[k] = it[k]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(sorted(cur.items())), ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n")
    return added


def prune(root: Path, keep_days: int = KEEP_DAYS) -> None:
    cutoff = (date.today() - timedelta(days=keep_days)).isoformat()[:7]
    for path in (root / "items").glob("*/*.json"):
        if path.stem < cutoff:
            path.unlink()
    for path in [p for d in ("models", "pricing", "repos", "hub") for p in (root / d).glob("*.json")]:
        if path.stem[:7] < cutoff:
            path.unlink()


# ---------- 小道具 ----------

def clip(text: str, n: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def first_sentences(text: str, n: int = 260) -> str:
    """英文の要旨の最初の 1〜2 文（n 文字まで）。"""
    text = re.sub(r"\s+", " ", text or "").strip()
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(s) > n:
            break
        out = (out + " " + s).strip()
    return clip(out or text, n)


def hid(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]


def iso_day(s: str) -> str:
    return (s or "")[:10]


# ---------- Hugging Face 注目論文（研究者が毎日選んで投票するもの） ----------

def fetch_hf_papers(http: Http, days: int) -> list[dict]:
    out = []
    today = date.today()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        r = http.get("https://huggingface.co/api/daily_papers", params={"date": d, "limit": 100})
        if r is None or r.status_code != 200:
            continue
        for row in r.json():
            p = row.get("paper") or {}
            pid = p.get("id")
            if not pid:
                continue
            out.append({
                "id": f"paper-{pid}",
                "source": "hf_papers",
                "kind": "paper",
                "title": clip(p.get("title") or row.get("title"), 240),
                "url": f"https://huggingface.co/papers/{pid}",
                "alt_url": f"https://arxiv.org/abs/{pid}",
                "date": iso_day(p.get("submittedOnDailyAt") or row.get("publishedAt") or d),
                "summary": first_sentences(p.get("summary") or row.get("summary") or ""),
                "score": int(p.get("upvotes") or 0),
                "extra": {"github": p.get("githubRepo") or "", "stars": int(p.get("githubStars") or 0),
                          "comments": int(row.get("numComments") or 0)},
            })
    return out


# ---------- Hugging Face トレンドのモデル ----------

def fetch_hf_models(http: Http, limit: int = 60) -> list[dict]:
    r = http.get("https://huggingface.co/api/models",
                  params={"sort": "trendingScore", "limit": limit, "full": "false", "config": "false"})
    if r is None or r.status_code != 200:
        return []
    out = []
    for m in r.json():
        tags = m.get("tags") or []
        lic = next((t.split(":", 1)[1] for t in tags if t.startswith("license:")), "")
        out.append({
            "id": m.get("id") or m.get("modelId"),
            "task": m.get("pipeline_tag") or "",
            "library": m.get("library_name") or "",
            "likes": int(m.get("likes") or 0),
            "downloads": int(m.get("downloads") or 0),
            "trending": int(m.get("trendingScore") or 0),
            "created": iso_day(m.get("createdAt") or ""),
            "license": lic,
            "tags": [t for t in tags if ":" not in t][:12],
        })
    return [m for m in out if m["id"]]


def save_models(root: Path, models: list[dict], day: str) -> None:
    if not models:
        return
    path = root / "models" / f"{day}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(models, ensure_ascii=False, indent=0) + "\n", encoding="utf-8", newline="\n")


# ---------- GitHub（作られたばかりで急にスターを集めているリポジトリ） ----------

def fetch_github(http: Http, days: int = 30) -> list[dict]:
    since = (date.today() - timedelta(days=days)).isoformat()
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    gap = 2.5 if token else 7.0   # 検索 API は認証なしで 1 分 10 回まで
    seen: dict[str, dict] = {}
    for topic in GITHUB_TOPICS:
        r = http.get("https://api.github.com/search/repositories",
                     params={"q": f"topic:{topic} created:>{since} stars:>30", "sort": "stars", "order": "desc", "per_page": 30},
                     headers=headers, min_gap=gap)
        if r is None or r.status_code != 200:
            print(f"  ! GitHub {topic}: {r.status_code if r is not None else '通信失敗'}")
            continue
        for repo in r.json().get("items", []):
            name = repo["full_name"]
            if name in seen:
                continue
            seen[name] = {
                "id": "repo-" + name.replace("/", "__"),
                "source": "github",
                "kind": "repo",
                "title": name,
                "url": repo["html_url"],
                "date": iso_day(repo.get("created_at")),
                "summary": clip(repo.get("description") or "", 200),
                "score": int(repo.get("stargazers_count") or 0),
                "extra": {"lang": repo.get("language") or "", "topics": (repo.get("topics") or [])[:10],
                          "license": ((repo.get("license") or {}).get("spdx_id") or "")},
            }
    return list(seen.values())


# ---------- Hacker News（エンジニアの間で話題になった記事。題名と点数だけ） ----------

AI_TITLE = re.compile(r"\b(ai|llms?|gpt[-\w]*|claude|gemini|openai|anthropic|agents?|agentic|deepseek|qwen|llama|mistral|"
                      r"chatgpt|copilot|neural|machine learning|diffusion|transformer|inference|mcp|rag|model)\b", re.I)


def fetch_hn(http: Http, days: int = 7, min_points: int = 80) -> list[dict]:
    since = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    seen: dict[str, dict] = {}
    for q in HN_QUERIES:
        r = http.get("https://hn.algolia.com/api/v1/search",
                     params={"query": q, "tags": "story", "hitsPerPage": 100,
                             "numericFilters": f"points>={min_points},created_at_i>{since}"})
        if r is None or r.status_code != 200:
            continue
        for h in r.json().get("hits", []):
            title = h.get("title") or ""
            if not AI_TITLE.search(title):
                continue
            oid = h["objectID"]
            seen[oid] = {
                "id": f"hn-{oid}",
                "source": "hn",
                "kind": "discussion",
                "title": clip(title, 200),
                "url": h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                "alt_url": f"https://news.ycombinator.com/item?id={oid}",
                "date": iso_day(h.get("created_at")),
                "summary": "",
                "score": int(h.get("points") or 0),
                "extra": {"comments": int(h.get("num_comments") or 0)},
            }
    return list(seen.values())


# ---------- 各社の発表・ニュース（RSS / Atom、題名とリンクだけ） ----------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el, *names: str) -> str:
    """名前空間を気にせず、子要素の文字（または href）を返す。"""
    for want in names:
        for c in el:
            if _local(c.tag) == want:
                if c.text and c.text.strip():
                    return c.text.strip()
                if c.get("href") and c.get("rel") in (None, "alternate"):
                    return c.get("href")
    return ""


def _parse_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, IndexError):
        pass
    m = re.match(r"\d{4}-\d{2}-\d{2}", s)
    return m.group(0) if m else ""


def parse_feed(xml: bytes, feed: Feed) -> list[dict]:
    """RSS 2.0 / RSS 1.0（RDF）/ Atom のどれでも読む。"""
    root = ET.fromstring(xml)
    out = []
    for el in root.iter():
        if _local(el.tag) not in ("item", "entry"):
            continue
        title = re.sub(r"<[^>]+>", "", _child(el, "title"))
        link = _child(el, "link") or _child(el, "guid")
        if not link.startswith("http"):
            for c in el:
                if _local(c.tag) == "link" and c.get("href"):
                    link = c.get("href")
                    break
        day = _parse_date(_child(el, "pubDate", "date", "published", "updated", "issued"))
        if not title or not link.startswith("http") or not day:
            continue
        if feed.filter and not AI_WORDS.search(title):
            continue
        out.append({
            "id": f"news-{feed.key}-{hid(link.strip())}",
            "source": "news",
            "kind": feed.kind,
            "title": clip(title, 200),
            "url": link.strip(),
            "date": day,
            "summary": "",
            "score": 0,
            "extra": {"publisher": feed.label, "feed": feed.key, "lang": feed.lang},
        })
    return out


def fetch_news(http: Http, days: int = 400) -> list[dict]:
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    out = []
    for feed in FEEDS:
        r = http.get(feed.url, headers={"User-Agent": "Mozilla/5.0 (compatible; " + UA + ")"})
        if r is None or r.status_code != 200:
            print(f"  ! {feed.label}: {r.status_code if r is not None else '通信失敗'}")
            continue
        try:
            rows = parse_feed(r.content, feed)
        except ET.ParseError as e:
            print(f"  ! {feed.label}: RSS を読めない ({e})")
            continue
        rows = [x for x in rows if cutoff <= x["date"] <= today]
        print(f"  {feed.label}: {len(rows)} 件")
        out += rows
    return out


def scrape_anthropic(html: str, key: str, label: str, kind: str) -> list[dict]:
    """anthropic.com/news の一覧から、題名・日付・リンクを拾う（RSS が無いため）。"""
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(/news/[a-z0-9\-]+)"[^>]*>(.*?)</a>', html, re.S):
        href, body = m.group(1), m.group(2)
        t = re.search(r"<time[^>]*>([^<]+)</time>", body)
        if not t or href in seen:
            continue
        try:
            day = datetime.strptime(t.group(1).strip(), "%b %d, %Y").date().isoformat()
        except ValueError:
            continue
        parts = [re.sub(r"<[^>]+>", "", x).strip() for x in re.split(r"<[^>]+>", body)]
        parts = [x for x in parts if x and x != t.group(1).strip()]
        if not parts:
            continue
        title = max(parts, key=len)
        seen.add(href)
        url = "https://www.anthropic.com" + href
        out.append({"id": f"news-{key}-{hid(url)}", "source": "news", "kind": kind, "title": clip(title, 200),
                    "url": url, "date": day, "summary": "", "score": 0,
                    "extra": {"publisher": label, "feed": key, "lang": "en"}})
    return out


def fetch_scraped(http: Http) -> list[dict]:
    out = []
    for key, label, url, kind, _ in SCRAPED:
        r = http.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; " + UA + ")"})
        if r is None or r.status_code != 200:
            print(f"  ! {label}: {r.status_code if r is not None else '通信失敗'}")
            continue
        rows = scrape_anthropic(r.text, key, label, kind)
        print(f"  {label}（ページから）: {len(rows)} 件")
        out += rows
    return out


# ---------- エンジニアのコミュニティ（Lobsters・DEV） ----------

def fetch_community(http: Http) -> list[dict]:
    out = []
    r = http.get("https://lobste.rs/t/ai.json")
    if r is not None and r.status_code == 200:
        for s in r.json():
            out.append({"id": f"lob-{s['short_id']}", "source": "community", "kind": "discussion",
                        "title": clip(s.get("title") or "", 200), "url": s.get("url") or s.get("comments_url"),
                        "alt_url": s.get("comments_url", ""), "date": iso_day(s.get("created_at")), "summary": "",
                        "score": int(s.get("score") or 0),
                        "extra": {"comments": int(s.get("comment_count") or 0), "publisher": "Lobsters",
                                  "topics": s.get("tags", [])}})
    for tag in ("ai", "llm", "machinelearning", "rag", "mcp"):
        r = http.get("https://dev.to/api/articles", params={"tag": tag, "top": 7, "per_page": 30})
        if r is None or r.status_code != 200:
            continue
        for a in r.json():
            out.append({"id": f"devto-{a['id']}", "source": "community", "kind": "community",
                        "title": clip(a.get("title") or "", 200), "url": a.get("url"),
                        "date": iso_day(a.get("published_at")), "summary": clip(a.get("description") or "", 200),
                        "score": int(a.get("public_reactions_count") or 0),
                        "extra": {"comments": int(a.get("comments_count") or 0), "publisher": "DEV Community",
                                  "topics": a.get("tag_list", []), "lang": "en"}})
    return [x for x in out if x["url"] and x["date"]]


# ---------- arXiv（テーマごとの週あたり論文数 = 研究の勢い） ----------

def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def arxiv_count(http: Http, query: str, start: date, end: date) -> int | None:
    rng = f"submittedDate:[{start:%Y%m%d}0000 TO {end:%Y%m%d}2359]"
    q = f"{ARXIV_CATS} AND ({query}) AND {rng}" if query else f"{ARXIV_CATS} AND {rng}"
    r = http.get("https://export.arxiv.org/api/query", params={"search_query": q, "max_results": 1}, min_gap=3.2)
    if r is None or r.status_code != 200:
        return None
    m = re.search(r"<opensearch:totalResults[^>]*>(\d+)<", r.text)
    return int(m.group(1)) if m else None


def fetch_arxiv_weekly(http: Http, root: Path, weeks: int) -> None:
    """直近 weeks 週ぶん（今週を含む）を数え直す。まだ数えていない週は全部数える。"""
    path = root / "arxiv_weekly.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    this_week = week_start(date.today())
    targets = [("_all", "")] + [(t.slug, t.arxiv) for t in TOPICS]
    for slug, query in targets:
        row = data.setdefault(slug, {})
        for i in range(weeks):
            ws = this_week - timedelta(weeks=i)
            key = ws.isoformat()
            if key in row and i >= 2:   # 2 週より前は確定しているので数え直さない
                continue
            n = arxiv_count(http, query, ws, ws + timedelta(days=6))
            if n is not None:
                row[key] = n
        print(f"  arXiv {slug}: {len(row)} 週")
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


# ---------- まとめて ----------

def sync(root: Path, *, backfill: bool = False, only: set[str] | None = None) -> None:
    from . import metrics   # metrics は sources を使うので、ここで読む
    http = Http()
    root.mkdir(parents=True, exist_ok=True)

    def want(name: str) -> bool:
        return only is None or name in only

    if want("papers"):
        print("Hugging Face 注目論文")
        rows = fetch_hf_papers(http, days=120 if backfill else 4)
        print(f"  {len(rows)} 件 / 新規 {save_items(root, 'hf_papers', rows)} 件")
    if want("models"):
        print("Hugging Face トレンドのモデル")
        models = fetch_hf_models(http)
        save_models(root, models, date.today().isoformat())
        print(f"  {len(models)} 件")
    if want("github"):
        print("GitHub の新しいリポジトリ")
        rows = fetch_github(http)
        print(f"  {len(rows)} 件 / 新規 {save_items(root, 'github', rows)} 件")
    if want("hn"):
        print("Hacker News")
        rows = fetch_hn(http, days=60 if backfill else 7)
        print(f"  {len(rows)} 件 / 新規 {save_items(root, 'hn', rows)} 件")
    if want("news"):
        print("各社の発表・報道・ブログ・日本語の記事・政府（RSS）")
        rows = fetch_news(http) + fetch_scraped(http)
        print(f"  {len(rows)} 件 / 新規 {save_items(root, 'news', rows)} 件")
    if want("community"):
        print("Lobsters・DEV")
        rows = fetch_community(http)
        print(f"  {len(rows)} 件 / 新規 {save_items(root, 'community', rows)} 件")
    if want("releases"):
        print("主要な組織の新しいモデル")
        print(f"  新規 {metrics.fetch_releases(http, root, days=180 if backfill else 21)} 件")
    if want("pricing"):
        print("API の価格（OpenRouter）")
        print(f"  {metrics.fetch_pricing(http, root)} モデル")
    if want("hub"):
        print("Hugging Face のアプリとデータセット")
        metrics.fetch_hub(http, root)
    if want("repos"):
        print("主要なオープンソースのスター数")
        print(f"  {metrics.fetch_repos(http, root)} 件")
    if want("downloads"):
        print("PyPI / npm のダウンロード数")
        metrics.fetch_downloads(http, root)
    if want("attention"):
        print("Wikipedia の閲覧数")
        metrics.fetch_attention(http, root, days=365 if backfill else 10)
    if want("arxiv"):
        print("arXiv の週ごとの論文数")
        fetch_arxiv_weekly(http, root, weeks=26)   # 確定した週は数え直さないので、毎日でも数十回で済む
    prune(root)
