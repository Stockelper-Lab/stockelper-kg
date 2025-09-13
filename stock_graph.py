import re
import pandas as pd
import OpenDartReader
import logging
from pymongo import MongoClient
import os
from dotenv import load_dotenv
from utils import measure_time
from datetime import datetime, timedelta
from tqdm import tqdm
import numpy as np
import time
import json
import ast
import requests
import warnings
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('[Graph DB]')
load_dotenv(dotenv_path=".env")

class StockGraph:
    def __init__(self, date_li):
        self.sleep_sec = 0.1
        self.NEO4J_URI = os.getenv("NEO4J_URI")
        self.NEO4J_USER = os.getenv("NEO4J_USER")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
        self.OPEN_DART_API_KEY = os.getenv("OPEN_DART_API_KEY")
        self.DB_URI = os.getenv("DB_URI")
        self.DB_NAME = os.getenv("DB_NAME")
        self.DB_COLLECTION_NAME = os.getenv("DB_COLLECTION_NAME")

        self.KIS_APP_KEY = os.getenv("KIS_APP_KEY")
        self.KIS_APP_SECRET = os.getenv("KIS_APP_SECRET")
        self.KIS_ACCESS_NUMBER = os.getenv("KIS_ACCESS_NUMBER")
        self.KIS_ACCESS_TOKEN = _get_access_token(self.KIS_APP_KEY, self.KIS_APP_SECRET)
        # token_path = "kis_access_token.dat"
        # if os.path.exists(token_path):
        #     with open(token_path, "r") as f:
        #         self.KIS_ACCESS_TOKEN = f.read()
        # else:
        #     self.KIS_ACCESS_TOKEN = None
        #     print(f"{token_path} 파일이 없습니다.")

        # Reuse HTTP session to speed up API calls
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=50)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.company_df = None
        self.price_df = None
        self.competitor_df = None
        self.fs_df = None
        self.total_df = None
        self.date_li = date_li

    # 회사 정보
    @measure_time
    def get_company_info(self):
        logger.info(f"[1. get_company_info...]")
        self.company_df_krx = _get_company_df_krx()
        stock_code_li = self.company_df_krx.stock_code

        company_kis_li = []
        for stock_code in tqdm(stock_code_li, desc='Collect kis company info'):
            _company_kis = _get_company_df_kis(stock_code, self.KIS_APP_KEY, self.KIS_APP_SECRET, self.KIS_ACCESS_TOKEN, self.session)
            company_kis_li.append(_company_kis)
            time.sleep(self.sleep_sec)

        company_df_kis = pd.concat(company_kis_li, ignore_index=True)
        company_df_kis['stock_sector_nm'].replace('', np.nan, inplace=True)
        company_df_kis.fillna('없음', inplace=True)
        self.company_df = pd.merge(self.company_df_krx, company_df_kis, how='left', on='stock_code')

    # 주가, 지표 정보
    @measure_time
    def get_price_info(self):
        logger.info(f"[2. get_price_info...]")
        stock_code_li = self.company_df_krx.stock_code

        price_kis_li = []
        for date in self.date_li:
            for stock_code in tqdm(stock_code_li, desc=f'Collect kis company info (date: {date})'):
                _price_kis = _get_price_df_kis(stock_code, date, date, self.KIS_APP_KEY, self.KIS_APP_SECRET, self.KIS_ACCESS_TOKEN, self.session)
                price_kis_li.append(_price_kis)
                time.sleep(self.sleep_sec)

        self.price_df = pd.concat(price_kis_li, ignore_index=True)

    # 경쟁사 정보
    @measure_time
    def get_competitor_info(self):
        logger.info(f"[3. get_competitor_info...]")
        self.competitor_df = _get_competitor_df(self.DB_URI, self.DB_NAME, self.DB_COLLECTION_NAME)

        stock_code_li = self.company_df_krx.stock_code
        
        # competitor_df가 비어있거나 stock_code 컬럼이 없는 경우 처리
        if self.competitor_df.empty or 'stock_code' not in self.competitor_df.columns:
            existing_stock_codes = set()
        else:
            existing_stock_codes = set(self.competitor_df.stock_code)
            
        missing_stock_codes = set(stock_code_li) - existing_stock_codes
        for stock_code in missing_stock_codes:
            _competitor = pd.DataFrame({'stock_code': [stock_code], 'compete_code_li': [[]]})
            self.competitor_df = pd.concat([self.competitor_df, _competitor], ignore_index=True)

    # 재무제표 정보
    @measure_time
    def get_financial_statements(self):
        logger.info(f"[4. get_financial_statements...]")
        stock_code_li = self.company_df_krx.stock_code
        date = self.date_li[0]

        fs_li = []
        for stock_code in tqdm(stock_code_li, desc=f'Collect financial statements info (date: {date})'):
            _fs = _get_fs_df(stock_code, date, self.OPEN_DART_API_KEY)
            fs_li.append(_fs)
            time.sleep(self.sleep_sec)

        self.fs_df = pd.concat(fs_li, ignore_index=True)

    # 종합
    def create_total_df(self):
        logger.info(f"[5. create_total_df...]")
        self.total_df = pd.merge(self.company_df, self.price_df, on='stock_code', how='left')
        self.total_df = pd.merge(self.total_df, self.competitor_df, on='stock_code', how='left')
        self.total_df = pd.merge(self.total_df, self.fs_df, on='stock_code', how='left')
        return self.total_df

    # 종합 Dataframe 생성
    @measure_time
    def run_all(self):
        self.get_company_info()
        self.get_price_info()
        self.get_competitor_info()
        self.get_financial_statements()
        return self.create_total_df()

