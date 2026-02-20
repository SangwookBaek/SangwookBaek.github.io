---
title: "TimescaleDB Migration 장애 복구기: 디스크 풀로 인한 카탈로그 손상과 삽질의 기록"
date: 2026-02-18 00:00:00 +0900
author: oogie
categories: [database,backend]
tags: [timescaledb,postgresql,migration]     # TAG names should always be lowercase]
use_math: false
---

## TL;DR

TimescaleDB Hypertable의 컬럼 타입을 변경하는 마이그레이션 도중 디스크가 꽉 차서 실패했다. 트랜잭션은 롤백되었지만 TimescaleDB 내부 카탈로그가 손상되어 과거 데이터에 접근할 수 없게 되었다. 데이터는 물리적으로 디스크에 살아있었지만, 일반 유저 권한으로는 복구가 불가능했고 결국 DBA의 슈퍼유저 권한이 필요했다.

---

## 1. 배경: 왜 이 마이그레이션이 필요했나

서비스 요구사항 변경으로 특정 컬럼의 타입을 `UUID`에서 `String`으로 변경해야 했다. 일반 테이블이었으면 `ALTER COLUMN ... TYPE` 한 줄이면 끝나는 작업이다.

문제는 이 컬럼이 **TimescaleDB Hypertable**에 있었다는 점이다.

### TimescaleDB Hypertable이란?

TimescaleDB는 PostgreSQL 위에서 시계열 데이터를 효율적으로 관리하기 위한 확장이다. 일반 테이블을 "Hypertable"로 변환하면, 시간 기준으로 데이터를 자동으로 **청크(chunk)** 단위로 분할하고, 오래된 청크는 **압축(compress)** 해서 저장한다.

```
Hypertable (hist_learning)
├── _hyper_1_1_chunk   (2024-11 ~ 2024-12) [압축됨]
├── _hyper_1_3_chunk   (2024-12 ~ 2025-01) [압축됨]
├── ...
├── _hyper_1_175_chunk (2026-02-03 ~ 2026-02-06) [비압축]
└── _hyper_1_219_chunk (2026-02-11 ~ 2026-02-12) [비압축]
```

압축된 청크는 내부적으로 별도의 압축 테이블(`compress_hyper_2_*`)에 데이터가 저장된다.

### 마이그레이션 절차

Hypertable에서 압축 대상 컬럼의 타입을 바꾸려면, 단순 ALTER가 불가능하다. 아래 순서를 따라야 한다:

```
1. 압축 정책 제거 (remove_compression_policy)
2. 모든 청크 압축 해제 (decompress_chunk) ← 여기서 디스크 사용량 급증
3. 압축 비활성화 (SET timescaledb.compress = false)
4. 컬럼 타입 변경 (ALTER COLUMN)
5. 압축 재설정 및 정책 복원
```

**2단계가 핵심이다.** 압축 해제 시 데이터가 압축 테이블에서 원본 청크 테이블로 복원되면서 디스크 사용량이 일시적으로 크게 증가한다.

---

## 2. 장애 발생: 디스크 풀

마이그레이션의 `decompress_chunk` 루프가 수십 개의 압축 청크를 순차적으로 해제하던 중, **디스크가 꽉 찼다.**

```sql
DO $$ DECLARE chunk_name text;
BEGIN
    FOR chunk_name IN SELECT c FROM show_chunks('hist_learning') c
    LOOP
        EXECUTE format('SELECT decompress_chunk(%L, true)', chunk_name);
        -- 여기서 디스크 풀 → PostgreSQL crash
    END LOOP;
END $$;
```

PostgreSQL이 crash되고, 재시작 후 트랜잭션은 롤백되었다. Alembic 마이그레이션 버전도 이전 상태로 남아있었고, 컬럼 타입도 UUID 그대로였다.

**겉보기에는 깔끔한 롤백이었다.** 하지만...

---

## 3. 데이터가 사라졌다 (처럼 보였다)

며칠 후 확인해보니, 과거 데이터에 접근할 수 없었다.

```sql
SELECT min(created), max(created) FROM hist_learning;
-- 2026-01-15 ~ 2026-02-12 (최근 약 1개월만 조회됨)

SELECT count(*) FROM hist_learning;
-- 166,367건 (원래보다 적음)
```

