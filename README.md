# 📊 Stockelper-KG: 한국 주식 지식 그래프 생성기

한국 주식 시장 데이터를 기반으로 **Neo4j 지식 그래프**를 구축하는 프로덕션급 Python 패키지입니다.
한국투자증권 API, OpenDART, KRX API, MongoDB를 활용해 기업·시세·재무·경쟁사 관계를 수집하고, 온톨로지 기반 뉴스/이벤트 그래프까지 통합합니다.

## ✨ 주요 기능

- 🔄 **스트리밍 모드**: 메모리 효율적 수집, 중단 시 자동 재시작, 기존 데이터 자동 스킵
- 📊 **다양한 데이터 소스**: KRX, 한국투자증권, OpenDART, MongoDB 통합
- 🎯 **모듈화 설계**: 수집기/그래프 빌더/온톨로지 분리로 확장성 확보
- 🔍 **중복 체크**: Neo4j constraint를 활용한 안전한 MERGE 업서트
- 🧠 **뉴스 이벤트 파이프라인**: GPT-4o + 이벤트 온톨로지 기반 분류·그래프 업서트
- ⚡ **효율적 트랜잭션**: 배치 MERGE 쿼리 및 constraint 자동 생성
- 🐳 **Docker 지원**: `docker-compose`로 Neo4j 포함 로컬 스택 기동

---

## 🚀 빠른 시작

### 필수 요구사항

- Python 3.12 (3.13 미만)
- Docker + Docker Compose (Neo4j 실행)
- uv (Python 패키지 관리자)
  ```bash
  # Linux/macOS
  curl -LsSf https://astral.sh/uv/install.sh | sh
  
  # macOS (Homebrew)
  brew install uv
  ```

### 설치 및 실행

#### 1. Neo4j 데이터베이스 시작

```bash
docker compose up -d
```

- HTTP: `http://localhost:21004`
- Bolt: `bolt://localhost:21005`
- 기본 인증: `neo4j / password` (`NEO4J_AUTH`로 변경 가능)

#### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env`에 필수 키 입력:

```bash
# OpenDART
OPEN_DART_API_KEY=your_dart_api_key

# 한국투자증권
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_ACCESS_TOKEN=
KIS_ACCESS_NUMBER=
KIS_ACCOUNT_NUMBER=
KIS_ACCOUNT_CODE=
KIS_VIRTUAL=true

# Neo4j (docker-compose 기본값)
NEO4J_URI=bolt://localhost:21005
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
NEO4J_AUTH=neo4j/password

# MongoDB (경쟁사 데이터)
DB_URI=mongodb://localhost:27017
DB_NAME=stockelper
DB_COLLECTION_NAME=competitors

# OpenAI (뉴스/이벤트 파이프라인)
OPENAI_API_KEY=sk-your-openai-key
```

> 뉴스/이벤트 파이프라인을 사용하려면 `OPENAI_API_KEY`가 반드시 필요합니다.

#### 3. 의존성 설치

```bash
uv sync
```

#### 4. 데이터 수집 및 그래프 구축

```bash
# 권장: 스트리밍 모드 (처리된 종목 자동 스킵)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# 병렬 수집 (API 레이트리밋 고려해 2~4 추천)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --max-workers 4

# 기존 그래프 무시 후 전체 재처리
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --no-skip-existing

# 기존 그래프에 새 날짜만 추가
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

레거시 배치 모드(전량 메모리 적재, 재시작 불가):

```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101
```

#### 5. 뉴스/이벤트 파이프라인 실행

GPT-4o와 온톨로지를 사용해 뉴스를 이벤트 그래프로 분류·업서트합니다. `corp_name`/`date`가 해석되면 KRX/KIS/DART 데이터를 추가 수집해 회사 스냅샷도 최신화합니다.

```bash
# 단일 파일 처리
uv run stockelper-kg-events --file data/news_articles/01_Samsung_P4_Expansion.txt