# KIS 토큰 로드
def _get_access_token(KIS_APP_KEY, KIS_APP_SECRET):
    url = "https://openapi.koreainvestment.com:9443/oauth2/tokenP"
    headers = {"Content-Type": "application/json"}
    data = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    res = requests.post(url, headers=headers, data=json.dumps(data))
    return res.json()["access_token"]

def get_date_list(date_st, date_fn):
    # 시작 날짜와 종료 날짜를 datetime 객체로 변환
    start_date = datetime.strptime(date_st, '%Y%m%d')  # date_st는 'YYYY-MM-DD' 형식의 문자열
    end_date = datetime.strptime(date_fn, '%Y%m%d')    # date_fn은 'YYYY-MM-DD' 형식의 문자열
    
    # 날짜 리스트 생성
    date_li = []
    current_date = start_date
    while current_date <= end_date:
        date_li.append(current_date.strftime('%Y%m%d'))  # 'YYYY-MM-DD' 형식의 문자열로 변환
        current_date += timedelta(days=1)  # 하루씩 증가
    return date_li
        
# 회사 정보 수집(KRX)
def _get_company_df_krx():
    """
    - 출처: KRX
    - 소요시간: 1초
    """
    url = 'https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'http://data.krx.co.kr/',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    data = {
        'bld': 'dbms/MDC/STAT/standard/MDCSTAT01901',  # 기업개요
        'mktId': 'ALL',  # 전체 시장: KOSPI + KOSDAQ
        'share': '1',
        'csvxls_isNo': 'false'
    }

    res = requests.post(url, headers=headers, data=data)
    res.encoding = 'utf-8-sig'
    json_data = res.json()
    
    df = pd.DataFrame(json_data['OutBlock_1'])
    df['ISU_SRT_CD'] = df['ISU_SRT_CD'].apply(lambda x: x.zfill(6)) # 종목코드 6자리로 통일
    df['LIST_DD'] = pd.to_datetime(df['LIST_DD'])
    df['LIST_SHRS'] = df['LIST_SHRS'].str.replace(',', '').astype(int) # 상장주식수 정수형으로 변경

    col_li = ['ISU_SRT_CD', 'ISU_NM', 'ISU_ABBRV', 'ISU_ENG_NM', 'LIST_DD', 'MKT_TP_NM', 'LIST_SHRS']
    df = df[col_li]
    df = df.rename(columns={'ISU_SRT_CD':'stock_code',
                            'ISU_NM':'stock_nm',
                            'ISU_ABBRV':'stock_abbrv',
                            'ISU_ENG_NM':'stock_nm_eng',
                            'LIST_DD':'listing_dt',
                            'MKT_TP_NM':'market_nm',
                            'LIST_SHRS':'outstanding_shares'})
    return df

