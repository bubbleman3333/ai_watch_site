"""data/ と content/ から dist/ に静的サイトを書き出す。"""
from __future__ import annotations

import json
import re
import shutil
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape

import markdown as md
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from .model import (KIND_LABEL, Corpus, Item, load_all, parse_note, topic_stats, week_range,
                    weekly)
from .topics import INDUSTRIES, INDUSTRY_BY_SLUG, TOPIC_BY_SLUG, TOPICS

ROOT = Path(__file__).resolve().parent.parent
JST = timezone(timedelta(hours=9))


def load_config(root: Path = ROOT) -> dict:
    return json.loads((root / "config" / "site.json").read_text(encoding="utf-8"))


# ---------- 図（SVG を文字列で作る。JS もライブラリも使わない） ----------

def sparkline(values: list[float], w: int = 160, h: int = 40, color: str = "currentColor", fill: bool = True,
              label: str = "") -> Markup:
    if not values or max(values) <= 0:
        return Markup(f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" aria-hidden="true"></svg>')
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    pad = 3
    n = len(values)
    pts = [(pad + (w - 2 * pad) * i / max(1, n - 1), h - pad - (h - 2 * pad) * (v - lo) / span) for i, v in enumerate(values)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f'<polygon points="{pts[0][0]:.1f},{h} {line} {pts[-1][0]:.1f},{h}" fill="{color}" opacity=".12"/>' if fill else ""
    lx, ly = pts[-1]
    aria = f'role="img" aria-label="{escape(label)}"' if label else 'aria-hidden="true"'
    return Markup(f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" {aria} preserveAspectRatio="none">'
                  f'{area}<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round" '
                  f'stroke-linecap="round" vector-effect="non-scaling-stroke"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="3" fill="{color}"/></svg>')


def bars(values: list[int], labels: list[str], color: str, w: int = 640, h: int = 160, unit: str = "件") -> Markup:
    """縦棒。目盛りは最大値と 0 だけ。"""
    if not values:
        return Markup("")
    top = max(values) or 1
    n = len(values)
    gap = 4
    left, bottom = 4, 22
    bw = (w - left - gap * (n - 1)) / n
    parts = []
    for i, (v, lab) in enumerate(zip(values, labels)):
        bh = (h - bottom - 14) * v / top
        x = left + i * (bw + gap)
        y = h - bottom - bh
        last = i == n - 1
        parts.append(f'<g><title>{escape(lab)}: {v:,}{unit}</title><rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
                     f'height="{max(bh, 1):.1f}" rx="3" fill="{color}" opacity="{1 if last else .55}"/>')
        if last or v == top:
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" class="bar-val">{v:,}</text>')
        if i % max(1, n // 6) == 0 or last:
            parts.append(f'<text x="{x + bw / 2:.1f}" y="{h - 6}" text-anchor="middle" class="bar-lab">{escape(lab)}</text>')
        parts.append("</g>")
    return Markup(f'<svg class="bars" viewBox="0 0 {w} {h}" role="img" aria-label="週ごとの件数">{"".join(parts)}</svg>')


# ---------- Markdown ----------

_LINK = re.compile(r"\]\((topic|industry|page|note):([\w\-_.]+)\)")


class Builder:
    def __init__(self, out: Path, site_url: str, root: Path = ROOT, today: date | None = None):
        self.out = out
        self.root = root
        self.site = load_config(root)
        self.site_url = site_url.rstrip("/") + "/"
        self.today = today or datetime.now(JST).date()
        self.pages: list[tuple[str, str]] = []   # (path, lastmod)
        self.env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape(["html", "xml"]),
                               trim_blocks=True, lstrip_blocks=True)
        self.env.globals.update(url=self.url, site=self.site, topics=TOPICS, industries=INDUSTRIES, T=TOPIC_BY_SLUG,
                                I=INDUSTRY_BY_SLUG, sparkline=sparkline, bars=bars, KIND_LABEL=KIND_LABEL)
        self.env.filters["md"] = self.render_md
        self.env.filters["jday"] = lambda s: f"{int(s[5:7])}月{int(s[8:10])}日" if s else ""
        self.env.filters["num"] = lambda n: f"{n:,}"
        self.env.filters["short"] = lambda n: f"{n / 10000:.1f}万" if n >= 10000 else f"{n:,}"

    def url(self, path: str = "") -> str:
        return self.site_url + path.lstrip("/")

    def render_md(self, text: str) -> Markup:
        def sub(m):
            kind, slug = m.group(1), m.group(2)
            path = {"topic": f"topic/{slug}/", "industry": f"industry/{slug}/", "page": f"{slug}/", "note": f"note/{slug}/"}[kind]
            return f"]({self.url(path)})"
        html = md.markdown(_LINK.sub(sub, text or ""), extensions=["tables", "sane_lists"])
        html = re.sub(r'<a href="(https?://(?!' + re.escape(self.site_url.split("//")[1]) + r'))',
                      r'<a rel="noopener" target="_blank" href="\1', html)
        return Markup(html)

    def content(self, kind: str, slug: str) -> dict:
        p = self.root / "content" / kind / f"{slug}.md"
        return parse_note(p.read_text(encoding="utf-8")) if p.exists() else {"body": ""}

    def write(self, path: str, template: str, *, lastmod: str | None = None, sitemap: bool = True, **ctx) -> None:
        ctx.setdefault("canonical", self.url(path))
        html = self.env.get_template(template).render({**self.common, **ctx})
        dest = self.out / path / "index.html" if path.endswith("/") or path == "" else self.out / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        if sitemap:
            self.pages.append((path, lastmod or self.today.isoformat()))

    # ---------- 本体 ----------

    def build(self) -> int:
        c: Corpus = load_all(self.root / "data", self.root / "content" / "notes", today=self.today)
        stats = topic_stats(c)
        by_slug = {s.slug: s for s in stats}
        rising = sorted(stats, key=lambda s: s.momentum, reverse=True)
        weeks = weekly(c)
        noted = [it for it in c.items if it.note]
        noted_models = [m for _, rows in c.model_days for m in rows if m.note]
        # 同じモデルが何日も入っているので、最後の日のものだけ
        noted_models = list({m.id: m for m in noted_models}.values())

        if self.out.exists():
            shutil.rmtree(self.out)
        (self.out / "static").mkdir(parents=True)
        for f in (self.root / "static").iterdir():
            shutil.copy(f, self.out / "static" / f.name)

        updated = datetime.now(JST).strftime("%Y-%m-%d %H:%M")
        self.common = dict(now=self.today, updated=updated,
                           counts=Counter(it.kind for it in c.items), n_models=len(c.models))

        hot = c.hot(days=7, n=14, per_source=3)
        papers = c.hot(days=7, n=10, kinds=("paper",))
        talk = c.hot(days=7, n=10, kinds=("discussion",))
        repos = c.hot(days=30, n=10, kinds=("repo",))
        news = [it for it in c.recent(10, ("news",))][:16]
        self.write("", "index.html", stats=stats, rising=rising, hot=hot, papers=papers, talk=talk, repos=repos,
                   news=news, models=c.models[:12], latest_week=weeks[0][0] if weeks else "")

        # テーマ
        self.write("topic/", "topics.html", stats=rising)
        for st in stats:
            t = st.topic
            inds = [i for i in INDUSTRIES if t.slug in i.topics]
            self.write(t.path, "topic.html", st=st, t=t, guide=self.content("topics", t.slug), industries_rel=inds,
                       items=st.items[:40], hot=sorted(st.items[:200], key=lambda it: it.heat + (.3 if it.note else 0), reverse=True)[:8],
                       models=st.models[:10])

        # 業種
        self.write("industry/", "industries.html")
        for ind in INDUSTRIES:
            rel = [by_slug[s] for s in ind.topics if s in by_slug]
            pool = {it.id: it for s in rel for it in s.items[:300] if it.note}
            picks = sorted(pool.values(), key=lambda it: it.date, reverse=True)[:12]
            self.write(ind.path, "industry.html", ind=ind, guide=self.content("industries", ind.slug), rel=rel, picks=picks)

        # 週ごと
        self.write("week/", "weeks.html", weeks=[(k, len(v), week_range(k)) for k, v in weeks[:60]])
        for k, rows in weeks[:60]:
            start, end = week_range(k)
            tc = Counter(s for it in rows for s in it.topics)
            top = {kind: sorted([it for it in rows if it.kind == kind], key=lambda it: it.heat, reverse=True)[:8]
                   for kind in ("news", "paper", "discussion", "repo")}
            self.write(f"week/{k}/", "week.html", key=k, start=start, end=end, rows=rows, top=top,
                       tc=tc.most_common(), noted=[it for it in rows if it.note][:20], lastmod=min(end, self.today).isoformat())

        # ひとこと解説
        for it in noted:
            rel = [x for x in by_slug[it.topics[0]].items[:60] if x.note and x.id != it.id][:5] if it.topics else []
            self.write(it.path, "note.html", it=it, model=None, rel=rel, lastmod=it.date)
        for m in noted_models:
            self.write(m.path, "note.html", it=None, model=m, rel=[], lastmod=self.today.isoformat())

        self.write("models/", "models.html", models=c.models, day=c.model_days[-1][0] if c.model_days else "")
        self.write("latest/", "latest.html", rows=c.recent(30))
        self.write("notes/", "notes.html", rows=sorted(noted, key=lambda it: it.date, reverse=True), models=noted_models)
        for slug in ("start", "about", "privacy"):
            self.write(f"{slug}/", "page.html", page=self.content("pages", slug))
        self.write("404.html", "404.html", sitemap=False)
        self.write_feed(noted, news)
        self.write_sitemap()
        (self.out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {self.url('sitemap.xml')}\n", encoding="utf-8")
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        return len(self.pages)

    def write_feed(self, noted: list[Item], news: list[Item]) -> None:
        rows = sorted(noted, key=lambda it: it.date, reverse=True)[:40]
        parts = []
        for it in rows:
            link = self.url(it.path)
            desc = (it.note or {}).get("body", "")[:300]
            d = datetime.fromisoformat(it.date).replace(tzinfo=JST)
            parts.append(f"<item><title>{escape(it.headline)}</title><link>{link}</link><guid>{link}</guid>"
                         f"<pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0900')}</pubDate>"
                         f"<description>{escape(desc)}</description></item>")
        xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel><title>{escape(self.site["name"])}</title>'
               f'<link>{self.url()}</link><description>{escape(self.site["description"])}</description><language>ja</language>'
               + "".join(parts) + "</channel></rss>\n")
        (self.out / "feed.xml").write_text(xml, encoding="utf-8")

    def write_sitemap(self) -> None:
        rows = "".join(f"<url><loc>{escape(self.url(p))}</loc><lastmod>{d}</lastmod></url>" for p, d in self.pages)
        (self.out / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{rows}</urlset>\n',
            encoding="utf-8")
