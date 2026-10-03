# content/ の書き方

AIウォッチの文章は、API ではなく **Claude Code のセッション（Claude）が書く**。データの取り込みと集計は毎朝自動、
文章はときどきセッションで足す、という分担。ここにあるのは全部 Markdown で、`python -m aiwatch build` で HTML になる。

| 場所 | 中身 | ファイル名 |
| --- | --- | --- |
| `topics/` | 技術テーマの解説（テーマのページの本文） | `aiwatch/topics.py` の `TOPICS` の slug |
| `industries/` | 業種別の使い方 | `INDUSTRIES` の slug |
| `pages/` | はじめかた・このサイトについて・プライバシー | `start` `about` `privacy` |
| `notes/` | 注目アイテム 1 件ごとの「ひとこと解説」 | アイテムの id（`python -m aiwatch pending` で出る） |

## 共通の決まり

- 読み手は **AI に詳しくない会社員・経営者**。専門用語は最初に一言で言い換える（例: 「RAG（社内文書を検索してから答えさせる仕組み）」）。
- 誇張しない。「革命的」「必須」「乗り遅れる」のような煽りは使わない。
- **数字・社名・事例を作らない**。確かでない数字は書かない。費用は「月数千円〜」のような幅で、時点（2026 年時点）を添える。
  実在企業の導入事例は、広く報じられて確かなものだけ。迷ったら「〜のような使い方」と一般的な形で書く。
- 本文中のサイト内リンクは次の書き方にする（ビルド時に URL になる）:
  - `[RAG](topic:rag)` → テーマのページ
  - `[製造業](industry:manufacturing)` → 業種のページ
  - `[はじめかた](page:start)` → 固定ページ
- テーマの slug: agents, coding, reasoning, rag, multimodal, image-gen, video-gen, speech, efficient, open-models,
  tools-mcp, robotics, safety, science, forecasting
- 業種の slug: manufacturing, retail, logistics, finance, healthcare, construction, backoffice, software, marketing,
  education, food-service, public
- 見出しは `##` から（`#` はページの題名に使われる）。表は Markdown の表でよい。

## topics/<slug>.md（2500〜4000 字）

```markdown
## ひとことで
## 仕組みをかんたんに
## いま何が起きているか
## どう使われているか        ← 表: | 使い方 | 誰が・どこで | 何が良くなるか |
## ビジネスへの応用           ← 業種ごとに 1〜2 行。業種ページへのリンクを付ける
## 始め方と費用感             ← 小さく試す順番。既製サービス → 自社データ → 作り込み
## 注意点・リスク
## 関連するテーマ
```

## industries/<slug>.md（3000〜4500 字）

```markdown
## この業種で AI が効くところ        ← 2〜3 段落。人手不足・属人化など業種の事情から
## 使いどころ（効果が出やすい順）       ← ### ごとに 1 つ。何をする / 使う技術（テーマへのリンク）/ 始め方 / 効果の目安
## 最初の 3 か月の進め方
## よくある失敗
## 気をつけること（法律・個人情報・品質）
```

## notes/<id>.md（400〜700 字）

```markdown
---
headline: 日本語の見出し（40 字以内。何が起きたかが分かるように）
point: 一文の要点（80 字以内。ビジネス上の意味まで）
---
### 何が起きた
### なぜ大事か
### ビジネスでの使いどころ
```

- 材料は `python -m aiwatch digest --offset 0 --limit 40 --out tmp.txt` で出る（題名・URL・抜粋・反応の数）。
  題名だけで中身が分からないときは、URL を開いて確かめてから書く。開けない・確かめられないときは書かずに飛ばす。
- 見出しを読むだけで内容が分かるようにする。英語の題名の直訳にしない。
- 「ビジネスでの使いどころ」は、具体的な業種・業務の名前を出す。関係ないものは「直接の使いどころはまだ少ないが〜」と正直に書く。
