# AIウォッチ

AI の最新技術の動きを毎日自動で集め、**技術テーマごとの勢い**・注目の発表と論文・話題のモデルとオープンソースを一覧にし、
それぞれの技術が**実際にどう使われていて、どの業種でどう役立つのか**を解説する静的サイト。**運用費ゼロ**
（取り込み元はキー不要の公開 API と RSS、生成と配信は GitHub Actions と GitHub Pages の無料枠）。

- 公開先: https://ai-watch.rakunowa.workers.dev/ （中身は bubbleman3333.github.io/ai_watch_site/。`site_stats/proxy` の Worker で配信し直している）
- 同じ作りのサイト: 補助金ウォッチ・国会ウォッチ など（`PycharmProjects/*_site`）

## 仕組み

```
arXiv / Hugging Face / GitHub / Hacker News / 各社 RSS ──fetch──▶ data/ ──┐
content/（Claude が書いた解説の Markdown） ─────────────────────────────┴─build─▶ dist/ ──▶ GitHub Pages
```

| ファイル | 役目 |
| --- | --- |
| `aiwatch/topics.py` | **技術テーマ 15 個と業種 12 個の定義**。キーワード（振り分け用）と arXiv の検索式（勢いの計算用） |
| `aiwatch/feeds.py` | RSS の取り込み元の一覧（1 行足せば増える） |
| `aiwatch/sources.py` | 記事・論文・リポジトリの取り込み。保存は題名・リンク・日付・数字・短い抜粋だけ（本文は保存しない） |
| `aiwatch/metrics.py` `aiwatch/dash.py` | 数字の定点観測（価格・関心・普及・主要 OSS・新モデル）の取り込みと集計 |
| `aiwatch/model.py` | 読み込みと集計。注目度（heat）、テーマの勢い（momentum）、解説を書く候補の選び方 |
| `aiwatch/build.py` | Jinja2 で `dist/` を書き出す。グラフは Python で SVG を作る（JS もグラフのライブラリも使わない） |
| `content/` | 文章。書き方の決まりは `content/README.md` |
| `.github/workflows/daily.yml` | 毎朝 5:37（JST）に fetch → データをコミット → テスト → build → Pages |

### 取り込み元（50 か所以上。一覧は `/sources/`）

| 取り込み元 | 定義の場所 | 保存先 | 何に使うか |
| --- | --- | --- | --- |
| RSS / Atom 40 余り（各社・研究・報道・日本語メディア・Zenn/Qiita・官公庁） | `aiwatch/feeds.py` の `FEEDS` | `data/items/news/` | 発表・報道・解説・技術記事・政策（題名とリンクだけ） |
| RSS の無いページ（Anthropic） | `feeds.py` の `SCRAPED` と `sources.scrape_anthropic` | 同上 | 一覧ページから題名・日付・リンクを読む |
| arXiv API | `topics.py` の `arxiv` | `data/arxiv_weekly.json` | **勢い**（AI 論文全体に占める割合の、直近 4 週 ÷ その前 8 週） |
| Hugging Face Daily Papers | | `data/items/hf_papers/` | 注目論文 |
| Hugging Face トレンド | | `data/models/<日付>.json` | 話題のモデル（順位の変化もここから） |
| Hugging Face 主要 37 組織 | `metrics.py` の `ORGS`（日本の組織に印） | `data/items/releases/` | 新しいモデル |
| Hugging Face Spaces / Datasets | | `data/hub/<日付>.json` | 話題のアプリとデータセット |
| GitHub 検索 | `sources.GITHUB_TOPICS` | `data/items/github/` | 30 日以内に作られて伸びているリポジトリ |
| GitHub 定点観測 | `metrics.py` の `REPOS` | `data/repos/<日付>.json` | 主要 OSS のスター数・最新リリース |
| Hacker News・Lobsters・DEV | | `data/items/hn/` `data/items/community/` | エンジニアの話題 |
| OpenRouter | | `data/pricing/<日付>.json` | **API 価格表**と値動き・新登場 |
| PyPI・npm | `metrics.py` の `PYPI` `NPM` | `data/downloads.json` | **開発現場での普及**（ダウンロード数） |
| Wikipedia 閲覧数 | `metrics.py` の `WIKI_ARTICLES` | `data/attention.json` | **世間の関心** |

