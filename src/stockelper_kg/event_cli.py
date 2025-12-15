"""CLI entry point for the news/event pipeline."""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import Config
from .graph import Neo4jClient
from .pipeline import EventPipeline

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EventInput:
    """Container for a single event text and its metadata."""

    identifier: str
    text: str
    metadata: Dict[str, Any]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Classify news events and upsert them into Neo4j."
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", type=str, help="Path to a single text file")
    src.add_argument(
        "--dir",
        dest="directory",
        type=str,
        help="Directory containing *.txt files (recursive)",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=".env",
        help="Path to the .env file with API/DB credentials (default: .env)",
    )
    return parser


def _read_text_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _collect_from_file(path_str: str) -> List[EventInput]:
    path = Path(path_str).expanduser().resolve()
    text = _read_text_file(path)
    meta = {"source": "file", "path": str(path), "filename": path.name}
    return [EventInput(str(path), text, meta)]


def _collect_from_directory(dir_str: str) -> List[EventInput]:
    root = Path(dir_str).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Directory not found: {root}")
    files = sorted(p for p in root.rglob("*.txt") if p.is_file())
    if not files:
        raise ValueError(f"No *.txt files found under {root}")
    inputs: List[EventInput] = []
    for path in files:
        text = _read_text_file(path)
        meta = {"source": "dir", "path": str(path), "filename": path.name}
        inputs.append(EventInput(str(path), text, meta))
    return inputs


def _collect_inputs(args: argparse.Namespace) -> List[EventInput]:
    if args.file:
        return _collect_from_file(args.file)
    if getattr(args, "directory", None):
        return _collect_from_directory(args.directory)
    return []


def _run_pipeline(
    pipeline: EventPipeline, items: List[EventInput]
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    total = len(items)
    for idx, item in enumerate(items, start=1):
        logger.info("[%d/%d] Processing %s", idx, total, item.identifier)
        try:
            event_results = pipeline.process(item.text, metadata=item.metadata)
            if not isinstance(event_results, list):
                event_results = [event_results]
            if not event_results:
                results.append(
                    {
                        "source": item.identifier,
                        "success": False,
                        "metadata": item.metadata,
                        "error": "No events returned",
                    }
                )
                continue

            total_events = len(event_results)
            for event_idx, event_data in enumerate(event_results, start=1):
                event_type = event_data.get("event_type", "UNKNOWN")
                corps = event_data.get("corp_names")
                corps_list = corps if isinstance(corps, list) else []
                corp_label = ", ".join([c for c in corps_list if c]) or "UNKNOWN"
                logger.info(
                    "[%s] ✓ event %d/%d type=%s corps=%s",
                    item.identifier,
                    event_idx,
                    total_events,
                    event_type,
                    corp_label,
                )
                results.append(
                    {
                        "source": item.identifier,
                        "success": True,
                        "event_index": event_idx,
                        "event_count": total_events,
                        "event_type": event_type,
                        "corps": corps_list,
                        "metadata": item.metadata,
                        "result": event_data,
                    }
                )
        except Exception as exc:
            logger.exception("[%s] ✗ processing failed", item.identifier)
            results.append(
                {
                    "source": item.identifier,
                    "success": False,
                    "metadata": item.metadata,
                    "error": str(exc),
                }
            )
    return results


def cli(argv: Optional[Iterable[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    inputs = _collect_inputs(args)
    if not inputs:
        parser.error("No inputs were collected. Check your arguments.")

    config = Config.from_env(args.env)
    setattr(config, "env_path", args.env)

    client: Optional[Neo4jClient] = None
    try:
        client = Neo4jClient(config.neo4j)
        client.ensure_constraints()
        pipeline = EventPipeline(config, client)
        report_rows = _run_pipeline(pipeline, inputs)
    finally:
        if client:
            client.close()

    failures = [row for row in report_rows if not row.get("success")]
    if failures:
        failed_sources = ", ".join(row["source"] for row in failures)
        logger.error("Processing completed with failures: %s", failed_sources)
        raise SystemExit(1)

    logger.info("All events processed successfully.")
    return 0


if __name__ == "__main__":
    cli()
