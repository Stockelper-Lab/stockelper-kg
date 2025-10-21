"""Tests for graph query builders."""

from stockelper_kg.graph.queries import create_stock_query, create_competitor_query


class TestGraphQueries:
    """Test Cypher query builders."""

    def test_create_stock_query(self):
        """Test stock query generation."""
        company = {
            "stock_code": "005930",
            "stock_nm": "삼성전자",
            "stock_abbrv": "삼성전자",
            "stock_nm_eng": "Samsung Electronics",
            "listing_dt": "1975-06-11",
            "market_nm": "KOSPI",
            "outstanding_shares": "5969783",
            "kospi200_item_yn": "Y",
            "capital_stock": 100000,
            "stock_sector_nm": "전기전자",
            "revenue": "1000000",
            "operating_income": "100000",
            "net_income": "80000",
            "total_assets": "5000000",
            "total_liabilities": "2000000",
            "total_equity": "3000000",
            "eps": "5000",
            "pbr": "1.5",
            "per": "15",
        }
        stock_price = {
            "stck_hgpr": 70000,
            "stck_lwpr": 68000,
            "stck_oprc": 69000,
            "stck_clpr": 69500,
        }

        query = create_stock_query("20250101", company, stock_price)

        assert "MERGE (Company:Company" in query
        assert "stock_code: '005930'" in query
        assert "stock_nm: '삼성전자'" in query
        assert "MERGE (Sector:Sector" in query
        assert "MERGE (StockPrice:StockPrice" in query
        assert "stck_clpr: 69500" in query
        assert "MERGE (Date:Date {date: '20250101'})" in query

    def test_create_competitor_query(self):
        """Test competitor query generation."""
        src = {
            "stock_code": "005930",
            "stock_nm": "삼성전자",
            "stock_abbrv": "삼성전자",
            "stock_nm_eng": "Samsung Electronics",
            "listing_dt": "1975-06-11",
            "market_nm": "KOSPI",
            "outstanding_shares": "5969783",
            "kospi200_item_yn": "Y",
            "capital_stock": 100000,
        }
        dst = {
            "stock_code": "000660",
            "stock_nm": "SK하이닉스",
            "stock_abbrv": "SK하이닉스",
            "stock_nm_eng": "SK Hynix",
            "listing_dt": "1996-12-26",
            "market_nm": "KOSPI",
            "outstanding_shares": "728002",
            "kospi200_item_yn": "Y",
            "capital_stock": 50000,
        }

        query = create_competitor_query(src, dst)

        assert "MERGE (Company:Company" in query
        assert "stock_code: '005930'" in query
        assert "MERGE (Competitor:Company" in query
        assert "stock_code: '000660'" in query
        assert "MERGE (Company)-[:HAS_COMPETITOR]->(Competitor)" in query
