"""数字の定点観測（metrics.py が貯めたもの）を、ページで見せる形にまとめる。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .metrics import NPM, PYPI, WIKI_ARTICLES


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _snapshots(d: Path) -> list[tuple[str, object]]:
    out = []
    for p in sorted(d.glob("*.json")):
        v = _load(p)
        if v is not None:
            out.append((p.stem, v))
    return out


def _pick_before(snaps: list[tuple[str, object]], day: str):
    """day 以前で一番新しいスナップショット（無ければ一番古いもの）。"""
    older = [s for s in snaps if s[0] <= day]
    return (older[-1] if older else snaps[0]) if snaps else None


def pct(new: float, old: float) -> float | None:
    return None if not old else (new - old) / old * 100


# ---------- 系列（関心・ダウンロード） ----------

@dataclass
class Series:
    key: str
    label: str
    days: list[str]
    values: list[int]
    group: str = ""
    url: str = ""

    @property
    def weekly(self) -> list[int]:
        """7 日ずつの合計（古い順。端の半端な週は捨てる）。"""
        v = self.values
        n = len(v) // 7
        start = len(v) - n * 7
        return [sum(v[start + i * 7: start + (i + 1) * 7]) for i in range(n)]

    @property
    def last7(self) -> int:
        return sum(self.values[-7:])

    @property
    def prev7(self) -> int:
        return sum(self.values[-14:-7])

    @property
    def last30(self) -> int:
        return sum(self.values[-30:])

    @property
    def prev30(self) -> int:
        return sum(self.values[-60:-30])

    @property
    def change7(self) -> float | None:
        return pct(self.last7, self.prev7)

    @property
    def change30(self) -> float | None:
        return pct(self.last30, self.prev30)

    @property
    def change90(self) -> float | None:
        """直近 30 日 ÷ 90〜120 日前の 30 日（3 か月前と比べた伸び）。"""
        if len(self.values) < 120:
            return None
        return pct(self.last30, sum(self.values[-120:-90]))


def _series(raw: dict, key: str, label: str, days: int = 365, **kw) -> Series | None:
    row = raw.get(key) or {}
    if not row:
        return None
    ds = sorted(row)[-days:]
    return Series(key=key, label=label, days=ds, values=[row[d] for d in ds], **kw)


def attention(data_dir: Path) -> list[Series]:
    raw = _load(data_dir / "attention.json") or {}
    out = []
    for lang, title, label in WIKI_ARTICLES:
        s = _series(raw, f"{lang}:{title}", label, group=lang,
                    url=f"https://{lang}.wikipedia.org/wiki/{title}")
        if s and s.values:
            out.append(s)
    return out


def downloads(data_dir: Path) -> list[Series]:
    raw = _load(data_dir / "downloads.json") or {}
    out = []
    for pkg in PYPI:
        s = _series(raw, f"pypi:{pkg}", pkg, group="Python（PyPI）", url=f"https://pypi.org/project/{pkg}/")
        if s and s.values:
            out.append(s)
    for pkg in NPM:
        s = _series(raw, f"npm:{pkg}", pkg, group="JavaScript（npm）", url=f"https://www.npmjs.com/package/{pkg}")
        if s and s.values:
            out.append(s)
    return out


# ---------- API の価格 ----------

@dataclass
class Price:
    id: str
    name: str
    created: str
    context: int
    inp: float
    out: float
    modality: str
    prev_in: float | None = None
    prev_out: float | None = None

    @property
    def vendor(self) -> str:
        return self.id.split("/")[0]

    @property
    def free(self) -> bool:
        return self.inp == 0 and self.out == 0

    @property
    def changed(self) -> bool:
        return self.prev_in is not None and (abs(self.prev_in - self.inp) > 1e-9 or abs((self.prev_out or 0) - self.out) > 1e-9)

    @property
    def change_pct(self) -> float | None:
        if self.prev_in is None:
            return None
        old = (self.prev_in or 0) + (self.prev_out or 0)
        return pct(self.inp + self.out, old)

    @property
    def blended(self) -> float:
        """入力 3 : 出力 1 で混ぜた 100 万トークンあたりの目安。"""
        return (self.inp * 3 + self.out) / 4

    @property
    def url(self) -> str:
        return f"https://openrouter.ai/{self.id}"


@dataclass
class Pricing:
    day: str
    rows: list[Price]
    since: str            # 比べた日

    @property
    def new(self) -> list[Price]:
        cut = (date.fromisoformat(self.day) - timedelta(days=30)).isoformat() if self.day else ""
        return sorted([p for p in self.rows if p.created >= cut and not p.free], key=lambda p: p.created, reverse=True)

    @property
    def changed(self) -> list[Price]:
        return [p for p in self.rows if p.changed]

    @property
    def vendors(self) -> list[tuple[str, int]]:
        from collections import Counter
        return Counter(p.vendor for p in self.rows).most_common()


def pricing(data_dir: Path, today: date) -> Pricing | None:
    snaps = _snapshots(data_dir / "pricing")
    if not snaps:
        return None
    day, rows = snaps[-1]
    prev = _pick_before(snaps[:-1], (today - timedelta(days=7)).isoformat()) if len(snaps) > 1 else None
    pmap = {r["id"]: r for r in (prev[1] if prev else [])}
    out = []
    for r in rows:
        p = Price(id=r["id"], name=r["name"], created=r.get("created", ""), context=r.get("context", 0),
                  inp=r["in"], out=r["out"], modality=r.get("modality", ""))
        if r["id"] in pmap:
            p.prev_in, p.prev_out = pmap[r["id"]]["in"], pmap[r["id"]]["out"]
        out.append(p)
    return Pricing(day=day, rows=out, since=prev[0] if prev else "")


# ---------- 主要なオープンソース ----------

@dataclass
class RepoStat:
    repo: str
    stars: int
    forks: int
    desc: str
    lang: str
    pushed: str
    release: str
    release_date: str
    gain: int | None = None      # 比べた日からのスターの増加
    gain_days: int = 0

    @property
    def url(self) -> str:
        return f"https://github.com/{self.repo}"

    @property
    def name(self) -> str:
        return self.repo.split("/")[-1]


def repos(data_dir: Path, today: date) -> tuple[list[RepoStat], str]:
    snaps = _snapshots(data_dir / "repos")
    if not snaps:
        return [], ""
    day, rows = snaps[-1]
    prev = _pick_before(snaps[:-1], (today - timedelta(days=30)).isoformat()) if len(snaps) > 1 else None
    pmap = {r["repo"]: r["stars"] for r in (prev[1] if prev else [])}
    out = []
    for r in rows:
        s = RepoStat(**{k: r.get(k, "") for k in ("repo", "stars", "forks", "desc", "lang", "pushed", "release", "release_date")})
        if r["repo"] in pmap:
            s.gain = r["stars"] - pmap[r["repo"]]
            s.gain_days = (date.fromisoformat(day) - date.fromisoformat(prev[0])).days
        out.append(s)
    out.sort(key=lambda s: (s.gain or 0, s.stars), reverse=True)
    return out, prev[0] if prev else ""


def hub(data_dir: Path) -> dict:
    snaps = _snapshots(data_dir / "hub")
    return snaps[-1][1] if snaps else {}


@dataclass
class Dash:
    attention: list[Series] = field(default_factory=list)
    downloads: list[Series] = field(default_factory=list)
    pricing: Pricing | None = None
    repos: list[RepoStat] = field(default_factory=list)
    repos_since: str = ""
    hub: dict = field(default_factory=dict)

    def rising_attention(self, n: int = 8) -> list[Series]:
        rows = [s for s in self.attention if s.change30 is not None and s.prev30 > 3000]
        return sorted(rows, key=lambda s: s.change30, reverse=True)[:n]

    def rising_downloads(self, n: int = 8) -> list[Series]:
        rows = [s for s in self.downloads if s.change30 is not None and s.prev30 > 10000]
        return sorted(rows, key=lambda s: s.change30, reverse=True)[:n]


def load_dash(data_dir: Path, today: date) -> Dash:
    rs, since = repos(data_dir, today)
    return Dash(attention=attention(data_dir), downloads=downloads(data_dir), pricing=pricing(data_dir, today),
                repos=rs, repos_since=since, hub=hub(data_dir))
