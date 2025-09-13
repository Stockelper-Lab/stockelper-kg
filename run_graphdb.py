from utils import create_graph_db, measure_time
from tqdm import tqdm
from stock_knowledge_graph import StockKnowledgeGraph
from stock_graph import StockGraph, get_date_list
import argparse
import logging
from datetime import datetime
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('[Graph DB]')

def parse_args():
    parser = argparse.ArgumentParser(description='Generate knowledge graph of stock domain')
    parser.add_argument('--date_st', type=str, required=True, help='Start date (format: YYYYMMDD)')
    parser.add_argument('--date_fn', type=str, required=True, help='Finish date (format: YYYYMMDD)')
    args = parser.parse_args()
    
    # 날짜 형식 검증
    try:
        datetime.strptime(args.date_st, '%Y%m%d')
        datetime.strptime(args.date_fn, '%Y%m%d')
    except ValueError:
        parser.error("Follow date format (format: YYYYMMDD)")
    return args

@measure_time
def main(date_st, date_fn):
    date_li = get_date_list(date_st, date_fn)
    stock_graph = StockGraph(date_li)
    graph_df = stock_graph.run_all()
    
    stock_code_li = graph_df.stock_code
    graph = StockKnowledgeGraph()
    # 제약조건은 1회만 생성
    graph.ensure_constraints()

    for stock_code in tqdm(stock_code_li, total=len(stock_code_li), desc="Generate graph db..."):
        create_graph_db(graph, graph_df, stock_code, date_li)

    # 모든 작업 후에만 닫기
    graph.close()

def cli():
    args = parse_args()
    date_st = args.date_st
    date_fn = args.date_fn
    logger.info(f"Date: {date_st} ~ {date_fn}")
    main(date_st, date_fn)

if __name__ == "__main__":
    cli()

# python run_graphdb.py --date_st 20250724 --date_fn 20250725
