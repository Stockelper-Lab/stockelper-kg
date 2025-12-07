"""CLI entry point for the news/event pipeline."""

from __future__ import annotations

import argparse
import json
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
    src.add_argument(
        "--dataset",
        type=str,
        help="JSONL dataset where each line is an event record",
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


def _collect_from_dataset(dataset_str: str) -> List[EventInput]:
    dataset_path = Path(dataset_str).expanduser().resolve()
    if not dataset_path.is_file():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    inputs: List[EventInput] = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for idx, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{dataset_path}:{idx} is not valid JSON: {exc}"
                ) from exc

            text = record.get("content") or record.get("text")
            content_file = record.get("content_file")
            if not text and content_file:
                file_path = Path(content_file)
                if not file_path.is_absolute():
                    file_path = (dataset_path.parent / file_path).resolve()
                text = _read_text_file(file_path)
            if not text:
                raise ValueError(
                    f"{dataset_path}:{idx} missing 'content' or 'content_file'."
                )

            extra_meta: Dict[str, Any] = {}
            if isinstance(record.get("metadata"), dict):
                extra_meta.update(record["metadata"])
            for key, value in record.items():
                if key in {"content", "content_file", "metadata", "text"}:
                    continue
                extra_meta.setdefault(key, value)
            if content_file:
                extra_meta.setdefault("content_file", content_file)

            identifier = (
                record.get("description")
                or record.get("url")
                or f"{dataset_path.name}:{idx}"
            )

            inputs.append(EventInput(str(identifier), text, extra_meta))

    if not inputs:
        raise ValueError(f"{dataset_path} did not yield any records.")
    return inputs


def _collect_inputs(args: argparse.Namespace) -> List[EventInput]:
    if args.file:
        return _collect_from_file(args.file)
    if getattr(args, "directory", None):
        return _collect_from_directory(args.directory)
    if args.dataset:
        return _collect_from_dataset(args.dataset)
    return []


def _run_pipeline(
    pipeline: EventPipeline, items: List[EventInput]
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    total = len(items)
    for idx, item in enumerate(items, start=1):
        logger.info("[%d/%d] Processing %s", idx, total, item.identifier)
        try:
            event_data = pipeline.process(item.text, metadata=item.metadata)
            event_type = event_data.get("event_type", "UNKNOWN")
            logger.info("[%s] ✓ event_type=%s", item.identifier, event_type)
            results.append(
                {
                    "source": item.identifier,
                    "success": True,
                    "event_type": event_type,
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
