"""保存したデータを読み、表示用にまとめる（テーマの勢い・注目度・週ごとの集計）。

ネットワークにも Jinja2 にも依存させない（テストしやすくするため）。
"""
from __future__ import annotations

import json
import re
from bisect import bisect_left
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .feeds import FEED_BY_KEY
from .topics import TOPICS, TOPIC_BY_SLUG, classify

KIND_LABEL = {"news": "発表", "media": "報道", "blog": "解説", "paper": "論文", "release": "新モデル",
              "discussion": "話題", "community": "技術記事", "repo": "OSS", "policy": "政策", "model": "モデル"}
SOURCE_LABEL = {"hf_papers": "Hugging Face 注目論文", "hn": "Hacker News", "github": "GitHub", "news": "各社の発表",
                "community": "コミュニティ", "releases": "Hugging Face"}
FEED_KINDS = ("news", "media", "blog", "policy")
# 載せないモデル（検閲外し・顔の入れ替え・成人向け）。悪用のほうが目立つため
HIDE_MODEL = re.compile(r"uncensor|nsfw|(face|character)[-_ ]?swap|abliterat|porn|hentai|lewd|nude|undress", re.I)
LAUNCH = re.compile(r"\b(introduc|launch|releas|announc|now available|unveil|new model|open[- ]source)|発表|提供開始|公開|リリース", re.I)

