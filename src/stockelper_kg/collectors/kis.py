"""Korea Investment & Securities API collector."""

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import KISConfig
from .base import BaseCollector


class KISCollector(BaseCollector):
    """Collector for Korea Investment & Securities API."""

    def __init__(self, config: KISConfig, sleep_seconds: float = 0.1, env_path: str = ".env"):
        """Initialize KIS collector.

        Args:
            config: KIS API configuration
            sleep_seconds: Seconds to sleep between API calls
            env_path: Path to .env file for token updates
        """
        super().__init__(sleep_seconds)
        self.config = config
        self.env_path = env_path
        self.access_token = self._get_access_token()
        self.session = self._create_session()

    def _get_access_token(self) -> str:
        """Get access token from KIS API.

        Returns:
            Access token string

        Raises:
            requests.RequestException: If token request fails
        """
        if self.config.access_token:
            return self.config.access_token

        return self._refresh_access_token()

    def _refresh_access_token(self) -> str:
        """Refresh access token from KIS API.

        Returns:
            New access token string

        Raises:
            requests.RequestException: If token request fails
        """
        url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
        headers = {"Content-Type": "application/json"}
        data = {
            "grant_type": "client_credentials",
            "appkey": self.config.app_key,
            "appsecret": self.config.app_secret,
        }
        
        self.logger.info("Requesting new access token...")
        res = requests.post(url, headers=headers, data=json.dumps(data))
        response_data = res.json()
        
        if res.status_code != 200:
            self.logger.error(f"Token request failed: {res.status_code} - {response_data}")
            raise requests.RequestException(f"Failed to get access token: {response_data}")
        
        new_token = response_data["access_token"]
        self.access_token = new_token
        
        # Update .env file with new token
        self._update_env_file(new_token)
        
        self.logger.info("Access token refreshed successfully")
        return new_token
    
    def _update_env_file(self, new_token: str) -> None:
        """Update .env file with new access token.

        Args:
            new_token: New access token to save
        """
        try:
            env_file = Path(self.env_path)
            if not env_file.exists():
                self.logger.warning(f".env file not found at {self.env_path}")
                return
            
            # Read current .env content
            content = env_file.read_text(encoding='utf-8')
            
            # Update KIS_ACCESS_TOKEN value
            # Match pattern: KIS_ACCESS_TOKEN=<value> or KIS_ACCESS_TOKEN=
            pattern = r'^(KIS_ACCESS_TOKEN=).*$'
            replacement = f'KIS_ACCESS_TOKEN={new_token}'
            
            if re.search(pattern, content, re.MULTILINE):
                # Replace existing token
                new_content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            else:
                # Add token if not exists
                self.logger.warning("KIS_ACCESS_TOKEN not found in .env, appending...")
                new_content = content.rstrip() + f'\n{replacement}\n'
            
            # Write back to file
            env_file.write_text(new_content, encoding='utf-8')
            self.logger.info(f"Updated KIS_ACCESS_TOKEN in {self.env_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to update .env file: {e}")

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
                
                # HTTP 상태 코드 체크 (500 에러 감지 - 토큰 만료 가능성)
                if res.status_code >= 500:
                    self.logger.warning(
                        f"[{stock_code}] Server error {res.status_code} (attempt {attempt + 1}/3)"
                    )
                    
                    # 첫 번째 시도에서 500 에러 시 토큰 재발급 시도
                    if attempt == 0:
                        self.logger.info(f"[{stock_code}] Attempting to refresh access token...")
                        try:
                            self.access_token = self._refresh_access_token()
                            headers["authorization"] = f"Bearer {self.access_token}"
                            time.sleep(1)
                            continue
                        except Exception as e:
                            self.logger.error(f"[{stock_code}] Token refresh failed: {e}")
                    
                    if attempt < 2:
                        time.sleep(3 ** attempt)  # 1초, 3초, 9초
                        continue
                    else:
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
        self, stock_code: str, date_st: str, date_fn: str
    ) -> Optional[pd.DataFrame]:
        """Collect price and indicator information.

        Args:
            stock_code: 6-digit stock code
            date_st: Start date (YYYYMMDD)
            date_fn: End date (YYYYMMDD)

        Returns:
            DataFrame with price info or None if failed
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
                
                # HTTP 상태 코드 체크 (500 에러 감지 - 토큰 만료 가능성)
                if res.status_code >= 500:
                    self.logger.warning(
                        f"[{stock_code}] Server error {res.status_code} (attempt {attempt + 1}/3)"
                    )
                    
                    # 첫 번째 시도에서 500 에러 시 토큰 재발급 시도
                    if attempt == 0:
                        self.logger.info(f"[{stock_code}] Attempting to refresh access token...")
                        try:
                            self.access_token = self._refresh_access_token()
                            headers["authorization"] = f"Bearer {self.access_token}"
                            time.sleep(1)
                            continue
                        except Exception as e:
                            self.logger.error(f"[{stock_code}] Token refresh failed: {e}")
                    
                    if attempt < 2:
                        time.sleep(3 ** attempt)  # 1초, 3초, 9초
                        continue
                    else:
                        return None
                
                data = res.json()

                if data.get("rt_cd") != "0":
                    self.logger.warning(
                        f"[{stock_code}] Price query failed: {data.get('msg1')}"
                    )
                    return None

                if (
                    not data
                    or "output1" not in data
                    or "output2" not in data
                    or not data["output2"]
                ):
                    self.logger.warning(f"[{stock_code}] No price data")
                    return None

                price_dict = {
                    "stock_code": stock_code,
                    "date": date_st,
                    "stck_hgpr": data["output2"][0].get("stck_hgpr", 0),
                    "stck_lwpr": data["output2"][0].get("stck_lwpr", 0),
                    "stck_oprc": data["output2"][0].get("stck_oprc", 0),
                    "stck_clpr": data["output2"][0].get("stck_clpr", 0),
                    "eps": data["output1"].get("eps", 0),
                    "pbr": data["output1"].get("pbr", 0),
                    "per": data["output1"].get("per", 0),
                }
                return pd.DataFrame([price_dict])

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.RequestException,
            ) as e:
                self.logger.warning(
                    f"[{stock_code}] Price connection error (attempt {attempt + 1}/3): {e}"
                )
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    self.logger.error(f"[{stock_code}] Price query max retries exceeded")
                    return None
            except Exception as e:
                self.logger.error(f"[{stock_code}] Price query unexpected error: {e}")
                return None

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
        company_df["stock_sector_nm"].replace("", np.nan, inplace=True)
        company_df.fillna("없음", inplace=True)

        # Collect price info
        price_list = []
        for date in dates:
            for stock_code in tqdm(
                stock_codes, desc=f"Collecting KIS price info (date: {date})"
            ):
                price_info = self.collect_price_info(stock_code, date, date)
                if price_info is not None:
                    price_list.append(price_info)
                else:
                    default_price = pd.DataFrame(
                        {
                            "stock_code": [stock_code],
                            "date": [date],
                            "stck_hgpr": [0],
                            "stck_lwpr": [0],
                            "stck_oprc": [0],
                            "stck_clpr": [0],
                            "eps": [0],
                            "pbr": [0],
                            "per": [0],
                        }
                    )
                    price_list.append(default_price)
                time.sleep(self.sleep_seconds)

        price_df = pd.concat(price_list, ignore_index=True)
        return company_df, price_df