**무슨 일이 일어난 걸까?**

---

## 4. 원인 분석: 카탈로그 손상

TimescaleDB의 데이터 저장 구조를 이해하면 원인이 보인다.

### TimescaleDB의 2중 구조

```
[사용자가 보는 것]
SELECT * FROM hist_learning
         ↓ (라우팅)
[실제 데이터 저장]
_timescaledb_catalog.chunk (카탈로그 = 어떤 청크가 있는지 메타데이터)
         ↓ (참조)
_timescaledb_internal._hyper_1_*_chunk (물리 테이블 = 실제 데이터)
_timescaledb_internal.compress_hyper_2_*_chunk (압축 데이터)
```

카탈로그는 "이 hypertable에는 이런 청크들이 있고, 각 청크는 이 시간 범위의 데이터를 담고 있다"는 메타데이터다. PostgreSQL이 `SELECT * FROM hist_learning`을 실행하면, 카탈로그를 참조해서 어떤 청크 테이블을 읽어야 하는지 결정한다.

### 카탈로그 vs 물리 테이블 비교

| 구분 | 물리 테이블 (디스크) | 카탈로그 (메타데이터) |
|------|---------------------|---------------------|
| 메인 청크 | **50개 존재** | **25개만 등록** |
| 압축 청크 | **45개 존재** | **22개만 등록** |

**물리 데이터는 100% 살아있었다.** 카탈로그에서 과거 청크(25개)의 항목만 사라진 것이다.

```sql
-- 카탈로그에 등록된 청크: 96번 이후만
SELECT id, table_name, status FROM _timescaledb_catalog.chunk
WHERE hypertable_id = 1 ORDER BY id;
-- chunk 96, 100, 104, ... (25개)

-- 물리적으로 존재하는 청크: 1번부터 전부
SELECT tablename FROM pg_tables
WHERE schemaname = '_timescaledb_internal' AND tablename LIKE '_hyper_1_%';
-- chunk 1, 3, 5, 9, 13, ... 96, 100, ... (50개)
```

카탈로그에 없는 청크는 쿼리 시 무시된다. 데이터가 디스크에 있어도 "존재하지 않는 것"으로 처리되는 것이다.

### 왜 카탈로그가 손상되었나

`decompress_chunk`는 내부적으로:
1. 압축 테이블에서 데이터를 읽어 원본 청크에 INSERT
2. 압축 테이블의 해당 데이터 DELETE
3. 카탈로그의 청크 상태를 `compressed` → `uncompressed`로 UPDATE

디스크 풀로 crash가 발생했을 때, PostgreSQL의 WAL(Write-Ahead Log) 기반 복구가 진행되지만, **디스크 공간 부족으로 복구 자체가 불완전**했을 수 있다. 트랜잭션의 DML(데이터 변경)은 롤백되었지만, TimescaleDB 카탈로그의 일부 항목이 복구되지 못한 것이다.

추가로, **고아 청크(orphaned chunk)** 도 발생했다:
- `compress_hyper_2_97_chunk` (1,698행) → 카탈로그에 있지만 어떤 메인 청크도 참조하지 않음
- `compress_hyper_2_102_chunk` (42행) → 동일

---

## 5. 복구 시도와 실패

### 시도 1: 카탈로그 직접 복구

가장 직관적인 방법 - 누락된 카탈로그 항목을 직접 INSERT하면 된다.

```sql
SELECT has_table_privilege('elice-aidt', '_timescaledb_catalog.chunk', 'INSERT');
-- false
```

**실패.** `_timescaledb_catalog`는 TimescaleDB 내부 테이블로, 일반 유저에게 INSERT 권한이 없다.

### 시도 2: pg_restore로 테이블 재생성

백업 파일(pg_dump custom format)이 있었으므로, 테이블을 DROP하고 백업에서 복원하는 방법을 시도했다.

```bash
pg_restore --no-owner --clean --if-exists \
  --table=hist_learning --table=hist_xapi \
  backup.dump
```

pg_restore의 `--clean` 옵션은 내부적으로 `DROP TABLE IF EXISTS hist_learning`을 실행한다. **하지만 CASCADE 없이.**

