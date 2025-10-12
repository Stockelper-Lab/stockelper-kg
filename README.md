# 📊 Stockelper-KG: 한국 주식 지식 그래프 생성기

한국 주식 시장 데이터를 기반으로 **Neo4j 지식 그래프**를 구축하는 프로덕션급 Python 패키지입니다.
한국투자증권 API, OpenDART, KRX API 등을 활용하여 기업 정보, 주가, 재무제표, 경쟁사 관계를 수집하고 Neo4j 그래프 데이터베이스로 구조화합니다.

## ✨ 주요 기능

- 🔄 **스트리밍 모드**: 메모리 효율적인 배치 처리 및 중단 시 자동 재시작
- 📊 **다양한 데이터 소스**: KRX, 한국투자증권, OpenDART, MongoDB 통합
- 🎯 **모듈화 설계**: 확장 가능하고 테스트 가능한 아키텍처
- 🔍 **중복 체크**: Neo4j 기반 자동 중복 검사 및 증분 업데이트
- ⚡ **성능 최적화**: 배치 쿼리 및 트랜잭션 관리
- 🧪 **테스트 완비**: pytest 기반 단위 테스트 및 커버리지 리포팅
- 🐳 **Docker 지원**: 완전한 컨테이너화 및 docker-compose 설정

---

## 🚀 빠른 시작

### 필수 요구사항

- **Python 3.12** (3.13 미만)
- **Docker + Docker Compose** (Neo4j 실행용)
- **uv** (Python 패키지 관리자)
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

**접속 정보:**
- HTTP: `http://localhost:21004`
- Bolt: `bolt://localhost:21005`
- 기본 인증: `neo4j / password`

#### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일에 필수 API 키 입력:
```bash
# OpenDART API 키 (필수)
OPEN_DART_API_KEY=your_dart_api_key

# 한국투자증권 API (필수)
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret
KIS_ACCESS_TOKEN=  # 자동 갱신됨

# Neo4j (docker-compose 기본값)
NEO4J_URI=bolt://localhost:21005
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# MongoDB (경쟁사 데이터)
DB_URI=mongodb://localhost:27017
DB_NAME=stockelper
DB_COLLECTION_NAME=competitors
```

#### 3. 의존성 설치

```bash
uv sync
```

#### 4. 데이터 수집 및 그래프 구축

**스트리밍 모드 (권장):**
```bash
# 특정 날짜 데이터 수집 (중복 자동 스킵)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# 배치 크기 조정 (기본값: 100)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 50
```

**레거시 모드:**
```bash
# 전체 데이터를 메모리에 적재 (비권장)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101
```

---

## 📖 사용법

### CLI 명령어

#### 기본 사용

```bash
# 스트리밍 모드로 특정 날짜 데이터 수집
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

#### 고급 옵션

```bash
# 배치 크기 조정 (메모리 사용량 제어)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 50

# 기존 데이터 재처리 (중복 스킵 비활성화)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --no-skip-existing

# 증분 업데이트 (기존 종목에 새 날짜만 추가)
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only

# 커스텀 .env 파일 사용
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --env /path/to/.env --streaming
```

### Python API 사용

```python
from stockelper_kg.config import Config
from stockelper_kg.graph import Neo4jClient
from stockelper_kg.collectors import StreamingOrchestrator
from stockelper_kg.utils import get_date_list

# 설정 로드
config = Config.from_env(".env")

# Neo4j 클라이언트 초기화
client = Neo4jClient(config.neo4j)
client.ensure_constraints()

# 날짜 리스트 생성
date_list = get_date_list("20250101", "20250101")

# 스트리밍 오케스트레이터 생성
orchestrator = StreamingOrchestrator(
    config=config,
    date_list=date_list,
    neo4j_client=client,
    batch_size=100,
    skip_existing=True,
)

# 데이터 수집 및 그래프 구축
stats = orchestrator.run_streaming()
print(f"처리 완료: {stats}")

