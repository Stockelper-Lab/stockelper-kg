"""Event-driven data collector for knowledge graph construction."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

from .dart import DartCollector
from .kis import KISCollector
from .krx import KRXCollector
from .mongodb import MongoDBCollector

logger = logging.getLogger(__name__)

_PRICE_COLUMNS = (
    "stck_hgpr",
    "stck_lwpr",
    "stck_oprc",
    "stck_clpr",
    "stck_prpr",
    "eps",
    "pbr",
    "per",
)


@dataclass
class EventCollector:
    """Collects and merges stock data for event-driven processing."""

    dart: DartCollector
    kis: KISCollector
    krx: KRXCollector
    competitors: MongoDBCollector | None = None

    _stock_map: dict[str, str] = field(default_factory=dict, init=False)
    _competitor_map: dict[str, list[str]] = field(default_factory=dict, init=False)
    _krx_df: pd.DataFrame | None = field(default=None, init=False)

    def resolve(self, corp_name: str) -> str | None:
        """Resolve corp_name to stock code."""
        self._ensure_stock_map()
        return self._stock_map.get(corp_name)

    def collect(self, stock_code: str, date: str) -> pd.DataFrame:
        """Collect and merge all stock data for given code and date."""
        date_clean = date.replace("-", "")

        codes = [stock_code, *self._get_competitors(stock_code)]
        krx_df = self._filter_krx(codes)
        if krx_df.empty:
            return pd.DataFrame()

        krx_df = krx_df.copy()
        krx_df["compete_code_li"] = [
            self._get_competitors(c) for c in krx_df["stock_code"]
        ]

        company_df = self.kis.collect_company_info(stock_code)
        if company_df is None:
            logger.warning("[%s] No company info", stock_code)
            company_df = pd.DataFrame([{"stock_code": stock_code}])

        price_df = self.kis.collect_price_info(stock_code, date_clean, date_clean)
        if price_df is None:
            price_df = self._fill_price_info(stock_code, date_clean)

        fs_df = self.dart.collect_financial_statement(stock_code, date_clean)

        return (
            krx_df.merge(company_df, on="stock_code", how="left")
            .merge(price_df, on="stock_code", how="left")
            .merge(fs_df, on="stock_code", how="left")
        )

    def _ensure_stock_map(self) -> None:
        if self._stock_map:
            return
        logger.info("Building stock code map from KRX...")
        df = self._get_krx()
        self._stock_map = {
            **dict(zip(df["stock_nm"], df["stock_code"])),
            **dict(zip(df["stock_abbrv"], df["stock_code"])),
        }

    def _ensure_competitor_map(self) -> None:
        if self._competitor_map:
            return

        if not self.competitors:
            return

        df = self.competitors.collect()
        if df.empty:
            return

        for row in df.to_dict("records"):
            code = str(row.get("stock_code", "")).strip()
            if code:
                rivals = row.get("compete_code_li") or []
                self._competitor_map[code] = [
                    str(v).strip() for v in rivals if str(v).strip()
                ]

    def _get_krx(self) -> pd.DataFrame:
        if self._krx_df is None:
            self._krx_df = self.krx.collect()
        return self._krx_df

    def _filter_krx(self, codes: list[str]) -> pd.DataFrame:
        df = self._get_krx()
        return df[df["stock_code"].isin(codes)]

    def _get_competitors(self, stock_code: str) -> list[str]:
        self._ensure_competitor_map()
        return self._competitor_map.get(stock_code, [])

    def _fill_price_info(self, stock_code: str, date: str) -> pd.DataFrame:
        return pd.DataFrame(
            [{"stock_code": stock_code, "date": date, **{c: 0 for c in _PRICE_COLUMNS}}]
        )
