"""KRX (Korea Exchange) data collector."""

import pandas as pd
import requests

from .base import BaseCollector


class KRXCollector(BaseCollector):
    """Collector for KRX stock exchange data."""

    def collect(self) -> pd.DataFrame:
        """Collect company information from KRX.

        Returns:
            DataFrame with company information

        Raises:
            requests.RequestException: If API request fails
        """
        url = "https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://data.krx.co.kr/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "bld": "dbms/MDC/STAT/standard/MDCSTAT01901",
            "mktId": "ALL",
            "share": "1",
            "csvxls_isNo": "false",
        }

        self.logger.info("Fetching company data from KRX...")
        res = requests.post(url, headers=headers, data=data)
        res.encoding = "utf-8-sig"
        json_data = res.json()

        df = pd.DataFrame(json_data["OutBlock_1"])
        df["ISU_SRT_CD"] = df["ISU_SRT_CD"].apply(lambda x: x.zfill(6))
        df["LIST_DD"] = pd.to_datetime(df["LIST_DD"])
        df["LIST_SHRS"] = df["LIST_SHRS"].str.replace(",", "").astype(int)

        columns = [
            "ISU_SRT_CD",
            "ISU_NM",
            "ISU_ABBRV",
            "ISU_ENG_NM",
            "LIST_DD",
            "MKT_TP_NM",
            "LIST_SHRS",
        ]
        df = df[columns]
        df = df.rename(
            columns={
                "ISU_SRT_CD": "stock_code",
                "ISU_NM": "stock_nm",
                "ISU_ABBRV": "stock_abbrv",
                "ISU_ENG_NM": "stock_nm_eng",
                "LIST_DD": "listing_dt",
                "MKT_TP_NM": "market_nm",
                "LIST_SHRS": "outstanding_shares",
            }
        )

        self.logger.info(f"Collected {len(df)} companies from KRX")
        return df