# 폴더 내 모든 텍스트 처리
uv run stockelper-kg-events --dir data/news_articles

# JSONL 데이터셋 일괄 처리 (샘플 제공)
uv run stockelper-kg-events --dataset data/news_test_cases.jsonl
```

- `--file` / `--dir` / `--dataset` 중 하나를 선택합니다.
- JSONL 레코드는 `content`(또는 `text`) 필드에 기사 본문을 넣고, 선택적으로 `metadata`(dict)나 `content_file`(본문 파일 경로) 필드를 사용할 수 있습니다.

---

## 📖 사용법

### CLI 명령어

**stockelper-kg** (데이터 수집/그래프 구축)

```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --max-workers 2
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --env /path/to/.env
```

**stockelper-kg-events** (뉴스/이벤트 업서트)

```bash
uv run stockelper-kg-events --file path/to/article.txt --env .env
uv run stockelper-kg-events --dataset data/news_test_cases.jsonl
```

### Python API 사용

```python
from stockelper_kg.config import Config
from stockelper_kg.collectors.streaming_orchestrator import StreamingOrchestrator
from stockelper_kg.graph import Neo4jClient
from stockelper_kg.utils import get_date_list

config = Config.from_env(".env")

client = Neo4jClient(config.neo4j)
client.ensure_constraints()

date_list = get_date_list("20250101", "20250101")

orchestrator = StreamingOrchestrator(
    config=config,
    date_list=date_list,
    neo4j_client=client,
    env_path=".env",
    skip_existing=True,
    max_workers=2,
)
stats = orchestrator.run_streaming()
print(f"처리 완료: {stats}")

client.close()
```

이벤트 파이프라인도 코드에서 동일하게 호출할 수 있습니다.

```python
from stockelper_kg.pipeline import create_pipeline

pipeline = create_pipeline(Config.from_env(".env"))
pipeline.process("기사 전문을 여기에 입력", metadata={"source": "example"})
```

### 스트리밍 모드 상세 가이드

스트리밍 모드 설명은 `docs/STREAMING_MODE.md`를 참고하세요.

**주요 장점:**
- ✅ 이미 처리된 종목 자동 스킵 및 재시작 지원
- ✅ 메모리 사용 최소화 (종목 단위 처리)
- ✅ 개별 종목 실패에도 전체 파이프라인 지속

---

## 🏗️ 프로젝트 구조

```
stockelper-kg/
├── data/
│   ├── news_articles/                # 샘플 기사 전문
│   └── news_test_cases.jsonl         # JSONL 샘플
├── docs/
│   └── STREAMING_MODE.md             # 스트리밍 모드 가이드
├── src/
│   └── stockelper_kg/
│       ├── __init__.py
│       ├── cli.py                    # 메인 CLI
│       ├── event_cli.py              # 뉴스/이벤트 CLI
│       ├── config.py                 # 설정 관리
│       ├── pipeline.py               # 이벤트 파이프라인
│       ├── collectors/
│       │   ├── base.py
│       │   ├── dart.py
│       │   ├── event.py
│       │   ├── kis.py
│       │   ├── krx.py
│       │   ├── mongodb.py
│       │   ├── orchestrator.py       # 레거시 배치 모드
│       │   └── streaming_orchestrator.py
│       ├── graph/
│       │   ├── builder.py
│       │   ├── client.py
│       │   ├── cypher.py
│       │   ├── event.py
│       │   ├── ontology.py
│       │   ├── payload.py
│       │   ├── queries.py            # 레거시 Cypher 빌더
│       │   └── schema.py
│       └── utils/
│           ├── dates.py
│           └── decorators.py
├── tests/
│   ├── test_config.py
│   ├── test_graph_queries.py
│   └── test_utils.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 모듈 설명