# 연결 종료
client.close()
```

### 스트리밍 모드 상세 가이드

스트리밍 모드의 자세한 사용법은 [STREAMING_MODE.md](STREAMING_MODE.md)를 참고하세요.

**주요 장점:**
- ✅ 메모리 효율적 (배치 크기만큼만 적재)
- ✅ 중단 시 자동 재시작 (처리된 종목 스킵)
- ✅ 실시간 진행상황 확인
- ✅ 개별 종목 실패 시에도 계속 진행

---

## 🏗️ 프로젝트 구조

```
stockelper-kg/
├── src/
│   └── stockelper_kg/
│       ├── __init__.py
│       ├── cli.py                    # CLI 진입점
│       ├── config.py                 # 설정 관리 (dataclass)
│       ├── collectors/               # 데이터 수집 모듈
│       │   ├── __init__.py
│       │   ├── base.py              # 추상 베이스 클래스
│       │   ├── krx.py               # KRX 거래소 데이터
│       │   ├── kis.py               # 한국투자증권 API
│       │   ├── dart.py              # OpenDART 재무제표
│       │   ├── mongodb.py           # MongoDB 경쟁사 데이터
│       │   ├── orchestrator.py      # 레거시 오케스트레이터
│       │   └── streaming_orchestrator.py  # 스트리밍 오케스트레이터
│       ├── graph/                    # Neo4j 그래프 관리
│       │   ├── __init__.py
│       │   ├── client.py            # Neo4j 클라이언트
│       │   ├── queries.py           # Cypher 쿼리 빌더
│       │   └── builder.py           # 그래프 빌더
│       └── utils/                    # 유틸리티
│           ├── __init__.py
│           ├── decorators.py        # 성능 측정 데코레이터
│           └── dates.py             # 날짜 처리 유틸
├── tests/                            # 단위 테스트
│   ├── test_config.py
│   ├── test_utils.py
│   └── test_graph_queries.py
├── scripts/                          # 실행 스크립트
│   ├── run_with_uv.sh
│   └── entrypoint.sh
├── docker-compose.yml                # Neo4j 컨테이너 설정
├── Dockerfile                        # 애플리케이션 컨테이너
├── pyproject.toml                    # 프로젝트 메타데이터
├── .env.example                      # 환경 변수 템플릿
├── README.md                         # 이 파일
└── STREAMING_MODE.md                 # 스트리밍 모드 가이드
```

### 모듈 설명

#### Collectors (데이터 수집)
- **BaseCollector**: 모든 수집기의 추상 베이스 클래스
- **KRXCollector**: 한국거래소 상장 종목 정보
- **KISCollector**: 한국투자증권 API (주가, 회사 정보)
- **DartCollector**: OpenDART API (재무제표)
- **MongoDBCollector**: MongoDB에서 경쟁사 관계 조회
- **StreamingOrchestrator**: 배치 스트리밍 및 재시작 지원

#### Graph (그래프 데이터베이스)
- **Neo4jClient**: Neo4j 연결 및 트랜잭션 관리
- **GraphBuilder**: 노드 및 관계 생성 로직
- **queries.py**: Cypher 쿼리 생성 함수

#### Utils (유틸리티)
- **measure_time**: 함수 실행 시간 측정 데코레이터
- **get_date_list**: 날짜 범위 생성

---

## 🧪 개발 및 테스트

### 테스트 실행

```bash
# 모든 테스트 실행
uv run pytest

# 커버리지 리포트 포함
uv run pytest --cov=src/stockelper_kg --cov-report=html

# 특정 테스트 파일만 실행
uv run pytest tests/test_config.py -v
```

### 코드 품질 도구

```bash
# 코드 포맷팅 (Black)
uv run black src/ tests/

# Import 정렬 (isort)
uv run isort src/ tests/

# 린팅 (flake8)
uv run flake8 src/ tests/

# 타입 체크 (mypy)
uv run mypy src/

# 모든 품질 검사 한번에
uv run black src/ tests/ && uv run isort src/ tests/ && uv run flake8 src/ tests/
```

### 개발 환경 설정

```bash
# 개발 의존성 포함 설치
uv sync

# 패키지를 editable 모드로 설치
uv pip install -e .
```

## 🐳 Docker 배포

### Docker Compose로 전체 스택 실행

```bash
# Neo4j 시작
docker compose up -d

# 로그 확인
docker compose logs -f neo4j

# 중지
docker compose down

# 데이터 포함 완전 삭제
docker compose down -v
```

### 애플리케이션 컨테이너 빌드

```bash
# 이미지 빌드
docker build -t stockelper-kg:latest .