# 회사 정보 수집(KIS)
def _get_company_df_kis(stock_code, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCESS_TOKEN, session: requests.Session):
    """
    - 출처: KIS
    - 소요시간: 6분30초
    """
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/search-stock-info"
    headers = {
        "Content-Type": "application/json",
        "authorization": f"Bearer {KIS_ACCESS_TOKEN}",  # Bearer 접두사 포함
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": "CTPF1002R",  # 실전 투자용
        "custtype": "P",
    }
    params = {
        "PRDT_TYPE_CD": "300", # 300: 주식, ETF, ETN, ELW
        "PDNO": stock_code
    }

    res = session.get(url, headers=headers, params=params)
    data = res.json()
    if data.get("rt_cd") != "0":
        print(f"[{stock_code}] 오류 발생: {data.get('msg1')}")
        return None
    if not data:
        print(f"[{stock_code}] 데이터가 없습니다.")
        return None
        
    df = pd.DataFrame([data['output']])
    df["stock_code"] = stock_code  # 종목코드 추가
    df = df[['stock_code','kospi200_item_yn','std_idst_clsf_cd_name']]
    df = df.rename(columns={'std_idst_clsf_cd_name':'stock_sector_nm'})
    return df

# 주식 지표, 주가 수집
def _get_price_df_kis(stock_code, date_st, date_fn, KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCESS_TOKEN, session: requests.Session):
    """
    - 출처: KIS
    - 소요시간: 6분30초
    """
    url = "https://openapi.koreainvestment.com:9443/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
    headers = {
    "Content-Type": "application/json",
    "authorization": f"Bearer {KIS_ACCESS_TOKEN}",
    "appkey": KIS_APP_KEY,
    "appsecret": KIS_APP_SECRET,
    "tr_id": "FHKST03010100",  # 실전 투자용
    "custtype": "P"
    }
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": stock_code,
        "FID_INPUT_DATE_1": date_st,
        "FID_INPUT_DATE_2": date_fn,
        "FID_PERIOD_DIV_CODE": "D",
        "FID_ORG_ADJ_PRC": 1
    }
    res = session.get(url, headers=headers, params=params)
    data = res.json()
    if data.get("rt_cd") != "0":
        print(f"[{stock_code}] 조회 실패: {data.get('msg1')}")
        return None
    if not data:
        print(f"[{stock_code}] 데이터가 없습니다.")
        return None

    try:
        price_dict = {
            'stock_code': stock_code,
            'date': date_st,
            'stck_hgpr': data['output2'][0]['stck_hgpr'],
            'stck_lwpr': data['output2'][0]['stck_lwpr'],
            'stck_oprc': data['output2'][0]['stck_oprc'],
            'stck_clpr': data['output2'][0]['stck_clpr'],
            'eps': data['output1']['eps'],
            'pbr': data['output1']['pbr'],
            'per': data['output1']['per']
        }
        price_df = pd.DataFrame([price_dict])
        return price_df
        
    except Exception as e:
        logger.error(f"Error to DB connection: {e}")
        logger.info(data)

