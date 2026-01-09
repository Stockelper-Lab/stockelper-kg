"""MongoDB -> Neo4j KG loader CLI.

Loads MongoDB collections produced by `stockelper-airflow` into the Neo4j KG
using the existing ontology-compatible node/edge pattern.

Collections:
- competitors: competitor relationships (Wisereport crawl)
- report: stock research reports (FnGuide report summary crawl)

This CLI intentionally requires only:
- Neo4j env vars (NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD)
- Mongo env vars (DB_URI/DB_NAME)

It does NOT require DART/KIS keys.
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv
from pymongo import MongoClient
from tqdm import tqdm

from .config import Neo4jConfig
from .graph import Neo4jClient
from .utils.dates import normalize_date

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _get_required_env(key: str) -> str:
    value = os.getenv(key)
    if value is None or str(value).strip() == "":
        raise ValueError(f"Required environment variable {key} is not set")
    return str(value)


def _zfill_stock_code(code: str) -> str:
    code = (code or "").strip()
    if code.isdigit():
        return code.zfill(6)
    return code


def _date_parts(date_iso: str) -> dict[str, Any]:
    try:
        dt = datetime.strptime(date_iso, "%Y-%m-%d")
        return {"date": date_iso, "year": dt.year, "month": dt.month, "day": dt.day}
    except Exception:  # noqa: BLE001
        return {"date": date_iso}


def _parse_goal_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except Exception:  # noqa: BLE001
        return None


def load_competitors(
    *,
    neo4j: Neo4jClient,
    mongo_db,
    collection_name: str,
    batch_size: int,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load competitors collection -> (:Company)-[:IS_COMPETITOR]->(:Company)."""
    col = mongo_db[collection_name]
    cursor = col.find()
    if limit:
        cursor = cursor.limit(int(limit))

    cypher = """
    UNWIND $rows AS row
    MERGE (a:Company {stock_code: row.src})
    SET a.corp_name = coalesce(a.corp_name, row.src_name),
        a.updated_at = datetime()
    MERGE (b:Company {stock_code: row.dst})
    SET b.corp_name = coalesce(b.corp_name, row.dst_name),
        b.updated_at = datetime()
    MERGE (a)-[:IS_COMPETITOR]->(b)
    MERGE (b)-[:IS_COMPETITOR]->(a)
    """

    rows: list[dict[str, Any]] = []
    loaded_pairs = 0

    for doc in cursor:
        src = _zfill_stock_code(str(doc.get("_id") or ""))
        if not src:
            continue

        target = doc.get("target_company") if isinstance(doc.get("target_company"), dict) else {}
        src_name = (str(target.get("name") or "").strip() or None)

        competitors = doc.get("competitors")
        if not isinstance(competitors, list) or not competitors:
            continue

        for comp in competitors:
            if not isinstance(comp, dict):
                continue
            dst = _zfill_stock_code(str(comp.get("code") or ""))
            if not dst or dst == src:
                continue
            dst_name = (str(comp.get("name") or "").strip() or None)
            rows.append({"src": src, "src_name": src_name, "dst": dst, "dst_name": dst_name})

            if len(rows) >= int(batch_size):
                neo4j.execute_query_with_params(cypher, {"rows": rows})
                loaded_pairs += len(rows)
                rows = []

    if rows:
        neo4j.execute_query_with_params(cypher, {"rows": rows})
        loaded_pairs += len(rows)

    return {"collection": collection_name, "loaded_competitor_pairs": loaded_pairs}