# 컨테이너 실행
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
| `KIS_VIRTUAL` | 모의투자 모드 | ❌ | `true` |
| `NEO4J_URI` | Neo4j Bolt URI | ✅ | `bolt://localhost:21005` |
| `NEO4J_USER` | Neo4j 사용자명 | ✅ | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 비밀번호 | ✅ | `password` |
| `DB_URI` | MongoDB URI | ✅ | `mongodb://localhost:27017` |
| `DB_NAME` | MongoDB 데이터베이스명 | ✅ | `stockelper` |
| `DB_COLLECTION_NAME` | MongoDB 컬렉션명 | ✅ | `competitors` |

### CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--date_st` | 시작 날짜 (YYYYMMDD) | 필수 |
| `--date_fn` | 종료 날짜 (YYYYMMDD) | 필수 |
| `--streaming` | 스트리밍 모드 활성화 | `False` |
| `--batch-size` | 배치 크기 (종목 수) | `100` |
| `--no-skip-existing` | 기존 종목 재처리 | `False` |
| `--update-only` | 증분 업데이트만 수행 | `False` |
| `--env` | .env 파일 경로 | `.env` |

## 📊 성능 최적화

### 메모리 사용량

| 모드 | 메모리 사용량 | 2,879개 종목 기준 |
|------|--------------|------------------|
| 레거시 (일괄) | ~8GB | 전체 DataFrame 적재 |
| 스트리밍 (배치 100) | ~300MB | 100개씩 처리 |
| 스트리밍 (배치 50) | ~150MB | 50개씩 처리 |

### 권장 설정

**초기 로드 (안정성 우선):**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 50
```

**일일 업데이트 (속도 우선):**
```bash
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

**대량 재처리:**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 200 --no-skip-existing
```

---

## 🔄 마이그레이션 가이드

### 기존 코드에서 마이그레이션

**이전 방식:**
```python
from stock_graph import StockGraph
from stock_knowledge_graph import StockKnowledgeGraph

# 실행
python run_graphdb.py --date_st 20250101 --date_fn 20250101
```

**새로운 방식:**
```python
from stockelper_kg.collectors import StreamingOrchestrator
from stockelper_kg.graph import Neo4jClient
from stockelper_kg.config import Config

# 실행
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

### 주요 변경사항

1. **모듈 구조**: 단일 파일 → 패키지 구조
2. **설정 관리**: 하드코딩 → dataclass 기반 설정
3. **데이터 처리**: 일괄 처리 → 스트리밍 처리
4. **에러 처리**: 전체 실패 → 개별 종목 격리
5. **재시작**: 처음부터 → 중단 지점부터

자세한 내용은 [REFACTORING_SUMMARY.md](REFACTORING_SUMMARY.md)를 참고하세요.

## 🐛 문제 해결

### 자주 묻는 질문

**Q: 중복 데이터가 생성됩니다**
- A: Neo4j의 UNIQUE constraint가 설정되어 있는지 확인하세요. 첫 실행 시 자동으로 생성됩니다.

**Q: 메모리 부족 오류가 발생합니다**
- A: `--batch-size`를 더 작게 설정하세요 (예: 25 또는 50).

**Q: API 토큰이 만료되었습니다**
- A: 500 에러 발생 시 자동으로 재발급되며 `.env` 파일에 저장됩니다.

**Q: 특정 종목만 재처리하고 싶습니다**
- A: 현재는 전체 재처리만 지원합니다. 향후 업데이트 예정입니다.

**Q: Neo4j 연결이 안됩니다**
- A: `docker compose ps`로 Neo4j가 실행 중인지 확인하고, `.env` 파일의 포트 번호를 확인하세요 (기본: 21005).

## 📚 추가 문서

- [스트리밍 모드 가이드](STREAMING_MODE.md) - 스트리밍 모드 상세 사용법
- [리팩토링 요약](REFACTORING_SUMMARY.md) - 프로젝트 구조 변경 내역
- [.env.example](.env.example) - 환경 변수 템플릿

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

**코드 스타일:**
- Black (line length 88)
- isort (black profile)
- Type hints 사용
- Docstring 작성 (Google style)

## 📜 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.

## 👨‍💻 개발자

- **Cheonsol Lee** - 초기 개발 및 리팩토링
- **Youngsang Jeong** - 아키텍처 설계 및 스트리밍 모드 구현

## 📞 문의

문제가 발생하거나 제안사항이 있으시면 GitHub Issues를 통해 알려주세요.

---

**Built with ❤️ for Korean Stock Market Analysis**
