from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .ontology import ONTOLOGY, build_ontology_prompts

load_dotenv()

client = OpenAI()
logger = logging.getLogger(__name__)


def classify_event(event: str, model: str = "gpt-4o-mini") -> dict[str, Any]:
    event_text = event.strip() if event else ""
    if not event_text:
        raise ValueError("event text is empty")

    ontology = build_ontology_prompts(detail="full")
    event_types = ", ".join(ONTOLOGY.event_map.keys())

    system_prompt = f"""You are a financial news event classification expert specializing in Korean stock market news.
Analyze Korean news/event text to classify into ontology event types, extract structured slots, and calculate sentiment score.

Task:
1. Event classification: Classify into one event type from ontology. If multiple events exist, select the most significant one.
2. Slot extraction:
   - required_slots: ONLY slots in ontology's "required" list for chosen event_type
   - optional_slots: Any other relevant information NOT in required list
3. Sentiment analysis: Calculate sentiment_score between -1.0 (negative) and 1.0 (positive).
   - Positive: earnings improvement (실적 개선), new contracts (신규 계약), technological innovation (기술 혁신), positive outlook (긍정적 전망), etc.
   - Negative: earnings deterioration (실적 악화), increased risks (리스크 증가), negative outlook (부정적 전망), regulatory tightening (규제 강화), etc.
   - Neutral: close to 0

[EVENT ONTOLOGY]
{json.dumps(ontology["events"], ensure_ascii=False, indent=2)}

Output must be in JSON format only."""

    user_prompt = f"""Analyze the following Korean news/event text.

News information:
- Text: {event.strip()}

Output only in the following JSON format (no other explanation, JSON only):
{{
  "event_type": "<string>",  // One of {event_types}, or "OTHER" if none applies. Must match exactly.
  "corp_name": "<string>",  // Korean company name exactly as it appears in the text (e.g., "삼성전자"). Use null if not mentioned.
  "required_slots": {{ "<slot_name>": "<value>", ... }},  // ONLY slots in ontology's "required" list for chosen event_type
  "optional_slots": {{ "<slot_name>": "<value>", ... }},  // Any other relevant info NOT in required list
  "summary": "<string>",  // Key summary in 1 sentence
  "sentiment_score": <float>,  // Real number between -1.0 (negative) and 1.0 (positive)
  "reported_by": "<string>",  // Source identifier (e.g., "DART", "연합뉴스")
  "reported_at": "<string>"  // Date in YYYY-MM-DD format
}}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=600,
    )

    content = resp.choices[0].message.content
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM response: {exc}") from exc

    required_slots = data.get("required_slots") or {}
    optional_slots = data.get("optional_slots") or {}

    if "sentiment_score" not in data:
        raise ValueError("sentiment_score is required but not found in LLM response")
    sentiment_score = float(data["sentiment_score"])
    if not (-1.0 <= sentiment_score <= 1.0):
        raise ValueError(
            f"sentiment_score must be a number between -1.0 and 1.0, got: {sentiment_score}"
        )

    event_type = data.get("event_type")
    if event_type not in ONTOLOGY.event_map:
        event_type = "OTHER"

    corp_name = (data.get("corp_name") or required_slots.get("corp_name") or "").strip()
    if not corp_name:
        raise ValueError("corp_name is required but not found in LLM response")
    data["corp_name"] = corp_name
    data["event_type"] = event_type
    data["sentiment_score"] = sentiment_score
    data["required_slots"] = required_slots
    data["optional_slots"] = optional_slots

    if date := required_slots.get("date"):
        data["date"] = date

    logger.info(f"Event: {data}")
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m stockelper_kg.graph.event <path/to/textfile>")
        raise SystemExit(1)

    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    result = classify_event(path.read_text(encoding="utf-8"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