**Collectors**
- `BaseCollector`: 공통 대기/로깅 유틸
- `KRXCollector`: 상장 종목 정보
- `KISCollector`: 한국투자증권 API (주가/기업 정보)
- `DartCollector`: OpenDART 재무제표
- `MongoDBCollector`: 경쟁사 데이터
- `DataOrchestrator`: 레거시 일괄 수집
- `StreamingOrchestrator`: 스트리밍 수집 및 재시작 지원
- `EventCollector`: 이벤트 파이프라인용 단일 종목 스냅샷 수집기

**Graph**
- `Neo4jClient`: 연결 관리, constraint 생성, 기본 쿼리 헬퍼
- `GraphBuilder`: 수집된 DataFrame → 그래프 페이로드 생성 후 MERGE
- `cypher.py`: `GraphPayload` → Cypher MERGE 문 변환 및 constraint 생성
- `ontology.py`: 노드/엣지/이벤트 온톨로지 정의 (LLM 프롬프트 & PK 매핑)
- `payload.py`: 이벤트/주가 스냅샷/경쟁사 GraphPayload 빌더
- `schema.py`: GraphPayload/노드/엣지 데이터 구조
- `event.py`: GPT-4o 기반 이벤트 분류
- `queries.py`: 레거시 Cypher 생성기

**News / Event Pipeline**
- `event_cli.py`: 파일/디렉터리/JSONL 입력을 받아 이벤트 업서트
- `pipeline.EventPipeline`: LLM 분류 → 그래프 업서트 → 필요 시 KRX/KIS/DART 재수집
- `collectors.event.EventCollector`: 단일 종목의 가격/재무/경쟁사 데이터를 병합 수집
- 샘플 데이터: `data/news_articles`, `data/news_test_cases.jsonl`

**Utils**
- `measure_time` (`decorators.py`): 실행 시간 측정
- `get_date_list`, `normalize_date`, `build_date_properties` (`dates.py`)

---

## 🧪 개발 및 테스트

```bash
# 모든 테스트 실행 (pyproject의 기본 addopts 포함)
uv run pytest

# 커버리지 HTML 리포트 추가
uv run pytest --cov=src/stockelper_kg --cov-report=html

# 특정 테스트만 실행
uv run pytest tests/test_config.py -v
```

### 코드 품질 도구

```bash
uv run black src/ tests/
uv run isort src/ tests/
uv run flake8 src/ tests/
uv run mypy src/
```

### 개발 환경 설정

```bash
uv sync
uv pip install -e .
```

## 🐳 Docker 배포

```bash
docker network create stockelper   # 최초 1회: compose에서 사용하는 네트워크
docker compose up -d           # Neo4j 시작
docker compose logs -f neo4j   # 로그 확인
docker compose down            # 중지
docker compose down -v         # 데이터까지 삭제
```

애플리케이션 이미지는 다음과 같이 실행합니다.

```bash
docker build -t stockelper-kg:latest .
docker run --rm \
  --env-file .env \
  --network stockelper \
  stockelper-kg:latest \
  --date_st 20250101 --date_fn 20250101 --streaming
```

## 🔧 설정 옵션

### 환경 변수

| 변수 | 설명 | 필수 | 기본값 |
|------|------|------|--------|
| `OPEN_DART_API_KEY` | OpenDART API 키 | ✅ | - |
| `KIS_APP_KEY` | 한국투자증권 앱 키 | ✅ | - |
| `KIS_APP_SECRET` | 한국투자증권 시크릿 | ✅ | - |
| `KIS_ACCESS_TOKEN` | 액세스 토큰 (자동 갱신) | ❌ | - |
| `KIS_ACCESS_NUMBER` | 사용자 식별 번호 | ❌ | - |
| `KIS_ACCOUNT_NUMBER` | 계좌번호 | ❌ | - |
| `KIS_ACCOUNT_CODE` | 계좌 구분 코드 | ❌ | - |
| `KIS_VIRTUAL` | 모의투자 모드 | ❌ | `true` |
| `NEO4J_URI` | Neo4j Bolt URI | ✅ | `bolt://localhost:21005` |
| `NEO4J_USER` | Neo4j 사용자명 | ✅ | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | ✅ | `password` |
| `NEO4J_AUTH` | Docker용 Neo4j 인증 | ❌ | `neo4j/password` |
| `DB_URI` | MongoDB URI | ✅ | `mongodb://localhost:27017` |
| `DB_NAME` | MongoDB 데이터베이스명 | ✅ | `stockelper` |
| `DB_COLLECTION_NAME` | MongoDB 컬렉션명 | ✅ | `competitors` |
| `OPENAI_API_KEY` | 뉴스/이벤트 파이프라인용 GPT-4o 키 | ❌* | - |

