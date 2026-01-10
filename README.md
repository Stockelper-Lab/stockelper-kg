# Stockelper Knowledge Graph (KG)

> Production-ready Python package for building Korean stock market knowledge graphs with Neo4j

한국 주식 시장 데이터를 Neo4j 지식 그래프로 구축하는 프로덕션급 Python 패키지입니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Neo4j](https://img.shields.io/badge/Neo4j-5.11+-018bff.svg)](https://neo4j.com/)

## Table of Contents

- [Overview](#overview)
- [Features](#-features)
- [Prerequisites](#prerequisites)
- [Quick Start](#-quick-start)
- [CLI Commands](#-cli-commands)
- [Data Collectors](#-data-collectors)
- [Graph Structure](#-graph-structure)
- [Project Structure](#project-structure)
- [Testing](#-testing)
- [Docker Deployment](#-docker-deployment)
- [Code Quality](#-code-quality)
- [Operating Tips](#-operating-tips)
- [Contributing](#contributing)
- [License](#-license)
- [Authors](#-authors)

## Overview

Stockelper-KG is a comprehensive knowledge graph builder for the Korean stock market that integrates multiple data sources (KRX, KIS, OpenDART, MongoDB) into a unified Neo4j graph database. It features efficient streaming processing, automatic deduplication, and event-based news classification using GPT-4.

## ✨ Features

- **Streaming Mode**: Memory-efficient data collection with automatic resume on interruption
- **Multiple Data Sources**: Unified integration of KRX, KIS (Korea Investment & Securities), OpenDART, and MongoDB
- **Modular Design**: Separated collectors, graph builders, and ontology layers
- **Deduplication**: Safe MERGE operations based on Neo4j constraints
- **News Event Pipeline**: GPT-4 powered event classification and graph upsert with event ontology
- **Efficient Transactions**: Batch MERGE queries with automatic constraint creation

<details>
<summary>한국어 설명</summary>

- **스트리밍 모드**: 메모리 효율적 수집, 중단 시 자동 재시작
- **다양한 데이터 소스**: KRX, KIS, OpenDART, MongoDB 통합
- **모듈화 설계**: 수집기/그래프 빌더/온톨로지 분리
- **중복 체크**: Neo4j constraint 기반 안전한 MERGE
- **뉴스 이벤트 파이프라인**: GPT-4o + 이벤트 온톨로지 기반 분류·그래프 업서트
- **효율적 트랜잭션**: 배치 MERGE 쿼리 및 자동 constraint 생성

</details>

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python**: 3.12 (required)
- **Docker & Docker Compose**: For running Neo4j
- **uv**: Python package installer ([Install uv](https://github.com/astral-sh/uv))

**Required API Keys:**
- [OpenDART API Key](https://opendart.fss.or.kr/) - For Korean financial reports
- [Korea Investment & Securities API](https://apiportal.koreainvestment.com/) - For real-time stock data
- [OpenAI API Key](https://platform.openai.com/) - For event pipeline (GPT-4)

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_ORG/stockelper-kg.git
cd stockelper-kg
```

### 2. Start Neo4j Database

```bash
docker compose up -d
```

**Neo4j Access:**
- Browser: http://localhost:21004
- Bolt URI: bolt://localhost:21005
- Default credentials: `neo4j` / `password`

### 3. Configure Environment Variables

```bash
cp .env.example .env
# Edit .env file with your API keys
```

**Required environment variables:**
```bash
# OpenDART API
OPEN_DART_API_KEY=your_opendart_api_key

# Korea Investment & Securities API
KIS_APP_KEY=your_kis_app_key
KIS_APP_SECRET=your_kis_app_secret

# Neo4j Database
NEO4J_URI=bolt://localhost:21005
NEO4J_USER=neo4j
NEO4J_PASSWORD=password

# MongoDB (optional, for competitor data)
DB_URI=mongodb://localhost:27017
DB_NAME=stockelper
DB_COLLECTION_NAME=competitors

# OpenAI API (for event pipeline)
OPENAI_API_KEY=your_openai_api_key
```

### 4. Install Dependencies

```bash
uv sync
```

### 5. Build Knowledge Graph

**Recommended: Streaming mode**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

**Parallel processing (2-4 workers recommended):**
```bash
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --max-workers 4
```

**Update existing graph with new dates:**
```bash
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

### 6. Process News Events (Optional)

**Single file:**
```bash
uv run stockelper-kg-events --file data/news_articles/article.txt
```

**Entire directory:**
```bash
uv run stockelper-kg-events --dir data/news_articles
```

**JSONL dataset:**
```bash
uv run stockelper-kg-events --dataset data/news_test_cases.jsonl
```

## 📖 CLI Commands

### stockelper-kg (Data Collection & Graph Building)

| Option | Description | Default |
|--------|-------------|---------|
| `--date_st` | Start date (YYYYMMDD) | Required |
| `--date_fn` | End date (YYYYMMDD) | Required |
| `--streaming` | Enable streaming mode | False |
| `--max-workers` | Number of parallel workers | None (sequential) |
| `--no-skip-existing` | Reprocess already processed stocks | False |
| `--update-only` | Add only new dates to existing graph | False |
| `--env` | Path to .env file | .env |

**Example:**
```bash
# Process data for a single day with streaming
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# Process date range with 4 parallel workers
uv run stockelper-kg --date_st 20250101 --date_fn 20250107 --streaming --max-workers 4
```

### stockelper-kg-events (News/Event Processing)

| Option | Description |
|--------|-------------|
| `--file` | Path to single text file |
| `--dir` | Directory path (recursive search) |
| `--dataset` | Path to JSONL dataset |
| `--env` | Path to .env file |

**Example:**
```bash
# Process single news article
uv run stockelper-kg-events --file news.txt

# Process all files in directory
uv run stockelper-kg-events --dir ./data/news_articles
```

## 🔧 Data Collectors

### KRXCollector
Collects listed stock information from Korea Exchange (KRX)
- Stock codes, company names, listing dates
- Market classification (KOSPI/KOSDAQ)

### KISCollector
Integrates with Korea Investment & Securities API
- Real-time stock prices and company information
- Automatic token refresh
- Rate limiting handling

### DartCollector
Fetches financial statements from OpenDART
- 5-year financial data
- Balance sheets, income statements, cash flow
- Corporate disclosures

### MongoDBCollector
Imports competitor relationship data from MongoDB
- Company competitor networks
- Industry classifications

### EventCollector
Multi-source event collector for news and corporate events
- News article processing
- Event classification using GPT-4
- Temporal event linking

## 🏗️ Graph Structure

### Node Types

| Node Label | Description | Key Properties |
|------------|-------------|----------------|
| `Company` | Listed companies | code, name, market, sector |
| `StockPrice` | Daily stock snapshots | date, open, high, low, close, volume |
| `Date` | Calendar dates | date (YYYYMMDD) |
| `Event` | Corporate events | type, description, date |
| `Document` | Source documents | title, content, url |

### Relationship Types

| Relationship | From → To | Description |
|-------------|-----------|-------------|
| `HAS_SNAPSHOT` | Company → StockPrice | Daily stock price snapshot |
| `MENTIONS` | Event → Company | Event mentions company |
| `COMPETES_WITH` | Company → Company | Competitor relationship |
| `OCCURRED_ON` | Event → Date | Event temporal link |
| `HAS_DOCUMENT` | Event → Document | Event source document |

**Example Cypher Query:**
```cypher
// Find all events mentioning Samsung Electronics in 2025
MATCH (c:Company {name: '삼성전자'})<-[:MENTIONS]-(e:Event)-[:OCCURRED_ON]->(d:Date)
WHERE d.date >= '20250101' AND d.date <= '20251231'
RETURN e.type, e.description, d.date
ORDER BY d.date DESC
```

## Project Structure

```
stockelper-kg/
├── src/
│   └── stockelper_kg/
│       ├── collectors/          # Data collection modules
│       │   ├── base.py
│       │   ├── krx.py          # KRX data collector
│       │   ├── kis.py          # Korea Investment & Securities API
│       │   ├── dart.py         # OpenDART financial data
│       │   ├── mongodb.py      # MongoDB competitor data
│       │   ├── event.py        # Event collector
│       │   └── streaming_orchestrator.py
│       ├── graph/               # Graph building & operations
│       │   ├── builder.py
│       │   ├── client.py       # Neo4j client
│       │   ├── ontology.py     # Graph schema definitions
│       │   ├── queries.py      # Cypher query templates
│       │   └── event.py        # Event graph operations
│       ├── cli.py              # Main CLI entry point
│       ├── event_cli.py        # Event pipeline CLI
│       └── config.py           # Configuration management
├── tests/                       # Unit and integration tests
├── docs/                        # Documentation
├── docker-compose.yml          # Neo4j setup
├── Dockerfile                  # Application container
├── pyproject.toml              # Project metadata & dependencies
└── README.md
```

## 🧪 Testing

Run the test suite to verify your installation:

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/stockelper_kg --cov-report=html

# Run specific test file
uv run pytest tests/test_config.py -v

# Run tests matching pattern
uv run pytest -k "test_collector" -v
```

View coverage report:
```bash
# Generate HTML coverage report
uv run pytest --cov=src/stockelper_kg --cov-report=html
# Open coverage report in browser
open htmlcov/index.html
```

## 🐳 Docker Deployment

### Using Docker Compose (Recommended)

```bash
# Start Neo4j database
docker compose up -d

# View logs
docker compose logs -f
```

### Building Application Container

```bash
# Build image
docker build -t stockelper-kg:latest .

# Run container
docker run --rm \
  --env-file .env \
  --network stockelper \
  stockelper-kg:latest \
  --date_st 20250101 --date_fn 20250101 --streaming
```

### Custom Docker Compose Setup

```yaml
version: '3.8'
services:
  neo4j:
    image: neo4j:5.11
    environment:
      NEO4J_AUTH: neo4j/password
    ports:
      - "21004:7474"
      - "21005:7687"
    volumes:
      - neo4j_data:/data

  stockelper-kg:
    build: .
    env_file: .env
    depends_on:
      - neo4j
    command: --date_st 20250101 --date_fn 20250101 --streaming

volumes:
  neo4j_data:
```

## 🔧 Code Quality

Maintain code quality with these tools:

```bash
# Format code with Black
uv run black src/ tests/

# Sort imports with isort
uv run isort src/ tests/

# Lint with flake8
uv run flake8 src/ tests/

# Type checking with mypy
uv run mypy src/

# Run all quality checks
uv run black src/ tests/ && \
uv run isort src/ tests/ && \
uv run flake8 src/ tests/ && \
uv run mypy src/
```

## 📊 Operating Tips

**Performance Recommendations:**
- Use streaming mode for production (handles interruptions gracefully)
- Set `--max-workers` to 2-4 to respect API rate limits
- Use `--update-only` for daily incremental updates
- Avoid legacy batch mode for large datasets

**API Rate Limiting:**
- KIS API: ~20 requests/second limit
- OpenDART: No strict limits but be respectful
- Parallel workers increase throughput but may trigger rate limits

**Error Handling:**
- Streaming mode automatically resumes on failure
- Check Neo4j logs if graph operations fail: `docker compose logs neo4j`
- Verify API credentials if collectors fail

**Production Checklist:**
- [ ] Neo4j constraints created (automatic on first run)
- [ ] All API keys configured in `.env`
- [ ] Neo4j data volume backed up regularly
- [ ] Monitor disk space for Neo4j data directory
- [ ] Set appropriate `--max-workers` based on your API quotas

## Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes**
   - Write tests for new functionality
   - Follow existing code style (Black, isort)
   - Update documentation as needed
4. **Run quality checks**
   ```bash
   uv run pytest
   uv run black src/ tests/
   uv run isort src/ tests/
   uv run flake8 src/ tests/
   ```
5. **Submit a pull request**

**Contribution Ideas:**
- Add new data collectors (FRED, Yahoo Finance, etc.)
- Improve event classification ontology
- Add visualization tools
- Write documentation and tutorials
- Report bugs and suggest features

## Troubleshooting

**Common Issues:**

1. **Neo4j connection failed**
   ```bash
   # Check if Neo4j is running
   docker compose ps
   # Check Neo4j logs
   docker compose logs neo4j
   ```

2. **API authentication errors**
   - Verify API keys in `.env` file
   - Check if KIS token needs refresh
   - Ensure OpenDART key is activated

3. **Memory issues**
   - Use streaming mode instead of batch mode
   - Reduce `--max-workers`
   - Increase Docker memory allocation

4. **Import errors**
   - Reinstall dependencies: `uv sync --force`
   - Check Python version: `python --version` (must be 3.12)

## Roadmap

- [ ] Support for additional Korean exchanges (KONEX)
- [ ] Real-time streaming data pipeline
- [ ] GraphQL API for knowledge graph queries
- [ ] Web UI for graph visualization
- [ ] Integration with popular backtesting frameworks
- [ ] Support for international stock markets

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👨‍💻 Authors

- **Youngsang Jeong** - Architecture design, streaming mode implementation
- **Cheonsol Lee** - Initial development, refactoring

## Acknowledgments

- [Neo4j](https://neo4j.com/) for the graph database platform
- [OpenDART](https://opendart.fss.or.kr/) for financial data access
- [Korea Investment & Securities](https://www.koreainvestment.com/) for stock market API
- All contributors who have helped shape this project

## Support

- **Issues**: [GitHub Issues](https://github.com/YOUR_ORG/stockelper-kg/issues)
- **Discussions**: [GitHub Discussions](https://github.com/YOUR_ORG/stockelper-kg/discussions)
- **Email**: Contact the maintainers for private inquiries

---

Made with ❤️ by the Stockelper-Lab team