```
ERROR: cannot drop table hist_learning because other objects depend on it
DETAIL: table _timescaledb_internal._hyper_1_1_chunk depends on table hist_learning
         table _timescaledb_internal._hyper_1_3_chunk depends on table hist_learning
         ... (50개 청크)
HINT: Use DROP ... CASCADE to drop the dependent objects too.
```

**실패.** pg_restore에는 CASCADE 옵션이 없다.

### 시도 3: 수동 DROP TABLE CASCADE

직접 CASCADE를 붙여서 실행했다.

```sql
DROP TABLE hist_learning CASCADE;
```

```
NOTICE: drop cascades to 50 other objects
DETAIL: drop cascades to table _timescaledb_internal._hyper_1_1_chunk
        drop cascades to table _timescaledb_internal._hyper_1_3_chunk
        ...
FATAL: extension "timescaledb" must be preloaded
```

50개 청크의 DROP cascade 처리까지는 진행되었으나, TimescaleDB의 **내부 이벤트 트리거**가 카탈로그 정리 작업을 수행하려다 crash했다. PostgreSQL backend가 죽으면서 트랜잭션이 롤백, 테이블은 그대로 남았다.

이 에러 메시지(`extension "timescaledb" must be preloaded`)는 사실 오해를 불러일으킨다. 실제로는 `shared_preload_libraries`에 timescaledb가 정상적으로 설정되어 있었다:

```sql
SELECT extname, extversion FROM pg_extension WHERE extname = 'timescaledb';
-- timescaledb | 2.18.2
```

**진짜 원인은 깨진 카탈로그 상태를 TimescaleDB의 내부 C 함수가 처리하다 crash하는 것**이었고, crash 시 출력되는 에러 메시지가 저것이었을 뿐이다.

### 왜 모든 시도가 실패했는가

| 작업 | 필요 권한 | 보유 여부 |
|------|----------|----------|
| 카탈로그 INSERT | postgres 슈퍼유저 | X |
| DROP TABLE CASCADE | 트리거 비활성화 필요 | X |
| `SET session_replication_role = 'replica'` | 슈퍼유저 | X |
| `timescaledb_pre_restore()` | 슈퍼유저 | X |

결국 모든 복구 경로가 **postgres 슈퍼유저 권한**을 요구했다.

---

## 6. 최종 해결: DevOps팀 요청

결론이 허무맹랑할 수 있지만 결국 DevOps팀에 복구를 요청했다.
Kubernetes 환경에서 PostgreSQL은 별도의 pod으로 운영되고 있었고, 슈퍼유저 접근은 인프라팀만 가능했다.
그래서 백업 및 DB 볼륨 증설을 함께 요청하면서 문제를 해결(??)했다.

---

## 7. 교훈

### 마이그레이션 전

- **디스크 여유 공간 확인은 필수.** TimescaleDB의 `decompress_chunk`는 일시적으로 디스크 사용량을 2배까지 증가시킬 수 있다. 마이그레이션 전 hypertable의 압축/비압축 크기를 반드시 확인하자.
- **배치 처리를 고려하자.** 모든 청크를 한 트랜잭션에서 decompress하지 말고, 청크 단위로 나눠서 처리하면 장애 시 피해 범위를 줄일 수 있다.

### 장애 발생 시

- **FATAL 에러 메시지를 액면 그대로 믿지 말자.** `extension must be preloaded`는 실제 원인이 아니었다. crash 시 출력되는 기본 에러 메시지일 뿐, 진짜 원인은 카탈로그 손상이었다.
- **물리 테이블과 카탈로그를 분리해서 확인하자.** `pg_tables`로 물리 테이블 존재 여부, `_timescaledb_catalog.chunk`로 카탈로그 상태를 각각 확인하면 문제의 본질을 빠르게 파악할 수 있다.

### 인프라 관점

- **TimescaleDB 사용 환경에서는 일반 유저의 복구 능력이 제한적이다.** 카탈로그 수정, 트리거 비활성화 등 핵심 복구 작업에 슈퍼유저가 필요하다. 장애 대응 플레이북에 DBA escalation 경로를 포함해야 한다.
