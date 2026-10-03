"""技術テーマ（トピック）と業種の定義。

取り込んだ論文・ニュース・モデル・リポジトリは、ここのキーワードでテーマに振り分ける。
テーマを足すときは TOPICS に 1 つ足し、`content/topics/<slug>.md` に解説を書く（無くても壊れない）。
`arxiv` は arXiv の週ごとの論文数を数える検索式（abs: = 要旨、ti: = 題名）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    slug: str
    name: str
    short: str            # 一行の説明（カードに出す）
    color: str            # カードの色（CSS の色）
    keywords: tuple[str, ...]   # 正規表現（大文字小文字は区別しない）
    arxiv: str            # arXiv の検索式（カテゴリの絞り込みは自動で付く）

    @property
    def path(self) -> str:
        return f"topic/{self.slug}/"


@dataclass(frozen=True)
class Industry:
    slug: str
    name: str
    short: str
    topics: tuple[str, ...]   # 特に関係の深いテーマ

    @property
    def path(self) -> str:
        return f"industry/{self.slug}/"


TOPICS: tuple[Topic, ...] = (
    Topic("agents", "AI エージェント", "指示を受けて、自分で手順を考えて道具を使い、仕事を最後までやる AI",
          "#7c3aed",
          (r"\bagents?\b", r"\bagentic\b", r"computer[- ]use", r"browser[- ]use", r"エージェント",
           r"\bmulti-agent\b", r"autonomous (task|workflow)"),
          'abs:"LLM agent" OR abs:"language agent" OR abs:agentic OR abs:"multi-agent" OR abs:"computer use"'),
    Topic("coding", "AI コーディング", "コードを書く・直す・レビューする AI。開発の生産性を大きく変えている",
          "#2563eb",
          (r"code generation", r"\bcoding\b", r"\bcopilot\b", r"swe-bench", r"software engineering",
           r"program synthesis", r"\bcodex\b", r"claude code", r"\bcursor\b", r"コーディング", r"コード生成",
           r"\bvibe coding\b", r"code review"),
          'abs:"code generation" OR abs:"SWE-bench" OR abs:"coding agent" OR abs:"program synthesis" OR abs:"software engineering agent"'),
    Topic("reasoning", "推論モデル", "答える前に長く「考える」ことで、数学・計画・難しい判断に強くなったモデル",
          "#db2777",
          (r"\breasoning\b", r"chain[- ]of[- ]thought", r"test[- ]time (compute|scaling)", r"\bthinking\b",
           r"\bo[134]\b", r"\br1\b", r"推論モデル", r"思考", r"\bgrpo\b", r"\brlvr\b"),
          'abs:"reasoning model" OR abs:"chain-of-thought" OR abs:"test-time scaling" OR abs:"test-time compute" OR abs:"long reasoning"'),
    Topic("rag", "RAG・社内データ検索", "社内文書やデータベースを検索して、根拠つきで答えさせる仕組み",
          "#059669",
          (r"retrieval[- ]augmented", r"\brag\b", r"\bretrieval\b", r"\bembeddings?\b", r"vector (db|database|search)",
           r"\brerank", r"knowledge graph", r"graphrag", r"検索拡張", r"ナレッジ"),
          'abs:"retrieval-augmented" OR abs:"retrieval augmented" OR abs:RAG OR abs:GraphRAG'),
    Topic("multimodal", "マルチモーダル・文書読み取り", "画像・図・PDF・画面を「見て」理解する AI。帳票の読み取りもここ",
          "#ea580c",
          (r"vision[- ]language", r"\bvlms?\b", r"multimodal", r"multi-modal", r"\bocr\b", r"document (understanding|parsing)",
           r"image-text-to-text", r"visual question", r"マルチモーダル", r"画像認識", r"帳票"),
          'abs:"vision-language" OR abs:"multimodal large language" OR abs:VLM OR abs:"document understanding"'),
    Topic("image-gen", "画像生成・編集", "文章から画像を作る・写真を直す AI。広告・デザイン・EC で実用段階",
          "#c026d3",
          (r"text[- ]to[- ]image", r"image (generation|editing|synthesis)", r"\bdiffusion\b", r"stable diffusion",
           r"\bflux\b", r"midjourney", r"画像生成", r"image-to-image"),
          'abs:"text-to-image" OR abs:"image editing" OR abs:"image generation"'),
    Topic("video-gen", "動画生成・ワールドモデル", "文章や画像から動画を作る AI と、世界の動きを予測する「ワールドモデル」",
          "#dc2626",
          (r"video (generation|diffusion|synthesis)", r"text[- ]to[- ]video", r"image[- ]to[- ]video", r"\bsora\b", r"\bveo\b",
           r"world models?", r"動画生成", r"ワールドモデル"),
          'abs:"video generation" OR abs:"text-to-video" OR abs:"world model" OR abs:"video diffusion"'),
    Topic("speech", "音声 AI", "聞き取り（文字起こし）・読み上げ・リアルタイム音声対話。電話や会議で使われる",
          "#0891b2",
          (r"\bspeech\b", r"\basr\b", r"\btts\b", r"text[- ]to[- ]speech", r"speech recognition", r"\bvoice\b",
           r"\baudio\b", r"spoken", r"音声", r"文字起こし", r"automatic-speech-recognition"),
          'abs:"speech recognition" OR abs:"text-to-speech" OR abs:"spoken language model" OR abs:"speech language model" OR abs:"voice agent"'),
    Topic("efficient", "小型・ローカル・省コスト化", "小さく速く安く動かす技術。量子化・蒸留・端末内で動く AI",
          "#65a30d",
          (r"quantiz", r"small language model", r"\bslms?\b", r"on-device", r"\bedge\b", r"distillation", r"\blora\b",
           r"efficient inference", r"\bgguf\b", r"llama\.cpp", r"\bmlx\b", r"speculative decoding", r"kv cache",
           r"mixture[- ]of[- ]experts", r"\bmoe\b", r"ローカル", r"軽量", r"量子化"),
          'abs:quantization OR abs:"knowledge distillation" OR abs:"on-device" OR abs:"speculative decoding" OR abs:"KV cache" OR abs:"small language model"'),
    Topic("open-models", "オープンモデル", "重みが公開され、自社サーバーで動かせるモデル（Llama・Qwen・Gemma など）",
          "#475569",
          (r"open[- ]weights?", r"open[- ]source (model|llm)", r"\bllama\b", r"\bqwen", r"\bmistral\b", r"\bgemma\b",
           r"\bdeepseek\b", r"\bphi-\d", r"\bolmo\b", r"\bkimi\b", r"\bglm\b", r"オープンモデル", r"オープンソース"),
          'abs:"open-weight" OR abs:"open-source LLM" OR abs:"open-source language model" OR abs:"open language model"'),
    Topic("tools-mcp", "ツール連携・MCP", "AI から社内システムや外部サービスを呼び出す仕組み。MCP は事実上の標準",
          "#0d9488",
          (r"tool[- ]use", r"tool[- ]calling", r"function[- ]calling", r"\bmcp\b", r"model context protocol",
           r"\bapi calls?\b", r"ツール連携", r"ツール呼び出し"),
          'abs:"tool use" OR abs:"tool calling" OR abs:"function calling" OR abs:"Model Context Protocol"'),
    Topic("robotics", "ロボット・フィジカル AI", "現実の世界で手足を動かす AI。工場・倉庫・自動運転",
          "#b45309",
          (r"\brobot", r"embodied", r"manipulation", r"humanoid", r"\bvlas?\b", r"vision-language-action",
           r"autonomous driving", r"self-driving", r"ロボット", r"自動運転", r"フィジカル"),
          'abs:"vision-language-action" OR abs:"robot learning" OR abs:"embodied AI" OR abs:humanoid OR abs:"robot manipulation"'),
    Topic("safety", "安全性・ガバナンス", "嘘（ハルシネーション）・情報漏えい・悪用を防ぐ技術と、法規制の動き",
          "#be123c",
          (r"\bsafety\b", r"alignment", r"jailbreak", r"hallucinat", r"red[- ]team", r"prompt injection",
           r"\bai act\b", r"regulation", r"privacy", r"watermark", r"deepfake", r"guardrail", r"moderation",
           r"安全", r"規制", r"ハルシネーション", r"ガイドライン", r"著作権"),
          'abs:jailbreak OR abs:hallucination OR abs:"AI safety" OR abs:"prompt injection" OR abs:"red teaming"'),
    Topic("science", "科学・医療への応用", "創薬・タンパク質・医療画像・材料・気象など、研究開発を速める AI",
          "#4f46e5",
          (r"protein", r"drug discovery", r"\bmedical\b", r"clinical", r"biolog", r"genom", r"materials? (science|discovery)",
           r"weather forecast", r"\bhealth", r"radiolog", r"pathology", r"医療", r"創薬", r"診断"),
          'abs:"drug discovery" OR abs:"protein design" OR abs:"medical imaging" OR abs:"clinical" OR abs:"materials discovery"'),
    Topic("forecasting", "予測・データ分析", "売上・需要・異常を予測する AI。表データや時系列の「基盤モデル」も登場",
          "#0284c7",
          (r"time[- ]series", r"forecast", r"tabular", r"anomaly detection", r"recommend", r"demand prediction",
           r"text[- ]to[- ]sql", r"data analysis", r"需要予測", r"予測", r"データ分析", r"異常検知", r"レコメンド"),
          'abs:"time series forecasting" OR abs:"tabular foundation" OR abs:"anomaly detection" OR abs:"text-to-SQL"'),
)

TOPIC_BY_SLUG = {t.slug: t for t in TOPICS}

INDUSTRIES: tuple[Industry, ...] = (
    Industry("manufacturing", "製造業", "検査・保全・技術伝承・設計", ("multimodal", "robotics", "forecasting", "rag", "agents")),
    Industry("retail", "小売・EC", "商品説明・画像・接客・需要予測", ("image-gen", "forecasting", "agents", "multimodal", "speech")),
    Industry("logistics", "物流・運送", "配車・問い合わせ・伝票読み取り", ("forecasting", "multimodal", "speech", "agents", "robotics")),
    Industry("finance", "金融・保険", "審査・不正検知・書類処理・顧客対応", ("multimodal", "rag", "safety", "forecasting", "agents")),
    Industry("healthcare", "医療・介護", "記録の自動作成・画像診断支援・見守り", ("speech", "science", "multimodal", "safety", "rag")),
    Industry("construction", "建設・不動産", "図面・現場写真・書類・物件説明", ("multimodal", "image-gen", "rag", "robotics", "agents")),
    Industry("backoffice", "バックオフィス・士業", "経理・人事・法務・契約書", ("rag", "agents", "multimodal", "tools-mcp", "safety")),
    Industry("software", "ソフトウェア開発・IT", "コーディング・テスト・運用・社内ツール", ("coding", "agents", "tools-mcp", "efficient", "open-models")),
    Industry("marketing", "マーケティング・営業", "広告制作・提案書・リスト作り・分析", ("image-gen", "video-gen", "agents", "forecasting", "rag")),
    Industry("education", "教育・研修", "個別指導・教材作り・採点", ("reasoning", "speech", "multimodal", "safety", "rag")),
    Industry("food-service", "飲食・宿泊・サービス", "予約電話・多言語対応・シフト・口コミ", ("speech", "forecasting", "agents", "image-gen", "multimodal")),
    Industry("public", "自治体・公共", "窓口・議事録・文書作成・防災", ("speech", "rag", "safety", "efficient", "multimodal")),
)

INDUSTRY_BY_SLUG = {i.slug: i for i in INDUSTRIES}

_COMPILED = {t.slug: [re.compile(k, re.IGNORECASE) for k in t.keywords] for t in TOPICS}


def classify(*texts: str) -> list[str]:
    """文章からテーマの slug を返す（当たったキーワードの多い順、最大 3 つ）。"""
    text = " ".join(x for x in texts if x)
    if not text:
        return []
    scored = []
    for t in TOPICS:
        hits = sum(1 for rx in _COMPILED[t.slug] if rx.search(text))
        if hits:
            scored.append((hits, t.slug))
    scored.sort(key=lambda x: (-x[0], [t.slug for t in TOPICS].index(x[1])))
    return [s for _, s in scored[:3]]
