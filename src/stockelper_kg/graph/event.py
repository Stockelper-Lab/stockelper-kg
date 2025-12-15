from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from .ontology import ONTOLOGY, build_ontology_prompts
from .payload import _normalize_corp_names

load_dotenv()

client = OpenAI()
logger = logging.getLogger(__name__)


def classify_events(text: str, model: str = "gpt-4o-mini") -> list[dict[str, Any]]:
    if not text or not text.strip():
        raise ValueError("event text is empty")

    ontology = build_ontology_prompts(detail="full")
    event_types = ", ".join(ONTOLOGY.event_map.keys())

    system_prompt = f"""You are a financial news event classification expert specializing in Korean stock market news.
Detect all distinct financial news/events in the text and extract structured slots.

Task:
1) Identify every separate event mentioned (a document may contain multiple events).
2) For each event, extract ALL participating company names in corp_names (list).
3) Fill required_slots using ONLY the ontology's required fields for that event_type.
4) Fill optional_slots with any other factual details.
5) Calculate sentiment_score between -1.0 (negative) and 1.0 (positive) for each event.

[EVENT ONTOLOGY]
{json.dumps(ontology["events"], ensure_ascii=False, indent=2)}

Output must be in JSON format only."""

    user_prompt = f"""Analyze the following Korean news/event text.

Output only in the following JSON format (no other explanation, JSON only):
{{
  "events": [
    {{
      "event_type": "{event_types} (or OTHER if none applies)",
      "corp_names": ["Company A", "Company B"],
      "summary": "Maximum 3 sentence summary for this event only. and explain reason of sentiment score",
      "required_slots": {{ ONLY slots in ontology's "required" list for chosen event_type}},
      "optional_slots": {{ "product_id": "...", ... }},
      "sentiment_score": -1.0(negative) ~ +1.0(positive),
      "reported_by": "YYYY-MM-DD",
      "reported_at": "<string>"
    }}
  ]
}}
- events array MUST NOT be empty. If no clear event, return one OTHER event with best-effort fields.
- corp_names MUST include every company involved in that event (list, no duplicates).

News information:
{text.strip()}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=1200,
    )

    events = _parse_events_response(resp.choices[0].message.content)
    logger.info("Extracted %d event(s)", len(events))
    return events


def _parse_events_response(content: str) -> list[dict[str, Any]]:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if len(lines) > 2 else content
        content = content.lstrip("json").strip()

    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        preview = content[:200] + "..." if len(content) > 200 else content
        logger.error("Failed to parse JSON. Preview: %s", preview)
        raise ValueError(f"Failed to parse LLM response: {exc}") from exc

    events = payload.get("events") or payload.get("event")
    if isinstance(events, dict):
        events = [events]
    if not isinstance(events, list) or not events:
        raise ValueError("LLM response did not include any events")

    normalized: list[dict[str, Any]] = []
    for idx, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise ValueError(f"Event #{idx} is not an object")
        normalized.append(_normalize_event_dict(event, idx))
    return normalized


def _normalize_event_dict(raw: dict[str, Any], idx: int) -> dict[str, Any]:
    data = dict(raw)
    data["required_slots"] = (
        data["required_slots"] if isinstance(data.get("required_slots"), dict) else {}
    )
    data["optional_slots"] = (
        data["optional_slots"] if isinstance(data.get("optional_slots"), dict) else {}
    )

    if "sentiment_score" not in data:
        raise ValueError(f"sentiment_score is required but missing in event #{idx}")
    sentiment_score = float(data["sentiment_score"])
    if not (-1.0 <= sentiment_score <= 1.0):
        raise ValueError(
            f"sentiment_score must be between -1.0 and 1.0, got: {sentiment_score} in event #{idx}"
        )
    data["sentiment_score"] = sentiment_score

    etype = (data.get("event_type") or "OTHER").strip().upper()
    if etype not in ONTOLOGY.event_map:
        etype = "OTHER"
    data["event_type"] = etype

    names: list[str] = []
    for source in (
        data.get("corp_names"),
        data.get("required_slots", {}).get("corp_names"),
        data.get("optional_slots", {}).get("corp_names"),
    ):
        if isinstance(source, list):
            names.extend(source)
    corp_names = _normalize_corp_names(names)
    data["corp_names"] = corp_names

    if date := data["required_slots"].get("date"):
        data["date"] = date

    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m stockelper_kg.graph.event <path/to/textfile>")
        raise SystemExit(1)

    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    text = path.read_text(encoding="utf-8")
    result = classify_events(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
