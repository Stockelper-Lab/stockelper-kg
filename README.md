# Stockelper Knowledge Graph (KG)

> 한국 주식 시장 지식 그래프 구축을 위한 프로덕션급 Python 패키지

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.11+-018bff.svg)](https://neo4j.com/)

## 목차

- [개요](#개요)
- [주요 기능](#-주요-기능)
- [사전 요구사항](#사전-요구사항)
- [빠른 시작](#-빠른-시작)
- [CLI 명령어](#-cli-명령어)
- [데이터 수집기](#-데이터-수집기)
- [그래프 구조](#-그래프-구조)
- [프로젝트 구조](#프로젝트-구조)
- [테스트](#-테스트)
- [Docker 배포](#-docker-배포)
- [코드 품질](#-코드-품질)
- [운영 가이드](#-운영-가이드)
- [문제 해결](#문제-해결)
- [라이선스](#-라이선스)

## 개요

**Stockelper Knowledge Graph**는 한국 주식 시장 데이터를 Neo4j 기반 지식 그래프로 구축하는 종합 플랫폼입니다. KRX, KIS, DART, MongoDB 등 다양한 데이터 소스를 통합하여 통일된 그래프 데이터베이스를 생성하며, 메모리 효율적인 스트리밍 처리, 자동 중복 제거, GPT-4 기반 이벤트 분류 기능을 제공합니다.

## ✨ 주요 기능

- **스트리밍 모드**: 메모리 효율적인 데이터 수집 및 중단 시 자동 재개 기능
- **다중 데이터 소스**: KRX, KIS(한국투자증권), DART, MongoDB 통합 연동
- **모듈형 설계**: 수집기, 그래프 빌더, 온톨로지 계층 분리
- **중복 제거**: Neo4j 제약조건 기반 안전한 MERGE 연산
- **뉴스 이벤트 파이프라인**: GPT-4 기반 이벤트 분류 및 그래프 업서트
- **효율적 트랜잭션**: 배치 MERGE 쿼리 및 자동 제약조건 생성

## 사전 요구사항

시작하기 전에 다음 항목이 설치되어 있는지 확인하세요:

- **Python**: 3.12 이상 (필수)
- **Docker & Docker Compose**: Neo4j 실행용
- **uv**: Python 패키지 설치 관리자 ([uv 설치하기](https://github.com/astral-sh/uv))

**필수 API 키:**
- [DART API 키](https://opendart.fss.or.kr/) - 금융감독원 전자공시
- [한국투자증권 API](https://apiportal.koreainvestment.com/) - 실시간 주식 데이터
- [OpenAI API 키](https://platform.openai.com/) - 이벤트 파이프라인용 (GPT-4)

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/YOUR_ORG/stockelper-kg.git
cd stockelper-kg
```

### 2. Neo4j 데이터베이스 시작

```bash
docker compose up -d
```

**Neo4j 접속 정보:**
- 브라우저: http://localhost:21004
- Bolt URI: bolt://localhost:21005
- 기본 인증 정보: `neo4j` / `password`

### 3. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 API 키 입력
```

**필수 환경 변수:**
```bash
# DART API (금융감독원)
OPEN_DART_API_KEY=your_opendart_api_key

# 한국투자증권 API
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret

# Neo4j 데이터베이스
NEO4J_URI=bolt://localhost:21005
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# MongoDB (선택사항, 경쟁사 데이터용)
DB_URI=mongodb://localhost:27017
DB_NAME=stockelper
DB_COLLECTION_NAME=competitors

# OpenAI API (이벤트 파이프라인용)
OPENAI_API_KEY=your_openai_api_key
```

### 4. 의존성 설치

```bash
uv sync
```

### 5. 지식 그래프 구축

**권장: 스트리밍 모드**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

**병렬 처리 (2-4개 워커 권장):**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --max-workers 4
```

**기존 그래프에 새 날짜 추가:**
```bash
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

### 6. 뉴스 이벤트 처리 (선택사항)

**단일 파일:**
```bash
uv run stockelper-kg-events --file data/news_articles/article.txt
```

**전체 디렉토리:**
```bash
uv run stockelper-kg-events --dir data/news_articles
```

**JSONL 데이터셋:**
```bash
uv run stockelper-kg-events --dataset data/news_test_cases.jsonl
```

## 📖 CLI 명령어

### stockelper-kg (데이터 수집 및 그래프 구축)

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--date_st` | 시작 날짜 (YYYYMMDD) | 필수 |
| `--date_fn` | 종료 날짜 (YYYYMMDD) | 필수 |
| `--streaming` | 스트리밍 모드 활성화 | False |
| `--max-workers` | 병렬 워커 수 | None (순차 처리) |
| `--no-skip-existing` | 이미 처리된 주식 재처리 | False |
| `--update-only` | 기존 그래프에 새 날짜만 추가 | False |
| `--env` | .env 파일 경로 | .env |

**사용 예시:**
```bash
# 단일 날짜 스트리밍 처리
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# 날짜 범위 처리 (4개 병렬 워커)
uv run stockelper-kg --date_st 20250101 --date_fn 20250107 --streaming --max-workers 4

# 특정 주식만 처리
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --stock-codes 005930,000660
```

### stockelper-kg-events (뉴스/이벤트 처리)

| 옵션 | 설명 |
|------|------|
| `--file` | 단일 텍스트 파일 경로 |
| `--dir` | 디렉토리 경로 (재귀 검색) |
| `--dataset` | JSONL 데이터셋 경로 |
| `--env` | .env 파일 경로 |

**사용 예시:**
```bash
# 단일 뉴스 기사 처리
uv run stockelper-kg-events --file news.txt

# 디렉토리 내 모든 파일 처리
uv run stockelper-kg-events --dir ./data/news_articles

# JSONL 형식 데이터셋 처리
uv run stockelper-kg-events --dataset ./data/news_test_cases.jsonl
```

### stockelper-kg-mongo (MongoDB 유틸리티)

MongoDB에서 주식 데이터를 조회하고 검증하는 도구입니다.

```bash
# 특정 주식 코드 데이터 조회
uv run stockelper-kg-mongo --stock-code 005930 --date 20250101

# 데이터 검증
uv run stockelper-kg-mongo --validate
```

## 🔧 데이터 수집기

### KRXCollector
한국거래소(KRX) 상장 종목 정보 수집
- 종목 코드, 기업명, 상장일
- 시장 분류 (KOSPI/KOSDAQ)
- 시가총액, 거래량, 주가

**수집 항목:**
- `stock_code`: 종목 코드
- `stock_nm`: 종목명
- `market_nm`: 시장 구분
- `listing_dt`: 상장일
- `outstanding_shares`: 상장 주식 수
- `capital_stock`: 자본금

### KISCollector
한국투자증권 API 연동
- 실시간 주가 및 기업 정보
- 자동 토큰 갱신
- API 속도 제한 처리

**수집 항목:**
- `stck_prpr`: 현재가
- `stck_hgpr`: 고가
- `stck_lwpr`: 저가
- `stck_oprc`: 시가
- `acml_vol`: 누적 거래량

### DartCollector
금융감독원 전자공시시스템(DART) 재무제표 수집
- 5개년 재무 데이터
- 대차대조표, 손익계산서, 현금흐름표
- 기업 공시 정보

**수집 항목:**
- `revenue`: 매출액
- `operating_income`: 영업이익
- `net_income`: 순이익
- `total_assets`: 총자산
- `total_equity`: 총자본

### MongoDBCollector
MongoDB 경쟁사 관계 데이터 가져오기
- 기업 경쟁사 네트워크
- 산업 분류
- Airflow DAG에서 수집한 전처리 데이터

### EventCollector
다중 소스 이벤트 수집기 (뉴스 및 기업 이벤트)
- 뉴스 기사 처리
- GPT-4 기반 이벤트 분류
- 시간 기반 이벤트 연결

**이벤트 유형:**
- `earnings`: 실적 발표
- `merger`: 인수합병
- `dividend`: 배당
- `leadership`: 경영진 변동
- `product_launch`: 신제품 출시
- `regulatory`: 규제 관련

## 🏗️ 그래프 구조

### 노드 타입

| 노드 레이블 | 설명 | 주요 속성 |
|------------|------|-----------|
| `Company` | 상장 기업 | code, name, market, sector |
| `StockPrice` | 일별 주가 스냅샷 | date, open, high, low, close, volume |
| `Date` | 캘린더 날짜 | date (YYYYMMDD) |
| `Event` | 기업 이벤트 | type, description, date |
| `Document` | 원본 문서 | title, content, url |

### 관계 타입

| 관계 | 방향 | 설명 |
|-----|------|------|
| `HAS_SNAPSHOT` | Company → StockPrice | 일별 주가 스냅샷 |
| `MENTIONS` | Event → Company | 이벤트가 기업 언급 |
| `COMPETES_WITH` | Company ↔ Company | 경쟁사 관계 |
| `OCCURRED_ON` | Event → Date | 이벤트 발생 날짜 |
| `HAS_DOCUMENT` | Event → Document | 이벤트 원본 문서 |

### Cypher 쿼리 예시

```cypher
-- 삼성전자의 2025년 모든 이벤트 조회
MATCH (c:Company {name: '삼성전자'})<-[:MENTIONS]-(e:Event)-[:OCCURRED_ON]->(d:Date)
WHERE d.date >= '20250101' AND d.date <= '20251231'
RETURN e.type, e.description, d.date
ORDER BY d.date DESC

-- 특정 날짜의 주가 정보 조회
MATCH (c:Company {code: '005930'})-[:HAS_SNAPSHOT]->(s:StockPrice)
WHERE s.date = '20250101'
RETURN c.name, s.open, s.high, s.low, s.close, s.volume

-- 경쟁사 네트워크 조회
MATCH (c:Company {name: '삼성전자'})-[:COMPETES_WITH]-(competitor:Company)
RETURN competitor.name, competitor.code, competitor.market

-- 최근 실적 발표 이벤트 조회
MATCH (e:Event {type: 'earnings'})-[:MENTIONS]->(c:Company)
MATCH (e)-[:OCCURRED_ON]->(d:Date)
WHERE d.date >= '20250101'
RETURN c.name, e.description, d.date
ORDER BY d.date DESC
LIMIT 10

-- 특정 산업의 모든 기업 조회
MATCH (c:Company)
WHERE c.sector = '반도체'
RETURN c.name, c.code, c.market_cap
ORDER BY c.market_cap DESC
```

## 프로젝트 구조

```
stockelper-kg/
├── src/
│   └── stockelper_kg/
│       ├── collectors/              # 데이터 수집 모듈
│       │   ├── base.py             # 기본 Collector 클래스
│       │   ├── krx.py              # KRX 데이터 수집
│       │   ├── kis.py              # 한국투자증권 API
│       │   ├── dart.py             # DART 재무제표
│       │   ├── dart_major_reports.py  # DART 주요 보고서
│       │   ├── mongodb.py          # MongoDB 경쟁사 데이터
│       │   ├── event.py            # 이벤트 수집기
│       │   ├── orchestrator.py     # 수집 오케스트레이터
│       │   └── streaming_orchestrator.py  # 스트리밍 오케스트레이터
│       ├── graph/                   # 그래프 구축 및 연산
│       │   ├── builder.py          # GraphBuilder 클래스
│       │   ├── client.py           # Neo4j 클라이언트
│       │   ├── ontology.py         # 그래프 스키마 정의
│       │   ├── queries.py          # Cypher 쿼리 템플릿
│       │   ├── event.py            # 이벤트 그래프 연산
│       │   ├── cypher.py           # Cypher 쿼리 생성
│       │   ├── payload.py          # 데이터 페이로드 변환
│       │   └── schema.py           # 스키마 정의
│       ├── utils/                   # 유틸리티
│       │   ├── dates.py            # 날짜 처리
│       │   └── logging.py          # 로깅 설정
│       ├── cli.py                   # 메인 CLI 진입점
│       ├── event_cli.py             # 이벤트 파이프라인 CLI
│       ├── mongo_cli.py             # MongoDB CLI
│       └── config.py                # 설정 관리
├── tests/                           # 단위 및 통합 테스트
│   ├── test_config.py
│   ├── test_collectors.py
│   ├── test_graph_builder.py
│   └── integration/
├── docs/                            # 문서
├── migrations/                      # Neo4j 마이그레이션
├── scripts/                         # 배포 스크립트
│   └── entrypoint.sh
├── docker-compose.yml              # Neo4j 설정
├── Dockerfile                      # 애플리케이션 컨테이너
├── pyproject.toml                  # 프로젝트 메타데이터 및 의존성
├── uv.lock                         # 의존성 잠금 파일
├── .env.example                    # 환경 변수 예시
└── README.md
```

## 🧪 테스트

설치를 확인하기 위해 테스트 스위트를 실행합니다:

```bash
# 모든 테스트 실행
uv run pytest

# 커버리지 리포트 포함
uv run pytest --cov=src/stockelper_kg --cov-report=html

# 특정 테스트 파일 실행
uv run pytest tests/test_config.py -v

# 패턴 매칭 테스트 실행
uv run pytest -k "test_collector" -v

# 통합 테스트만 실행 (Neo4j 필요)
uv run pytest tests/integration/ -v
```

커버리지 리포트 확인:
```bash
# HTML 커버리지 리포트 생성
uv run pytest --cov=src/stockelper_kg --cov-report=html

# 브라우저에서 커버리지 리포트 열기
open htmlcov/index.html
```

## 🐳 Docker 배포

### Docker Compose 사용 (권장)

```bash
# Neo4j 데이터베이스 시작
docker compose up -d

# 로그 확인
docker compose logs -f neo4j

# 서비스 중지
docker compose down

# 데이터 볼륨 포함 완전 삭제
docker compose down -v
```

### 애플리케이션 컨테이너 빌드

```bash
# 이미지 빌드
docker build -t stockelper-kg:latest .

# 컨테이너 실행
docker run --rm \
  --env-file .env \
  --network host \
  stockelper-kg:latest \
  --date_st 20250101 --date_fn 20250101 --streaming

# 백그라운드 실행
docker run -d \
  --name stockelper-kg-worker \
  --env-file .env \
  --network host \
  stockelper-kg:latest \
  --date_st 20250101 --date_fn 20250107 --streaming --max-workers 4
```

### 커스텀 Docker Compose 설정

```yaml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.11
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_dbms_memory_heap_max__size: 16G
      NEO4J_dbms_memory_pagecache_size: 4G
    ports:
      - "21004:7474"
      - "21005:7687"
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs

  stockelper-kg:
    build: .
    env_file: .env
    depends_on:
      - neo4j
    command: --date_st 20250101 --date_fn 20250101 --streaming
    restart: on-failure

volumes:
  neo4j_data:
  neo4j_logs:
```

## 🔧 코드 품질

코드 품질 유지 도구:

```bash
# Black으로 코드 포맷팅
uv run black src/ tests/

# isort로 import 정렬
uv run isort src/ tests/

# flake8로 린트
uv run flake8 src/ tests/

# mypy로 타입 체크
uv run mypy src/

# 모든 품질 체크 실행
uv run black src/ tests/ && \
uv run isort src/ tests/ && \
uv run flake8 src/ tests/ && \
uv run mypy src/
```

**코드 스타일 가이드:**
- 최대 줄 길이: 88자 (Black 기본값)
- 타입 힌트 사용 권장
- Docstring: Google 스타일
- 변수명: snake_case
- 클래스명: PascalCase

## 📊 운영 가이드

### 성능 권장사항

- **스트리밍 모드 사용**: 프로덕션에서는 반드시 스트리밍 모드 사용 (중단 시 자동 재개)
- **워커 수 설정**: API 속도 제한을 고려하여 `--max-workers`를 2-4로 설정
- **증분 업데이트**: 일일 업데이트 시 `--update-only` 사용
- **배치 모드 지양**: 대용량 데이터셋에는 레거시 배치 모드 사용하지 않기

### API 속도 제한

- **KIS API**: 초당 약 20회 요청 제한
- **DART API**: 엄격한 제한 없음 (적절한 사용 권장)
- **OpenAI API**: 분당 요청 수 제한 (플랜에 따라 상이)
- **병렬 워커**: 처리량 증가하지만 속도 제한 유발 가능

### 에러 처리

- 스트리밍 모드는 실패 시 자동 재개
- 그래프 작업 실패 시 Neo4j 로그 확인: `docker compose logs neo4j`
- 수집기 실패 시 API 인증 정보 확인
- 네트워크 에러 시 자동 재시도 (최대 3회)

### 프로덕션 체크리스트

- [ ] Neo4j 제약조건 생성 (첫 실행 시 자동)
- [ ] `.env` 파일에 모든 API 키 설정
- [ ] Neo4j 데이터 볼륨 정기 백업 설정
- [ ] Neo4j 데이터 디렉토리 디스크 공간 모니터링
- [ ] API 할당량에 맞는 `--max-workers` 설정
- [ ] 로그 로테이션 설정
- [ ] 모니터링 알람 설정 (Prometheus, Grafana)

### 백업 및 복구

```bash
# Neo4j 데이터 백업
docker exec neo4j neo4j-admin database dump neo4j --to-path=/backups

# 백업 파일 호스트로 복사
docker cp neo4j:/backups/neo4j.dump ./backups/

# 백업에서 복구
docker exec neo4j neo4j-admin database load neo4j --from-path=/backups

# 정기 백업 스크립트 (cron)
# 매일 새벽 2시에 백업
# 0 2 * * * /path/to/backup-script.sh
```

## 문제 해결

### 일반적인 문제

#### 1. Neo4j 연결 실패

**증상**: `ServiceUnavailable: Unable to connect to bolt://localhost:21005`

**해결책**:
```bash
# Neo4j 실행 여부 확인
docker compose ps

# Neo4j 로그 확인
docker compose logs neo4j

# Neo4j 재시작
docker compose restart neo4j

# 네트워크 확인
telnet localhost 21005
```

#### 2. API 인증 에러

**증상**: `401 Unauthorized` 또는 `403 Forbidden`

**해결책**:
- DART API 키 확인: https://opendart.fss.or.kr/
- KIS API 키 및 시크릿 확인
- `.env` 파일의 API 키 형식 확인
- API 사용량 제한 확인

**DART API 키 발급:**
1. https://opendart.fss.or.kr/ 접속
2. 회원가입 및 로그인
3. 인증키 신청 → 즉시 발급

**KIS API 키 발급:**
1. 한국투자증권 계좌 개설
2. https://apiportal.koreainvestment.com/ 접속
3. 앱 등록 → APP Key/Secret 발급

#### 3. 메모리 부족

**증상**: `MemoryError` 또는 `OOM (Out of Memory)`

**해결책**:
```bash
# 스트리밍 모드 사용 (필수)
uv run stockelper-kg --streaming --date_st 20250101 --date_fn 20250101

# 워커 수 줄이기
uv run stockelper-kg --streaming --max-workers 2

# Docker 메모리 할당 증가
docker compose down
# docker-compose.yml에서 Neo4j 메모리 설정 조정
docker compose up -d
```

#### 4. OpenAI API 에러

**증상**: `RateLimitError` 또는 `AuthenticationError`

**해결책**:
- API 키 확인: https://platform.openai.com/api-keys
- 사용량 제한 확인
- GPT-4 모델 권한 확인
- 청구 정보 및 잔액 확인

#### 5. 중복 노드 생성

**증상**: 같은 `stock_code`로 여러 `Company` 노드 생성

**해결책**:
```cypher
-- UNIQUE 제약조건 추가 (자동으로 생성되어야 함)
CREATE CONSTRAINT company_code_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.code IS UNIQUE;

-- 중복 노드 확인
MATCH (c:Company)
WITH c.code AS code, collect(c) AS nodes
WHERE size(nodes) > 1
RETURN code, size(nodes) AS count
ORDER BY count DESC;

-- 중복 노드 병합 (APOC 플러그인 필요)
MATCH (c:Company)
WITH c.code AS code, collect(c) AS nodes
WHERE size(nodes) > 1
CALL apoc.refactor.mergeNodes(nodes, {properties: 'combine'})
YIELD node
RETURN node;
```

#### 6. Import 에러

**증상**: `ModuleNotFoundError` 또는 `ImportError`

**해결책**:
```bash
# 의존성 강제 재설치
uv sync --force

# Python 버전 확인 (반드시 3.12)
python --version

# 가상환경 재생성
rm -rf .venv
uv sync

# 개발 모드로 패키지 설치
uv pip install -e .
```

#### 7. 스트리밍 중단 후 재시작

**증상**: 스트리밍 중 프로세스 종료

**해결책**:
```bash
# 스트리밍 모드는 자동으로 이미 처리된 주식 건너뜀
uv run stockelper-kg --streaming --date_st 20250101 --date_fn 20250107

# 강제로 모두 재처리
uv run stockelper-kg --streaming --date_st 20250101 --date_fn 20250107 --no-skip-existing
```

## 성능 최적화

### Neo4j 튜닝

```conf
# neo4j.conf
dbms.memory.heap.initial_size=8G
dbms.memory.heap.max_size=16G
dbms.memory.pagecache.size=4G

# 쿼리 성능 향상 인덱스
CREATE INDEX company_code IF NOT EXISTS FOR (c:Company) ON (c.code);
CREATE INDEX stock_price_date IF NOT EXISTS FOR (s:StockPrice) ON (s.date);
CREATE INDEX event_date IF NOT EXISTS FOR (e:Event) ON (e.date);
CREATE INDEX date_value IF NOT EXISTS FOR (d:Date) ON (d.date);

# 제약조건
CREATE CONSTRAINT company_code_unique IF NOT EXISTS
FOR (c:Company) REQUIRE c.code IS UNIQUE;
CREATE CONSTRAINT date_value_unique IF NOT EXISTS
FOR (d:Date) REQUIRE d.date IS UNIQUE;
```

### 배치 크기 조정

```python
# src/stockelper_kg/graph/builder.py
class GraphBuilder:
    SNAPSHOT_BATCH_SIZE = 50  # 기본값: 30

# 메모리가 충분한 경우 배치 크기 증가하여 성능 향상
# 메모리가 부족한 경우 배치 크기 감소
```

### 병렬 처리 최적화

```bash
# CPU 코어 수에 따라 조정 (일반적으로 코어 수의 50-75%)
# 4코어: --max-workers 2
# 8코어: --max-workers 4
# 16코어: --max-workers 8

# API 속도 제한 고려
# KIS API는 초당 20회 제한이므로 과도한 병렬화는 오히려 에러 발생
uv run stockelper-kg --streaming --max-workers 4 --date_st 20250101 --date_fn 20250107
```

## 로드맵

향후 개발 계획:

- [ ] 추가 한국 거래소 지원 (KONEX)
- [ ] 실시간 스트리밍 데이터 파이프라인
- [ ] 지식 그래프 쿼리용 GraphQL API
- [ ] 그래프 시각화 웹 UI
- [ ] 백테스팅 프레임워크 통합
- [ ] 해외 주식 시장 지원
- [ ] Airflow DAG 통합
- [ ] Prometheus/Grafana 모니터링 대시보드

## 📄 라이선스

이 프로젝트는 MIT 라이선스에 따라 제공됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 👨‍💻 저자

- **Youngsang Jeong** - 아키텍처 설계, 스트리밍 모드 구현
- **Cheonsol Lee** - 초기 개발, 리팩토링

## 감사의 글

- [Neo4j](https://neo4j.com/) - 그래프 데이터베이스 플랫폼
- [금융감독원 DART](https://opendart.fss.or.kr/) - 재무 데이터 접근
- [한국투자증권](https://www.koreainvestment.com/) - 주식 시장 API
- 프로젝트 개발에 기여한 모든 분들

## 지원

- **이슈**: [GitHub Issues](https://github.com/YOUR_ORG/stockelper-kg/issues)
- **토론**: [GitHub Discussions](https://github.com/YOUR_ORG/stockelper-kg/discussions)
- **이메일**: 개인 문의는 관리자에게 연락

---

❤️ Stockelper-Lab 팀이 만들었습니다
