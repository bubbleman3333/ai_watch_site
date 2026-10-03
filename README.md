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
| `aiwatch/sources.py` | 取り込み。保存は題名・リンク・日付・数字・短い抜粋だけ（本文は保存しない） |
| `aiwatch/model.py` | 読み込みと集計。注目度（heat）、テーマの勢い（momentum）、解説を書く候補の選び方 |
| `aiwatch/build.py` | Jinja2 で `dist/` を書き出す。グラフは Python で SVG を作る（JS もグラフのライブラリも使わない） |
| `content/` | 文章。書き方の決まりは `content/README.md` |
| `.github/workflows/daily.yml` | 毎朝 5:37（JST）に fetch → データをコミット → テスト → build → Pages |

### 取り込み元

| 取り込み元 | 保存先 | 何に使うか |
| --- | --- | --- |
| arXiv API | `data/arxiv_weekly.json` | テーマごとの週あたりの論文数 → **勢い**（AI 論文全体に占める割合の、直近 4 週 ÷ その前 8 週） |
| Hugging Face Daily Papers | `data/items/hf_papers/` | 研究者が票を入れた注目論文 |
| Hugging Face トレンド | `data/models/<日付>.json` | 話題のモデル（毎日の上位 60。順位の変化もここから） |
| GitHub 検索 API | `data/items/github/` | 30 日以内に作られてスターを集めたリポジトリ |
| Hacker News（Algolia） | `data/items/hn/` | エンジニアの間の話題（AI の語を題名に含み 80 点以上） |
| 各社 RSS | `data/items/news/` | OpenAI・Google DeepMind・Google・Microsoft・NVIDIA・AWS・Hugging Face・Mistral・ITmedia AI+（題名とリンクだけ） |

アイテムは 400 日で消す。検閲外し・顔の入れ替え・成人向けのモデルは載せない（`model.py` の `HIDE_MODEL`）。

## 生成されるページ

| パス | 内容 |
| --- | --- |
| `/` | 今週の注目・技術テーマの勢い・業種の入口・各社の発表・注目論文・話題のモデル・急成長の OSS・Hacker News |
| `/topic/<slug>/` | テーマの解説（`content/topics/`）＋ 論文の割合と件数のグラフ ＋ 最近の注目・新着・話題のモデル |
| `/industry/<slug>/` | 業種別の使い方（`content/industries/`）＋ 関係の深いテーマ ＋ 関係する解説 |
| `/note/<id>/` `/notes/` | 1 件ごとの解説（`content/notes/`）と一覧 |
| `/models/` `/latest/` `/week/<YYYY-Www>/` | 話題のモデル上位、直近 30 日の新着（絞り込みつき）、週ごとのまとめ |
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
