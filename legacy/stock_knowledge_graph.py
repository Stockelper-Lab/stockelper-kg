from dotenv import load_dotenv
from neo4j import GraphDatabase
import os
import logging
import warnings
warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('[Graph DB]')
load_dotenv(dotenv_path=".env")

# 주식 지식그래프 클래스
class StockKnowledgeGraph:
    def __init__(self):
        self.NEO4J_URI = os.getenv("NEO4J_URI")
        self.NEO4J_USER = os.getenv("NEO4J_USER")
        self.NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
        self.driver = GraphDatabase.driver(self.NEO4J_URI, auth=(self.NEO4J_USER, self.NEO4J_PASSWORD))

    def close(self):
        self.driver.close()

    # 제약조건을 1회만 생성
    def ensure_constraints(self):
        with self.driver.session() as session:
            session.execute_write(self._create_constraints)

    # 데이터만 추가 (제약조건은 ensure_constraints에서 한 번만 생성)
    def create_schema(self, cypher_query):
        with self.driver.session() as session:
            session.execute_write(self._create_data, cypher_query)

    # 여러 쿼리를 하나의 트랜잭션으로 실행 (성능 개선)
    def run_queries(self, queries):
        def _run_all(tx, qs):
            for q in qs:
                tx.run(q)
        with self.driver.session() as session:
            session.execute_write(_run_all, queries)

    # 노드 삭제
    def delete_data(self):
        with self.driver.session() as session:
            session.execute_write(self._delete_data)

    # 제약조건 추가
    @staticmethod
    def _create_constraints(tx):
        tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company) REQUIRE c.stock_code IS UNIQUE")
        tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (s:Stock) REQUIRE s.stock_code IS UNIQUE")
        tx.run("CREATE CONSTRAINT IF NOT EXISTS FOR (d:Date) REQUIRE d.date IS UNIQUE")

    # Cypher 쿼리 입력
    @staticmethod
    def _create_data(tx, cypher_query):
        tx.run(cypher_query)

    # 모든 노드와 관계 삭제
    @staticmethod
    def _delete_data(tx):
        tx.run("MATCH (n) DETACH DELETE n")
        print("Knowledge graph schema deleted!")

    # 모든 노드 개수 조회
    def get_node_count(self):
        query = "MATCH (n) RETURN count(n) AS total_node_count"
        with self.driver.session() as session:
            result = session.run(query)
            print(result.single()["total_node_count"])

# 주식 노드 생성
def _create_cypher_query_stock(date, company_dict, stock_price_dict):
    cypher_query = f"""
    // 회사 노드 생성
    MERGE (Company:Company {{
        stock_code: '{company_dict['stock_code']}', 
        stock_nm: '{company_dict['stock_nm']}', 
        stock_abbrv: '{company_dict['stock_abbrv']}',
        stock_nm_eng: '{company_dict['stock_nm_eng']}',
        listing_dt: '{company_dict['listing_dt']}',
        market_nm: '{company_dict['market_nm']}',
        outstanding_shares: '{company_dict['outstanding_shares']}',
        kospi200_item_yn: '{company_dict['kospi200_item_yn']}',
        capital_stock: {company_dict['capital_stock']}
        }})

    // 섹터 노드 생성
    MERGE (Sector:Sector {{
        stock_sector_nm: '{company_dict['stock_sector_nm']}'
        }})
    
    // 주가 노드 생성
    MERGE (StockPrice:StockPrice {{
        stck_hgpr: {stock_price_dict['stck_hgpr']}, 
        stck_lwpr: {stock_price_dict['stck_lwpr']}, 
        stck_oprc: {stock_price_dict['stck_oprc']}, 
        stck_clpr: {stock_price_dict['stck_clpr']}
        }})
    
    // 재무제표 노드 생성
    MERGE (FinancialStatements:FinancialStatements {{
        revenue: '{company_dict['revenue']}', 
        operating_income: '{company_dict['operating_income']}', 
        net_income: '{company_dict['net_income']}',
        total_assets: '{company_dict['total_assets']}', 
        total_liabilities: '{company_dict['total_liabilities']}', 
        total_equity: '{company_dict['total_equity']}', 
        capital_stock: '{company_dict['capital_stock']}'
        }})

    // 지표 노드 생성  'eps', 'pbr', 'per'
    MERGE (Indicator:Indicator {{
        eps: '{company_dict['eps']}',
        pbr: '{company_dict['pbr']}',
        per: '{company_dict['per']}'
        }})
    
    // 날짜 노드 생성
    MERGE (Date:Date {{date: '{date}'}})
    
    // 관계 생성
    MERGE (Company)-[:HAS_STOCK_PRICE]->(StockPrice)
    MERGE (Company)-[:HAS_FINANCIAL_STATEMENTS]->(FinancialStatements)
    MERGE (StockPrice)-[:RECORDED_ON]->(Date)
    MERGE (Company)-[:BELONGS_TO]->(Sector)
    MERGE (Company)-[:HAS_INDICATOR]->(Indicator)
    """
    return cypher_query

# 경쟁사 노드 생성
def _create_cypher_query_competitor(src, dst):
    cypher_query = f"""
    MERGE (Company:Company {{
        stock_code: '{src['stock_code']}', 
        stock_nm: '{src['stock_nm']}', 
        stock_abbrv: '{src['stock_abbrv']}',
        stock_nm_eng: '{src['stock_nm_eng']}',
        listing_dt: '{src['listing_dt']}',
        market_nm: '{src['market_nm']}',
        outstanding_shares: '{src['outstanding_shares']}',
        kospi200_item_yn: '{src['kospi200_item_yn']}',
        capital_stock: {src['capital_stock']}
    }})
    
    MERGE (Competitor:Company {{
        stock_code: '{dst['stock_code']}', 
        stock_nm: '{dst['stock_nm']}', 
        stock_abbrv: '{dst['stock_abbrv']}',
        stock_nm_eng: '{dst['stock_nm_eng']}',
        listing_dt: '{dst['listing_dt']}',
        market_nm: '{dst['market_nm']}',
        outstanding_shares: '{dst['outstanding_shares']}',
        kospi200_item_yn: '{dst['kospi200_item_yn']}',
        capital_stock: {dst['capital_stock']}
    }})
    
    MERGE (Company)-[:HAS_COMPETITOR]->(Competitor)
    """
    return cypher_query