\* `stockelper-kg-events` 실행 시 필수

### CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--date_st` | 시작 날짜 (YYYYMMDD) | 필수 |
| `--date_fn` | 종료 날짜 (YYYYMMDD) | 필수 |
| `--streaming` | 스트리밍 모드 활성화 | `False` |
| `--max-workers` | 병렬 워커 수 (None이면 순차 처리) | `None` |
| `--no-skip-existing` | 이미 처리된 종목도 재처리 | `False` |
| `--update-only` | 기존 그래프에 새 날짜만 추가 (스트리밍 전용) | `False` |
| `--env` | .env 파일 경로 | `.env` |

## 📊 운영 팁

- 스트리밍 모드가 기본이며, Neo4j에 존재하는 종목은 자동 스킵됩니다. 전체 재처리가 필요하면 `--no-skip-existing`을 사용하세요.
- 레이트리밋을 피하려면 `--max-workers`를 2~4 사이로 설정하고 필요 시 순차 처리로 전환하세요.
- 일일 업데이트에는 `--update-only`가 가장 빠릅니다.
- 레거시 모드는 모든 데이터를 메모리에 적재하므로 대규모 데이터에는 비권장입니다.

## 🔄 마이그레이션 가이드

**기존 방식:**

```python
from stock_graph import StockGraph
from stock_knowledge_graph import StockKnowledgeGraph
python run_graphdb.py --date_st 20250101 --date_fn 20250101
```

**현재 방식:**

```python
from stockelper_kg.collectors import StreamingOrchestrator
from stockelper_kg.graph import Neo4jClient
from stockelper_kg.config import Config

uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

### 주요 변경사항

1. 단일 파일 스크립트 → 패키지 구조
2. 설정 하드코딩 → dataclass 기반 `Config.from_env`
3. 일괄 처리 → 스트리밍 + 자동 재시작
4. LLM 이벤트 온톨로지 추가 (`stockelper-kg-events`)

## 🐛 문제 해결

- **중복 데이터 생성**: 첫 실행 시 `Neo4jClient.ensure_constraints()`가 constraint를 생성합니다. 스키마 권한을 확인하세요.
- **메모리 부족**: 스트리밍 모드에서 실행하거나 병렬 워커 수를 줄이세요.
- **API 토큰 만료**: KIS 토큰은 자동 재발급되어 `.env`에 저장됩니다. 실패 시 재시도하세요.
- **Neo4j 연결 실패**: `docker compose ps`로 컨테이너 상태를 확인하고 포트(`21005`)와 비밀번호를 점검하세요.

## 📚 추가 문서

- `docs/STREAMING_MODE.md` - 스트리밍 모드 가이드
- `.env.example` - 환경 변수 템플릿
- `data/news_test_cases.jsonl` - 이벤트 파이프라인 입력 예시

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**코드 스타일**
- Black (line length 88)
- isort (black profile)
- Type hints 권장
- Google 스타일 Docstring

## 📜 라이선스

MIT License - [LICENSE](LICENSE) 참고

## 👨‍💻 개발자

- **Cheonsol Lee** - 초기 개발 및 리팩토링
- **Youngsang Jeong** - 아키텍처 설계 및 스트리밍 모드 구현

## 📞 문의

문제가 발생하거나 제안사항이 있으시면 GitHub Issues로 알려주세요.

---

**Built with ❤️ for Korean Stock Market Analysis**
