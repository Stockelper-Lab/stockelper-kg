# 📊 Knowledge Graph Generator

본 프로젝트는 한국 주식 시장 데이터를 기반으로 **GraphDB(Neo4j)**를 구축하고, 다양한 노드 및 관계를 생성하여 금융 도메인의 지식그래프를 구성하는 도구입니다.  
데이터는 한국투자증권 API, OpenDART, KRX API 등을 활용하여 수집되며, 기업 간 관계와 재무 정보를 Neo4j 기반 그래프로 시각화/분석할 수 있습니다.  

---

## 🚀 Features
- 특정 기간 동안의 **GraphDB 구축 자동화**
- 회사 정보, 주가, 지표, 경쟁사, 재무제표 등 **다양한 노드와 관계 수집**
- Neo4j 서버와 연동하여 **Node & Relation 생성**
- 자연어 질의를 Cypher 쿼리로 변환 (LLM 연동 시 확장 가능)

---

## 🛠️ Installation

### Requirements
- Python >= 3.9
- Neo4j Community/Enterprise Server
- Jupyter Notebook (optional, 테스트 용도)

### Install dependencies
```bash
pip install -r requirements.txt
```
---
## ⚙️ 환경 변수 설정
프로젝트 실행 전에 API Key 및 DB 접속 정보를 .env 파일에 저장해야 합니다.
프로젝트 내부의 sample.env 파일에 해당하는 key 값을 채우고 파일명을 .env로 변경합니다.

```
# DART API 키 정보
OPEN_DART_API_KEY = ''

# 한국투자증권 API 키 정보 (실전투자)
KIS_APP_KEY=''
KIS_APP_SECRET=''
KIS_ACCESS_TOKEN=''
KIS_ACCESS_NUMBER = ''

# 계좌 정보 (선택적)
KIS_ACCOUNT_NUMBER=''
KIS_ACCOUNT_CODE=''

# 모의투자 여부 (true/false)
KIS_VIRTUAL=true

# Neo4j
NEO4J_URI = ''
NEO4J_USER = ''
NEO4J_PASSWORD = ''

# MongoDB
DB_URI = ''
DB_NAME = ''
DB_COLLECTION_NAME = ''
```
---
## 📌 Usage
- GraphDB 구축 (특정 기간)
```
python run_graphdb.py --date_st 20250724 --date_fn 20250725
```
- Jupyter Notebook 테스트
```
jupyter notebook run_graphdb.ipynb
```
---
## 📂 Project Structure

- run_graphdb.py: 특정 기간 동안의 GraphDB를 구축하는 실행 스크립트
```
python run_graphdb.py --date_st 20250724 --date_fn 20250725
```

- stock_graph.py: Graph DB에 포함되는 데이터 수집 함수 구현
  - 환경변수 불러오기
  - 회사 정보 수집
  - 주가 및 지표 정보 수집
  - 경쟁사 정보 수집
  - 재무제표 정보 수집

- stock_knowledge_graph.py: Neo4j 서버에 노드와 관계(Node & Relation)를 생성하는 모듈
- utils.py: 실행 시간 측정 유틸리티, GraphDB 생성 관련 공용 함수
---
## 📜 License
- This project is licensed under the MIT License.
---
## 👨‍💻 Developer
```
Cheonsol Lee
```
