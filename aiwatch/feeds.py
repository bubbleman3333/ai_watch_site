"""RSS / Atom の取り込み元の一覧。足すときは 1 行足すだけ（題名とリンクしか保存しない）。

kind（ページでの分類）:
  news       各社の公式発表
  blog       研究所・専門家のブログ、ニュースレター
  media      報道（テック系メディア）
  community  エンジニアの技術記事（Zenn・Qiita など）
  policy     政府・行政の発表

filter=True のものは AI と関係のない記事も流れてくるので、題名に AI の語があるものだけ残す。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Feed:
    key: str
    label: str
    url: str
    kind: str
    lang: str = "en"
    filter: bool = False
    weight: float = 0.5   # 注目度の基本点（0〜1）


FEEDS: tuple[Feed, ...] = (
    # 各社の公式発表
    Feed("openai", "OpenAI", "https://openai.com/news/rss.xml", "news", weight=0.9),
    Feed("deepmind", "Google DeepMind", "https://deepmind.google/blog/rss.xml", "news", weight=0.85),
    Feed("google", "Google AI", "https://blog.google/technology/ai/rss/", "news", weight=0.75),
    Feed("google-research", "Google Research", "https://research.google/blog/rss/", "news", weight=0.6),
    Feed("microsoft", "Microsoft", "https://news.microsoft.com/source/topics/ai/feed/", "news", weight=0.65),
    Feed("msr", "Microsoft Research", "https://www.microsoft.com/en-us/research/feed/", "news", weight=0.5),
    Feed("nvidia", "NVIDIA", "https://blogs.nvidia.com/feed/", "news", weight=0.6),
    Feed("nvidia-dev", "NVIDIA Developer", "https://developer.nvidia.com/blog/feed", "news", weight=0.45),
    Feed("apple-ml", "Apple Machine Learning", "https://machinelearning.apple.com/rss.xml", "news", weight=0.6),
    Feed("aws", "AWS Machine Learning", "https://aws.amazon.com/blogs/machine-learning/feed/", "news", weight=0.4),
    Feed("amazon-science", "Amazon Science", "https://www.amazon.science/index.rss", "news", weight=0.45),
    Feed("huggingface", "Hugging Face", "https://huggingface.co/blog/feed.xml", "news", weight=0.5),
    Feed("mistral", "Mistral AI", "https://mistral.ai/rss.xml", "news", weight=0.6),
    Feed("databricks", "Databricks", "https://www.databricks.com/feed", "news", filter=True, weight=0.4),
    Feed("sakana", "Sakana AI", "https://sakana.ai/feed.xml", "news", weight=0.55),
    Feed("together", "Together AI", "https://www.together.ai/blog/rss.xml", "news", weight=0.4),
    Feed("cloudflare", "Cloudflare", "https://blog.cloudflare.com/tag/ai/rss/", "news", weight=0.45),
    Feed("github", "GitHub", "https://github.blog/ai-and-ml/feed/", "news", weight=0.55),
    # 研究所・専門家
    Feed("bair", "Berkeley AI Research", "https://bair.berkeley.edu/blog/feed.xml", "blog", weight=0.5),
    Feed("mit-news", "MIT News", "https://news.mit.edu/rss/topic/artificial-intelligence2", "blog", weight=0.45),
    Feed("import-ai", "Import AI（Jack Clark）", "https://importai.substack.com/feed", "blog", weight=0.55),
    Feed("simonw", "Simon Willison", "https://simonwillison.net/atom/everything/", "blog", filter=True, weight=0.5),
    Feed("latent-space", "Latent Space", "https://www.latent.space/feed", "blog", weight=0.5),
    # 報道
    Feed("techcrunch", "TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/", "media", weight=0.6),
    Feed("verge", "The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "media", weight=0.6),
    Feed("ars", "Ars Technica", "https://arstechnica.com/ai/feed/", "media", weight=0.55),
    Feed("mittr", "MIT Technology Review", "https://www.technologyreview.com/topic/artificial-intelligence/feed", "media", weight=0.6),
    Feed("wired", "WIRED", "https://www.wired.com/feed/tag/ai/latest/rss", "media", weight=0.5),
    # 日本語
    Feed("itmedia", "ITmedia AI+", "https://rss.itmedia.co.jp/rss/2.0/aiplus.xml", "media", "ja", weight=0.65),
    Feed("publickey", "Publickey", "https://www.publickey1.jp/atom.xml", "media", "ja", filter=True, weight=0.6),
    Feed("xtech", "日経クロステック", "https://xtech.nikkei.com/rss/xtech-it.rdf", "media", "ja", filter=True, weight=0.6),
    Feed("impress", "Impress Watch", "https://www.watch.impress.co.jp/data/rss/1.0/ipw/feed.rdf", "media", "ja", filter=True, weight=0.55),
    Feed("nvidia-jp", "NVIDIA 日本", "https://blogs.nvidia.co.jp/feed/", "news", "ja", weight=0.5),
    Feed("aws-jp", "AWS 日本", "https://aws.amazon.com/jp/blogs/news/feed/", "news", "ja", filter=True, weight=0.45),
    Feed("zenn-ai", "Zenn（AI）", "https://zenn.dev/topics/ai/feed", "community", "ja", weight=0.4),
    Feed("zenn-llm", "Zenn（LLM）", "https://zenn.dev/topics/llm/feed", "community", "ja", weight=0.4),
    Feed("zenn-genai", "Zenn（生成AI）", "https://zenn.dev/topics/%E7%94%9F%E6%88%90ai/feed", "community", "ja", weight=0.4),
    Feed("qiita-llm", "Qiita（LLM）", "https://qiita.com/tags/llm/feed", "community", "ja", weight=0.4),
    Feed("qiita-genai", "Qiita（生成AI）", "https://qiita.com/tags/%E7%94%9F%E6%88%90ai/feed", "community", "ja", weight=0.4),
    Feed("digital", "デジタル庁", "https://www.digital.go.jp/rss/news.xml", "policy", "ja", filter=True, weight=0.7),
    Feed("meti", "経済産業省", "https://www.meti.go.jp/ml_index_release_atom.xml", "policy", "ja", filter=True, weight=0.7),
)

# RSS の無いところはページを直接読む（sources.fetch_scraped）。(key, 表示名, 一覧ページ, kind, 基本点)
SCRAPED: tuple[tuple[str, str, str, str, float], ...] = (
    ("anthropic", "Anthropic", "https://www.anthropic.com/news", "news", 0.9),
)

FEED_BY_KEY = {f.key: f for f in FEEDS}
for _k, _label, _url, _kind, _w in SCRAPED:
    FEED_BY_KEY[_k] = Feed(_k, _label, _url, _kind, weight=_w)

AI_WORDS = re.compile(
    r"\b(ai|a\.i\.|llms?|gpt[-\w]*|chatgpt|claude|gemini|copilot|openai|anthropic|agents?|agentic|machine learning|"
    r"neural|deep learning|genai|generative|inference|mcp|rag|transformer|diffusion|model)\b|"
    r"人工知能|生成|ＡＩ|AI|エージェント|機械学習|深層学習|LLM|言語モデル|チャットボット", re.I)
