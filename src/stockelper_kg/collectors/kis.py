"""Korea Investment & Securities API collector."""

import logging
import json
import re
import time
from threading import Lock
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import KISConfig
from .base import BaseCollector


logger = logging.getLogger(__name__)


class KISTokenManager:
    def __init__(self, config: KISConfig, env_path: str):
        self.config = config
        self.env_path = env_path
        self._token = config.access_token
        self._lock = Lock()

    def token(self) -> str:
        if self._token:
            return self._token
        with self._lock:
            if self._token:
                return self._token
            self._token = self._request_token()
            self.config.access_token = self._token
            return self._token

    def refresh(self) -> str:
        with self._lock:
            self._token = self._request_token()
            self.config.access_token = self._token
            return self._token

    def _request_token(self) -> str:
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }

        res = requests.post(url, headers=headers, data=json.dumps(data))
        response_data = res.json()
        if res.status_code != 200:
            raise requests.RequestException(
                f"Failed to get access token: {res.status_code} - {response_data}"
            )

        new_token = response_data["access_token"]
        self._update_env_file(new_token)
        return new_token

    def _update_env_file(self, new_token: str) -> None:
        env_file = Path(self.env_path)
        if not env_file.exists():
            logger.warning(f".env file not found at {self.env_path}")
            return

        content = env_file.read_text(encoding="utf-8")
        pattern = r"^(KIS_ACCESS_TOKEN=).*$"
        replacement = f"KIS_ACCESS_TOKEN={new_token}"

        if re.search(pattern, content, re.MULTILINE):
            new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
        else:
            logger.warning("KIS_ACCESS_TOKEN not found in .env, appending...")
            new_content = content.rstrip() + f"\n{replacement}\n"

        env_file.write_text(new_content, encoding="utf-8")
        logger.info(f"Updated KIS_ACCESS_TOKEN in {self.env_path}")


