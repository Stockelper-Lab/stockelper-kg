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
    if not event or not event.strip():
        raise ValueError("event text is empty")

    ontology = build_ontology_prompts(detail="full")
    event_types = ", ".join(ONTOLOGY.event_map.keys())
    prompt = f"""
Classify financial news/events into ontology event types and extract slots.

[EVENT ONTOLOGY]
{ontology["events"]}

Task:
1. Extract event_type and corp_name from text (REQUIRED - must be in output root).
2. Fill required_slots: ONLY slots in ontology's "required" list for chosen event_type.
3. Fill optional_slots: Any other relevant info NOT in ontology's required list.

[INPUT TEXT]
{event.strip()}

[OUTPUT JSON SCHEMA]
{{
  "event_type": "{event_types}, or OTHER if none applies",
  "corp_name": "Company name (REQUIRED - extract from text)",
  "summary": "Key summary (1 sentence)",
  "required_slots": {{ "date": "...", ... }},
  "optional_slots": {{ "product_id": "...", ... }},
  "reported_by": "YYYY-MM-DD",
  "reported_at": "..."
}}
"""

    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=600,
    )

    try:
        data = json.loads(resp.choices[0].message.content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Failed to parse LLM response: {exc}") from exc

    data.setdefault("required_slots", {})
    data.setdefault("optional_slots", {})

    etype = data.get("event_type") or "OTHER"
    if etype not in ONTOLOGY.event_map:
        etype = "OTHER"
    data["event_type"] = etype

    corp_name = (
        data.get("corp_name") or data["required_slots"].get("corp_name") or ""
    ).strip()
    if not corp_name:
        raise ValueError("corp_name is required but not found in LLM response")
    data["corp_name"] = corp_name
    if date := data["required_slots"].get("date"):
        data["date"] = date

    logger.info(f"Event: {data}")
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m stockelper_kg.graph.event <path/to/textfile>")
        raise SystemExit(1)

    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        print(f"File not found: {path}")
        raise SystemExit(1)

    text = path.read_text(encoding="utf-8")
    result = classify_event(text)
    print(json.dumps(result, ensure_ascii=False, indent=2))
