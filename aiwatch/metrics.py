"""「数字の定点観測」の取り込み。アイテム（記事）ではなく、毎日の数字を時系列で貯める。

  data/pricing/<YYYY-MM-DD>.json   OpenRouter の全モデルの API 価格と文脈長（その日のスナップショット）
  data/attention.json              Wikipedia の閲覧数（記事ごと・日ごと）= 世間の関心
  data/downloads.json              PyPI / npm の AI ライブラリのダウンロード数（日ごと）= 開発現場での普及
  data/repos/<YYYY-MM-DD>.json     主要な AI オープンソースのスター数・最新リリース
  data/hub/<YYYY-MM-DD>.json       Hugging Face のトレンドのアプリ（Spaces）とデータセット
  data/items/releases/             主要な組織（日本の組織を含む）が新しく公開したモデル
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote

from .sources import Http, clip, iso_day, save_items

WIKI_UA = "AIWatch/1.0 (https://ai-watch.rakunowa.workers.dev/about/; non-commercial trend dashboard)"

# Wikipedia の記事（言語, 題名, 表示名）
WIKI_ARTICLES: tuple[tuple[str, str, str], ...] = (
    ("en", "ChatGPT", "ChatGPT"),
    ("en", "Claude_(language_model)", "Claude"),
    ("en", "Gemini_(chatbot)", "Gemini"),
    ("en", "Grok_(chatbot)", "Grok"),
    ("en", "DeepSeek", "DeepSeek"),
    ("en", "Qwen", "Qwen"),
    ("en", "Llama_(language_model)", "Llama"),
    ("en", "Mistral_AI", "Mistral AI"),
    ("en", "OpenAI", "OpenAI（会社）"),
    ("en", "Anthropic", "Anthropic（会社）"),
    ("en", "Nvidia", "NVIDIA（会社）"),
    ("en", "Large_language_model", "大規模言語モデル"),
    ("en", "Generative_artificial_intelligence", "生成 AI"),
    ("en", "AI_agent", "AI エージェント"),
    ("en", "Retrieval-augmented_generation", "RAG"),
    ("en", "Model_Context_Protocol", "MCP"),
    ("en", "Vibe_coding", "バイブコーディング"),
    ("en", "Prompt_engineering", "プロンプトエンジニアリング"),
    ("en", "Hallucination_(artificial_intelligence)", "ハルシネーション"),
    ("en", "Artificial_general_intelligence", "AGI（汎用人工知能）"),
    ("en", "Humanoid_robot", "人型ロボット"),
    ("en", "Sora_(text-to-video_model)", "Sora"),
    ("en", "Stable_Diffusion", "Stable Diffusion"),
    ("en", "AI_safety", "AI の安全性"),
    ("ja", "ChatGPT", "ChatGPT（日本語版）"),
    ("ja", "生成的人工知能", "生成 AI（日本語版）"),
    ("ja", "大規模言語モデル", "大規模言語モデル（日本語版）"),
    ("ja", "人工知能", "人工知能（日本語版）"),
)

PYPI = ("openai", "anthropic", "google-genai", "langchain", "langgraph", "llama-index", "transformers", "vllm",
        "ollama", "mcp", "crewai", "dspy", "litellm", "sentence-transformers", "chromadb", "pydantic-ai",
        "openai-agents", "smolagents", "unsloth", "docling")
NPM = ("openai", "@anthropic-ai/sdk", "ai", "@google/genai", "langchain", "@modelcontextprotocol/sdk", "ollama",
       "@openai/agents", "@langchain/langgraph", "@mastra/core")

REPOS = ("ollama/ollama", "ggml-org/llama.cpp", "vllm-project/vllm", "sgl-project/sglang", "huggingface/transformers",
         "langchain-ai/langchain", "langchain-ai/langgraph", "run-llama/llama_index", "open-webui/open-webui",
         "langgenius/dify", "n8n-io/n8n", "comfyanonymous/ComfyUI", "microsoft/autogen", "crewAIInc/crewAI",
         "modelcontextprotocol/servers", "anthropics/claude-code", "openai/codex", "google-gemini/gemini-cli",
         "BerriAI/litellm", "unslothai/unsloth", "infiniflow/ragflow", "mem0ai/mem0", "browser-use/browser-use",
         "microsoft/markitdown", "docling-project/docling", "FlowiseAI/Flowise", "lobehub/lobe-chat",
         "mudler/LocalAI", "hiyouga/LLaMA-Factory", "Mintplex-Labs/anything-llm", "pytorch/pytorch",
         "openai/whisper", "huggingface/smolagents", "stanfordnlp/dspy", "pydantic/pydantic-ai")

# 新しいモデルを見張る組織（Hugging Face のアカウント名, 表示名, 日本の組織か）
ORGS: tuple[tuple[str, str, bool], ...] = (
    ("openai", "OpenAI", False), ("google", "Google", False), ("meta-llama", "Meta", False),
    ("microsoft", "Microsoft", False), ("nvidia", "NVIDIA", False), ("mistralai", "Mistral AI", False),
    ("Qwen", "Qwen（Alibaba）", False), ("deepseek-ai", "DeepSeek", False), ("moonshotai", "Moonshot AI", False),
    ("zai-org", "Z.ai（GLM）", False), ("tencent", "Tencent", False), ("baidu", "Baidu", False),
    ("ibm-granite", "IBM Granite", False), ("allenai", "Ai2", False), ("apple", "Apple", False),
    ("LiquidAI", "Liquid AI", False), ("black-forest-labs", "Black Forest Labs", False),
    ("stabilityai", "Stability AI", False), ("Lightricks", "Lightricks", False), ("HuggingFaceTB", "Hugging Face", False),
    ("CohereLabs", "Cohere", False), ("ByteDance-Seed", "ByteDance Seed", False), ("MiniMaxAI", "MiniMax", False),
    ("llm-jp", "LLM-jp（国立情報学研究所）", True), ("sbintuitions", "SB Intuitions", True), ("pfnet", "Preferred Networks", True),
    ("cyberagent", "サイバーエージェント", True), ("elyza", "ELYZA", True), ("tokyotech-llm", "Swallow（科学大）", True),
    ("rinna", "rinna", True), ("stockmark", "ストックマーク", True), ("kotoba-tech", "Kotoba Technologies", True),
    ("Rakuten", "楽天", True), ("SakanaAI", "Sakana AI", True), ("weblab-GENIAC", "松尾研（GENIAC）", True),
    ("abeja", "ABEJA", True), ("nvidia-jp", "NVIDIA 日本", True),
)
ORG_BY_ID = {o[0]: o for o in ORGS}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0, sort_keys=isinstance(data, dict)) + "\n",
                    encoding="utf-8", newline="\n")


# ---------- API の価格（OpenRouter） ----------

def fetch_pricing(http: Http, root: Path) -> int:
    r = http.get("https://openrouter.ai/api/v1/models")
    if r is None or r.status_code != 200:
        print("  ! OpenRouter を読めない")
        return 0
    rows = []
    for m in r.json().get("data", []):
        p = m.get("pricing") or {}
        try:
            pin = float(p.get("prompt") or 0) * 1e6
            pout = float(p.get("completion") or 0) * 1e6
        except ValueError:
            continue
        if pin < 0 or pout < 0:   # 「自動で選ぶ」ルーターは -1 になっている
            continue
        arch = m.get("architecture") or {}
        rows.append({
            "id": m["id"], "name": clip(m.get("name") or m["id"], 80),
            "created": date.fromtimestamp(m["created"]).isoformat() if m.get("created") else "",
            "context": int(m.get("context_length") or 0),
            "in": round(pin, 4), "out": round(pout, 4),
            "modality": arch.get("modality") or "",
        })
    _dump(root / "pricing" / f"{date.today().isoformat()}.json", sorted(rows, key=lambda x: x["id"]))
    return len(rows)


# ---------- 世間の関心（Wikipedia の閲覧数） ----------

def fetch_attention(http: Http, root: Path, days: int) -> None:
    path = root / "attention.json"
    data = _load(path)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    for lang, title, _ in WIKI_ARTICLES:
        key = f"{lang}:{title}"
        url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{lang}.wikipedia/all-access/user/"
               f"{quote(title, safe='')}/daily/{start:%Y%m%d}/{end:%Y%m%d}")
        r = http.get(url, headers={"User-Agent": WIKI_UA}, min_gap=1.5)
        if r is None or r.status_code != 200:
            print(f"  ! Wikipedia {key}: {r.status_code if r is not None else '通信失敗'}")
            continue
        row = data.setdefault(key, {})
        for it in r.json().get("items", []):
            t = it["timestamp"]
            row[f"{t[:4]}-{t[4:6]}-{t[6:8]}"] = int(it["views"])
        cut = (date.today() - timedelta(days=400)).isoformat()
        data[key] = {k: v for k, v in sorted(row.items()) if k >= cut}
    _dump(path, data)


# ---------- 開発現場での普及（PyPI / npm のダウンロード数） ----------

def fetch_downloads(http: Http, root: Path) -> None:
    path = root / "downloads.json"
    data = _load(path)
    for pkg in PYPI:
        r = http.get(f"https://pypistats.org/api/packages/{pkg}/overall", params={"mirrors": "false"}, min_gap=2.0)
        if r is None or r.status_code != 200:
            print(f"  ! PyPI {pkg}: {r.status_code if r is not None else '通信失敗'}")
            continue
        row = data.setdefault(f"pypi:{pkg}", {})
        for it in r.json().get("data", []):
            if it.get("category") == "without_mirrors":
                row[it["date"]] = int(it["downloads"])
    for pkg in NPM:
        r = http.get(f"https://api.npmjs.org/downloads/range/last-year/{quote(pkg, safe='@/')}")
        if r is None or r.status_code != 200:
            print(f"  ! npm {pkg}: {r.status_code if r is not None else '通信失敗'}")
            continue
        row = data.setdefault(f"npm:{pkg}", {})
        for it in r.json().get("downloads", []):
            row[it["day"]] = int(it["downloads"])
    cut = (date.today() - timedelta(days=400)).isoformat()
    for k in data:
        data[k] = {d: v for d, v in sorted(data[k].items()) if d >= cut}
    _dump(path, data)


# ---------- 主要な AI オープンソースのスター数 ----------

def _github_headers() -> dict:
    h = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        try:   # 手元では gh にログインしていればそのトークンを使う（認証なしだと 1 時間 60 回まで）
            token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            token = ""
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def fetch_repos(http: Http, root: Path) -> int:
    h = _github_headers()
    with_release = "Authorization" in h
    rows = []
    for name in REPOS:
        r = http.get(f"https://api.github.com/repos/{name}", headers=h, min_gap=0.3)
        if r is None or r.status_code != 200:
            print(f"  ! GitHub {name}: {r.status_code if r is not None else '通信失敗'}")
            continue
        j = r.json()
        row = {"repo": j["full_name"], "stars": j["stargazers_count"], "forks": j["forks_count"],
               "desc": clip(j.get("description") or "", 160), "lang": j.get("language") or "",
               "pushed": iso_day(j.get("pushed_at")), "release": "", "release_date": ""}
        if with_release:
            rr = http.get(f"https://api.github.com/repos/{name}/releases/latest", headers=h, min_gap=0.3)
            if rr is not None and rr.status_code == 200:
                row["release"] = clip(rr.json().get("tag_name") or "", 40)
                row["release_date"] = iso_day(rr.json().get("published_at"))
        rows.append(row)
    _dump(root / "repos" / f"{date.today().isoformat()}.json", rows)
    return len(rows)


# ---------- Hugging Face のトレンドのアプリとデータセット ----------

def fetch_hub(http: Http, root: Path) -> None:
    out = {}
    r = http.get("https://huggingface.co/api/spaces", params={"sort": "trendingScore", "limit": 40})
    if r is not None and r.status_code == 200:
        out["spaces"] = [{"id": s["id"], "likes": s.get("likes", 0), "sdk": s.get("sdk") or "",
                          "title": clip(((s.get("cardData") or {}).get("title")) or "", 80),
                          "desc": clip(((s.get("cardData") or {}).get("short_description")) or "", 140)}
                         for s in r.json()]
    r = http.get("https://huggingface.co/api/datasets", params={"sort": "trendingScore", "limit": 30})
    if r is not None and r.status_code == 200:
        out["datasets"] = [{"id": d["id"], "likes": d.get("likes", 0), "downloads": d.get("downloads", 0),
                            "tags": [t for t in d.get("tags", []) if t.startswith(("task_categories:", "language:"))][:6]}
                           for d in r.json()]
    if out:
        _dump(root / "hub" / f"{date.today().isoformat()}.json", out)


# ---------- 主要な組織の新しいモデル ----------

def fetch_releases(http: Http, root: Path, days: int) -> int:
    cut = (date.today() - timedelta(days=days)).isoformat()
    rows = []
    for org, label, jp in ORGS:
        r = http.get("https://huggingface.co/api/models",
                     params={"author": org, "sort": "createdAt", "direction": -1, "limit": 30, "full": "false"})
        if r is None or r.status_code != 200:
            continue
        for m in r.json():
            day = iso_day(m.get("createdAt"))
            if not day or day < cut or m.get("private"):
                continue
            mid = m.get("id") or m.get("modelId")
            rows.append({
                "id": "release-" + mid.replace("/", "__"), "source": "releases", "kind": "release",
                "title": mid, "url": f"https://huggingface.co/{mid}", "date": day, "summary": "",
                "score": int(m.get("likes") or 0),
                "extra": {"org": org, "publisher": label, "jp": jp, "task": m.get("pipeline_tag") or "",
                          "downloads": int(m.get("downloads") or 0), "lang": "ja" if jp else "en"},
            })
    return save_items(root, "releases", rows) if rows else 0
