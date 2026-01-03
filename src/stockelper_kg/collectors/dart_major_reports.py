"""DART 36 major report type collector (structured endpoints) -> Local PostgreSQL.

Updated strategy (2026-01-03):
- Use 36 'major report' endpoints (structured JSON) instead of generic list/document parsing.
- Store to Local PostgreSQL (not remote AWS).
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any

import requests
from sqlalchemy import Column, Date, DateTime, MetaData, String, Table, Text, create_engine
from sqlalchemy.dialects.postgresql import JSONB, insert

OPENDART_BASE_URL = "https://opendart.fss.or.kr/api"


def _camel_to_snake(name: str) -> str:
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def _yyyymmdd(dt: date | datetime | str) -> str:
    if isinstance(dt, datetime):
        return dt.strftime("%Y%m%d")
    if isinstance(dt, date):
        return dt.strftime("%Y%m%d")
    s = str(dt or "").strip()
    if len(s) == 10 and "-" in s:
        return s.replace("-", "")
    if len(s) == 8 and s.isdigit():
        return s
    raise ValueError(f"Invalid date: {dt!r}")


def _parse_rcept_dt(dt_yyyymmdd: str) -> date:
    s = _yyyymmdd(dt_yyyymmdd)
    return datetime.strptime(s, "%Y%m%d").date()


def _infer_rcept_dt(*, rcept_no: str, rcept_dt_raw: str | None) -> date:
    """Infer receipt date.

    Notes:
    - Some major report endpoints omit `rcept_dt` in their payload.
    - `rcept_no` starts with YYYYMMDD, so we can safely derive the date from it.
    """
    raw = (rcept_dt_raw or "").strip()
    if raw:
        try:
            return _parse_rcept_dt(raw)
        except Exception:  # noqa: BLE001
            pass

    prefix = (rcept_no or "")[:8]
    if prefix.isdigit():
        return _parse_rcept_dt(prefix)

    # Worst-case fallback: today (UTC)
    return datetime.utcnow().date()


class MajorReportType(Enum):
    """Major report endpoints (36 types).

    Each value is (endpoint, korean_name, category).
    Source: docs/references/DART(modified events).md (민우, 2026-01-03)
    """

    # 기업 상태 관련 (5)
    AST_INHTRF_ETC_PTBK_OPT = ("astInhtrfEtcPtbkOpt", "자산양수도(기타)_풋백옵션", "기업상태")
    DF_OCR = ("dfOcr", "부도발생", "기업상태")
    BSN_SP = ("bsnSp", "영업정지", "기업상태")
    CTRCVS_BGRQ = ("ctrcvsBgrq", "회생절차_개시신청", "기업상태")
    DS_RS_OCR = ("dsRsOcr", "해산사유_발생", "기업상태")

    # 증자/감자 관련 (4)
    PIIC_DECSN = ("piicDecsn", "유상증자_결정", "증자감자")
    FRIC_DECSN = ("fricDecsn", "무상증자_결정", "증자감자")
    PIFRIC_DECSN = ("pifricDecsn", "유무상증자_결정", "증자감자")
    CR_DECSN = ("crDecsn", "감자_결정", "증자감자")

    # 채권은행 관련 (2)
    EX_BNK_MNG_PCBG = ("exBnkMngPcbg", "채권은행_관리절차_개시", "채권은행")
    EX_BNK_MNG_PCSP = ("exBnkMngPcsp", "채권은행_관리절차_중단", "채권은행")

    # 소송 관련 (1)
    LWST_ETC_PRPS = ("lwstEtcPrps", "소송등_제기", "소송")

    # 해외 상장 관련 (4)
    OVSCS_MKT_LST_DECSN = ("ovscsMktLstDecsn", "해외증권시장_상장_결정", "해외상장")
    OVSCS_MKT_DLST_DECSN = ("ovscsMktDlstDecsn", "해외증권시장_상장폐지_결정", "해외상장")
    OVSCS_MKT_LST = ("ovscsMktLst", "해외증권시장_상장", "해외상장")
    OVSCS_MKT_DLST = ("ovscsMktDlst", "해외증권시장_상장폐지", "해외상장")

    # 사채 발행 관련 (4)
    CVBD_IS_DECSN = ("cvbdIsDecsn", "전환사채권_발행결정", "사채발행")
    BDWT_IS_DECSN = ("bdwtIsDecsn", "신주인수권부사채권_발행결정", "사채발행")
    EXBD_IS_DECSN = ("exbdIsDecsn", "교환사채권_발행결정", "사채발행")
    WOCCS_IS_DECSN = ("woccsIsDecsn", "상각형_조건부자본증권_발행결정", "사채발행")

    # 자기주식 관련 (4)
    TSSTK_AQ_DECSN = ("tsstkAqDecsn", "자기주식_취득_결정", "자기주식")
    TSSTK_DP_DECSN = ("tsstkDpDecsn", "자기주식_처분_결정", "자기주식")
    TSSTK_AQ_TRC_CTR_DECSN = ("tsstkAqTrcCtrDecsn", "자기주식취득_신탁계약_체결_결정", "자기주식")
    TSSTK_AQ_TRC_CTR_CC_DECSN = ("tsstkAqTrcCtrCcDecsn", "자기주식취득_신탁계약_해지_결정", "자기주식")

    # 영업양수도 관련 (2)
    BSN_INH_DECSN = ("bsnInhDecsn", "영업양수_결정", "영업양수도")
    BSN_TRF_DECSN = ("bsnTrfDecsn", "영업양도_결정", "영업양수도")

    # 자산양수도 관련 (2)
    TG_AST_INH_DECSN = ("tgAstInhDecsn", "유형자산_양수_결정", "자산양수도")
    TG_AST_TRF_DECSN = ("tgAstTrfDecsn", "유형자산_양도_결정", "자산양수도")

    # 타법인 주식 관련 (2)
    OTCPR_STK_INH_DECSN = ("otcprStkInhDecsn", "타법인주식_양수결정", "타법인주식")
    OTCPR_STK_TRF_DECSN = ("otcprStkTrfDecsn", "타법인주식_양도결정", "타법인주식")

    # 사채권 양수도 관련 (2)
    STK_RTBD_INH_DECSN = ("stkRtbdInhDecsn", "주권관련_사채권_양수_결정", "사채권양수도")
    STK_RTBD_TRF_DECSN = ("stkRtbdTrfDecsn", "주권관련_사채권_양도_결정", "사채권양수도")

    # 합병/분할 관련 (4)
    CMP_MG_DECSN = ("cmpMgDecsn", "회사합병_결정", "합병분할")
    CMP_DV_DECSN = ("cmpDvDecsn", "회사분할_결정", "합병분할")
    CMP_DVMG_DECSN = ("cmpDvmgDecsn", "회사분할합병_결정", "합병분할")
    STK_EXTR_DECSN = ("stkExtrDecsn", "주식교환이전_결정", "합병분할")

    @property
    def endpoint(self) -> str:
        return self.value[0]

    @property
    def korean_name(self) -> str:
        return self.value[1]

    @property
    def category(self) -> str:
        return self.value[2]


@dataclass(frozen=True)
class UniverseStock:
    corp_code: str
    stock_code: str
    corp_name: str
    sector: str | None = None
    market_cap_tier: str | None = None


class DartMajorReportCollector:
    """Collect 36 major report types and store to Local PostgreSQL."""

    def __init__(
        self,
        *,
        api_key: str,
        postgres_conn_string: str,
        sleep_seconds: float = 0.2,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()

        # Local PostgreSQL (not remote)
        self.engine = create_engine(postgres_conn_string, pool_pre_ping=True)
        self.metadata = MetaData()
        self._table_cache: dict[str, Table] = {}

    # ---------- Universe ----------
    @staticmethod
    def load_universe(universe_path: str) -> list[UniverseStock]:
        with open(universe_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        stocks = data.get("stocks") or []
        if not isinstance(stocks, list):
            raise ValueError("Invalid universe format: 'stocks' must be a list")

        parsed: list[UniverseStock] = []
        for row in stocks:
            if not isinstance(row, dict):
                continue
            corp_code = str(row.get("corp_code") or "").strip()
            stock_code = str(row.get("stock_code") or "").strip().zfill(6)
            corp_name = str(row.get("corp_name") or "").strip()
            if not (corp_code.isdigit() and len(corp_code) == 8):
                raise ValueError(f"Invalid corp_code: {corp_code!r}")
            if not (stock_code.isdigit() and len(stock_code) == 6):
                raise ValueError(f"Invalid stock_code: {stock_code!r}")
            if not corp_name:
                raise ValueError("corp_name is required")

            parsed.append(
                UniverseStock(
                    corp_code=corp_code,
                    stock_code=stock_code,
                    corp_name=corp_name,
                    sector=row.get("sector"),
                    market_cap_tier=row.get("market_cap_tier"),
                )
            )
        return parsed

    # ---------- PostgreSQL ----------
    def _get_table(self, report_type: MajorReportType) -> Table:
        table_key = report_type.endpoint
        if table_key in self._table_cache:
            return self._table_cache[table_key]

        table_name = f"dart_{_camel_to_snake(report_type.endpoint)}"
        table = Table(
            table_name,
            self.metadata,
            Column("rcept_no", String(20), primary_key=True),
            Column("corp_code", String(8), nullable=False),
            Column("stock_code", String(6)),
            Column("corp_name", Text),
            Column("rcept_dt", Date, nullable=False),
            Column("report_type", String(64), nullable=False),
            Column("category", String(64), nullable=False),
            Column("collected_at", DateTime(timezone=True), nullable=False),
            Column("payload", JSONB, nullable=False),
        )
        # Create minimal table if migration hasn't been applied yet.
        table.create(self.engine, checkfirst=True)
        self._table_cache[table_key] = table
        return table

    def _insert_ignore_duplicates(self, table: Table, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        stmt = insert(table).values(rows).on_conflict_do_nothing(index_elements=["rcept_no"])
        with self.engine.begin() as conn:
            result = conn.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    # ---------- OpenDART major report endpoints ----------
    def _get_major_report_items(
        self,
        *,
        report_type: MajorReportType,
        corp_code: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        url = f"{OPENDART_BASE_URL}/{report_type.endpoint}.json"
        params = {
            "crtfc_key": self.api_key,
            "corp_code": corp_code,
            "bgn_de": _yyyymmdd(start_date),
            "end_de": _yyyymmdd(end_date),
        }

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                time.sleep(self.sleep_seconds)
                res = self.session.get(url, params=params, timeout=self.timeout_seconds)
                res.raise_for_status()
                data = res.json()

                status = str(data.get("status") or "")
                if status == "000":
                    items = data.get("list") or []
                    return items if isinstance(items, list) else []
                if status == "013":  # no data
                    return []
                if status == "020":  # rate limit
                    wait = 60
                    time.sleep(wait)
                    continue

                message = data.get("message")
                raise RuntimeError(
                    f"OpenDART major report failed: endpoint={report_type.endpoint}, status={status}, message={message}"
                )
            except Exception as exc:  # noqa: BLE001 - controlled retries
                last_exc = exc
                wait = min(2 ** (attempt - 1), 8)
                time.sleep(wait)

        raise RuntimeError(
            f"OpenDART request failed after retries: endpoint={report_type.endpoint}, corp_code={corp_code}"
        ) from last_exc

    # ---------- Public APIs ----------
    def collect_report_type(
        self,
        *,
        stock: UniverseStock,
        report_type: MajorReportType,
        start_date: str,
        end_date: str,
    ) -> int:
        """Collect a single report type for a single company and store to Postgres.

        Returns number of inserted rows (duplicates ignored).
        """
        items = self._get_major_report_items(
            report_type=report_type,
            corp_code=stock.corp_code,
            start_date=start_date,
            end_date=end_date,
        )
        if not items:
            return 0

        collected_at = datetime.now(timezone.utc)
        rows: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rcept_no = str(item.get("rcept_no") or "").strip()
            rcept_dt_raw = item.get("rcept_dt")
            if not rcept_no:
                continue

            rows.append(
                {
                    "rcept_no": rcept_no,
                    "corp_code": stock.corp_code,
                    "stock_code": stock.stock_code,
                    "corp_name": stock.corp_name,
                    "rcept_dt": _infer_rcept_dt(rcept_no=rcept_no, rcept_dt_raw=str(rcept_dt_raw) if rcept_dt_raw is not None else None),
                    "report_type": report_type.endpoint,
                    "category": report_type.category,
                    "collected_at": collected_at,
                    "payload": item,
                }
            )

        table = self._get_table(report_type)
        return self._insert_ignore_duplicates(table, rows)

    def collect_all_report_types_for_company(
        self,
        *,
        stock: UniverseStock,
        lookback_days: int = 30,
        end_date: str | None = None,
    ) -> dict[str, int]:
        """Collect all 36 types for a single company (lookback window).

        Returns mapping: endpoint -> inserted_rows
        """
        end_dt = datetime.utcnow().date() if end_date is None else _parse_rcept_dt(end_date)
        start_dt = end_dt - timedelta(days=int(lookback_days))
        start = start_dt.strftime("%Y%m%d")
        end = end_dt.strftime("%Y%m%d")

        out: dict[str, int] = {}
        for report_type in MajorReportType:
            inserted = self.collect_report_type(
                stock=stock,
                report_type=report_type,
                start_date=start,
                end_date=end,
            )
            out[report_type.endpoint] = inserted
        return out

    def collect_universe(
        self,
        *,
        universe_path: str,
        lookback_days: int = 30,
        end_date: str | None = None,
    ) -> dict[str, dict[str, int]]:
        """Collect all 36 types for all companies in the universe."""
        stocks = self.load_universe(universe_path)
        results: dict[str, dict[str, int]] = {}
        for stock in stocks:
            results[stock.stock_code] = self.collect_all_report_types_for_company(
                stock=stock,
                lookback_days=lookback_days,
                end_date=end_date,
            )
        return results


def main() -> int:
    """Simple CLI entry (optional).

    Environment:
    - OPEN_DART_API_KEY
    - LOCAL_POSTGRES_CONN_STRING
    - DART_UNIVERSE_JSON (optional) default: ./modules/dart_disclosure/universe.ai-sector.template.json
    - DART_LOOKBACK_DAYS (optional) default: 30
    """
    api_key = os.getenv("OPEN_DART_API_KEY") or ""
    pg = os.getenv("LOCAL_POSTGRES_CONN_STRING") or ""
    if not api_key or not pg:
        raise SystemExit("Missing OPEN_DART_API_KEY or LOCAL_POSTGRES_CONN_STRING")

    universe_path = os.getenv(
        "DART_UNIVERSE_JSON",
        os.path.join("modules", "dart_disclosure", "universe.ai-sector.template.json"),
    )
    lookback_days = int(os.getenv("DART_LOOKBACK_DAYS", "30"))

    collector = DartMajorReportCollector(api_key=api_key, postgres_conn_string=pg)
    collector.collect_universe(universe_path=universe_path, lookback_days=lookback_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