# ひとこと解説で使うタスク名（Hugging Face の pipeline_tag）の日本語
TASK_JA = {
    "text-generation": "文章生成", "image-text-to-text": "画像を読む", "text-to-image": "画像生成",
    "image-to-image": "画像編集", "text-to-video": "動画生成", "image-to-video": "画像→動画",
    "text-to-speech": "音声合成", "automatic-speech-recognition": "文字起こし", "audio-to-audio": "音声変換",
    "feature-extraction": "埋め込み", "sentence-similarity": "文の類似度", "text-classification": "文章分類",
    "token-classification": "固有表現", "image-classification": "画像分類", "object-detection": "物体検出",
    "image-segmentation": "領域分割", "zero-shot-classification": "分類", "translation": "翻訳",
    "summarization": "要約", "any-to-any": "なんでも変換", "robotics": "ロボット", "reinforcement-learning": "強化学習",
    "video-text-to-text": "動画を読む", "text-ranking": "並べ替え", "depth-estimation": "奥行き推定",
    "image-to-3d": "3D 生成", "text-to-3d": "3D 生成", "audio-text-to-text": "音声を読む", "time-series-forecasting": "時系列予測",
    "visual-document-retrieval": "文書検索", "text-to-audio": "音生成", "unconditional-image-generation": "画像生成",
}
TASK_TOPIC = {
    "text-to-image": "image-gen", "image-to-image": "image-gen", "unconditional-image-generation": "image-gen",
    "text-to-video": "video-gen", "image-to-video": "video-gen", "text-to-speech": "speech",
    "automatic-speech-recognition": "speech", "audio-to-audio": "speech", "audio-text-to-text": "speech",
    "text-to-audio": "speech", "image-text-to-text": "multimodal", "video-text-to-text": "multimodal",
    "visual-document-retrieval": "rag", "feature-extraction": "rag", "sentence-similarity": "rag", "text-ranking": "rag",
    "robotics": "robotics", "time-series-forecasting": "forecasting", "any-to-any": "multimodal",
}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_key(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_range(key: str) -> tuple[date, date]:
    y, w = key.split("-W")
    start = date.fromisocalendar(int(y), int(w), 1)
    return start, start + timedelta(days=6)


def parse_note(text: str) -> dict:
    """content/notes/<id>.md を読む。先頭の --- で囲んだ部分は key: value。"""
    meta: dict[str, str] = {}
    body = text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        body = m.group(2)
    meta["body"] = body.strip()
    return meta


@dataclass
class Item:
    id: str
    source: str
    kind: str
    title: str
    url: str
    date: str
    summary: str = ""
    score: int = 0
    alt_url: str = ""
    extra: dict = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    heat: float = 0.0          # 0〜1。同じ取り込み元の中での注目度
    note: dict | None = None   # Claude が書いたひとこと解説

    @classmethod
    def from_raw(cls, raw: dict) -> "Item":
        it = cls(id=raw["id"], source=raw["source"], kind=raw["kind"], title=raw["title"], url=raw["url"],
                 date=raw["date"], summary=raw.get("summary", ""), score=int(raw.get("score") or 0),
                 alt_url=raw.get("alt_url", ""), extra=raw.get("extra") or {})
        feed = FEED_BY_KEY.get(it.extra.get("feed", ""))
        if feed:   # 取り込み元の分類は feeds.py を正とする（あとから分類を変えても古いデータに効く）
            it.kind = feed.kind
            it.extra["publisher"] = feed.label
            it.extra["lang"] = feed.lang
        words = " ".join(it.extra.get("topics") or [])
        it.topics = classify(it.title, it.summary, words)
        return it

    @property
    def day(self) -> date:
        return date.fromisoformat(self.date)

    @property
    def week(self) -> str:
        return week_key(self.day)

    @property
    def kind_label(self) -> str:
        return KIND_LABEL.get(self.kind, self.kind)

    @property
    def publisher(self) -> str:
        return self.extra.get("publisher") or SOURCE_LABEL.get(self.source, self.source)

    @property
    def is_ja(self) -> bool:
        return self.extra.get("lang") == "ja" or bool(self.extra.get("jp"))

    @property
    def score_label(self) -> str:
        if self.kind == "paper":
            return f"▲{self.score}"
        if self.kind == "discussion":
            return f"{self.score} pt・{self.extra.get('comments', 0)} コメント"
        if self.kind == "repo":
            return f"★{self.score:,}"
        if self.kind in ("release", "community") and self.score:
            return f"♥{self.score:,}"
        return ""

    @property
    def headline(self) -> str:
        return (self.note or {}).get("headline") or self.title

    @property
    def path(self) -> str:
        return f"note/{self.id}/"

    def digest(self) -> str:
        lines = [f"## {self.id}", f"種類: {self.kind_label}（{self.publisher}）", f"日付: {self.date}",
                 f"題名: {self.title}", f"URL: {self.url}"]
        if self.summary:
            lines.append(f"抜粋: {self.summary}")
        if self.score_label:
            lines.append(f"反応: {self.score_label}")
        if self.extra.get("topics"):
            lines.append("タグ: " + ", ".join(self.extra["topics"]))
        if self.topics:
            lines.append("テーマ: " + ", ".join(self.topics))
        return "\n".join(lines)


@dataclass
class ModelRow:
    id: str
    task: str
    likes: int
    downloads: int
    trending: int
    created: str
    license: str
    tags: list[str]
    rank: int = 0
    kind: str = "model"
    prev_rank: int | None = None
    days_on: int = 1
    note: dict | None = None

    @property
    def task_ja(self) -> str:
        return TASK_JA.get(self.task, self.task or "—")

    @property
    def owner(self) -> str:
        return self.id.split("/")[0]

    @property
    def name(self) -> str:
        return self.id.split("/")[-1]

    @property
    def url(self) -> str:
        return f"https://huggingface.co/{self.id}"

    @property
    def note_id(self) -> str:
        return "model-" + self.id.replace("/", "__")

    @property
    def topics(self) -> list[str]:
        t = TASK_TOPIC.get(self.task)
        rest = classify(self.id, " ".join(self.tags))
        out = ([t] if t else []) + [x for x in rest if x != t]
        return out[:2] or ["open-models"]

    @property
    def title(self) -> str:
        return self.id

    @property
    def date(self) -> str:
        return self.created

    @property
    def headline(self) -> str:
        return (self.note or {}).get("headline") or self.name

    @property
    def path(self) -> str:
        return f"note/{self.note_id}/"

    def digest(self) -> str:
        return "\n".join([f"## {self.note_id}", "種類: モデル（Hugging Face のトレンド）", f"モデル: {self.id}",
                          f"URL: {self.url}", f"タスク: {self.task}（{self.task_ja}）", f"ライセンス: {self.license}",
                          f"いいね: {self.likes} / ダウンロード: {self.downloads}", f"作成日: {self.created}",
                          "タグ: " + ", ".join(self.tags)])


@dataclass
class TopicStat:
    slug: str
    weeks: list[str]                 # arXiv の週（月曜の日付）、古い順
    arxiv: list[int]                 # その週の論文数
    share: list[float]               # 全体に占める割合（%）
    mentions: list[int]              # 直近 12 週の、取り込んだアイテムのうちこのテーマの件数
    mention_weeks: list[str]
    momentum: float                  # 直近 4 週の割合 ÷ その前 8 週の割合
    items: list[Item] = field(default_factory=list)
    models: list[ModelRow] = field(default_factory=list)

    @property
    def topic(self):
        return TOPIC_BY_SLUG[self.slug]

    @property
    def trend(self) -> tuple[str, str]:
        m = self.momentum
        if m >= 1.25:
            return "急上昇", "up2"
        if m >= 1.08:
            return "上昇", "up"
        if m <= 0.85:
            return "落ち着き", "down"
        return "横ばい", "flat"

    @property
    def momentum_pct(self) -> int:
        return round((self.momentum - 1) * 100)

    @property
    def last_arxiv(self) -> int:
        return self.arxiv[-1] if self.arxiv else 0

    @property
    def recent_mentions(self) -> int:
        return sum(self.mentions[-2:])


@dataclass
class Corpus:
    items: list[Item]
    model_days: list[tuple[str, list[ModelRow]]]
    arxiv: dict[str, dict[str, int]]
    notes: dict[str, dict]
    today: date

    @property
    def by_id(self) -> dict[str, Item]:
        return {it.id: it for it in self.items}

    @property
    def models(self) -> list[ModelRow]:
        return self.model_days[-1][1] if self.model_days else []

    def recent(self, days: int, kinds: tuple[str, ...] | None = None) -> list[Item]:
        cut = (self.today - timedelta(days=days)).isoformat()
        return [it for it in self.items if it.date >= cut and (kinds is None or it.kind in kinds)]

    def hot(self, days: int = 7, n: int = 20, kinds: tuple[str, ...] | None = None, per_source: int | None = None) -> list[Item]:
        rows = sorted(self.recent(days, kinds), key=lambda it: (it.heat + (0.25 if it.note else 0), it.date), reverse=True)
        if per_source is None:
            return rows[:n]
        out, used = [], Counter()
        for it in rows:
            key = it.extra.get("feed") or it.source
            if used[key] >= per_source:
                continue
            used[key] += 1
            out.append(it)
            if len(out) >= n:
                break
        return out


def _percentile_heat(items: list[Item]) -> None:
    """取り込み元ごとに、直近 90 日の点数の順位で 0〜1 にする。"""
    by_src: dict[str, list[int]] = defaultdict(list)
    for it in items:
        if it.extra.get("feed") is None:
            by_src[it.source].append(it.score)
    for k in by_src:
        by_src[k].sort()
    for it in items:
        if it.kind in FEED_KINDS or (it.kind == "community" and it.source == "news"):
            feed = FEED_BY_KEY.get(it.extra.get("feed", ""))
            base = feed.weight if feed else 0.4
            it.heat = min(1.0, base + (0.15 if LAUNCH.search(it.title) else 0))
            continue
        arr = by_src[it.source]
        it.heat = bisect_left(arr, it.score) / max(1, len(arr) - 1) if arr else 0
        if it.kind in ("repo", "community"):
            it.heat *= 0.85


def load_notes(notes_dir: Path) -> dict[str, dict]:
    out = {}
    if notes_dir.exists():
        for p in notes_dir.glob("*.md"):
            out[p.stem] = parse_note(p.read_text(encoding="utf-8"))
    return out


def load_all(data_dir: Path, notes_dir: Path | None = None, today: date | None = None) -> Corpus:
    today = today or date.today()
    notes = load_notes(notes_dir or data_dir.parent / "content" / "notes")
    items: list[Item] = []
    for path in sorted((data_dir / "items").glob("*/*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 壊れたファイルは飛ばして残りで作る
            continue
        for row in raw.values():
            try:
                it = Item.from_raw(row)
            except (KeyError, ValueError):
                continue
            if it.date <= today.isoformat():
                items.append(it)
    _percentile_heat(items)
    for it in items:
        it.note = notes.get(it.id)
    items.sort(key=lambda it: (it.date, it.heat), reverse=True)

    model_days = []
    paths = sorted((data_dir / "models").glob("*.json"))
    seen_days: Counter = Counter()
    prev_rank: dict[str, int] = {}
    for path in paths:
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        out = []
        rows = [r for r in rows if not HIDE_MODEL.search(r["id"] + " " + " ".join(r.get("tags", [])))]
        for i, r in enumerate(rows, 1):
            m = ModelRow(id=r["id"], task=r.get("task", ""), likes=r.get("likes", 0), downloads=r.get("downloads", 0),
                         trending=r.get("trending", 0), created=r.get("created", ""), license=r.get("license", ""),
                         tags=r.get("tags", []), rank=i)
            seen_days[m.id] += 1
            m.days_on = seen_days[m.id]
            m.prev_rank = prev_rank.get(m.id)
            m.note = notes.get(m.note_id)
            out.append(m)
        prev_rank = {m.id: m.rank for m in out}
        model_days.append((path.stem, out))

    arxiv_path = data_dir / "arxiv_weekly.json"
    arxiv = json.loads(arxiv_path.read_text(encoding="utf-8")) if arxiv_path.exists() else {}
    return Corpus(items=items, model_days=model_days, arxiv=arxiv, notes=notes, today=today)


def topic_stats(c: Corpus, weeks: int = 26) -> list[TopicStat]:
    """テーマごとの勢い。今週（途中の週）は割合の計算から外す。"""
    this_week = week_start(c.today).isoformat()
    all_w = c.arxiv.get("_all", {})
    keys = sorted(k for k in all_w if k < this_week)[-weeks:]
    mention_weeks = [week_key(week_start(c.today) - timedelta(weeks=i)) for i in range(11, -1, -1)]
    by_topic_week: dict[str, Counter] = defaultdict(Counter)
    for it in c.items:
        for s in it.topics:
            by_topic_week[s][it.week] += 1
    out = []
    for t in TOPICS:
        row = c.arxiv.get(t.slug, {})
        ks = [k for k in keys if k in row and all_w.get(k)]   # 取得に失敗した週は飛ばす（0 と数えない）
        counts = [row[k] for k in ks]
        share = [100 * row[k] / all_w[k] for k in ks]
        recent, before = share[-4:], share[-12:-4]
        if recent and before and sum(before) > 0:
            mom = (sum(recent) / len(recent)) / (sum(before) / len(before))
        else:
            mom = 1.0
        st = TopicStat(slug=t.slug, weeks=ks, arxiv=counts, share=share,
                       mentions=[by_topic_week[t.slug][w] for w in mention_weeks], mention_weeks=mention_weeks,
                       momentum=mom)
        st.items = [it for it in c.items if t.slug in it.topics]
        st.models = [m for m in c.models if t.slug in m.topics]
        out.append(st)
    return out


def pick_for_notes(c: Corpus, notes_dir: Path, days: int = 14) -> list:
    """ひとこと解説を書く候補。直近の注目アイテム（取り込み元ごとに偏らないように）と、トレンド上位のモデル。"""
    have = set(load_notes(notes_dir))
    rows = [it for it in c.hot(days=days, n=400, per_source=None) if it.id not in have]
    # 取り込み元ごとに順番に取る（論文ばかりにならないように）
    buckets: dict[str, list] = defaultdict(list)
    for it in rows:
        buckets[it.kind].append(it)
    buckets["model"] = [m for m in c.models[:20] if m.note_id not in have]
    buckets["repo"] = buckets["repo"][:8]   # リポジトリは玉石混交なので上位だけ
    order = ["news", "paper", "discussion", "model", "repo"]
    out = []
    while any(buckets[k] for k in order):
        for k in order:
            if buckets[k]:
                out.append(buckets[k].pop(0))
    return out


def weekly(c: Corpus) -> list[tuple[str, list[Item]]]:
    """週ごとのアイテム（新しい週から）。"""
    by: dict[str, list[Item]] = defaultdict(list)
    for it in c.items:
        by[it.week].append(it)
    return sorted(by.items(), reverse=True)
