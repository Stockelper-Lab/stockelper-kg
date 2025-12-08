"""OpenDart API collector for financial statements."""

import time

import pandas as pd
import OpenDartReader

from .base import BaseCollector
from ..utils.dates import normalize_date


class DartCollector(BaseCollector):
    def __init__(self, api_key: str, sleep_seconds: float = 0.1):
        super().__init__(sleep_seconds)
        self.dart = OpenDartReader(api_key)
        self.columns_kr = [
            "매출액",
            "영업이익",
            "당기순이익",
            "자산총계",
            "부채총계",
            "자본총계",
            "자본금",
        ]
        self.columns_en = [
            "revenue",
            "operating_income",
            "net_income",
            "total_assets",
            "total_liabilities",
            "total_equity",
            "capital_stock",
        ]

    def collect_financial_statement(self, stock_code: str, date: str) -> pd.DataFrame:
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

        for bsns_year, reprt_code, quarter_nm in quarters:
            try:
                dart_df = self.dart.finstate(
                    corp=stock_code, bsns_year=str(bsns_year), reprt_code=reprt_code
                )
                if dart_df is None or len(dart_df) == 0:
                    continue

                fs_info = []
                for col_nm in self.columns_kr:
                    try:
                        mask = (dart_df["account_nm"] == col_nm) & (
                            dart_df["fs_nm"] == "연결재무제표"
                        )
                        value = dart_df.loc[mask, "thstrm_amount"].values
                        if len(value) == 0:
                            mask = (dart_df["account_nm"] == col_nm) & (
                                dart_df["fs_nm"] == "재무제표"
                            )
                            value = dart_df.loc[mask, "thstrm_amount"].values
                        fs_info.append(
                            int(value[0].replace(",", "")) if len(value) > 0 else 0
                        )
                    except Exception:
                        fs_info.append(0)

                reported_date = None
                if "thstrm_dt" in dart_df.columns:
                    value = dart_df["thstrm_dt"].dropna().astype(str).head(1)
                    if not value.empty:
                        reported_date = normalize_date(value.iloc[0])

                fs_df = pd.DataFrame([fs_info], columns=self.columns_en)
                fs_df["year"] = bsns_year
                fs_df["quarter"] = quarter_nm
                fs_df["stock_code"] = stock_code
                fs_df["reported_date"] = reported_date
                return fs_df[
                    ["stock_code", "year", "quarter", "reported_date", *self.columns_en]
                ]

            except Exception as e:
                self.logger.debug(f"Error fetching data for {stock_code}: {e}")
                continue

        self.logger.warning(f"No available financial data for {stock_code}")
        fs_df = pd.DataFrame([[0] * len(self.columns_en)], columns=self.columns_en)
        fs_df["year"] = bsns_year
        fs_df["quarter"] = quarter_nm
        fs_df["stock_code"] = stock_code
        fs_df["reported_date"] = None
        return fs_df[
            ["stock_code", "year", "quarter", "reported_date", *self.columns_en]
        ]

    def collect(self, stock_codes: list, date: str) -> pd.DataFrame:
        from tqdm import tqdm

        fs_list = []
        for stock_code in tqdm(
            stock_codes, desc=f"Collecting financial statements (date: {date})"
        ):
            fs_list.append(self.collect_financial_statement(stock_code, date))
            time.sleep(self.sleep_seconds)
        return pd.concat(fs_list, ignore_index=True)
