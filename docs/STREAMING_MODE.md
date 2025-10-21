# 스트리밍 모드 사용 가이드

## 개요

스트리밍 모드는 대용량 데이터 수집 시 메모리 효율성과 중단 시 재시작 기능을 제공하는 개선된 데이터 수집 방식입니다.

## 주요 기능

### ✅ 중복 체크 및 재시작
- 중간에 중단되어도 이미 처리된 종목은 자동으로 스킵
- Neo4j에서 처리된 종목 목록을 자동으로 확인
- 실패한 종목만 재처리 가능

### ✅ 메모리 효율성
- 배치 단위로 데이터 수집 및 업로드
- 전체 데이터를 메모리에 적재하지 않음
- 종목별로 즉시 Neo4j에 업로드 후 메모리 해제

### ✅ 실시간 진행상황
- 배치별 처리 현황 실시간 표시
- 성공/실패 통계 즉시 확인
- 실패한 종목 목록 자동 기록

### ✅ 증분 업데이트
- 기존 종목에 새로운 날짜 데이터만 추가
- 불필요한 중복 수집 방지
- 일일 업데이트에 최적화

## 사용법

### 1. 기본 스트리밍 모드 (권장)

```bash
# 스트리밍 모드로 실행 (중복 자동 스킵)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming

# 배치 크기 조정 (기본값: 100)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 50
```

### 2. 중단 후 재시작

```bash
# 중간에 Ctrl+C로 중단했다가 다시 실행하면
# 이미 처리된 종목은 자동으로 스킵하고 이어서 진행
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming
```

**출력 예시:**
```
Found 1500 stocks already in database
Will process 1379 stocks (skipping 1500 existing)
```

### 3. 기존 종목 재처리 (강제)

```bash
# 이미 존재하는 종목도 다시 처리
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --no-skip-existing
```

### 4. 증분 업데이트 (날짜만 추가)

```bash
# 기존 종목에 새로운 날짜 데이터만 추가
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

**사용 시나리오:**
- 1월 1일 데이터로 초기 로드 완료
- 1월 10일 데이터를 추가하고 싶을 때
- `--update-only` 옵션으로 기존 종목에 새 날짜만 추가

### 5. 레거시 배치 모드 (비권장)

```bash
# 기존 방식 (메모리 많이 사용, 중단 시 처음부터 재시작)
uv run stockelper-kg --date_st 20250101 --date_fn 20250101
```

## 옵션 설명

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--streaming` | 스트리밍 모드 활성화 | False |
| `--batch-size` | 배치 크기 (종목 수) | 100 |
| `--no-skip-existing` | 기존 종목도 재처리 | False (스킵함) |
| `--update-only` | 기존 종목에 날짜만 추가 | False |
| `--env` | .env 파일 경로 | .env |

## 처리 흐름

### 스트리밍 모드

```
1. 정적 데이터 수집 (1회)
   └─ 회사 정보 (KRX)
   └─ 경쟁사 정보 (MongoDB)

2. Neo4j에서 처리된 종목 확인
   └─ 이미 존재하는 종목 스킵

3. 배치별 처리 (100개씩)
   ├─ 종목 1: 수집 → Neo4j 업로드 → 메모리 해제
   ├─ 종목 2: 수집 → Neo4j 업로드 → 메모리 해제
   └─ ...

4. 통계 출력
   └─ 처리/스킵/실패 종목 수
```

### 레거시 모드

```
1. 전체 데이터 수집 (메모리에 적재)
   ├─ 회사 정보 (2,879개)
   ├─ 주가 정보 (2,879 × N일)
   ├─ 경쟁사 정보
   └─ 재무제표 정보

2. DataFrame 병합 (메모리 부담)

3. Neo4j 업로드 (종목별 순차)
```

## 성능 비교

| 항목 | 레거시 모드 | 스트리밍 모드 |
|------|------------|--------------|
| **메모리 사용** | 높음 (전체 적재) | 낮음 (배치만) |
| **중단 시 재시작** | 처음부터 | 이어서 진행 |
| **진행상황 확인** | 수집 완료 후 | 실시간 |
| **API 부하** | 한번에 집중 | 분산 |
| **실패 처리** | 전체 실패 | 종목별 스킵 |

## 로그 예시

### 정상 처리
```
======================================================================
Starting streaming data collection with resume capability
======================================================================
[1. Collecting static data (company + competitors)...]
Collected 2879 companies from KRX
Collected competitor data from MongoDB
Found 0 stocks already in database
Will process 2879 stocks (skipping 0 existing)

======================================================================
Processing batch 1/29 (100 stocks)
======================================================================
Processing batch: 100%|████████████| 100/100 [05:23<00:00,  3.23s/it]
Batch 1 complete: 98 success, 2 failed

======================================================================
Processing batch 2/29 (100 stocks)
======================================================================
...
```

### 재시작 시
```
Found 1500 stocks already in database
Will process 1379 stocks (skipping 1500 existing)

======================================================================
Processing batch 1/14 (100 stocks)
======================================================================
[005930] Already exists, skipping
[000660] Already exists, skipping
[051910] Collecting data...
```

## 에러 처리

### 개별 종목 실패
- 특정 종목 실패 시 해당 종목만 스킵하고 계속 진행
- 실패한 종목 목록은 로그에 기록
- 재실행 시 실패한 종목만 다시 시도 가능

### API 토큰 만료
- 500 에러 발생 시 자동으로 토큰 재발급
- `.env` 파일에 새 토큰 자동 저장
- 재시도 로직으로 자동 복구

### 네트워크 오류
- 재시도 로직 (최대 3회)
- 지수 백오프 (1초, 3초, 9초)
- 실패 시 다음 종목으로 진행

## 권장 사항

### 초기 로드
```bash
# 배치 크기를 작게 설정하여 안정성 확보
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 50
```

### 일일 업데이트
```bash
# 증분 업데이트로 새 날짜만 추가
uv run stockelper-kg --date_st 20250110 --date_fn 20250110 --streaming --update-only
```

### 대량 재처리
```bash
# 배치 크기를 크게 설정하여 속도 향상
uv run stockelper-kg --date_st 20250101 --date_fn 20250101 --streaming --batch-size 200 --no-skip-existing
```

## 문제 해결

### Q: 중복 데이터가 생성됩니다
A: Neo4j의 MERGE 쿼리가 제대로 작동하는지 확인하세요. `stock_code`가 unique constraint로 설정되어 있어야 합니다.

### Q: 메모리가 부족합니다
A: `--batch-size`를 더 작게 설정하세요 (예: 50 또는 25).

### Q: 특정 종목만 재처리하고 싶습니다
A: 현재는 전체 재처리만 지원합니다. 향후 업데이트 예정입니다.

### Q: 처리 속도가 너무 느립니다
A: `--batch-size`를 크게 설정하거나, `config.sleep_seconds`를 줄이세요 (단, API rate limit 주의).

## 다음 단계

- [ ] 특정 종목 목록만 처리하는 기능
- [ ] 병렬 처리 지원
- [ ] 체크포인트 파일 저장
- [ ] 웹 UI로 진행상황 모니터링
