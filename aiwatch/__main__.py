"""使い方:
  python -m aiwatch fetch [--backfill] [--only papers,models,github,hn,news,arxiv]   取り込む
  python -m aiwatch build [--out dist] [--site-url URL]                              サイトを生成
  python -m aiwatch all                                                              fetch → build
  python -m aiwatch pending [--limit 40]          ひとこと解説がまだ無い注目アイテム（Claude が書く分）
  python -m aiwatch digest --limit 40 --out FILE  解説を書くための材料をテキストで書き出す
  python -m aiwatch stats                         取り込み済みの様子
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .build import ROOT, Builder, load_config
from .model import load_all, pick_for_notes
from .sources import sync


def main(argv: list[str] | None = None) -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="aiwatch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--backfill", action="store_true", help="初回用。過去 120 日の論文・26 週の arXiv を取る")
    f.add_argument("--only", default="", help="カンマ区切りで取り込み元を絞る")
    b = sub.add_parser("build")
    b.add_argument("--out", default="dist")
    b.add_argument("--site-url", default=None)
    a = sub.add_parser("all")
    a.add_argument("--out", default="dist")
    a.add_argument("--site-url", default=None)
    pe = sub.add_parser("pending")
    pe.add_argument("--limit", type=int, default=40)
    d = sub.add_parser("digest")
    d.add_argument("--offset", type=int, default=0)
    d.add_argument("--limit", type=int, default=40)
    d.add_argument("--out", default="-")
    sub.add_parser("stats")
    args = p.parse_args(argv)

    data = ROOT / "data"
    site = load_config(ROOT)
    if args.cmd in ("fetch", "all"):
        only = set(x for x in getattr(args, "only", "").split(",") if x) or None
        sync(data, backfill=getattr(args, "backfill", False), only=only)
    if args.cmd in ("build", "all"):
        n = Builder(Path(args.out), args.site_url or site["site_url"]).build()
        print(f"{n} ページを {args.out}/ に生成した")
    if args.cmd in ("pending", "digest"):
        corpus = load_all(data)
        rows = pick_for_notes(corpus, ROOT / "content" / "notes")
        if args.cmd == "pending":
            for it in rows[: args.limit]:
                print(f"{it.id}\t{it.kind}\t{it.date}\t{it.title}")
            print(f"未執筆 {len(rows)} 件")
        else:
            chunk = rows[args.offset: args.offset + args.limit]
            text = "\n\n".join(it.digest() for it in chunk)
            if args.out == "-":
                print(text)
            else:
                Path(args.out).write_text(text + "\n", encoding="utf-8")
                print(f"{len(chunk)} 件を {args.out} に書いた")
    if args.cmd == "stats":
        corpus = load_all(data)
        c = Counter(it.source for it in corpus.items)
        print("アイテム:", dict(c))
        print("モデルのスナップショット:", len(corpus.model_days), "日")
        t = Counter(s for it in corpus.items for s in it.topics)
        for slug, n in t.most_common():
            print(f"  {n:5d}  {slug}")


if __name__ == "__main__":
    main()
