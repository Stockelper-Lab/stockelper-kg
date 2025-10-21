"""Cypher query builders for Neo4j."""

from typing import Dict


def create_stock_query(date: str, company: Dict, stock_price: Dict) -> str:
    """Create Cypher query for stock node and relationships.

    Args:
        date: Date in YYYYMMDD format
        company: Company information dictionary
        stock_price: Stock price information dictionary

    Returns:
        Cypher query string
    """
    query = f"""
    // Create Company node
    MERGE (Company:Company {{
        stock_code: '{company['stock_code']}', 
        stock_nm: '{company['stock_nm']}', 
        stock_abbrv: '{company['stock_abbrv']}',
        stock_nm_eng: '{company['stock_nm_eng']}',
        listing_dt: '{company['listing_dt']}',
        market_nm: '{company['market_nm']}',
        outstanding_shares: '{company['outstanding_shares']}',
        kospi200_item_yn: '{company['kospi200_item_yn']}',
        capital_stock: {company['capital_stock']}
        }})

    // Create Sector node
    MERGE (Sector:Sector {{
        stock_sector_nm: '{company['stock_sector_nm']}'
        }})
    
    // Create StockPrice node
    MERGE (StockPrice:StockPrice {{
        stck_hgpr: {stock_price['stck_hgpr']}, 
        stck_lwpr: {stock_price['stck_lwpr']}, 
        stck_oprc: {stock_price['stck_oprc']}, 
        stck_clpr: {stock_price['stck_clpr']}
        }})
    
    // Create FinancialStatements node
    MERGE (FinancialStatements:FinancialStatements {{
        revenue: '{company['revenue']}', 
        operating_income: '{company['operating_income']}', 
        net_income: '{company['net_income']}',
        total_assets: '{company['total_assets']}', 
        total_liabilities: '{company['total_liabilities']}', 
        total_equity: '{company['total_equity']}', 
        capital_stock: '{company['capital_stock']}'
        }})

    // Create Indicator node
    MERGE (Indicator:Indicator {{
        eps: '{company['eps']}',
        pbr: '{company['pbr']}',
        per: '{company['per']}'
        }})
    
    // Create Date node
    MERGE (Date:Date {{date: '{date}'}})
    
    // Create relationships
    MERGE (Company)-[:HAS_STOCK_PRICE]->(StockPrice)
    MERGE (Company)-[:HAS_FINANCIAL_STATEMENTS]->(FinancialStatements)
    MERGE (StockPrice)-[:RECORDED_ON]->(Date)
    MERGE (Company)-[:BELONGS_TO]->(Sector)
    MERGE (Company)-[:HAS_INDICATOR]->(Indicator)
    """
    return query


def create_competitor_query(src: Dict, dst: Dict) -> str:
    """Create Cypher query for competitor relationship.

    Args:
        src: Source company information dictionary
        dst: Destination (competitor) company information dictionary

    Returns:
        Cypher query string
    """
    query = f"""
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
    return query
