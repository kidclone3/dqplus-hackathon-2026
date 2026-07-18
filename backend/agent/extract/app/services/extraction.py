import json

from openai import AsyncOpenAI

from app import config
from app.schemas.founder import FOUNDER_SCHEMA
from app.schemas.investor import INVESTOR_SCHEMA

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY or "not-set", base_url=config.OPENAI_BASE_URL)

SYSTEM_PROMPT = """You extract structured data from text describing a startup founder/company or an investor.
Rules:
- Use only information present in the text. Use null for unknown scalars and [] for unknown arrays.
- Normalize sectors/industries to lowercase single words or hyphenated terms (e.g. "fintech", "health-tech", "e-commerce").
- Normalize stages to exactly: pre-seed, seed, series-a, series-b, growth.
- Normalize regions/geographies to lowercase (e.g. "vietnam", "sea", "apac", "us", "eu", "global").
- Monetary amounts are in USD numbers (e.g. "1.5M" -> 1500000)."""


async def extract_attributes(role: str, text: str) -> dict:
    schema = INVESTOR_SCHEMA if role == "investor" else FOUNDER_SCHEMA
    completion = await client.chat.completions.create(
        model=config.OPENAI_CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract the {role} profile from this text:\n\n{text}"},
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    return json.loads(completion.choices[0].message.content)


def build_embedding_text(role: str, attrs: dict) -> str:
    parts = []
    if role == "founder":
        if attrs.get("company_name"):
            parts.append(attrs["company_name"])
        if attrs.get("industry"):
            parts.append(f"{', '.join(attrs['industry'])} startup")
        if attrs.get("stage"):
            parts.append(f"at {attrs['stage']} stage")
        if attrs.get("country"):
            parts.append(f"based in {attrs['country']}")
        if attrs.get("target_regions"):
            parts.append(f"targeting {', '.join(attrs['target_regions'])}")
        if attrs.get("business_model"):
            parts.append(f"business model: {attrs['business_model']}")
        if attrs.get("product_description"):
            parts.append(attrs["product_description"])
        if attrs.get("traction_summary"):
            parts.append(f"Traction: {attrs['traction_summary']}")
    else:
        if attrs.get("firm_name"):
            parts.append(attrs["firm_name"])
        if attrs.get("investor_type"):
            parts.append(f"{attrs['investor_type']} investor")
        if attrs.get("sectors"):
            parts.append(f"investing in {', '.join(attrs['sectors'])}")
        if attrs.get("stages"):
            parts.append(f"at {', '.join(attrs['stages'])} stages")
        if attrs.get("geographies"):
            parts.append(f"in {', '.join(attrs['geographies'])}")
        if attrs.get("thesis"):
            parts.append(f"Thesis: {attrs['thesis']}")
        if attrs.get("constraints"):
            parts.append(f"Avoids: {attrs['constraints']}")
    return ". ".join(parts) or f"{role} profile with no extracted details"
