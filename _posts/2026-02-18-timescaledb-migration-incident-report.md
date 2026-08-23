---
layout: post
title: "TimescaleDB Migration 장애 복구하기: 디스크 풀로 인한 카탈로그 손상에 따른 복구"
date: 2026-02-18 10:00:00 +0900
categories: [Database]
tags: [PostgreSQL, TimescaleDB, Migration, Incident, Recovery]
---

## UUID를 String으로 바꾸는 일은 왜 이렇게 커졌을까

처음에는 컬럼 타입 하나를 바꾸는 마이그레이션이었다. TimescaleDB hypertable에 있는 UUID를 String으로 바꿔야 했다.

PostgreSQL 테이블이라면 `ALTER TABLE`을 하면 되는 것 아닌가 싶었다. 그런데 이 테이블은 압축이 켜진 hypertable이었다. 압축된 chunk에는 바로 타입 변경을 할 수 없어서, 압축 정책을 멈추고 chunk를 풀고, 압축을 끄고, 타입을 바꾼 뒤 다시 설정을 되돌리는 순서가 필요했다.

대략 이런 흐름이었다.

```sql
SELECT remove_compression_policy('table_name');

DO $$
DECLARE
  chunk_name regclass;
BEGIN
  FOR chunk_name IN
    SELECT show_chunks('table_name')
  LOOP
    PERFORM decompress_chunk(chunk_name);
  END LOOP;
END $$;

ALTER TABLE table_name SET (timescaledb.compress = false);
ALTER TABLE table_name ALTER COLUMN id TYPE text;
```

여기까지는 “번거롭지만 끝낼 수 있는 작업”이라고 생각했다. 문제는 chunk를 하나씩 풀던 도중 디스크가 가득 찼고, PostgreSQL 프로세스가 죽으면서 시작됐다.

## 롤백됐는데 왜 과거 데이터는 안 보일까

마이그레이션은 트랜잭션 안에서 실행되고 있었다. 그래서 처음에는 실패했으니 원래 상태로 돌아갔을 거라고 생각했다.

실제로 최근 데이터는 조회됐다. 그런데 기간을 넓혀 보니 어느 시점 이전의 데이터가 전부 보이지 않았다.

```sql
SELECT min(time), max(time), count(*)
FROM table_name;
```

테이블 자체가 사라진 것도 아니고, 최근 데이터도 남아 있었다. 그러면 SQL이 틀린 게 아니라, hypertable이 시간대별로 나뉘어 가진 chunk 중 일부를 PostgreSQL이 더 이상 찾지 못하는 상태일 수 있겠다고 봤다.

TimescaleDB의 hypertable은 논리적으로는 한 테이블이지만, 내부적으로는 여러 chunk 테이블로 쪼개져 있다. TimescaleDB 카탈로그는 어떤 chunk가 이 hypertable에 속하는지, 어느 시간 범위를 담당하는지 관리한다.

```text
hypertable
  ├── chunk 1
  ├── chunk 2
  ├── ...
  └── chunk N

TimescaleDB catalog
  └── 이 chunk들이 hypertable의 일부라는 메타데이터
```

디스크 풀과 프로세스 종료 사이에서 WAL 복구가 완전하지 않았거나, 카탈로그와 실제 테이블의 관계가 어긋났을 가능성을 의심했다. 여기서는 원인을 확정할 수 없었다. 다만 결과는 분명했다. 물리적으로 남아 있는 chunk가 있어도, 카탈로그에 등록되어 있지 않으면 일반 조회에서는 보이지 않을 수 있다.

## 실제 chunk와 카탈로그를 세어보니

확인해 보니 물리적으로는 약 50개의 chunk가 남아 있었는데, TimescaleDB 카탈로그에는 25개 정도만 잡혔다. 압축 chunk도 비슷했다. 실제로는 약 45개가 있었지만 카탈로그에서는 22개 정도만 조회됐다.

즉 데이터 파일이 전부 날아갔다고 보기보다, 과거 chunk들이 orphan 상태가 되었을 가능성이 높아 보였다. “테이블을 조회했는데 데이터가 없다”와 “데이터가 없다”가 항상 같은 말은 아니라는 걸 여기서 처음 체감했다.

그래서 다음 질문은 자연스럽게 바뀌었다. 없어진 데이터를 복원하는 게 아니라, 남아 있는 chunk를 다시 hypertable로 인식시키려면 어떻게 해야 할까?

## 카탈로그만 다시 넣으면 안 되나?

처음 시도는 내부 카탈로그에 chunk 정보를 직접 넣는 것이었다. 하지만 TimescaleDB 카탈로그는 일반 애플리케이션 계정으로 수정할 수 없었다. 권한을 올린다고 끝날 문제도 아니었다. chunk 이름, 시간 범위, 압축 chunk와의 관계를 정확히 복원하지 못하면 더 나쁜 상태를 만들 수 있다.

그 다음에는 `pg_restore --clean`으로 덮어쓰는 방법을 봤다. 그런데 `--clean`은 관련 객체의 의존성 때문에 예상보다 넓은 범위를 건드릴 수 있었다. hypertable과 extension이 얽힌 상태에서는 단순히 테이블 하나를 지웠다 복원하는 작업이 아니었다.

마지막으로 `DROP TABLE ... CASCADE`를 시도했을 때는 PostgreSQL이 `FATAL: extension must be preloaded`와 함께 다시 죽었다. extension은 이미 로드된 상태였기 때문에 더 이상한 증상이었다. 깨진 카탈로그를 읽는 extension 내부 함수에서 문제가 난 것 아닐까 추정했지만, 이 역시 로그와 복구 환경 없이 단정할 수는 없었다.

## 이 시점부터는 DB 안에서만 풀 수 있는 문제가 아니었다

DB는 Kubernetes 위에서 돌고 있었다. 실제 복구를 하려면 PostgreSQL superuser 권한, 백업 상태, PVC의 여유 공간이 모두 필요했다. 애플리케이션에서 마이그레이션 SQL을 조금 더 고치는 문제와는 달랐다.

그래서 운영 담당자에게는 세 가지를 요청해야 했다.

- 장애 전 백업 또는 스냅샷이 있는지
- 복구 작업 중 디스크를 얼마나 확장할 수 있는지
- TimescaleDB 카탈로그와 물리 chunk를 확인할 수 있는 권한을 줄 수 있는지

처음에는 컬럼 타입 하나의 문제였다. 그런데 압축, chunk, WAL, 카탈로그, 저장 공간이 한 번에 만나는 작업이었다.

다음에는 decompression이 필요한 작업을 하기 전에 chunk 크기와 여유 디스크를 먼저 계산해야 할 것 같다. 그리고 “트랜잭션이 롤백됐다”는 사실만으로 extension이 관리하는 모든 내부 상태까지 원래대로 돌아왔다고 생각하면 안 된다는 것도 남았다.