def load_reports(
    *,
    neo4j: Neo4jClient,
    mongo_db,
    collection_name: str,
    batch_size: int,
    date_st: str | None = None,
    date_fn: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Load report collection -> Event/Document pattern.

    - Document.rcept_no: RPT_{mongo_id}
    - Event.event_id: EVT_{Document.rcept_no}
    - Event.type: REPORT
    """
    col = mongo_db[collection_name]

    start_iso = normalize_date(date_st) if date_st else None
    end_iso = normalize_date(date_fn) if date_fn else None

    query: dict[str, Any] = {}
    if start_iso or end_iso:
        cond: dict[str, Any] = {}
        if start_iso:
            cond["$gte"] = start_iso
        if end_iso:
            cond["$lte"] = end_iso
        query["date"] = cond

    cursor = col.find(query).sort([("date", 1), ("code", 1), ("company", 1)])
    if limit:
        cursor = cursor.limit(int(limit))

    cypher = """
    UNWIND $rows AS row
    // Company
    MERGE (c:Company {stock_code: row.stock_code})
    SET c.corp_name = coalesce(c.corp_name, row.corp_name),
        c.updated_at = datetime()

    // Dates
    MERGE (d:Date {date: row.date})
    SET d.year = row.year, d.month = row.month, d.day = row.day
    MERGE (ed:EventDate {date: row.date})
    SET ed.year = row.year, ed.month = row.month, ed.day = row.day
    MERGE (ed)-[:IS_DATE]->(d)
    MERGE (c)-[:ON_DATE]->(d)

    // Document
    MERGE (doc:Document {rcept_no: row.rcept_no})
    SET doc.report_nm = coalesce(doc.report_nm, row.report_nm),
        doc.rcept_dt = row.rcept_dt,
        doc.url = coalesce(doc.url, ''),
        doc.body = row.body,
        doc.source = row.source,
        doc.provider = row.provider,
        doc.opinion = row.opinion,
        doc.goal_price = row.goal_price,
        doc.updated_at = datetime()

    // Event
    MERGE (e:Event {event_id: row.event_id})
    SET e.type = row.event_type,
        e.source = row.source,
        e.summary = row.body,
        e.report_provider = row.provider,
        e.opinion = row.opinion,
        e.goal_price = row.goal_price,
        e.stock_code = row.stock_code,
        e.updated_at = datetime()

    // Relationships
    MERGE (c)-[:INVOLVED_IN]->(e)
    MERGE (e)-[:REPORTED_BY]->(doc)
    MERGE (e)-[:OCCURRED_ON]->(ed)
    """

    rows: list[dict[str, Any]] = []
    loaded = 0

    for doc in cursor:
        date_iso = normalize_date(doc.get("date"))
        if not date_iso:
            continue
        stock_code = _zfill_stock_code(str(doc.get("code") or ""))
        if not stock_code:
            continue

        corp_name = (str(doc.get("company") or "").strip() or None)
        summary = str(doc.get("summary") or "").strip()
        provider = (str(doc.get("provider") or "").strip() or None)
        opinion = (str(doc.get("opinion") or "").strip() or None)
        goal_price = _parse_goal_price(doc.get("goal_price"))

        mongo_id = str(doc.get("_id"))
        rcept_no = f"RPT_{mongo_id}"
        event_id = f"EVT_{rcept_no}"

        parts = _date_parts(date_iso)
        rows.append(
            {
                "event_id": event_id,
                "event_type": "REPORT",
                "source": "REPORT",
                "rcept_no": rcept_no,
                "report_nm": provider or "REPORT",
                "rcept_dt": date_iso,
                "date": parts["date"],
                "year": parts.get("year"),
                "month": parts.get("month"),
                "day": parts.get("day"),
                "stock_code": stock_code,
                "corp_name": corp_name,
                "provider": provider,
                "opinion": opinion,
                "goal_price": goal_price,
                "body": summary,
            }
        )

        if len(rows) >= int(batch_size):
            neo4j.execute_query_with_params(cypher, {"rows": rows})
            loaded += len(rows)
            rows = []

    if rows:
        neo4j.execute_query_with_params(cypher, {"rows": rows})
        loaded += len(rows)

    return {
        "collection": collection_name,
        "start_date": start_iso,
        "end_date": end_iso,
        "loaded_reports": loaded,
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Load MongoDB competitors/report into Neo4j KG.")
    p.add_argument("--env", type=str, default=".env", help="Path to .env file (default: .env)")
    p.add_argument(
        "--competitors",
        action="store_true",
        help="Load competitor relationships from MongoDB",
    )
    p.add_argument(
        "--reports",
        action="store_true",
        help="Load research reports from MongoDB",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Load both competitors and reports (default if no flags are set)",
    )
    p.add_argument(
        "--competitors-collection",
        type=str,
        default=None,
        help="MongoDB collection name for competitors (default: DB_COLLECTION_NAME or 'competitors')",
    )
    p.add_argument(
        "--reports-collection",
        type=str,
        default="report",
        help="MongoDB collection name for reports (default: report)",
    )
    p.add_argument(
        "--report-date-st",
        type=str,
        default=None,
        help="Optional report start date filter (YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD)",
    )
    p.add_argument(
        "--report-date-fn",
        type=str,
        default=None,
        help="Optional report end date filter (YYYYMMDD / YYYY-MM-DD / YYYY/MM/DD)",
    )
    p.add_argument("--batch-size", type=int, default=2000, help="UNWIND batch size (default: 2000)")
    p.add_argument("--limit", type=int, default=None, help="Optional limit for debugging")
    return p


def cli(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    # Determine what to load
    load_all = bool(args.all) or (not args.competitors and not args.reports)
    load_comp = bool(args.competitors) or load_all
    load_rep = bool(args.reports) or load_all

    # Load env file (only for this CLI)
    load_dotenv(dotenv_path=args.env)

    neo4j_cfg = Neo4jConfig(
        uri=_get_required_env("NEO4J_URI"),
        user=_get_required_env("NEO4J_USER"),
        password=_get_required_env("NEO4J_PASSWORD"),
    )
    mongo_uri = _get_required_env("DB_URI")
    mongo_db_name = _get_required_env("DB_NAME")

    competitor_collection = (
        args.competitors_collection
        or (os.getenv("DB_COLLECTION_NAME") or "").strip()
        or "competitors"
    )
    reports_collection = str(args.reports_collection or "report").strip() or "report"

    # Connect
    logger.info("Connecting to Neo4j: %s", neo4j_cfg.uri)
    neo4j = Neo4jClient(neo4j_cfg)
    neo4j.ensure_constraints()

    logger.info("Connecting to MongoDB: db=%s", mongo_db_name)
    mongo = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    mongo.admin.command("ping")
    db = mongo[mongo_db_name]

    try:
        results: list[dict[str, Any]] = []

        if load_rep:
            logger.info("Loading reports from MongoDB collection=%s", reports_collection)
            results.append(
                load_reports(
                    neo4j=neo4j,
                    mongo_db=db,
                    collection_name=reports_collection,
                    batch_size=int(args.batch_size),
                    date_st=args.report_date_st,
                    date_fn=args.report_date_fn,
                    limit=args.limit,
                )
            )

        if load_comp:
            logger.info("Loading competitors from MongoDB collection=%s", competitor_collection)
            results.append(
                load_competitors(
                    neo4j=neo4j,
                    mongo_db=db,
                    collection_name=competitor_collection,
                    batch_size=int(args.batch_size),
                    limit=args.limit,
                )
            )

        logger.info("MongoDB -> Neo4j load completed: %s", results)
        try:
            neo4j.get_node_count()
        except Exception:  # noqa: BLE001
            pass
        return 0
    finally:
        try:
            mongo.close()
        except Exception:  # noqa: BLE001
            pass
        neo4j.close()


if __name__ == "__main__":
    raise SystemExit(cli())