# MongoDB 연동(경쟁사)
def _get_competitor_df(DB_URI, DB_NAME, DB_COLLECTION_NAME):
    try:
        # MongoDB 연결 시도 (타임아웃 설정)
        client = MongoClient(DB_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
        db = client[DB_NAME]
        collection = db[DB_COLLECTION_NAME]
        
        # 연결 테스트
        client.admin.command('ping')
        
        documents = collection.find()
        data = list(documents)
        if data:
            competitor_df = pd.DataFrame(data)
            logger.info("Convert MongoDB to competitor_df")
            competitor_df = competitor_df.rename(columns = {'_id':'stock_code'})
        
            # 'competitors' 컬럼의 각 리스트에서 'code'만 추출하여 새 컬럼 'competitor_li'에 저장
            if 'competitors' in competitor_df.columns:
                competitor_df['compete_code_li'] = competitor_df['competitors'].apply(
                    lambda comp_list: [comp['code'] for comp in comp_list if 'code' in comp] if isinstance(comp_list, list) else []
                )
                competitor_df = competitor_df[['stock_code','compete_code_li']]
            else:
                # competitors 컬럼이 없으면 기본 구조만 생성
                competitor_df = competitor_df[['stock_code']]
                competitor_df['compete_code_li'] = [[] for _ in range(len(competitor_df))]
            return competitor_df
        else:
            logger.info("No data in collection")
            return pd.DataFrame(columns=['stock_code', 'compete_code_li'])  # 빈 DataFrame with columns
    except Exception as e:
        logger.error(f"Failed to DB connection: {e}")
        logger.info("Using empty competitor DataFrame due to connection failure")
        return pd.DataFrame(columns=['stock_code', 'compete_code_li'])  # 빈 DataFrame with columns
    finally:
        try:
            client.close()
        except:
            pass

# 재무제표 정보 추출
def _get_fs_df(stock_code, date, OPEN_DART_API_KEY):
    """
    - 출처: OpenDartReader
    - 소요시간: 20분
    - 컬럼 소개: stock_code(종목코드), revenue(매출액), operating_income(영업이익), net_income(당기순이익), 
               total_assets(자산총계), total_liabilities(부채총계), total_capital(자본총계), capital_stock(자본금),
               year(연도), quarter(분기)
    """

    # 날짜 기준으로 bsns_year와 reprt_code를 순차적으로 생성하는 함수
    def _get_quarter_list(date):
        year = int(date[:4])
        month = int(date[4:6])
    
        # 현재 날짜 기준으로 분기 우선순위 설정
        if month in [1, 2, 3]:
            quarters = [(year-1, '11011', '4')]  # 작년 4분기
        elif month in [4, 5, 6]:
            quarters = [(year, '11013', '1'), (year-1, '11011', '4')]  # 1Q -> 작년 4Q
        elif month in [7, 8, 9]:
            quarters = [(year, '11012', '2'), (year, '11013', '1'), (year-1, '11011', '4')]  # 2Q -> 1Q -> 작년 4Q
        else:
            quarters = [(year, '11014', '3'), (year, '11012', '2'), (year, '11013', '1'), (year-1, '11011', '4')]  # 3Q -> 2Q -> 1Q -> 작년 4Q
        return quarters

    dart = OpenDartReader(OPEN_DART_API_KEY) 
    col_nm_li = ['매출액', '영업이익', '당기순이익', '자산총계', '부채총계', '자본총계', '자본금']
    col_eng_li = ['revenue', 'operating_income', 'net_income', 'total_assets', 'total_liabilities', 'total_equity', 'capital_stock']

    for bsns_year, reprt_code, quarter_nm in _get_quarter_list(date):
        try:
            print()
            print(f"Financial Statements: (stock_code: {stock_code}, year: {bsns_year}, quarter: {quarter_nm})")
            dart_df = dart.finstate(corp=stock_code, bsns_year=str(bsns_year), reprt_code=reprt_code)

            if dart_df is None or len(dart_df) == 0:
                continue

            fs_info = []
            for col_nm in col_nm_li:
                try:
                    value = dart_df[(dart_df['account_nm'] == col_nm) & (dart_df['fs_nm'] == '연결재무제표')]['thstrm_amount'].values
                    if len(value) == 0:
                        value = dart_df[(dart_df['account_nm'] == col_nm) & (dart_df['fs_nm'] == '재무제표')]['thstrm_amount'].values
                    fs_info.append(int(value[0].replace(',', '')) if len(value) > 0 else 0)
                except Exception as e:
                    # print(f"Error processing {stock_code} - {col_nm}: {e}")
                    fs_info.append(0)

            fs_df = pd.DataFrame([fs_info], columns=col_eng_li)
            fs_df['year'] = bsns_year
            fs_df['quarter'] = quarter_nm
            fs_df['stock_code'] = stock_code
            fs_df = fs_df[['stock_code', 'year', 'quarter']+col_eng_li]
            return fs_df

        except Exception as e:
            # print(f"Error fetching data for {stock_code}: {e}")
            continue

    # 모든 분기 시도 실패 시 0으로 채워진 DataFrame 반환
    print(f"No available financial data for {stock_code}")
    fs_df = pd.DataFrame([[0] * len(col_eng_li)], columns=col_eng_li)
    fs_df['year'] = bsns_year
    fs_df['quarter'] = quarter_nm
    fs_df['stock_code'] = stock_code
    fs_df = fs_df[['stock_code', 'year', 'quarter']+col_eng_li]
    return fs_df
