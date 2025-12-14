"""Graph database builder."""

from __future__ import annotations

import json
import logging
import math
from datetime import date as date_cls, datetime as datetime_cls
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd

from .client import Neo4jClient
from .cypher import payload_to_cypher
from .payload import build_competitor_payload, build_stock_snapshot_payload
from ..utils.dates import normalize_date

logger = logging.getLogger(__name__)


class GraphBuilder:
    """Builds knowledge graph from collected data."""

    COMPANY_FIELDS: Tuple[str, ...] = (
        "stock_code",
        "stock_nm",
        "stock_abbrv",
        "stock_nm_eng",
        "listing_dt",
        "market_nm",
        "outstanding_shares",
        "kospi200_item_yn",
        "capital_stock",
        "corp_code",
        "corp_name",
        "corp_cls",
        "std_idst_clsf_cd_name",
    )
    PRICE_FIELDS: Tuple[str, ...] = (
        "stock_code",
        "stck_hgpr",
        "stck_lwpr",
        "stck_oprc",
        "stck_clpr",
        "stck_prpr",
    )
    FINANCIAL_FIELDS: Tuple[str, ...] = (
        "stock_code",
        "revenue",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "capital_stock",
        "year",
        "quarter",
        "reported_date",
    )
    INDICATOR_FIELDS: Tuple[str, ...] = ("stock_code", "eps", "pbr", "per")

    def __init__(self, client: Neo4jClient):
        """Initialize graph builder.

        Args:
            client: Neo4j client instance
        """
        self.client = client

    def build_stock_data(
        self, graph_df: pd.DataFrame, stock_code: str, dates: List[str]
    ) -> List[str]:
        """Build Cypher queries for stock data."""
        filter_df = graph_df[graph_df["stock_code"] == stock_code]
        if filter_df.empty:
            logger.warning(f"No data found for stock_code: {stock_code}")
            return []

        base_record = filter_df.iloc[0].to_dict()
        company_props = self._prepare_company_properties(base_record)
        financials = self._extract_financials(base_record)

        normalized_dates = [d for d in (normalize_date(value) for value in dates) if d]
        if not normalized_dates:
            logger.warning(
                "No valid dates supplied for %s; skipping snapshot generation",
                stock_code,
            )
            return []

        if "date" not in filter_df.columns:
            logger.warning(
                "Input dataframe for %s has no 'date' column; cannot align price data",
                stock_code,
            )
            return []

        queries: List[str] = []
        normalized_date_series = filter_df["date"].apply(normalize_date)

        for date in normalized_dates:
            date_df = filter_df[normalized_date_series == date]
            if date_df.empty:
                logger.warning(
                    f"No data for {company_props.get('stock_nm', stock_code)} "
                    f"({stock_code}) on date {date}"
                )
                continue

            snapshot_record = date_df.iloc[0].to_dict()
            stock_price = self._select_fields(snapshot_record, self.PRICE_FIELDS)
            stock_price.setdefault("stock_code", stock_code)
            stock_price["traded_at"] = date
            stock_price["date"] = date
            stock_price = self._align_price_fields(stock_price)

            indicators = self._extract_indicators(snapshot_record, date)
            fs_snapshot = self._prepare_financial_snapshot(financials, date)

            payload = build_stock_snapshot_payload(
                company=company_props,
                date=date,
                stock_price=stock_price,
                financials=fs_snapshot,
                indicators=indicators,
            )
            queries.append(payload_to_cypher(payload))

        return queries

    def build_competitor_data(
        self, graph_df: pd.DataFrame, stock_code: str
    ) -> List[str]:
        """Build Cypher queries for competitor relationships."""
        src_df = graph_df[graph_df["stock_code"] == stock_code]
        if src_df.empty:
            return []

        src_company = self._prepare_company_properties(src_df.iloc[0].to_dict())
        compete_code_list = self._extract_competitors(src_df)
        if not compete_code_list:
            return []

        queries: List[str] = []
        for target_code in compete_code_list:
            if stock_code == target_code:
                continue

            dst_df = graph_df[graph_df["stock_code"] == target_code]
            if dst_df.empty:
                logger.warning(f"Competitor {target_code} not found in data")
                continue

            dst_company = self._prepare_company_properties(dst_df.iloc[0].to_dict())
            payload = build_competitor_payload(src_company, dst_company)
            queries.append(payload_to_cypher(payload))

        return queries

    def build_graph(self, graph_df: pd.DataFrame, stock_code: str, dates: List[str]):
        """Build complete graph for a stock."""
        queries = []
        queries.extend(self.build_stock_data(graph_df, stock_code, dates))
        queries.extend(self.build_competitor_data(graph_df, stock_code))

        if queries:
            self.client.execute_queries(queries)

    def _select_fields(
        self, record: Dict[str, Any], fields: Iterable[str]
    ) -> Dict[str, Any]:
        """Select and sanitise a subset of fields from a record."""
        result: Dict[str, Any] = {}
        for key in fields:
            if key not in record:
                continue
            value = self._normalise_value(record[key])
            if value is None:
                continue
            result[key] = value
        return result

    def _prepare_company_properties(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure Company nodes carry consistent identity properties."""
        props = self._select_fields(record, self.COMPANY_FIELDS)
        fallback_name = next(
            (
                val
                for val in (
                    props.get("corp_name"),
                    record.get("corp_name"),
                    props.get("stock_nm"),
                    record.get("stock_nm"),
                    props.get("stock_abbrv"),
                    record.get("stock_abbrv"),
                )
                if val
            ),
            None,
        )
        normalised_name = self._normalise_value(fallback_name)
        if normalised_name:
            props.setdefault("corp_name", normalised_name)
            props.setdefault("stock_nm", normalised_name)
        return props

    def _align_price_fields(self, price: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure both legacy and canonical price keys are present."""
        if "stck_prpr" not in price and (close := price.get("stck_clpr")) is not None:
            price["stck_prpr"] = close
        if "stck_clpr" not in price and (present := price.get("stck_prpr")) is not None:
            price["stck_clpr"] = present
        return price

    def _normalise_value(self, value: Any) -> Any:
        """Normalise pandas/numpy-friendly values into JSON-safe scalars."""
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        if pd.isna(value):
            return None
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, (datetime_cls, date_cls)):
            return value.isoformat()
        if hasattr(value, "item") and not isinstance(value, (bytes, str)):
            return value.item()
        if isinstance(value, (pd.Series, pd.DataFrame)):
            return None
        return value

    def _extract_financials(self, record: Dict[str, Any]) -> Dict[str, Any] | None:
        """Extract financial statement properties."""
        data = self._select_fields(record, self.FINANCIAL_FIELDS)
        if not data:
            return None

        if "stock_code" not in data and record.get("stock_code"):
            data["stock_code"] = self._normalise_value(record["stock_code"])

        fiscal_year = data.pop("year", None)
        fiscal_period = data.pop("quarter", None)
        if fiscal_year is not None:
            data["fiscal_year"] = fiscal_year
        if fiscal_period is not None:
            data["fiscal_period"] = str(fiscal_period)
        return data

    def _extract_indicators(
        self, record: Dict[str, Any], as_of: str
    ) -> Dict[str, Any] | None:
        """Extract indicator metrics for the given snapshot."""
        data = self._select_fields(record, self.INDICATOR_FIELDS)
        if not data:
            return None
        if "stock_code" not in data and record.get("stock_code"):
            data["stock_code"] = self._normalise_value(record["stock_code"])
        canonical = normalize_date(as_of)
        if canonical:
            data["as_of"] = canonical
        return data

    def _extract_competitors(self, df: pd.DataFrame) -> List[str]:
        """Return a normalised list of competitor stock codes."""
        if df.empty or "compete_code_li" not in df.columns:
            return []

        raw_value = df["compete_code_li"].iloc[0]
        if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
            return []

        if isinstance(raw_value, list):
            return [str(code).strip() for code in raw_value if code]

        if isinstance(raw_value, str):
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return [str(code).strip() for code in parsed if code]

        return []

    def _prepare_financial_snapshot(
        self, financials: Dict[str, Any] | None, as_of: str
    ) -> Dict[str, Any] | None:
        """Attach a reporting date to financial statements per snapshot."""
        if not financials:
            return None
        snapshot = dict(financials)
        explicit_reported = normalize_date(snapshot.get("reported_date"))
        canonical_as_of = normalize_date(as_of)
        reported = explicit_reported or canonical_as_of
        if reported:
            snapshot["reported_date"] = reported
        return snapshot
