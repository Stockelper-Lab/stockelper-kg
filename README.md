# Stockelper Knowledge Graph (KG)

한국 주식 시장 데이터를 Neo4j 지식 그래프로 구축하는 프로덕션급 Python 패키지입니다.

## ✨ 주요 기능

- **스트리밍 모드**: 메모리 효율적 수집, 중단 시 자동 재시작
- **다양한 데이터 소스**: KRX, KIS, OpenDART, MongoDB 통합
- **모듈화 설계**: 수집기/그래프 빌더/온톨로지 분리
- **중복 체크**: Neo4j constraint 기반 안전한 MERGE
- **뉴스 이벤트 파이프라인**: GPT-4o + 이벤트 온톨로지 기반 분류·그래프 업서트
- **효율적 트랜잭션**: 배치 MERGE 쿼리 및 자동 constraint 생성

## 🚀 빠른 시작

### 1. Neo4j 데이터베이스 시작

```bash
docker compose up -d
```

- HTTP: http://localhost:21004
- Bolt: bolt://localhost:21005
- 기본 인증: neo4j / password

### 2. 환경 변수 설정

```bash
cp .env.example .env
# .env 파일 수정
```

필수 환경 변수:
```bash
# OpenDART
OPEN_DART_API_KEY=

# 한국투자증권
KIS_APP_KEY=
KIS_APP_SECRET=

# Neo4j
NEO4J_URI=bolt://localhost:21005
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# MongoDB
DB_URI=mongodb://localhost:27017
DB_NAME=stockelper
DB_COLLECTION_NAME=competitors

# OpenAI (이벤트 파이프라인용)
OPENAI_API_KEY=
```

### 3. 의존성 설치

```bash
uv sync
```

### 4. 데이터 수집 및 그래프 구축

```bash
# 권장: 스트리밍 모드
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# 병렬 수집 (2-4 workers 권장)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --max-workers 4

# 기존 그래프에 새 날짜만 추가
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

### 5. 뉴스/이벤트 파이프라인

```bash
# 단일 파일
uv run stockelper-kg-events --file data/news_articles/article.txt

# 폴더 전체
uv run stockelper-kg-events --dir data/news_articles

# JSONL 데이터셋
uv run stockelper-kg-events --dataset data/news_test_cases.jsonl
```

## 📖 CLI 명령어

### stockelper-kg (데이터 수집/그래프 구축)

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--date_st` | 시작 날짜 (YYYYMMDD) | 필수 |
| `--date_fn` | 종료 날짜 (YYYYMMDD) | 필수 |
| `--streaming` | 스트리밍 모드 활성화 | False |
| `--max-workers` | 병렬 워커 수 | None (순차) |
| `--no-skip-existing` | 처리된 종목도 재처리 | False |
| `--update-only` | 기존 그래프에 새 날짜만 추가 | False |
| `--env` | .env 파일 경로 | .env |

### stockelper-kg-events (뉴스/이벤트 업서트)

| 옵션 | 설명 |
|------|------|
| `--file` | 단일 텍스트 파일 경로 |
| `--dir` | 디렉터리 경로 (재귀 검색) |
| `--dataset` | JSONL 데이터셋 경로 |
| `--env` | .env 파일 경로 |

## 🔧 데이터 수집기

### KRXCollector
- 상장 종목 정보 (종목코드, 종목명, 상장일 등)

### KISCollector
- 한국투자증권 API
- 실시간 주가/기업 정보
- 자동 토큰 갱신

### DartCollector
- OpenDART 재무제표
- 5년 재무 데이터

### MongoDBCollector
- MongoDB 경쟁사 데이터

### EventCollector
- 다중 소스 이벤트 수집기

## 🏗️ 그래프 구조

### 노드 타입
- Company (기업)
- StockPrice (주가)
- Date (날짜)
- Event (이벤트)
- Document (문서)

### 관계 타입
- HAS_SNAPSHOT (회사 → 주가 스냅샷)
- MENTIONS (이벤트 → 회사)
- COMPETES_WITH (회사 → 경쟁사)

## 🧪 테스트

```bash
# 전체 테스트
uv run pytest

# 커버리지 포함
uv run pytest --cov=src/stockelper_kg --cov-report=html

# 특정 테스트
uv run pytest tests/test_config.py -v
```

## 🐳 Docker 배포

```bash
# Neo4j 시작
docker compose up -d

# 애플리케이션 이미지 빌드
docker build -t stockelper-kg:latest .

# 실행
docker run --rm   --env-file .env   --network stockelper   stockelper-kg:latest   --date_st 20250101 --date_fn 20250101 --streaming
```

## 🔧 코드 품질

```bash
uv run black src/ tests/
uv run isort src/ tests/
uv run flake8 src/ tests/
uv run mypy src/
```

## 📊 운영 팁

- 스트리밍 모드 권장 (처리된 종목 자동 스킵)
- API 레이트리밋 고려하여 `--max-workers` 2-4 설정
- 일일 업데이트는 `--update-only` 사용
- 대규모 데이터는 레거시 배치 모드 비권장

## 📄 라이선스

MIT License

## 👨‍💻 개발자

- Youngsang Jeong - 아키텍처 설계, 스트리밍 모드
- Cheonsol Lee - 초기 개발, 리팩토링
