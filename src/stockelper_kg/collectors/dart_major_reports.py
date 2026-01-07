"""DART major report type collector (structured endpoints) -> Local PostgreSQL.

Updated strategy (2026-01-03):
- Use OpenDART 'major report' endpoints (structured JSON) instead of generic list/document parsing.
- Default is 36 endpoints, but can be reduced via `report_types=...` or env vars.
- Store to Local PostgreSQL (not remote AWS).
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any
from xml.etree import ElementTree as ET
from pathlib import Path

import requests
from sqlalchemy import Column, Date, DateTime, Index, MetaData, String, Table, Text, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine

OPENDART_BASE_URL = "https://opendart.fss.or.kr/api"
logger = logging.getLogger(__name__)

# Default cache location for corpCode.zip (writable in Airflow container).
DEFAULT_CORPCODE_CACHE_PATHS = (
    os.getenv("OPENDART_CORPCODE_CACHE_PATH"),
    "/opt/airflow/data/opendart_corpCode.zip",
    "/tmp/opendart_corpCode.zip",
)

# How long to keep corpCode.zip cache (hours). If the file is newer than this, reuse it.
DEFAULT_CORPCODE_CACHE_MAX_AGE_HOURS = float(os.getenv("OPENDART_CORPCODE_CACHE_MAX_AGE_HOURS", "168"))  # 7 days

# corpCode.xml is critical; allow longer wait/retry than per-endpoint retries.
DEFAULT_CORPCODE_MAX_RETRIES = int(os.getenv("OPENDART_CORPCODE_MAX_RETRIES", "30"))
DEFAULT_FAIL_FAST_ON_020 = os.getenv("OPENDART_FAIL_FAST_ON_020", "1").strip() not in ("0", "false", "False", "no", "NO")


class OpenDartAllKeysRateLimited(RuntimeError):
    """All provided OpenDART API keys are rate-limited (020)."""


def _parse_api_keys(raw: str | None) -> list[str]:
    """Parse api keys from env/variable.

    Supported formats:
    - JSON list: '["key1","key2"]'
    - Comma / whitespace separated: 'key1,key2' or 'key1 key2'
    """
    s = str(raw or "").strip()
    if not s:
        return []

    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                out = [str(x).strip() for x in data if str(x).strip()]
                return [x for x in out if x]
        except Exception:  # noqa: BLE001
            pass

    parts = re.split(r"[,\s]+", s)
    return [p for p in (x.strip() for x in parts) if p]


def _parse_report_type_endpoints(raw: Any | None) -> list[str]:
    """Parse major report type endpoints from env/variable/args.

    Supported formats:
    - Python list (e.g., Airflow Variable JSON): ["piicDecsn", "crDecsn"]
    - JSON list string: '["piicDecsn","crDecsn"]'
    - Comma / whitespace separated: "piicDecsn,crDecsn" or "piicDecsn crDecsn"
    """
    if raw is None:
        return []

    if isinstance(raw, (list, tuple, set)):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return [x for x in out if x]

    s = str(raw or "").strip()
    if not s:
        return []

    if s.startswith("[") and s.endswith("]"):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                out = [str(x).strip() for x in data if str(x).strip()]
                return [x for x in out if x]
        except Exception:  # noqa: BLE001
            pass

    parts = re.split(r"[,\s]+", s)
    return [p for p in (x.strip() for x in parts) if p]


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
    """Major report endpoints (full set).

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
    # NOTE: Official endpoint names follow OpenDART guide (DS005)
    EX_BNK_MNG_PCBG = ("bnkMngtPcbg", "채권은행_관리절차_개시", "채권은행")
    EX_BNK_MNG_PCSP = ("bnkMngtPcsp", "채권은행_관리절차_중단", "채권은행")

    # 소송 관련 (1)
    LWST_ETC_PRPS = ("lwstLg", "소송등_제기", "소송")

    # 해외 상장 관련 (4)
    OVSCS_MKT_LST_DECSN = ("ovLstDecsn", "해외증권시장_상장_결정", "해외상장")
    OVSCS_MKT_DLST_DECSN = ("ovDlstDecsn", "해외증권시장_상장폐지_결정", "해외상장")
    OVSCS_MKT_LST = ("ovLst", "해외증권시장_상장", "해외상장")
    OVSCS_MKT_DLST = ("ovDlst", "해외증권시장_상장폐지", "해외상장")

    # 사채 발행 관련 (4)
    CVBD_IS_DECSN = ("cvbdIsDecsn", "전환사채권_발행결정", "사채발행")
    BDWT_IS_DECSN = ("bdwtIsDecsn", "신주인수권부사채권_발행결정", "사채발행")
    EXBD_IS_DECSN = ("exbdIsDecsn", "교환사채권_발행결정", "사채발행")
    WOCCS_IS_DECSN = ("wdCocobdIsDecsn", "상각형_조건부자본증권_발행결정", "사채발행")

    # 자기주식 관련 (4)
    TSSTK_AQ_DECSN = ("tsstkAqDecsn", "자기주식_취득_결정", "자기주식")
    TSSTK_DP_DECSN = ("tsstkDpDecsn", "자기주식_처분_결정", "자기주식")
    TSSTK_AQ_TRC_CTR_DECSN = ("tsstkAqTrctrCnsDecsn", "자기주식취득_신탁계약_체결_결정", "자기주식")
    TSSTK_AQ_TRC_CTR_CC_DECSN = ("tsstkAqTrctrCcDecsn", "자기주식취득_신탁계약_해지_결정", "자기주식")

    # 영업양수도 관련 (2)
    BSN_INH_DECSN = ("bsnInhDecsn", "영업양수_결정", "영업양수도")
    BSN_TRF_DECSN = ("bsnTrfDecsn", "영업양도_결정", "영업양수도")

    # 자산양수도 관련 (2)
    TG_AST_INH_DECSN = ("tgastInhDecsn", "유형자산_양수_결정", "자산양수도")
    TG_AST_TRF_DECSN = ("tgastTrfDecsn", "유형자산_양도_결정", "자산양수도")

    # 타법인 주식 관련 (2)
    OTCPR_STK_INH_DECSN = ("otcprStkInvscrInhDecsn", "타법인주식_양수결정", "타법인주식")
    OTCPR_STK_TRF_DECSN = ("otcprStkInvscrTrfDecsn", "타법인주식_양도결정", "타법인주식")

    # 사채권 양수도 관련 (2)
    STK_RTBD_INH_DECSN = ("stkrtbdInhDecsn", "주권관련_사채권_양수_결정", "사채권양수도")
    STK_RTBD_TRF_DECSN = ("stkrtbdTrfDecsn", "주권관련_사채권_양도_결정", "사채권양수도")

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
    """Collect major report types and store to Local PostgreSQL.

    By default, collects all OpenDART major-report endpoints (full set).
    You can restrict the set via:
    - init arg: report_types=[...]
    - env vars (preferred): DART_CURATED_MAJOR_REPORT_ENDPOINTS / DART_CURATED_MAJOR_REPORT_TYPES
      - fallback: DART_MAJOR_REPORT_ENDPOINTS / DART_MAJOR_REPORT_TYPES
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_keys: list[str] | str | None = None,
        postgres_conn_string: str | None = None,
        engine: Engine | None = None,
        sleep_seconds: float = 0.2,
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
        report_types: list[str] | str | None = None,
    ):
        if api_key is not None and api_keys is not None:
            raise ValueError("Provide either `api_key` or `api_keys`, not both.")

        keys: list[str]
        if api_keys is not None:
            if isinstance(api_keys, list):
                keys = [str(x).strip() for x in api_keys if str(x).strip()]
            else:
                keys = _parse_api_keys(str(api_keys))
        else:
            keys = _parse_api_keys(str(api_key))

        if not keys:
            raise ValueError("Missing OpenDART API key(s): provide `api_key` or `api_keys`.")

        # Backward compatibility: keep `api_key` as the first key, but internally rotate using `api_keys`.
        self.api_keys = list(keys)
        self.api_key = self.api_keys[0]
        self._api_key_cursor = 0
        self._api_key_exhausted: set[str] = set()

        self.sleep_seconds = sleep_seconds
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.session = requests.Session()
        # OpenDART에서 "잘못된 URL(101)"로 응답하는 엔드포인트는 더 이상 지원되지 않는 것으로 보고
        # 한 번 감지되면 이후 호출을 즉시 스킵하여 전체 수집이 중단되지 않도록 합니다.
        self._unsupported_endpoints: set[str] = set()

        # Local PostgreSQL (not remote)
        #
        # NOTE:
        # - Airflow DAGs may pass a ready SQLAlchemy Engine via `engine=...`.
        # - CLI / library usage typically provides a DSN via `postgres_conn_string=...`.
        # Support BOTH for backward compatibility.
        if engine is not None and postgres_conn_string:
            raise ValueError("Provide either `engine` or `postgres_conn_string`, not both.")
        if engine is None and not postgres_conn_string:
            raise ValueError("Missing DB config: provide `engine` or `postgres_conn_string`.")

        if engine is not None:
            self.engine = engine
        else:
            self.engine = create_engine(str(postgres_conn_string), pool_pre_ping=True)
        self.metadata = MetaData()
        self._table_cache: dict[str, Table] = {}
        self._all_listed_cache: list[UniverseStock] | None = None
        self._corpcode_zip_cache_path: str | None = next(
            (p for p in DEFAULT_CORPCODE_CACHE_PATHS if p),
            None,
        )
        # Backfill progress tracking (idempotency / resume)
        self._progress_table_name = (
            os.getenv("DART_CURATED_PROGRESS_TABLE")
            or os.getenv("DART_MAJOR_REPORT_PROGRESS_TABLE")
            or "dart_major_reports_backfill_progress"
        )
        # Ensure bootstrap queries stay fast (best-effort index creation per table).
        self._bootstrap_index_ensured: set[str] = set()

        # Major report endpoints to collect.
        # - Default: all types (full set; backward compatible).
        # - Can be reduced via init arg `report_types=...` or env vars:
        #   - DART_CURATED_MAJOR_REPORT_ENDPOINTS / DART_CURATED_MAJOR_REPORT_TYPES
        #   - (fallback) DART_MAJOR_REPORT_ENDPOINTS / DART_MAJOR_REPORT_TYPES
        self.major_report_types: list[MajorReportType] = self._resolve_report_types(report_types)

    def _resolve_report_types(self, raw: list[str] | str | None) -> list[MajorReportType]:
        """Resolve requested report types into MajorReportType list (order-preserving, de-duplicated)."""
        requested_raw = raw
        if requested_raw is None:
            requested_raw = (
                os.getenv("DART_CURATED_MAJOR_REPORT_ENDPOINTS")
                or os.getenv("DART_CURATED_MAJOR_REPORT_TYPES")
                or os.getenv("DART_MAJOR_REPORT_ENDPOINTS")
                or os.getenv("DART_MAJOR_REPORT_TYPES")
            )

        requested = _parse_report_type_endpoints(requested_raw)
        if not requested:
            return list(MajorReportType)

        by_endpoint = {rt.endpoint: rt for rt in MajorReportType}
        by_name = {rt.name: rt for rt in MajorReportType}

        resolved: list[MajorReportType] = []
        seen_endpoints: set[str] = set()
        unknown: list[str] = []

        for t in requested:
            key = str(t).strip()
            if not key:
                continue
            rt = by_endpoint.get(key) or by_name.get(key)
            if rt is None:
                unknown.append(key)
                continue
            if rt.endpoint in seen_endpoints:
                continue
            seen_endpoints.add(rt.endpoint)
            resolved.append(rt)

        if unknown:
            raise ValueError(
                "Unknown major report type(s): "
                f"{unknown}. Use OpenDART endpoint names like 'piicDecsn' or Enum names like 'PIIC_DECSN'."
            )

        return resolved

    @staticmethod
    def _parse_opendart_error_payload(payload: bytes) -> tuple[str | None, str | None]:
        """Parse OpenDART error payload (JSON or XML), best-effort."""
        raw = (payload or b"").strip()
        if not raw:
            return None, None

        # JSON: {"status":"020","message":"..."}
        if raw.startswith(b"{"):
            try:
                data = json.loads(raw.decode("utf-8", errors="replace"))
                return str(data.get("status") or "") or None, str(data.get("message") or "") or None
            except Exception:  # noqa: BLE001
                return None, None

        # XML: <result><status>020</status><message>...</message></result>
        if raw.startswith(b"<"):
            try:
                root = ET.fromstring(raw)
                status = (root.findtext(".//status") or "").strip() or None
                message = (root.findtext(".//message") or "").strip() or None
                return status, message
            except Exception:  # noqa: BLE001
                return None, None

        return None, None

    # ---------- OpenDART API key rotation ----------
    def _has_available_api_key(self) -> bool:
        return any(k not in self._api_key_exhausted for k in self.api_keys)

    def _next_api_key(self) -> str:
        """Return next available API key (round-robin), skipping exhausted keys."""
        if len(self.api_keys) == 1:
            return self.api_keys[0]

        if not self._has_available_api_key():
            raise OpenDartAllKeysRateLimited("OpenDART rate-limited (020): all api keys exhausted.")

        n = len(self.api_keys)
        for _ in range(n):
            key = self.api_keys[self._api_key_cursor % n]
            self._api_key_cursor = (self._api_key_cursor + 1) % n
            if key not in self._api_key_exhausted:
                return key

        # Fallback (shouldn't happen)
        for key in self.api_keys:
            if key not in self._api_key_exhausted:
                return key
        raise OpenDartAllKeysRateLimited("OpenDART rate-limited (020): all api keys exhausted.")

    def _mark_api_key_rate_limited(self, key: str) -> None:
        """Mark a key as exhausted for the rest of this run (used when we see status=020)."""
        if len(self.api_keys) > 1 and key:
            self._api_key_exhausted.add(key)

    def _read_corpcode_zip(self, zip_bytes: bytes) -> list[UniverseStock]:
        """Parse OpenDART corpCode.zip bytes into listed companies (corp_code+stock_code)."""
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            xml_name = next((name for name in zf.namelist() if name.lower().endswith(".xml")), None)
            if not xml_name:
                raise RuntimeError("corpCode.zip did not contain an XML file.")
            xml_bytes = zf.read(xml_name)

        try:
            root = ET.fromstring(xml_bytes)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Failed to parse corpCode.xml from OpenDART.") from exc

        out_by_stock: dict[str, UniverseStock] = {}
        for el in root.findall(".//list"):
            corp_code = (el.findtext("corp_code") or "").strip()
            stock_code = (el.findtext("stock_code") or "").strip()
            corp_name = (el.findtext("corp_name") or "").strip()

            if not (corp_code.isdigit() and len(corp_code) == 8):
                continue
            if not (stock_code.isdigit() and len(stock_code) == 6):
                continue
            if not corp_name:
                continue

            out_by_stock.setdefault(
                stock_code,
                UniverseStock(corp_code=corp_code, stock_code=stock_code, corp_name=corp_name),
            )

        return list(out_by_stock.values())

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

    # ---------- Listed companies (corpCode.xml) ----------
    def _load_all_listed_from_corp_code_xml(self) -> list[UniverseStock]:
        """Return all listed companies from OpenDART corpCode.xml.

        Notes:
        - OpenDART provides a zipped XML containing corp_code/stock_code/corp_name for all corps.
        - We treat "listed" as rows that have a valid 6-digit `stock_code`.
        """
        # 1) Prefer local cache if present (avoids rate-limit 020).
        cache_path = self._corpcode_zip_cache_path
        if cache_path:
            p = Path(cache_path)
            if p.exists() and zipfile.is_zipfile(str(p)):
                try:
                    # Cache TTL check (best-effort)
                    age_hours = (time.time() - p.stat().st_mtime) / 3600.0
                    if age_hours <= DEFAULT_CORPCODE_CACHE_MAX_AGE_HOURS:
                        zip_bytes = p.read_bytes()
                        return self._read_corpcode_zip(zip_bytes)
                    logger.info(
                        "corpCode cache is too old (age_hours=%.1f > %.1f), re-downloading.",
                        age_hours,
                        DEFAULT_CORPCODE_CACHE_MAX_AGE_HOURS,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to read cached corpCode zip (%s): %s", p, exc)

        # 2) Download from OpenDART with basic retry/backoff.
        url = f"{OPENDART_BASE_URL}/corpCode.xml"
        # NOTE: API key is rotated per attempt if multiple keys are configured.

        last_status: str | None = None
        last_message: str | None = None
        last_exc: Exception | None = None

        max_retries = max(self.max_retries, DEFAULT_CORPCODE_MAX_RETRIES)
        for attempt in range(1, max_retries + 1):
            try:
                api_key = self._next_api_key()
                params = {"crtfc_key": api_key}
                res = self.session.get(url, params=params, timeout=max(self.timeout_seconds, 60.0))
                res.raise_for_status()

                # Success path: must be a ZIP.
                if zipfile.is_zipfile(io.BytesIO(res.content)):
                    zip_bytes = res.content
                    # Best-effort cache write for future runs.
                    if cache_path:
                        try:
                            p = Path(cache_path)
                            p.parent.mkdir(parents=True, exist_ok=True)
                            p.write_bytes(zip_bytes)
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("Failed to write corpCode cache (%s): %s", cache_path, exc)
                    return self._read_corpcode_zip(zip_bytes)

                # Non-zip response: parse OpenDART error payload (often XML with <status>020</status>)
                status, message = self._parse_opendart_error_payload(res.content)
                last_status, last_message = status, message

                if status == "020":
                    # rate limit: typically per-day per-key. If multiple keys exist, rotate immediately.
                    if len(self.api_keys) > 1:
                        self._mark_api_key_rate_limited(api_key)
                        if self._has_available_api_key():
                            logger.warning(
                                "OpenDART corpCode.xml rate-limited (020) for one key. Rotating key (exhausted=%s/%s).",
                                len(self._api_key_exhausted),
                                len(self.api_keys),
                            )
                            continue
                        raise OpenDartAllKeysRateLimited(
                            f"OpenDART corpCode.xml rate-limited (020): all api keys exhausted. message={message!r}"
                        )

                    # Single-key mode: keep existing behavior (fail-fast or wait/retry).
                    if DEFAULT_FAIL_FAST_ON_020:
                        raise OpenDartAllKeysRateLimited(
                            f"OpenDART corpCode.xml rate-limited (020): message={message!r}"
                        )
                    wait = min(60 * attempt, 300)
                    logger.warning(
                        "OpenDART corpCode.xml rate-limited (020). Waiting %ss then retrying (%s/%s).",
                        wait,
                        attempt,
                        max_retries,
                    )
                    time.sleep(wait)
                    continue

                snippet = res.content[:200].decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"OpenDART corpCode.xml did not return a zip: status={status!r} message={message!r} content_type={res.headers.get('Content-Type')!r} snippet={snippet!r}"
                )
            except OpenDartAllKeysRateLimited:
                raise
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                wait = min(2 ** (attempt - 1), 8)
                time.sleep(wait)

        raise RuntimeError(
            f"OpenDART corpCode.xml failed after retries: status={last_status!r} message={last_message!r}"
        ) from last_exc

    def list_all_listed_companies(self) -> list[UniverseStock]:
        """List all listed companies (corp_code+stock_code) from OpenDART corpCode.xml (cached per instance)."""
        if self._all_listed_cache is None:
            self._all_listed_cache = self._load_all_listed_from_corp_code_xml()
        return list(self._all_listed_cache)

    # ---------- Backfill progress (PostgreSQL) ----------
    def _ensure_progress_table(self, table_name: str) -> None:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
          stock_code VARCHAR(6) NOT NULL,
          corp_code VARCHAR(8),
          corp_name TEXT,
          endpoint TEXT NOT NULL,
          start_date DATE NOT NULL,
          end_date DATE NOT NULL,
          status TEXT NOT NULL,
          inserted_rows INTEGER,
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (stock_code, endpoint, start_date, end_date)
        );
        CREATE INDEX IF NOT EXISTS idx_{table_name}_status ON "{table_name}" (status);
        CREATE INDEX IF NOT EXISTS idx_{table_name}_stock ON "{table_name}" (stock_code);
        """
        with self.engine.begin() as conn:
            for stmt in ddl.strip().split(";"):
                s = stmt.strip()
                if s:
                    conn.execute(text(s))

    def _progress_done_set(self, *, table_name: str, start_date: str, end_date: str) -> set[tuple[str, str]]:
        """Return set of (stock_code, endpoint) that are marked done for the given range."""
        self._ensure_progress_table(table_name)
        start_dt = _parse_rcept_dt(start_date)
        end_dt = _parse_rcept_dt(end_date)
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    f"""
                    SELECT stock_code, endpoint
                    FROM "{table_name}"
                    WHERE start_date = :start_dt
                      AND end_date = :end_dt
                      AND status LIKE 'done%'
                    """
                ),
                {"start_dt": start_dt, "end_dt": end_dt},
            ).fetchall()
        return {(str(r[0]), str(r[1])) for r in rows}

    def _mark_progress_done(
        self,
        *,
        table_name: str,
        stock: UniverseStock,
        endpoint: str,
        start_date: str,
        end_date: str,
        inserted_rows: int | None,
        status: str = "done",
    ) -> None:
        self._ensure_progress_table(table_name)
        start_dt = _parse_rcept_dt(start_date)
        end_dt = _parse_rcept_dt(end_date)
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    f"""
                    INSERT INTO "{table_name}" (
                      stock_code, corp_code, corp_name, endpoint,
                      start_date, end_date, status, inserted_rows, updated_at
                    )
                    VALUES (
                      :stock_code, :corp_code, :corp_name, :endpoint,
                      :start_date, :end_date, :status, :inserted_rows, NOW()
                    )
                    ON CONFLICT (stock_code, endpoint, start_date, end_date)
                    DO UPDATE SET
                      corp_code = EXCLUDED.corp_code,
                      corp_name = EXCLUDED.corp_name,
                      status = EXCLUDED.status,
                      inserted_rows = EXCLUDED.inserted_rows,
                      updated_at = NOW()
                    """
                ),
                {
                    "stock_code": stock.stock_code,
                    "corp_code": stock.corp_code,
                    "corp_name": stock.corp_name,
                    "endpoint": str(endpoint),
                    "start_date": start_dt,
                    "end_date": end_dt,
                    "status": str(status),
                    "inserted_rows": int(inserted_rows) if inserted_rows is not None else None,
                },
            )

    def _has_any_rows_for_stock_in_table(
        self,
        *,
        table_name: str,
        stock_code: str,
        start_date: str,
        end_date: str,
    ) -> bool:
        """Best-effort bootstrap: if table has any row for stock_code in range, treat as already collected."""
        start_dt = _parse_rcept_dt(start_date)
        end_dt = _parse_rcept_dt(end_date)
        with self.engine.begin() as conn:
            exists = conn.execute(
                text(
                    """
                    SELECT EXISTS(
                      SELECT 1
                      FROM information_schema.tables
                      WHERE table_schema='public' AND table_name = :t
                    )
                    """
                ),
                {"t": table_name},
            ).scalar()
            if not exists:
                return False

            # Best-effort: create supporting indexes once per table to keep the bootstrap check cheap.
            if table_name not in self._bootstrap_index_ensured:
                try:
                    conn.execute(
                        text(
                            f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_stock_dt" ON "{table_name}" (stock_code, rcept_dt);'
                        )
                    )
                    conn.execute(
                        text(f'CREATE INDEX IF NOT EXISTS "idx_{table_name}_dt" ON "{table_name}" (rcept_dt);')
                    )
                except Exception:  # noqa: BLE001
                    pass
                self._bootstrap_index_ensured.add(table_name)

            hit = conn.execute(
                text(
                    f"""
                    SELECT 1
                    FROM "{table_name}"
                    WHERE stock_code = :stock_code
                      AND rcept_dt >= :start_dt
                      AND rcept_dt <= :end_dt
                    LIMIT 1
                    """
                ),
                {"stock_code": str(stock_code), "start_dt": start_dt, "end_dt": end_dt},
            ).fetchone()
        return hit is not None

    @staticmethod
    def _load_priority_stock_codes(priority_universe_path: str) -> list[str]:
        """Load priority stock codes from the Airflow universe JSON (list-of-dicts) or stockelper-kg universe (dict)."""
        with open(priority_universe_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        codes: list[str] = []
        if isinstance(data, list):
            for row in data:
                if not isinstance(row, dict):
                    continue
                sc = str(row.get("stock_code") or "").strip()
                if sc:
                    sc = sc.zfill(6)
                    if sc.isdigit() and len(sc) == 6:
                        codes.append(sc)
            return codes

        if isinstance(data, dict):
            stocks = data.get("stocks") or []
            if isinstance(stocks, list):
                for row in stocks:
                    if not isinstance(row, dict):
                        continue
                    sc = str(row.get("stock_code") or "").strip()
                    if sc:
                        sc = sc.zfill(6)
                        if sc.isdigit() and len(sc) == 6:
                            codes.append(sc)
            return codes

        return codes

    def collect_backfill_chunk(
        self,
        *,
        start_date: str,
        end_date: str,
        chunk_size: int = 500,
        priority_universe_path: str | None = None,
    ) -> dict[str, Any]:
        """Backfill up to `chunk_size` companies per run.

        Order:
        1) Priority universe (stock codes in JSON) first
        2) Then other listed companies

        Idempotency / resume:
        - Uses a progress table in Postgres to skip already-processed (stock_code, endpoint, range).
        - Bootstraps progress as 'done_bootstrap' if DB already contains rows for that (stock_code, endpoint, range).
        """
        start_s = _yyyymmdd(start_date)
        end_s = _yyyymmdd(end_date)
        if int(chunk_size) <= 0:
            raise ValueError(f"chunk_size must be positive: {chunk_size!r}")

        progress_table = self._progress_table_name
        done = self._progress_done_set(table_name=progress_table, start_date=start_s, end_date=end_s)

        # Load listed companies (corpCode cache strongly recommended)
        try:
            all_listed = self.list_all_listed_companies()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "020" in msg or "rate-limit" in msg or "rate limited" in msg or "사용한도" in msg or "요청 제한" in msg:
                logger.warning("Stopping chunk early: failed to load corpCode due to rate limit (020): %s", exc)
                return {
                    "start_date": start_s,
                    "end_date": end_s,
                    "chunk_size": int(chunk_size),
                    "processed_stock_codes": [],
                    "processed_count": 0,
                    "inserted_total": 0,
                    "per_company": {},
                    "stopped_reason": "rate_limit_020_corpcode",
                }
            raise
        all_by_code = {s.stock_code: s for s in all_listed}

        # Priority list from JSON (Airflow universe file format)
        priority_codes: list[str] = []
        if priority_universe_path:
            try:
                priority_codes = self._load_priority_stock_codes(priority_universe_path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to load priority universe (%s): %s", priority_universe_path, exc)
                priority_codes = []

        seen: set[str] = set()
        priority_stocks: list[UniverseStock] = []
        for code in priority_codes:
            if code in seen:
                continue
            st = all_by_code.get(code)
            if st is None:
                continue
            priority_stocks.append(st)
            seen.add(code)

        # Remaining stocks (sorted for deterministic resume)
        remaining_stocks = [s for s in sorted(all_listed, key=lambda x: x.stock_code) if s.stock_code not in seen]

        def _stock_is_complete(stock_code: str) -> bool:
            # Complete means we have done markers for all endpoints.
            needed = len(self.major_report_types)
            cnt = 0
            for rt in self.major_report_types:
                if (stock_code, rt.endpoint) in done:
                    cnt += 1
            return cnt >= needed

        # Select next chunk of incomplete companies
        targets: list[UniverseStock] = []
        for s in priority_stocks:
            if len(targets) >= int(chunk_size):
                break
            if not _stock_is_complete(s.stock_code):
                targets.append(s)

        if len(targets) < int(chunk_size):
            for s in remaining_stocks:
                if len(targets) >= int(chunk_size):
                    break
                if not _stock_is_complete(s.stock_code):
                    targets.append(s)

        logger.info(
            "Backfill chunk selected: targets=%s chunk_size=%s priority=%s total_listed=%s",
            len(targets),
            int(chunk_size),
            len(priority_stocks),
            len(all_listed),
        )

        processed: list[str] = []
        inserted_total = 0
        per_company: dict[str, dict[str, int]] = {}

        for stock in targets:
            processed.append(stock.stock_code)
            per_company[stock.stock_code] = {}

            for rt in self.major_report_types:
                key = (stock.stock_code, rt.endpoint)
                if key in done:
                    continue

                # Bootstrap: if data already exists for this stock+endpoint+range, mark done and skip API call.
                dart_table = f"dart_{_camel_to_snake(rt.endpoint)}"
                try:
                    if self._has_any_rows_for_stock_in_table(
                        table_name=dart_table,
                        stock_code=stock.stock_code,
                        start_date=start_s,
                        end_date=end_s,
                    ):
                        self._mark_progress_done(
                            table_name=progress_table,
                            stock=stock,
                            endpoint=rt.endpoint,
                            start_date=start_s,
                            end_date=end_s,
                            inserted_rows=None,
                            status="done_bootstrap",
                        )
                        done.add(key)
                        continue
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Bootstrap check failed: stock=%s endpoint=%s err=%s", stock.stock_code, rt.endpoint, exc)

                # Call API + insert
                try:
                    inserted = self.collect_report_type(
                        stock=stock,
                        report_type=rt,
                        start_date=start_s,
                        end_date=end_s,
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc)
                    if (
                        "status=020" in msg
                        or "(020)" in msg
                        or "rate-limited" in msg
                        or "rate limited" in msg
                        or "사용한도" in msg
                        or "요청 제한" in msg
                    ):
                        # Stop gracefully; next scheduled run (24h later) should resume from progress.
                        logger.warning("Stopping chunk early due to rate limit (020). stock=%s endpoint=%s", stock.stock_code, rt.endpoint)
                        return {
                            "start_date": start_s,
                            "end_date": end_s,
                            "chunk_size": int(chunk_size),
                            "processed_stock_codes": processed,
                            "processed_count": len(processed),
                            "inserted_total": inserted_total,
                            "per_company": per_company,
                            "stopped_reason": "rate_limit_020",
                        }
                    # Non-rate-limit error: leave it for retry in future runs
                    logger.warning("Collect failed: stock=%s endpoint=%s err=%s", stock.stock_code, rt.endpoint, exc)
                    continue

                per_company[stock.stock_code][rt.endpoint] = int(inserted or 0)
                inserted_total += int(inserted or 0)

                # Mark progress as done even if inserted==0 (means called successfully but no data)
                self._mark_progress_done(
                    table_name=progress_table,
                    stock=stock,
                    endpoint=rt.endpoint,
                    start_date=start_s,
                    end_date=end_s,
                    inserted_rows=int(inserted or 0),
                    status="done",
                )
                done.add(key)

        return {
            "start_date": start_s,
            "end_date": end_s,
            "chunk_size": int(chunk_size),
            "processed_stock_codes": processed,
            "processed_count": len(processed),
            "inserted_total": inserted_total,
            "per_company": per_company,
            "stopped_reason": None,
        }

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
        # Best-effort indexes for common lookups / bootstrap checks.
        # (If the official migration ran, these already exist; IF NOT, create them here.)
        Index(f"idx_{table_name}_corp_dt", table.c.corp_code, table.c.rcept_dt).create(
            self.engine, checkfirst=True
        )
        Index(f"idx_{table_name}_stock_dt", table.c.stock_code, table.c.rcept_dt).create(
            self.engine, checkfirst=True
        )
        Index(f"idx_{table_name}_dt", table.c.rcept_dt).create(self.engine, checkfirst=True)
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
        # 이미 지원 불가로 판정된 엔드포인트면 즉시 스킵
        if report_type.endpoint in self._unsupported_endpoints:
            return []

        url = f"{OPENDART_BASE_URL}/{report_type.endpoint}.json"
        base_params = {
            "corp_code": corp_code,
            "bgn_de": _yyyymmdd(start_date),
            "end_de": _yyyymmdd(end_date),
        }

        last_exc: Exception | None = None
        attempt = 0
        while attempt < self.max_retries:
            api_key = self._next_api_key()
            params = {"crtfc_key": api_key, **base_params}
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
                if status == "101":  # invalid URL (unsupported endpoint)
                    message = data.get("message")
                    # 전사적으로 스킵 처리(같은 엔드포인트를 모든 회사에 대해 계속 호출하지 않도록)
                    self._unsupported_endpoints.add(report_type.endpoint)
                    # best-effort: 전체 파이프라인을 실패시키지 않음
                    return []
                if status == "020":  # rate limit
                    # If multiple keys exist, rotate immediately.
                    if len(self.api_keys) > 1:
                        self._mark_api_key_rate_limited(api_key)
                        if self._has_available_api_key():
                            logger.warning(
                                "OpenDART rate-limited (020) for one key. Rotating key (exhausted=%s/%s). endpoint=%s corp_code=%s",
                                len(self._api_key_exhausted),
                                len(self.api_keys),
                                report_type.endpoint,
                                corp_code,
                            )
                            continue
                        raise OpenDartAllKeysRateLimited(
                            f"OpenDART rate-limited (020): all api keys exhausted. endpoint={report_type.endpoint} corp_code={corp_code}"
                        )

                    # Single-key mode: keep existing behavior (fail-fast or wait/retry).
                    if DEFAULT_FAIL_FAST_ON_020:
                        raise OpenDartAllKeysRateLimited(
                            f"OpenDART rate-limited (020): endpoint={report_type.endpoint} corp_code={corp_code}"
                        )
                    wait = 60
                    logger.warning(
                        "OpenDART rate-limited (020). endpoint=%s corp_code=%s wait=%ss",
                        report_type.endpoint,
                        corp_code,
                        wait,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue

                message = data.get("message")
                raise RuntimeError(
                    f"OpenDART major report failed: endpoint={report_type.endpoint}, status={status}, message={message}"
                )
            except OpenDartAllKeysRateLimited:
                raise
            except Exception as exc:  # noqa: BLE001 - controlled retries
                last_exc = exc
                attempt += 1
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
        """Collect all configured types for a single company (lookback window).

        Returns mapping: endpoint -> inserted_rows
        """
        end_dt = datetime.utcnow().date() if end_date is None else _parse_rcept_dt(end_date)
        start_dt = end_dt - timedelta(days=int(lookback_days))
        start = start_dt.strftime("%Y%m%d")
        end = end_dt.strftime("%Y%m%d")

        out: dict[str, int] = {}
        for report_type in self.major_report_types:
            inserted = self.collect_report_type(
                stock=stock,
                report_type=report_type,
                start_date=start,
                end_date=end,
            )
            out[report_type.endpoint] = inserted
        return out

    def collect_all_report_types_for_company_range(
        self,
        *,
        stock: UniverseStock,
        start_date: str,
        end_date: str,
    ) -> dict[str, int]:
        """Collect all configured types for a single company in an explicit date range.

        Returns mapping: endpoint -> inserted_rows
        """
        start = _yyyymmdd(start_date)
        end = _yyyymmdd(end_date)

        out: dict[str, int] = {}
        for report_type in self.major_report_types:
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
        """Collect all configured types for all companies in the universe."""
        stocks = self.load_universe(universe_path)
        results: dict[str, dict[str, int]] = {}
        for stock in stocks:
            results[stock.stock_code] = self.collect_all_report_types_for_company(
                stock=stock,
                lookback_days=lookback_days,
                end_date=end_date,
            )
        return results

    def collect_all_listed(
        self,
        *,
        lookback_days: int = 30,
        end_date: str | None = None,
    ) -> dict[str, dict[str, int]]:
        """Collect all configured types for ALL listed companies (derived from corpCode.xml)."""
        stocks = self.list_all_listed_companies()
        results: dict[str, dict[str, int]] = {}
        for stock in stocks:
            results[stock.stock_code] = self.collect_all_report_types_for_company(
                stock=stock,
                lookback_days=lookback_days,
                end_date=end_date,
            )
        return results

    def collect_all_listed_range(
        self,
        *,
        start_date: str,
        end_date: str,
    ) -> dict[str, dict[str, int]]:
        """Collect all configured types for ALL listed companies in a date range (backfill)."""
        stocks = self.list_all_listed_companies()
        results: dict[str, dict[str, int]] = {}
        for stock in stocks:
            results[stock.stock_code] = self.collect_all_report_types_for_company_range(
                stock=stock,
                start_date=start_date,
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
    api_keys_raw = os.getenv("OPEN_DART_API_KEYS") or os.getenv("OPEN_DART_API_KEY") or ""
    pg = os.getenv("LOCAL_POSTGRES_CONN_STRING") or ""
    api_keys = _parse_api_keys(api_keys_raw)
    if not api_keys or not pg:
        raise SystemExit("Missing OPEN_DART_API_KEYS/OPEN_DART_API_KEY or LOCAL_POSTGRES_CONN_STRING")

    universe_path = os.getenv(
        "DART_UNIVERSE_JSON",
        os.path.join("modules", "dart_disclosure", "universe.ai-sector.template.json"),
    )
    lookback_days = int(os.getenv("DART_LOOKBACK_DAYS", "30"))

    collector = DartMajorReportCollector(api_keys=api_keys, postgres_conn_string=pg)
    collector.collect_universe(universe_path=universe_path, lookback_days=lookback_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


