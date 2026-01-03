"""Structured node, edge, and event ontology definitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Literal


PromptDetail = Literal["full", "lite"]


@dataclass(frozen=True)
class NodeProperty:
    """Represents a property belonging to a node definition."""

    name: str
    key: str
    api: str
    method: str

    def to_prompt_dict(self, detail: PromptDetail = "full") -> dict:
        """Serialise to a JSON-friendly dict."""
        data = {"name": self.name, "key": self.key}
        if detail == "full":
            data["api"] = self.api
            data["method"] = self.method
        return data


PrimaryKey = Tuple[str, ...]


@dataclass(frozen=True)
class NodeDefinition:
    """Represents an entity type in the knowledge graph."""

    name: str
    description: str
    separation_reason: str
    examples: Tuple[str, ...]
    primary_keys: Tuple[PrimaryKey, ...]
    properties: Tuple[NodeProperty, ...] = ()

    def to_prompt_dict(self, detail: PromptDetail = "full") -> dict:
        """Serialise to JSON-friendly dict."""
        data = {
            "name": self.name,
            "description": self.description,
            "primary_keys": [
                keys[0] if len(keys) == 1 else " + ".join(keys)
                for keys in self.primary_keys
            ],
        }
        if detail == "full":
            data["separation_reason"] = self.separation_reason
            if self.examples:
                data["examples"] = list(self.examples)
        elif self.examples:
            data["example"] = self.examples[0]
        if self.properties:
            data["properties"] = [
                prop.to_prompt_dict(detail=detail) for prop in self.properties
            ]
        return data


@dataclass(frozen=True)
class EdgeDefinition:
    """Represents a relationship type between entities."""

    name: str
    direction: str
    description: str
    example: str
    symmetric: bool = False

    def to_prompt_dict(self, detail: PromptDetail = "full") -> dict:
        """Serialise to JSON-friendly dict."""
        data = {
            "name": self.name,
            "direction": self.direction,
            "description": self.description,
            "symmetric": self.symmetric,
        }
        if detail == "full" and self.example:
            data["example"] = self.example
        return data


@dataclass(frozen=True)
class EventDefinition:
    """Represents one event type from the ontology."""

    type: str
    description: str
    guideline: str
    required_slots: Tuple[str, ...]
    optional_slots: Tuple[str, ...]

    def to_prompt_dict(self, detail: PromptDetail = "full") -> dict:
        """Serialise to JSON-friendly dict."""
        data = {
            "type": self.type,
            "definition": self.description,
            "slots": {
                "required": list(self.required_slots),
            },
        }
        if detail == "full":
            data["slots"]["optional"] = list(self.optional_slots)
        if self.guideline:
            data["guideline"] = self.guideline
        return data


_NODE_DEFINITIONS: Tuple[NodeDefinition, ...] = (
    NodeDefinition(
        name="Company",
        description="모든 그래프의 중심이 되는 기업 단위 엔티티",
        separation_reason="corp_code 기반으로 고유 식별 가능",
        examples=("삼성전자", "BYD"),
        primary_keys=(
            ("stock_code",),
            ("corp_code",),
            ("corp_name",),
        ),
        properties=(
            NodeProperty(
                "고유번호",
                "corp_code",
                "OpenDART corpCode.xml",
                'dart.corp_code("삼성전자")',
            ),
            NodeProperty(
                "한글명",
                "corp_name",
                "OpenDART company.json",
                'dart.company_profile(cc)["corp_name"]',
            ),
            NodeProperty(
                "영문명",
                "corp_name_eng",
                "OpenDART company.json",
                'dart.company_profile(cc)["corp_name_eng"]',
            ),
            NodeProperty(
                "산업코드",
                "induty_code",
                "OpenDART company.json",
                'dart.company_profile(cc)["induty_code"]',
            ),
            NodeProperty(
                "시장구분",
                "corp_cls",
                "OpenDART company.json",
                'dart.company_profile(cc)["corp_cls"]',
            ),
            NodeProperty(
                "종목코드",
                "stock_code",
                "OpenDART company.json",
                'dart.company_profile(cc)["stock_code"]',
            ),
            NodeProperty(
                "섹터",
                "std_idst_clsf_cd_name",
                "KIS",
                "kis.indicator(stock_code)",
            ),
            NodeProperty(
                "자본금",
                "capital_stock",
                "KIS / OpenDART 재무",
                'dart.finstate_map_accounts(dart.finstate(cc, 2024))["capital_stock"]["value"]',
            ),
        ),
    ),
    NodeDefinition(
        name="Event",
        description="기업의 사건(공시, 뉴스)",
        separation_reason="시점, 영향, 참여 주체가 구분되는 행위 단위",
        examples=("합병", "증설", "규제"),
        primary_keys=(("event_id",),),
        properties=(
            NodeProperty(
                "사건ID",
                "event_id",
                "내부",
                'f"EVT_{rcept_no}"',
            ),
            NodeProperty(
                "유형(L1)",
                "pblntf_ty",
                "OpenDART list.json",
                'row.get("pblntf_ty", "B")',
            ),
            NodeProperty(
                "유형(L2)",
                "pblntf_detail_ty",
                "OpenDART list.json",
                'row.get("pblntf_detail_ty", row.get("report_nm"))',
            ),
            NodeProperty(
                "일자",
                "reported_at",
                "OpenDART list.json",
                'row["rcept_dt"]',
            ),
        ),
    ),
    NodeDefinition(
        name="Document",
        description="원천 데이터(공시, 뉴스 기사)",
        separation_reason="이벤트와 원천 자료를 분리하여 다대다 연결",
        examples=("DART 2025-09A", "연합뉴스 2025-09-01"),
        primary_keys=(
            ("rcept_no",),
            ("document_id",),
            ("url",),
            ("title",),
        ),
        properties=(
            NodeProperty(
                "공시번호",
                "rcept_no",
                "OpenDART list.json",
                'dart.list_filings(cc,"2025-01-01","2025-12-31","B").iloc[0]["rcept_no"]',
            ),
            NodeProperty(
                "제목",
                "report_nm",
                "OpenDART list.json",
                'df.iloc[0]["report_nm"]',
            ),
            NodeProperty(
                "게시일",
                "rcept_dt",
                "OpenDART list.json",
                'df.iloc[0]["rcept_dt"]',
            ),
            NodeProperty(
                "URL",
                "url",
                "DART viewer / 뉴스 링크",
                "dart.document_url(rcept_no)",
            ),
            NodeProperty(
                "본문",
                "body",
                "OpenDART document.xml / 기사 전문",
                "dart.document_text(rcept_no)",
            ),
        ),
    ),
    NodeDefinition(
        name="Person",
        description="임원·대주주 등 실질 주체",
        separation_reason="시계열 관계(임기, 지분)는 엣지에서 표현",
        examples=("이재용", "정용진"),
        primary_keys=(("name_ko", "corp_code"),),
        properties=(
            NodeProperty(
                "이름",
                "name_ko",
                "OpenDART majorstock.json",
                'dart.major_shareholders(cc).iloc[0].get("rprt_nm")',
            ),
        ),
    ),
    NodeDefinition(
        name="Product",
        description="사업보고서의 주요 제품 및 서비스",
        separation_reason="제품군 단위 분석",
        examples=("DRAM", "Galaxy S24"),
        primary_keys=(
            ("product_id",),
            ("name",),
        ),
        properties=(
            NodeProperty(
                "제품ID",
                "product_id",
                "사업보고서 본문",
                'dart.extract_products(text, rcept_no)[0]["product_id"]',
            ),
            NodeProperty(
                "제품명",
                "name",
                "사업보고서 본문",
                'dart.extract_products(text, rcept_no)[0]["name"]',
            ),
            NodeProperty(
                "제품군",
                "category",
                "사업보고서 본문",
                'dart.extract_products(text, rcept_no)[0]["category"]',
            ),
        ),
    ),
    NodeDefinition(
        name="Facility",
        description="생산라인·공장",
        separation_reason="CAPEX/중단 이벤트 반복 축",
        examples=("평택 P3",),
        primary_keys=(("facility_id",),),
        properties=(
            NodeProperty(
                "설비ID",
                "facility_id",
                "사업보고서/주요사항 본문",
                'dart.extract_facilities(text, rcept_no)[0]["facility_id"]',
            ),
            NodeProperty(
                "지역",
                "region",
                "본문",
                'dart.extract_facilities(text, rcept_no)[0].get("region")',
            ),
            NodeProperty(
                "CAPA",
                "capacity",
                "본문",
                'dart.extract_facilities(text, rcept_no)[0].get("capacity")',
            ),
        ),
    ),
    NodeDefinition(
        name="Observation",
        description="시계열 수치 데이터 (가격, 매출, 금리 등)",
        separation_reason="시점별 기록을 독립 노드로 관리",
        examples=("종가", "매출액"),
        primary_keys=(("metric", "observed_at", "corp_code"),),
        properties=(
            NodeProperty(
                "지표명",
                "metric",
                "다양한 원천",
                "도메인별 수집 로직 참조",
            ),
            NodeProperty(
                "값",
                "value",
                "다양한 원천",
                "수집된 시계열 값",
            ),
            NodeProperty(
                "관측일",
                "observed_at",
                "다양한 원천",
                "관측 일자",
            ),
            NodeProperty(
                "단위",
                "unit",
                "다양한 원천",
                "지표 단위",
            ),
        ),
    ),
    NodeDefinition(
        name="Date",
        description="그래프 내 모든 시계열 노드와 사건을 정규화하는 날짜 노드",
        separation_reason="여러 이벤트/관측치가 동일 날짜를 공유하므로 중복을 방지",
        examples=("2025-01-01",),
        primary_keys=(("date",),),
        properties=(
            NodeProperty("날짜", "date", "내부", "YYYY-MM-DD 포맷"),
            NodeProperty("연도", "year", "내부", "int(date[:4])"),
            NodeProperty(
                "월",
                "month",
                "내부",
                'int(date.replace("-", "")[4:6])',
            ),
            NodeProperty(
                "일",
                "day",
                "내부",
                'int(date.replace("-", "")[6:8])',
            ),
        ),
    ),
    NodeDefinition(
        name="PriceDate",
        description="시세 데이터 전용 날짜 노드 (캘린더 Date와 매핑)",
        separation_reason="시세 노드 수가 많아도 공용 Date 과밀을 피하기 위함",
        examples=("2025-01-01",),
        primary_keys=(("date",),),
        properties=(
            NodeProperty("날짜", "date", "내부", "YYYY-MM-DD 포맷"),
            NodeProperty("연도", "year", "내부", "int(date[:4])"),
            NodeProperty(
                "월",
                "month",
                "내부",
                'int(date.replace("-", "")[4:6])',
            ),
            NodeProperty(
                "일",
                "day",
                "내부",
                'int(date.replace("-", "")[6:8])',
            ),
        ),
    ),
    NodeDefinition(
        name="FinancialDate",
        description="재무제표 전용 날짜 노드 (캘린더 Date와 매핑)",
        separation_reason="재무 데이터의 기준/공시일을 캘린더 Date와 분리",
        examples=("2025-02-15",),
        primary_keys=(("date",),),
        properties=(
            NodeProperty("날짜", "date", "내부", "YYYY-MM-DD 포맷"),
            NodeProperty("연도", "year", "내부", "int(date[:4])"),
            NodeProperty(
                "월",
                "month",
                "내부",
                'int(date.replace("-", "")[4:6])',
            ),
            NodeProperty(
                "일",
                "day",
                "내부",
                'int(date.replace("-", "")[6:8])',
            ),
        ),
    ),
    NodeDefinition(
        name="IndicatorDate",
        description="파생 지표 전용 날짜 노드 (캘린더 Date와 매핑)",
        separation_reason="Indicator 시계열을 캘린더 Date로 묶기 전 완충층",
        examples=("2025-01-01",),
        primary_keys=(("date",),),
        properties=(
            NodeProperty("날짜", "date", "내부", "YYYY-MM-DD 포맷"),
            NodeProperty("연도", "year", "내부", "int(date[:4])"),
            NodeProperty(
                "월",
                "month",
                "내부",
                'int(date.replace("-", "")[4:6])',
            ),
            NodeProperty(
                "일",
                "day",
                "내부",
                'int(date.replace("-", "")[6:8])',
            ),
        ),
    ),
    NodeDefinition(
        name="EventDate",
        description="이벤트 전용 날짜 노드 (캘린더 Date와 매핑)",
        separation_reason="뉴스/공시 이벤트의 일자를 캘린더 Date와 분리",
        examples=("2025-01-01",),
        primary_keys=(("date",),),
        properties=(
            NodeProperty("날짜", "date", "내부", "YYYY-MM-DD 포맷"),
            NodeProperty("연도", "year", "내부", "int(date[:4])"),
            NodeProperty(
                "월",
                "month",
                "내부",
                'int(date.replace("-", "")[4:6])',
            ),
            NodeProperty(
                "일",
                "day",
                "내부",
                'int(date.replace("-", "")[6:8])',
            ),
        ),
    ),
    NodeDefinition(
        name="FinancialStatements",
        description="재무제표 계정 단위 데이터",
        separation_reason="정량 값 추적",
        examples=("매출액", "영업이익"),
        # NOTE:
        # - GraphBuilder 및 Neo4j constraint 가 (stock_code, fiscal_year, fiscal_period)
        #   조합을 기본 키로 사용하므로 여기도 동일하게 맞춘다.
        primary_keys=(("stock_code", "fiscal_year", "fiscal_period"),),
        properties=(
            NodeProperty(
                "매출액",
                "revenue",
                "OpenDART finstate()",
                'dart.finstate_map_accounts(dart.finstate(cc, 2024))["revenue"]["value"]',
            ),
            NodeProperty(
                "영업이익",
                "operating_income",
                "OpenDART finstate()",
                '...["operating_income"]["value"]',
            ),
            NodeProperty(
                "당기순이익",
                "net_income",
                "OpenDART finstate()",
                '...["net_income"]["value"]',
            ),
            NodeProperty(
                "자산총계",
                "total_assets",
                "OpenDART finstate()",
                '...["total_assets"]["value"]',
            ),
            NodeProperty(
                "부채총계",
                "total_liabilities",
                "OpenDART finstate()",
                '...["total_liabilities"]["value"]',
            ),
            NodeProperty(
                "자본총계",
                "total_equity",
                "OpenDART finstate()",
                '...["total_equity"]["value"]',
            ),
            NodeProperty(
                "자본금",
                "capital_stock",
                "OpenDART finstate()",
                '...["capital_stock"]["value"]',
            ),
        ),
    ),
    NodeDefinition(
        name="Indicator",
        description="파생 재무지표",
        separation_reason="KIS 등 외부 지표 연동",
        examples=("EPS", "PBR"),
        primary_keys=(("stock_code", "as_of"),),
        properties=(
            NodeProperty(
                "EPS",
                "eps",
                "KIS inquire-price",
                'kis.indicator(stock_code)["eps"]',
            ),
            NodeProperty(
                "PER",
                "per",
                "KIS inquire-price",
                'kis.indicator(stock_code)["per"]',
            ),
            NodeProperty(
                "PBR",
                "pbr",
                "KIS inquire-price",
                'kis.indicator(stock_code)["pbr"]',
            ),
            NodeProperty(
                "BPS",
                "bps",
                "KIS inquire-price",
                'kis.indicator(stock_code)["bps"]',
            ),
        ),
    ),
    NodeDefinition(
        name="StockPrice",
        description="분/일 단위 시세 데이터",
        separation_reason="시장 시세를 Observation과 별도 관리",
        examples=("시가", "종가"),
        primary_keys=(("stock_code", "traded_at"),),
        properties=(
            NodeProperty(
                "시가",
                "stck_oprc",
                "KIS inquire-daily-price",
                'kis.daily_price(stock_code,"20250101","20250131")[0]["stck_oprc"]',
            ),
            NodeProperty(
                "종가",
                "stck_prpr",
                "KIS inquire-daily-price",
                '...["stck_prpr"]',
            ),
            NodeProperty(
                "고가",
                "stck_hgpr",
                "KIS inquire-daily-price",
                '...["stck_hgpr"]',
            ),
            NodeProperty(
                "저가",
                "stck_lwpr",
                "KIS inquire-daily-price",
                '...["stck_lwpr"]',
            ),
            NodeProperty(
                "상한가",
                "stck_mxpr",
                "KIS inquire-daily-price",
                '...["stck_mxpr"]',
            ),
            NodeProperty(
                "하한가",
                "stck_llam",
                "KIS inquire-daily-price",
                '...["stck_llam"]',
            ),
            NodeProperty(
                "전일종가",
                "stck_sdpr",
                "KIS inquire-daily-price",
                '...["stck_sdpr"]',
            ),
        ),
    ),
    NodeDefinition(
        name="Security",
        description="상장 유가증권",
        separation_reason="회사와 종목코드 연결",
        examples=("005930", "000660"),
        primary_keys=(
            ("stock_code",),
            ("isin",),
        ),
        properties=(
            NodeProperty("종목코드", "stock_code", "KRX", "krx.lookup(stock_name)"),
            NodeProperty("ISIN", "isin", "KRX", "krx.lookup_isin(stock_code)"),
            NodeProperty("티커", "ticker", "해외거래소", "custom mapping"),
            NodeProperty("시장", "market", "KRX", "krx.market(stock_code)"),
            NodeProperty("통화", "currency", "KRX/KIS", "krx.currency(stock_code)"),
        ),
    ),
    NodeDefinition(
        name="Metric",
        description="Observation 단위 지표 메타데이터",
        separation_reason="Observation 값의 단위를 명시",
        examples=("PRICE.CLOSE", "SALES"),
        primary_keys=(("metric_id",),),
        properties=(
            NodeProperty("지표ID", "metric_id", "내부", "도메인 정의"),
            NodeProperty("지표명", "name", "내부", "도메인 정의"),
            NodeProperty("단위", "unit", "내부", "도메인 정의"),
            NodeProperty("설명", "description", "내부", "도메인 정의"),
        ),
    ),
)


_EDGE_DEFINITIONS: Tuple[EdgeDefinition, ...] = (
    EdgeDefinition(
        "HAS_SECURITY", "Company → Security", "종목 코드 매핑", "삼성전자 → 005930"
    ),
    EdgeDefinition(
        "ON_DATE", "Company → Date", "회사 단위 날짜 허브 연결", "삼성전자 → 2025-01-01"
    ),
    EdgeDefinition(
        "IS_DATE",
        "PriceDate/FinancialDate/IndicatorDate/EventDate → Date",
        "타입별 날짜를 공용 캘린더 Date에 매핑",
        "PriceDate → 2025-01-01",
    ),
    EdgeDefinition(
        "HAS_STOCK_PRICE",
        "Company → StockPrice",
        "일별 주가 연결",
        "삼성전자 → 2025-01-01",
    ),
    EdgeDefinition(
        "HAS_FINANCIAL_STATEMENTS",
        "Company → FinancialStatements",
        "재무제표 계정 연결",
        "삼성전자 → FY2024 재무제표",
    ),
    EdgeDefinition(
        "REPORTED_ON",
        "FinancialStatements → FinancialDate",
        "재무제표 기준/공시일 연결 (타입별 날짜 노드)",
        "FY2024 재무제표 → 2025-02-15",
    ),
    EdgeDefinition(
        "HAS_INDICATOR",
        "Company → Indicator",
        "파생 재무지표 연결",
        "삼성전자 → EPS/PER",
    ),
    EdgeDefinition(
        "MEASURED_ON",
        "Indicator → IndicatorDate",
        "파생 지표 기준일 연결 (타입별 날짜 노드)",
        "EPS/PER → 2025-01-01",
    ),
    EdgeDefinition(
        "HAS_OFFICER", "Company → Person", "임원/CEO 연결", "삼성전자 → 이재용"
    ),
    EdgeDefinition(
        "HAS_SUBSIDIARY", "Company → Company", "그룹 관계", "SK하이닉스 → 솔리다임"
    ),
    EdgeDefinition(
        "BENEFICIAL_OWNER",
        "Person → Company",
        "지분율 관계",
        "이재용 → 삼성전자 (18.1%)",
    ),
    EdgeDefinition(
        "INVOLVED_IN", "Company → Event", "기업이 사건에 참여", "삼성전자 → 평택 증설"
    ),
    EdgeDefinition(
        "REPORTED_BY", "Event → Document", "출처 연결", "증설 결정 → DART 2025-09"
    ),
    EdgeDefinition(
        "AFFECTS", "Event → Observation", "사건의 영향", "증설 → 주가(+2.1%)"
    ),
    EdgeDefinition(
        "CAUSES", "Event → Event", "사건의 인과관계", "ESS 수요 → 엘앤에프 주가 급등"
    ),
    EdgeDefinition(
        "HAS_PRODUCT", "Company → Product", "제품군 연결", "삼성전자 → DRAM"
    ),
    EdgeDefinition(
        "HAS_FACILITY", "Company → Facility", "생산라인 연결", "삼성전자 → 평택 P3"
    ),
    EdgeDefinition(
        "OF_METRIC", "Observation → Metric", "지표 단위 연결", "70,000원 → PRICE.CLOSE"
    ),
    EdgeDefinition(
        "SIMILAR_TO",
        "Company/Product ↔ Company/Product",
        "산업/제품 유사성",
        "BYD ↔ SERES",
        symmetric=True,
    ),
    EdgeDefinition(
        "SIMILAR_EVENT",
        "Event ↔ Event",
        "내용·시점 유사",
        "증설 ↔ 증설",
        symmetric=True,
    ),
    EdgeDefinition(
        "SUPPLIES_TO", "Company → Company", "제품/서비스 공급 관계", "삼성전자 → Apple"
    ),
    EdgeDefinition(
        "IS_COMPETITOR",
        "Company ↔ Company",
        "경쟁사 관계",
        "삼성전자 ↔ Apple",
        symmetric=True,
    ),
    EdgeDefinition(
        "HAS_EVENT", "Company → Event", "레거시 이벤트 연결", "삼성전자 → 2025Q1"
    ),
    EdgeDefinition(
        "OCCURRED_ON",
        "Event → EventDate",
        "이벤트 발생일 연결 (타입별 날짜 노드)",
        "증설 → 2025-09-01",
    ),
    EdgeDefinition(
        "RECORDED_ON",
        "StockPrice → PriceDate",
        "시세 기록 날짜 (타입별 날짜 노드)",
        "주가 → 2025-09-01",
    ),
)


_EVENT_DEFINITIONS: Tuple[EventDefinition, ...] = (
    EventDefinition(
        "SUPPLY_CAPACITY_CHANGE",
        "공장 건설/증설/감산/생산능력 변경/설비투자",
        "단순 해외 법인 설립은 제외, 설비 투자 동반 시 우선 분류",
        ("date",),
        (
            "facility_id",
            "capacity_delta",
            "duration",
            "total_capacity",
            "investment_amount",
        ),
    ),
    EventDefinition(
        "SUPPLY_HALT",
        "라인/사업장 가동중단",
        "재해/사고 원인이라도 생산 중단이 발생하면 본 타입 우선",
        ("date",),
        ("facility_id", "duration", "reason", "impact"),
    ),
    EventDefinition(
        "DEMAND_SALES_CONTRACT",
        "단일판매/공급계약 체결 또는 해지",
        "수주/발주/계약종료 포함",
        ("counterparty", "contract_value", "date"),
        ("duration", "product_id"),
    ),
    EventDefinition(
        "REVENUE_EARNINGS",
        "분기/연간 실적 발표 (잠정실적 포함)",
        "",
        ("period", "metric", "value", "date"),
        ("consensus_comparison", "previous_comparison"),
    ),
    EventDefinition(
        "EFFICIENCY_AUTOMATION",
        "스마트팩토리/자동화/DX/공정개선 투자",
        "",
        ("date",),
        ("investment_amount", "process", "facility_id", "expected_effect"),
    ),
    EventDefinition(
        "STRATEGY_MNA",
        "M&A/인수합병/지분투자",
        "경영권 확보 목적 시 OWNERSHIP_CHANGE보다 우선",
        ("counterparty", "deal_value", "date"),
        ("region", "mna_type", "stake_percentage"),
    ),
    EventDefinition(
        "STRATEGY_SPINOFF",
        "인적/물적 분할·분할합병",
        "",
        ("counterparty", "date"),
        ("deal_value", "region", "spinoff_type"),
    ),
    EventDefinition(
        "STRATEGY_OVERSEAS",
        "해외 투자/법인 설립/해외 진출",
        "공장 건설 등 생산능력 변경 시 SUPPLY_CAPACITY_CHANGE로 분류",
        ("region", "date"),
        ("investment_amount", "facility_id", "purpose"),
    ),
    EventDefinition(
        "STRATEGY_PARTNERSHIP",
        "전략적 제휴/MOU/합작법인(JV)/공동연구",
        "",
        ("counterparty", "purpose", "date"),
        ("investment_amount", "region", "capacity_plan"),
    ),
    EventDefinition(
        "TECH_NEW_PRODUCT",
        "신제품/신기술/신규 서비스 출시",
        "",
        ("product_id", "date"),
        ("launch_date", "specs", "target_market"),
    ),
    EventDefinition(
        "WORKFORCE_EVENT",
        "인력 감축/채용/파업/노사합의",
        "",
        ("action_type", "num_employees", "date"),
        ("duration", "participants", "reason"),
    ),
    EventDefinition(
        "LEGAL_LITIGATION",
        "소송/특허분쟁/규제기관 제재/벌금",
        "",
        ("counterparty", "date"),
        ("claim_value", "court", "litigation_type"),
    ),
    EventDefinition(
        "CRISIS_EVENT",
        "화재/폭발/횡령/배임/사이버공격",
        "생산 중단이 있으면 SUPPLY_HALT 우선",
        ("incident_type", "location", "date"),
        ("impact", "cause", "damage_estimate"),
    ),
    EventDefinition(
        "PRODUCT_RECALL",
        "리콜/판매중단/품질결함",
        "",
        ("issue", "date"),
        ("product_id", "scope", "cost_impact"),
    ),
    EventDefinition(
        "POLICY_IMPACT",
        "정부 정책/규제 변화/세제 혜택",
        "",
        ("policy_name", "impact_type", "date"),
        ("region", "value"),
    ),
    EventDefinition(
        "VIRAL_EVENT",
        "테마주/밈/유명인 발언",
        "",
        ("trigger", "sector", "date"),
        ("score", "duration"),
    ),
    EventDefinition(
        "OWNERSHIP_CHANGE",
        "최대주주 변경/지분 매각/블록딜",
        "경영권 인수 목적 M&A는 STRATEGY_MNA",
        ("actor", "stake_change", "date"),
        ("purpose", "value"),
    ),
    EventDefinition(
        "REGULATORY_APPROVAL",
        "FDA 승인/품목허가/임상 결과/특허 등록 등 규제 승인",
        "",
        ("regulator", "approval_type", "product_id", "date"),
        ("region", "details"),
    ),
    EventDefinition(
        "CAPITAL_RAISE",
        "유상증자/CB/BW/교환사채/증권신고서/전환청구권 등 자본조달·희석 이벤트",
        "DART 공시의 '결정' 공시가 가장 중요하며, 이후 정정/이행은 보조 신호로 활용",
        ("date",),
        (
            "raise_type",
            "amount",
            "counterparty",
            "issue_price",
            "dilution_ratio",
            "purpose",
        ),
    ),
    EventDefinition(
        "CAPITAL_RETURN",
        "자사주 취득/처분/소각, 배당 등 주주환원 이벤트",
        "주주가치 제고 목적의 자사주 소각/배당은 긍정 신호로 해석될 가능성이 높음",
        ("date",),
        ("action_type", "amount", "share_count", "method", "purpose"),
    ),
    EventDefinition(
        "CAPITAL_STRUCTURE_CHANGE",
        "감자 등 자본구조 변경 이벤트",
        "무상감자는 부정, 유상감자는 상황에 따라 혼재",
        ("date",),
        ("change_ratio", "reason", "method", "impact"),
    ),
    EventDefinition(
        "LISTING_STATUS_CHANGE",
        "거래정지/상장폐지/재개/상폐심사 등 상장상태 변화",
        "상장폐지/거래정지는 극단적 부정 신호가 될 수 있어 우선 분류",
        ("date",),
        ("action_type", "reason", "status", "authority"),
    ),
    EventDefinition(
        "OTHER",
        "위 분류에 해당하지 않는 기타 뉴스",
        "",
        ("description", "date"),
        (),
    ),
)


@dataclass(frozen=True)
class Ontology:
    """Container for graph schema definitions."""

    nodes: Tuple[NodeDefinition, ...] = _NODE_DEFINITIONS
    relationships: Tuple[EdgeDefinition, ...] = _EDGE_DEFINITIONS
    events: Tuple[EventDefinition, ...] = _EVENT_DEFINITIONS

    @property
    def node_map(self) -> Dict[str, NodeDefinition]:
        return {node.name: node for node in self.nodes}

    @property
    def relationship_map(self) -> Dict[str, EdgeDefinition]:
        return {edge.name: edge for edge in self.relationships}

    @property
    def event_map(self) -> Dict[str, EventDefinition]:
        return {event.type: event for event in self.events}


ONTOLOGY = Ontology()


def build_ontology_prompts(detail: PromptDetail = "full") -> dict:
    """Build prompt dictionaries from the ontology for LLM consumption."""
    return {
        "events": [event.to_prompt_dict(detail=detail) for event in ONTOLOGY.events],
        "nodes": [node.to_prompt_dict(detail=detail) for node in ONTOLOGY.nodes],
        "relationships": [
            rel.to_prompt_dict(detail=detail) for rel in ONTOLOGY.relationships
        ],
    }