class KISCollector(BaseCollector):
    """Collector for Korea Investment & Securities API."""

    def __init__(
        self,
        config: KISConfig,
        sleep_seconds: float = 0.1,
        env_path: str = ".env",
        token_manager: Optional[KISTokenManager] = None,
    ):
        """Initialize KIS collector.

        Args:
            config: KIS API configuration
            sleep_seconds: Seconds to sleep between API calls
            env_path: Path to .env file for token updates
            token_manager: Shared token manager (optional)
        """
        super().__init__(sleep_seconds)
        self.config = config
        self.env_path = env_path
        self.token_manager = token_manager or KISTokenManager(config, env_path)
        self.access_token = self._get_access_token()
        self.session = self._create_session()

    def _get_access_token(self) -> str:
        return self.token_manager.token()

    def _refresh_access_token(self) -> str:
        return self.token_manager.refresh()

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry strategy.

        Returns:
            Configured requests Session
        """
        session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
        )
        adapter = HTTPAdapter(
            pool_connections=20, pool_maxsize=50, max_retries=retry_strategy
        )
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def collect_company_info(self, stock_code: str) -> Optional[pd.DataFrame]:
        """Collect company information for a stock.

        Args:
            stock_code: 6-digit stock code

        Returns:
            DataFrame with company info or None if failed
        """
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/search-stock-info"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": "CTPF1002R",
            "custtype": "P",
        }
        params = {"PRDT_TYPE_CD": "300", "PDNO": stock_code}

        for attempt in range(3):
            try:
                res = self.session.get(url, headers=headers, params=params, timeout=30)

                # HTTP 상태 코드 체크
                if res.status_code >= 500:
                    self.logger.warning(
                        f"[{stock_code}] Server error {res.status_code} (attempt {attempt + 1}/3)"
                    )
                    if attempt < 2:
                        time.sleep(3**attempt)  # 1초, 3초, 9초
                        continue
                    return None
                if res.status_code in (401, 403):
                    self.logger.info(
                        f"[{stock_code}] Attempting to refresh access token..."
                    )
                    try:
                        self.access_token = self._refresh_access_token()
                        headers["authorization"] = f"Bearer {self.access_token}"
                        time.sleep(1)
                        continue
                    except Exception as e:
                        self.logger.error(
                            f"[{stock_code}] Token refresh failed: {e}"
                        )
                        return None

                data = res.json()

                if data.get("rt_cd") != "0":
                    self.logger.warning(f"[{stock_code}] API error: {data.get('msg1')}")
                    return None

                if not data or "output" not in data:
                    self.logger.warning(f"[{stock_code}] No data")
                    return None

                df = pd.DataFrame([data["output"]])
                df["stock_code"] = stock_code
                df = df[["stock_code", "kospi200_item_yn", "std_idst_clsf_cd_name"]]
                df = df.rename(columns={"std_idst_clsf_cd_name": "stock_sector_nm"})
                return df

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
            ) as e:
                self.logger.warning(
                    f"[{stock_code}] Connection error (attempt {attempt + 1}/3): {e}"
                )
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    self.logger.error(f"[{stock_code}] Max retries exceeded")
                    return None
            except Exception as e:
                self.logger.error(f"[{stock_code}] Unexpected error: {e}")
                return None

    def collect_price_info(
        self,
        stock_code: str,
        date_st: str,
        date_fn: str,
        requested_dates: Optional[set[str]] = None,
    ) -> Optional[pd.DataFrame]:
        """Collect price and indicator information for a date range.

        Args:
            stock_code: 6-digit stock code
            date_st: Start date (YYYYMMDD)
            date_fn: End date (YYYYMMDD)
            requested_dates: Optional whitelist of dates to keep

        Returns:
            DataFrame with price rows (one per date) or None if failed
        """
        url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        headers = {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self.access_token}",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
            "tr_id": "FHKST03010100",
            "custtype": "P",
        }
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": date_st,
            "FID_INPUT_DATE_2": date_fn,
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": 1,
        }

        for attempt in range(3):
            try:
                res = self.session.get(url, headers=headers, params=params, timeout=30)
            except requests.RequestException:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                raise

            if res.status_code >= 500:
                if attempt < 2:
                    time.sleep(3**attempt)
                    continue
                res.raise_for_status()
            if res.status_code in (401, 403):
                if attempt < 2:
                    self.access_token = self._refresh_access_token()
                    headers["authorization"] = f"Bearer {self.access_token}"
                    time.sleep(1)
                    continue
                res.raise_for_status()

            data = res.json()
            if data.get("rt_cd") != "0":
                raise requests.RequestException(
                    f"[{stock_code}] Price query failed: {data.get('msg1')}"
                )
            if not data or "output1" not in data or "output2" not in data or not data["output2"]:
                raise ValueError(f"[{stock_code}] No price data")

            rows = []
            dates_filter = {d for d in requested_dates} if requested_dates else None
            eps = data["output1"].get("eps", 0)
            pbr = data["output1"].get("pbr", 0)
            per = data["output1"].get("per", 0)

            for item in data["output2"]:
                bsop_date = item.get("stck_bsop_date") or item.get("bas_dt")
                if not bsop_date:
                    continue
                if dates_filter and bsop_date not in dates_filter:
                    continue

                close_price = item.get("stck_clpr", 0)
                present_price = item.get("stck_prpr") or close_price

                rows.append(
                    {
                        "stock_code": stock_code,
                        "date": bsop_date,
                        "stck_hgpr": item.get("stck_hgpr", 0),
                        "stck_lwpr": item.get("stck_lwpr", 0),
                        "stck_oprc": item.get("stck_oprc", 0),
                        "stck_clpr": close_price,
                        "stck_prpr": present_price,
                        "eps": eps,
                        "pbr": pbr,
                        "per": per,
                        "missing_price": False,
                    }
                )

            if rows:
                return pd.DataFrame(rows)
            raise ValueError(f"[{stock_code}] No price rows in response")

        raise RuntimeError(f"[{stock_code}] Price query retry exhausted")

    def collect(self, stock_codes: list, dates: list) -> tuple:
        """Collect all KIS data for given stocks and dates.

        Args:
            stock_codes: List of stock codes
            dates: List of dates in YYYYMMDD format

        Returns:
            Tuple of (company_df, price_df)
        """
        from tqdm import tqdm

        # Collect company info
        company_list = []
        for stock_code in tqdm(stock_codes, desc="Collecting KIS company info"):
            company_info = self.collect_company_info(stock_code)
            if company_info is not None:
                company_list.append(company_info)
            else:
                default_company = pd.DataFrame(
                    {
                        "stock_code": [stock_code],
                        "kospi200_item_yn": ["N"],
                        "stock_sector_nm": ["정보없음"],
                    }
                )
                company_list.append(default_company)
            time.sleep(self.sleep_seconds)

        company_df = pd.concat(company_list, ignore_index=True)
        company_df["stock_sector_nm"] = company_df["stock_sector_nm"].replace(
            "", np.nan
        )
        company_df.fillna("없음", inplace=True)

        # Collect price info (one API call per stock across the whole date range)
        if not dates:
            price_df = pd.DataFrame()
            return company_df, price_df

        requested_dates = {str(d) for d in dates}
        min_date = min(requested_dates)
        max_date = max(requested_dates)

        price_list = []
        for stock_code in tqdm(
            stock_codes, desc="Collecting KIS price info (range)"
        ):
            try:
                price_info = self.collect_price_info(
                    stock_code, min_date, max_date, requested_dates=requested_dates
                )
            except Exception as e:
                self.logger.warning(
                    f"[{stock_code}] Price fetch failed, using defaults: {e}"
                )
                price_info = None

            if price_info is None or price_info.empty:
                price_info = pd.DataFrame(
                    {
                        "stock_code": stock_code,
                        "date": sorted(requested_dates),
                        "stck_hgpr": None,
                        "stck_lwpr": None,
                        "stck_oprc": None,
                        "stck_clpr": None,
                        "stck_prpr": None,
                        "eps": None,
                        "pbr": None,
                        "per": None,
                        "missing_price": True,
                    }
                )
                price_list.append(price_info)
                time.sleep(self.sleep_seconds)
                continue

            existing_dates = set(price_info["date"])
            missing = requested_dates - existing_dates
            if missing:
                defaults = pd.DataFrame(
                    {
                        "stock_code": stock_code,
                        "date": list(missing),
                        "stck_hgpr": None,
                        "stck_lwpr": None,
                        "stck_oprc": None,
                        "stck_clpr": None,
                        "stck_prpr": None,
                        "eps": price_info["eps"].iloc[0] if not price_info.empty else None,
                        "pbr": price_info["pbr"].iloc[0] if not price_info.empty else None,
                        "per": price_info["per"].iloc[0] if not price_info.empty else None,
                        "missing_price": True,
                    }
                )
                price_info = pd.concat([price_info, defaults], ignore_index=True)
            price_list.append(price_info)
            time.sleep(self.sleep_seconds)

        price_df = pd.concat(price_list, ignore_index=True)
        return company_df, price_df
