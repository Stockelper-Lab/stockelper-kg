"""OpenDart API collector for financial statements."""

import time
from typing import List

import pandas as pd
import OpenDartReader

from .base import BaseCollector


class DartCollector(BaseCollector):
    """Collector for OpenDart financial statement data."""

    def __init__(self, api_key: str, sleep_seconds: float = 0.1):
        """Initialize DART collector.

        Args:
            api_key: OpenDart API key
            sleep_seconds: Seconds to sleep between API calls
        """
        super().__init__(sleep_seconds)
        self.dart = OpenDartReader(api_key)
        self.column_names = [
            "매출액",
            "영업이익",
            "당기순이익",
            "자산총계",
            "부채총계",
            "자본총계",
            "자본금",
        ]
        self.column_names_eng = [
            "revenue",
            "operating_income",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "capital_stock",
        ]

    def _get_quarter_list(self, date: str) -> List[tuple]:
        """Get quarter list based on date.

        Args:
            date: Date in YYYYMMDD format

        Returns:
            List of (year, report_code, quarter_name) tuples
        """
        year = int(date[:4])
        month = int(date[4:6])

        if month in [1, 2, 3]:
            quarters = [(year - 1, "11011", "4")]
        elif month in [4, 5, 6]:
            quarters = [(year, "11013", "1"), (year - 1, "11011", "4")]
        elif month in [7, 8, 9]:
            quarters = [
                (year, "11012", "2"),
                (year, "11013", "1"),
                (year - 1, "11011", "4"),
            ]
        else:
            quarters = [
                (year, "11014", "3"),
                (year, "11012", "2"),
                (year, "11013", "1"),
                (year - 1, "11011", "4"),
            ]
        return quarters

    def collect_financial_statement(
        self, stock_code: str, date: str
    ) -> pd.DataFrame:
        """Collect financial statement for a stock.

        Args:
            stock_code: 6-digit stock code
            date: Date in YYYYMMDD format

        Returns:
            DataFrame with financial statement data
        """
        for bsns_year, reprt_code, quarter_nm in self._get_quarter_list(date):
            try:
                self.logger.debug(
                    f"Financial Statements: (stock_code: {stock_code}, year: {bsns_year}, quarter: {quarter_nm})"
                )
                dart_df = self.dart.finstate(
                    corp=stock_code, bsns_year=str(bsns_year), reprt_code=reprt_code
                )

                if dart_df is None or len(dart_df) == 0:
                    continue

                fs_info = []
                for col_nm in self.column_names:
                    try:
                        value = dart_df[
                            (dart_df["account_nm"] == col_nm)
                            & (dart_df["fs_nm"] == "연결재무제표")
                        ]["thstrm_amount"].values
                        if len(value) == 0:
                            value = dart_df[
                                (dart_df["account_nm"] == col_nm)
                                & (dart_df["fs_nm"] == "재무제표")
                            ]["thstrm_amount"].values
                        fs_info.append(
                            int(value[0].replace(",", "")) if len(value) > 0 else 0
                        )
                    except Exception:
                        fs_info.append(0)

                fs_df = pd.DataFrame([fs_info], columns=self.column_names_eng)
                fs_df["year"] = bsns_year
                fs_df["quarter"] = quarter_nm
                fs_df["stock_code"] = stock_code
                fs_df = fs_df[["stock_code", "year", "quarter"] + self.column_names_eng]
                return fs_df

            except Exception as e:
                self.logger.debug(f"Error fetching data for {stock_code}: {e}")
                continue

        # Return zeros if all quarters fail
        self.logger.warning(f"No available financial data for {stock_code}")
        fs_df = pd.DataFrame([[0] * len(self.column_names_eng)], columns=self.column_names_eng)
        fs_df["year"] = bsns_year
        fs_df["quarter"] = quarter_nm
        fs_df["stock_code"] = stock_code
        fs_df = fs_df[["stock_code", "year", "quarter"] + self.column_names_eng]
        return fs_df

    def collect(self, stock_codes: list, date: str) -> pd.DataFrame:
        """Collect financial statements for all stocks.

        Args:
            stock_codes: List of stock codes
            date: Date in YYYYMMDD format

        Returns:
            DataFrame with all financial statements
        """
        from tqdm import tqdm

        fs_list = []
        for stock_code in tqdm(
            stock_codes, desc=f"Collecting financial statements (date: {date})"
        ):
            fs = self.collect_financial_statement(stock_code, date)
            fs_list.append(fs)
            time.sleep(self.sleep_seconds)

        return pd.concat(fs_list, ignore_index=True)
