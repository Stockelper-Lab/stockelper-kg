import logging
from stock_knowledge_graph import _create_cypher_query_stock, _create_cypher_query_competitor
from datetime import datetime
import time
import warnings
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('[Graph DB]')

# 시간 측정 데코레이터
def measure_time(func):
    """함수 실행 시간을 측정하는 데코레이터"""
    def format_time(seconds):
        """초 단위 시간을 시:분:초 형태로 변환"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        log_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return log_str

    def wrapper(*args, **kwargs):
        start_time = time.time()
        logger.info(f"----------------------------------------------------------------------")
        logger.info(f"Start time: {datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 함수 실행
        result = func(*args, **kwargs)
        
        end_time = time.time()
        total_elapsed_time = end_time - start_time
        logger.info(f"End time: {datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info(f"Total Time: {format_time(total_elapsed_time)}")
        return result
    return wrapper
    
def _get_competitor_info(stock_code, graph_df):
    # source: stock_code에 해당하는 회사 정보 저장
    src_company_dict = graph_df[graph_df['stock_code'] == stock_code].iloc[0].to_dict()
    
    # destination: 경쟁사 데이터 추출
    compete_code_li = graph_df[graph_df['stock_code'] == stock_code].compete_code_li.values[0]
    
    dst_company_dict_li = []
    for compete_stock_code in compete_code_li:
        try:
            # source 회사 제외
            if stock_code == compete_stock_code:
                continue
            dst_company_dict = graph_df[graph_df['stock_code'] == compete_stock_code].iloc[0].to_dict()
            dst_company_dict_li.append(dst_company_dict)
        except Exception as e:
            # logging.info(f"경쟁사 없음({stock_code}): {e}")
            continue
    
    return src_company_dict, dst_company_dict_li

# 그래프 DB 생성
def create_graph_db(graph, graph_df, stock_code, date_li):
    try:
        filter_df = graph_df[graph_df['stock_code'] == stock_code]
        company_dict = filter_df.iloc[0].to_dict()

        queries = []
        # 1. 주식 데이터 추가 (날짜별)
        for date in date_li:
            try:
                stock_price_dict = filter_df[filter_df['date'] == date].iloc[0].to_dict()
                cypher_stock_query = _create_cypher_query_stock(date, company_dict, stock_price_dict)
                queries.append(cypher_stock_query)
            except Exception as e:
                logging.error(f"Error: {company_dict['stock_nm']}({stock_code}) 날짜 {date} 추가 불가: {e}")
                continue

        # 2. 경쟁사 데이터 추가
        try:
            src_company_dict, dst_company_dict_li = _get_competitor_info(stock_code, graph_df)
            for dst_company_dict in dst_company_dict_li:
                cypher_competitor_query = _create_cypher_query_competitor(src_company_dict, dst_company_dict)
                queries.append(cypher_competitor_query)
        except Exception as e:
            logging.error(f"Error: 경쟁사 데이터 추가 불가: {e}")

        # 하나의 트랜잭션으로 실행 (성능 개선)
        if queries:
            graph.run_queries(queries)

    except Exception as e:
        logging.error(f"Error: 주식 데이터 생성 불가: {e}")
