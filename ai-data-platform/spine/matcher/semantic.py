import json
import math
import os
import re
import urllib.request
import urllib.error
from typing import Any

# ── Configuration ──────────────────────────────────────────────────
# Mặc định dùng FPT Cloud API (Gemma) nếu có API_KEY, fallback về các provider khác
FPT_BASE = "https://mkp-api.fptcloud.com"
FPT_MODEL = "gemma-4-31B-it"

LLM_BASE = os.environ.get("LLM_API_BASE", FPT_BASE)
LLM_MODEL = os.environ.get("LLM_MODEL", FPT_MODEL)
EMBEDDING_BASE = os.environ.get("EMBEDDING_API_BASE", FPT_BASE)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "")


def _resolve_llm_base() -> tuple[str, str]:
    """Trả về (api_base_url, api_key). Ưu tiên API_KEY → FPT Cloud, fallback DeepSeek/OpenRouter."""
    key = os.environ.get("API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    return LLM_BASE, key


def _resolve_embedding_base() -> tuple[str, str]:
    """Trả về (api_base_url, api_key) cho embedding."""
    key = os.environ.get("API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get("EMBEDDING_API_KEY", "")
    return EMBEDDING_BASE, key


# ── LLM: Schema Extraction ────────────────────────────────────────

def call_llm(prompt: str) -> dict:
    """Gọi LLM (DeepSeek/OpenRouter) để trích xuất schema chuẩn từ text."""
    base, key = _resolve_llm_base()

    if not key:
        return _fallback_extract(prompt)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        # FPT sits behind Cloudflare, which 403s the default urllib User-Agent.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "Bạn là chuyên gia trích xuất dữ liệu doanh nghiệp. "
                                          "Trả lời bằng JSON hợp lệ, không kèm prose."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=data,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode())
        content = result["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception:
        return _fallback_extract(prompt)


def _fallback_extract(text: str) -> dict:
    """Rule-based fallback khi không gọi được LLM."""
    text_lower = text.lower()
    sectors = re.findall(r'(?:sector|industry|field|lĩnh vực)[^:]*:\s*([^\n.]+)', text, re.I)
    sectors_list = []
    if sectors:
        sectors_list = [s.strip() for s in re.split(r'[,;]', sectors[0]) if s.strip()]

    stage = ""
    for s in re.finditer(r'\b(seed|series\s*a[^z]|series\s*b|pre-seed|pre-seed|early.stage|growth)\b', text_lower):
        stage = s.group(1)
        break

    check_size = ""
    for s in re.findall(r'\$[\d,]+(?:\.\d+)?\s*(?:k|m|b|K|M|B)?', text):
        check_size = s
        break

    geo = ""
    countries = ["vietnam", "singapore", "indonesia", "thailand", "usa", "japan",
                 "south korea", "china", "india", "malaysia", "philippines"]
    for c in countries:
        if c in text_lower:
            geo = c.title()
            break

    desc_match = re.search(r'(?:description|about|summary|mô tả)[^:]*:\s*([^\n]{10,})', text, re.I)
    description = desc_match.group(1).strip() if desc_match else text[:300]

    return {
        "stage": stage,
        "check_size": check_size,
        "geo": geo,
        "sectors": sectors_list[:5],
        "thesis": "",
        "description": description,
        "signals": "",
    }


# ── Embedding ──────────────────────────────────────────────────────

def get_embedding(text: str) -> list[float]:
    """Tạo embedding vector. Thử API trước, fallback về char-trigram nếu không có key/model."""
    if not text:
        return [0.0] * 256

    base, key = _resolve_embedding_base()
    if key and EMBEDDING_MODEL:
        try:
            return _call_embedding_api(text, base, key)
        except Exception:
            pass
    return _char_ngram_embedding(text)


def _call_embedding_api(text: str, base: str, key: str) -> list[float]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
        # FPT sits behind Cloudflare, which 403s the default urllib User-Agent.
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": text[:4096],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{base}/embeddings",
        data=data,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    return result["data"][0]["embedding"]


def _char_ngram_embedding(text: str, dim: int = 256) -> list[float]:
    """Character trigram embedding — deterministic, không cần API, vẫn capture
    được pattern ngôn ngữ (tốt hơn bag-of-words đơn thuần)."""
    vec = [0.0] * dim
    cleaned = re.sub(r'\s+', ' ', text.lower()).strip()
    for i in range(len(cleaned) - 2):
        ngram = cleaned[i:i + 3]
        h = hash(ngram)
        idx = abs(h) % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


# ── Cosine Similarity ──────────────────────────────────────────────

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Cosine similarity ∈ [-1, 1]. 0 nếu đầu vào lỗi."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    dot = sum(a * b for a, b in zip(vec1, vec2))
    n1 = math.sqrt(sum(a * a for a in vec1))
    n2 = math.sqrt(sum(b * b for b in vec2))
    return dot / (n1 * n2) if n1 and n2 else 0.0


# ── Schema Extraction ──────────────────────────────────────────────

def extract_schema(entity_text: str, is_startup: bool) -> dict:
    """Trích xuất profile thành schema chuẩn bằng LLM.

    Returns:
        {
            "metadata": {"stage", "check_size", "geo", "sectors", "signals"},
            "embedding": [float]  # vector từ phần định tính
        }
    """
    role = "STARTUP" if is_startup else "INVESTOR / PARTNER"

    prompt = f"""You are a specialized data extractor. Extract the following {role} profile into a structured JSON schema.
Ensure your response is valid JSON with these keys:
- stage: The investment stage or current stage (e.g., Seed, Series A)
- check_size: The typical investment size or fundraising goal
- geo: Geographic focus or location
- sectors: Array of industry sectors
- thesis: The core investment thesis or startup vision
- description: A brief summary of what they do
- signals: Any behavioral signals or past investments / partnerships

Text to extract:
{entity_text[:5000]}
"""

    schema = call_llm(prompt)

    # Phần định tính (thesis + description + signals) → đem đi embed
    qualitative_text = " ".join([
        str(schema.get("thesis", "")),
        str(schema.get("description", "")),
        str(schema.get("signals", "")),
    ])
    embedding = get_embedding(qualitative_text)

    sectors_raw = schema.get("sectors", [])
    if isinstance(sectors_raw, str):
        sectors_raw = [s.strip() for s in sectors_raw.split(",")]

    return {
        "metadata": {
            "stage": str(schema.get("stage", "")),
            "check_size": str(schema.get("check_size", "")),
            "geo": str(schema.get("geo", "")),
            "sectors": [s.lower().strip() for s in sectors_raw if s and s.strip()],
            "signals": str(schema.get("signals", "")),
        },
        "embedding": embedding,
    }


# ── Scoring Components ─────────────────────────────────────────────

def _check_size_score(startup_size: str, partner_size: str) -> float:
    """So sánh check size (15% weight). Tỷ lệ overlap nếu parse được."""
    def _parse(s: str) -> float:
        s = s.replace(",", "").replace("$", "").strip().lower()
        m = re.match(r"(\d+(?:\.\d+)?)\s*([kmb]?)", s)
        if not m:
            return 0.0
        num = float(m.group(1))
        unit = m.group(2)
        if unit == "k":
            num *= 1_000
        elif unit == "m":
            num *= 1_000_000
        elif unit == "b":
            num *= 1_000_000_000
        return num

    if not startup_size or not partner_size:
        return 0.5
    sv = _parse(startup_size)
    pv = _parse(partner_size)
    if sv == 0 or pv == 0:
        return 0.5
    return min(sv, pv) / max(sv, pv)


def _geo_score(startup_geo: str, partner_geo: str) -> float:
    """Điểm địa lý (5% weight). Ưu tiên trùng khớp chính xác."""
    if not startup_geo or not partner_geo:
        return 0.3
    sg = startup_geo.lower().strip()
    pg = partner_geo.lower().strip()
    if sg == pg or sg in pg or pg in sg:
        return 1.0
    # Cùng khu vực Đông Nam Á
    sea = {"vietnam", "thailand", "indonesia", "singapore", "malaysia",
           "philippines", "laos", "cambodia", "myanmar", "brunei", "southeast asia"}
    if sg in sea and pg in sea:
        return 0.7
    if any(k in sg for k in ("asia", "global", "international")) or \
       any(k in pg for k in ("asia", "global", "international")):
        return 0.5
    return 0.0


def _behavior_score(s_meta: dict, p_meta: dict) -> float:
    """Tín hiệu hành vi (10% weight)."""
    score = 0.4
    s_sig = s_meta.get("signals", "").lower()
    p_sig = p_meta.get("signals", "").lower()
    if s_sig and p_sig:
        s_words = set(re.findall(r"[a-z]+", s_sig))
        p_words = set(re.findall(r"[a-z]+", p_sig))
        if s_words and p_words:
            overlap = len(s_words & p_words) / max(1, len(s_words | p_words))
            score += overlap * 0.4
    if s_meta.get("stage") and p_meta.get("stage"):
        if s_meta["stage"].lower().strip() == p_meta["stage"].lower().strip():
            score += 0.2
    return min(1.0, score)


# ── Main Scoring Function ──────────────────────────────────────────

def calculate_fit_score(startup_text: str, partner_text: str) -> dict:
    """Tính độ Fit chuẩn dựa trên Reciprocal Matching & Weighted Scoring.

    Điểm tổng có trọng số:
      - Semantic (cosine hai chiều): 40%
      - Trùng ngành:                    20%
      - Check size:                     15%
      - Stage:                          10%
      - Geo:                             5%
      - Behavioral signals:              10%
    """
    # 1. Trích xuất schema + embedding hai bên
    s_schema = extract_schema(startup_text, is_startup=True)
    p_schema = extract_schema(partner_text, is_startup=False)

    s_meta = s_schema["metadata"]
    p_meta = p_schema["metadata"]

    # 2. Semantic (40%) — cosine similarity HAI CHIỀU (reciprocal matching)
    sim_sp = cosine_similarity(s_schema["embedding"], p_schema["embedding"])
    sim_ps = cosine_similarity(p_schema["embedding"], s_schema["embedding"])
    semantic_score = max(0.0, (sim_sp + sim_ps) / 2)

    # 3. Sector overlap (20%)
    s_sectors = set(s_meta["sectors"])
    p_sectors = set(p_meta["sectors"])
    if s_sectors and p_sectors:
        sector_overlap = len(s_sectors & p_sectors) / max(1, len(s_sectors | p_sectors))
    elif s_sectors and not p_sectors:
        sector_overlap = 0.0
    elif not s_sectors and p_sectors:
        sector_overlap = 0.0
    else:
        sector_overlap = 0.5

    # 4. Check size fit (15%)
    check_size_score = _check_size_score(s_meta["check_size"], p_meta["check_size"])

    # 5. Stage match (10%)
    stage_score = 1.0 if (
        s_meta["stage"] and p_meta["stage"]
        and s_meta["stage"].lower().strip() == p_meta["stage"].lower().strip()
    ) else 0.3

    # 6. Geo fit (5%)
    geo_score = _geo_score(s_meta["geo"], p_meta["geo"])

    # 7. Behavioral signals (10%)
    behavior_score = _behavior_score(s_meta, p_meta)

    # Tổng hợp weighted sum (tất cả đã ∈ [0,1])
    total_score = (
        (semantic_score * 0.40)
        + (sector_overlap * 0.20)
        + (check_size_score * 0.15)
        + (stage_score * 0.10)
        + (geo_score * 0.05)
        + (behavior_score * 0.10)
    )

    return {
        "composite_score": round(max(0.0, min(1.0, total_score)) * 100),
        "breakdown": {
            "semantic": round(semantic_score, 4),
            "sector_overlap": round(sector_overlap, 4),
            "check_size": round(check_size_score, 4),
            "stage": round(stage_score, 4),
            "geo": round(geo_score, 4),
            "behavior": round(behavior_score, 4),
        },
    }