アイテムと日ごとのスナップショットは 400 日で消す。検閲外し・顔の入れ替え・成人向けのモデルは載せない（`model.py` の `HIDE_MODEL`）。
Wikipedia は連続で叩くと 429 を返すので 1.5 秒間隔。GitHub の定点観測は、手元では `gh auth token` を使う（認証なしだと 1 時間 60 回まで）。

## 生成されるページ

| パス | 内容 |
| --- | --- |
| `/` | 今週の注目・技術テーマの勢い・業種の入口・各社の発表・注目論文・話題のモデル・急成長の OSS・Hacker News |
| `/topic/<slug>/` | テーマの解説（`content/topics/`）＋ 論文の割合と件数のグラフ ＋ 最近の注目・新着・話題のモデル |
| `/industry/<slug>/` | 業種別の使い方（`content/industries/`）＋ 関係の深いテーマ ＋ 関係する解説 |
| `/note/<id>/` `/notes/` | 1 件ごとの解説（`content/notes/`）と一覧 |
| `/models/` `/latest/` `/week/<YYYY-Www>/` | 話題のモデル・アプリ・データセット、直近 30 日の新着（絞り込みつき）、週ごとのまとめ |
| `/pricing/` | API 価格表（並べ替え・絞り込み）、30 日の新登場、値動き |
| `/attention/` `/adoption/` | 世間の関心（Wikipedia）、開発現場での普及（PyPI/npm・主要 OSS） |
| `/releases/` `/japan/` `/sources/` | 主要組織の新モデル、日本の動き（政策・報道・国産モデル・技術記事）、情報源の一覧 |
| `/start/` `/about/` `/privacy/` | はじめかた・データの集め方・プライバシー（`content/pages/`） |
| `/feed.xml` `/sitemap.xml` `/robots.txt` `/404.html` | |

## コマンド（`.venv` を使う）

```powershell
.\.venv\Scripts\python -u -m aiwatch fetch --backfill     # 初回だけ。arXiv を 26 週ぶん数えるので 1 時間ほど
.\.venv\Scripts\python -u -m aiwatch fetch                # 毎日の分（数分）。--only news,hn のように絞れる
.\.venv\Scripts\python -m aiwatch build --site-url http://127.0.0.1:8765
.\.venv\Scripts\python -m http.server 8765 -d dist         # http://127.0.0.1:8765/
.\.venv\Scripts\python -m aiwatch stats
.\.venv\Scripts\python -m pytest -q
```

初回だけ `python -m venv .venv` と `.\.venv\Scripts\pip install -r requirements.txt`。

## 解説を足す（Claude Code のセッションで）

LLM を呼ぶコードはリポジトリに置かない。解説は Claude Code のセッションで書く。

```powershell
.\.venv\Scripts\python -m aiwatch pending --limit 40                          # まだ解説の無い注目アイテム
.\.venv\Scripts\python -m aiwatch digest --offset 0 --limit 25 --out ..\ai_watch_tmp\batch.txt   # 書くための材料
```

材料を 25 件ずつサブエージェントに渡し、`content/README.md` に従って `content/notes/<id>.md` に書かせる
（URL を開いて確かめさせ、確かめられないものは飛ばさせる）。書いたら build → commit → push。

## 手を入れるとき

- **テーマを足す・キーワードを直す**: `aiwatch/topics.py` の `TOPICS`。arXiv の件数は新しいテーマの分だけ次の fetch で数えられる
  （`--backfill` を付けると 26 週ぶん）。解説は `content/topics/<slug>.md`。
- **取り込み元を足す**: RSS なら `sources.py` の `FEEDS` に 1 行。題名とリンク以外は保存しないこと。
- **注目度の重み**: `model.py` の `MAJOR`（各社の発表の基本点）と `_percentile_heat`。
- **色**: `static/style.css` の `:root`。テーマの色は `topics.py`。

## 出典

arXiv・Hugging Face・GitHub・Hacker News（Algolia）の公開 API と、各社が公開している RSS。各社とは関係のない非公式サイト。
