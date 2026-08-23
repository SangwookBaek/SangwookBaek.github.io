---
layout: post
title: "Pod이 SIGKILL되면 PostgreSQL 커넥션은 어떻게 될까"
date: 2026-05-22 10:00:00 +0900
categories: [PostgreSQL, Kubernetes]
tags: [PostgreSQL, Kubernetes, Connection Pool, SIGKILL, Incident]
---

## 이상했던 건 죽은 Pod보다 살아남은 Pod이었다

Spot 인스턴스 회수로 Pod 하나가 SIGKILL됐다. 죽은 Pod 자체는 어쩔 수 없는 장애라고 생각했다. 문제는 그 직후 남아 있던 Pod의 CPU와 메모리가 100%까지 올라가고, SQLAlchemy QueuePool이 가득 차면서 결국 그 Pod도 죽었다는 점이었다.

처음에는 재시도 트래픽이 살아남은 Pod으로 몰렸다고 생각했다. 그런데 로그를 보니 이상한 점이 하나 더 있었다. 특정 트랜잭션이 약 4분 동안 열린 상태로 남아 있었다. 우리 서비스에는 4분짜리 SQL이 없었다.

그러면 질문은 “왜 트래픽이 몰렸나?”보다 먼저 이것이 됐다. 실행 중인 SQL이 없는데 PostgreSQL은 왜 4분 동안 커넥션을 붙잡고 있었을까?

## 애플리케이션이 죽으면 DB는 바로 알까?

애플리케이션과 PostgreSQL 사이에는 TCP 연결이 있다. 프로세스가 정상적으로 종료되면 소켓을 닫고, TCP FIN이 전달된다. PostgreSQL은 상대가 연결을 끝냈다는 것을 알고 backend 프로세스와 트랜잭션을 정리할 수 있다.

```text
애플리케이션 종료
  → socket close
  → FIN
  → PostgreSQL이 연결 종료를 인식
```

그런데 SIGKILL은 정상 종료 경로를 기다려주지 않는다. Pod 또는 노드가 갑자기 사라지는 상황에서 FIN이 항상 전달된다고 기대하기 어렵다. PostgreSQL 입장에서는 다음 패킷이 오지 않는 연결처럼 남을 수 있다.

```text
Pod SIGKILL
  → 애플리케이션 정리 코드가 실행되지 않음
  → FIN이 전달되지 않을 수 있음
  → PostgreSQL은 한동안 연결이 살아 있다고 볼 수 있음
```

여기서 처음 든 생각은, 이게 우리가 본 4분짜리 트랜잭션의 설명이 될 수 있겠다는 것이었다. 다만 SIGKILL과 그 시간값만으로 원인을 확정할 수는 없다. TCP keepalive, 풀의 재사용 방식, 실제 요청 처리 흐름도 같이 봐야 한다.

## 그런데 왜 SQL이 없어도 트랜잭션은 열려 있을까?

PostgreSQL은 클라이언트 연결마다 backend process를 하나씩 둔다. 애플리케이션에서 커넥션을 빌려 트랜잭션을 시작한 뒤, 외부 API 호출처럼 DB 밖의 작업을 기다릴 수도 있다.

```text
커넥션 획득
  → BEGIN
  → SQL 실행
  → 외부 API 대기
  → COMMIT 또는 ROLLBACK
```

이 사이에 Pod이 죽으면 `COMMIT`도 `ROLLBACK`도 보내지지 않는다. PostgreSQL에는 `idle in transaction` 상태가 남을 수 있고, 해당 커넥션은 풀에도 바로 돌아오지 않는다. 트랜잭션이 잡은 락이 있었다면 다른 요청까지 영향을 받을 수 있다.

장애 당시 요청 처리 중 외부 API를 기다리는 구간이 있었고, 이 경로가 커넥션을 오래 쥐고 있었을 가능성을 의심했다. 하지만 이는 로그 정황에서 나온 가설이다. 실제로 어떤 backend PID가 어떤 요청과 연결됐는지까지 추적해야 확신할 수 있다.

## 4분은 누가 정해 준 시간일까?

우리 설정에서는 아래 값들이 기본값인 0, 즉 꺼진 상태였다.

```sql
SHOW idle_in_transaction_session_timeout;
SHOW statement_timeout;
```

`statement_timeout`은 실행 중인 SQL을 제한하지만, SQL이 끝난 뒤 외부 응답을 기다리는 상황에는 직접 답이 되지 않는다. 반면 `idle_in_transaction_session_timeout`은 트랜잭션 안에서 유휴 상태인 세션을 정리할 수 있다.

TCP keepalive도 후보였다. OS와 네트워크 설정에 따라 죽은 peer를 감지하는 시간이 달라진다. 관측된 약 4분이 keepalive나 인프라의 timeout과 관련 있는지는 아직 확인하지 못했다. 숫자가 비슷하다는 이유만으로 원인이라고 부르면 안 될 것 같다.

그래도 애플리케이션이 항상 정상적으로 커넥션을 반납할 것이라는 전제는 위험해 보였다. Pod 재시작이나 강제 종료가 있는 환경에서는 DB 쪽에도 최후의 정리 장치가 있어야 한다.

## 지금 바꾸려는 것

우선 `idle_in_transaction_session_timeout`과 `statement_timeout`을 서비스의 실제 요청 시간에 맞춰 설정하려고 한다. 너무 짧게 잡으면 정상 요청을 끊을 수 있고, 너무 길게 두면 이번처럼 커넥션 풀이 잠기는 시간을 늘린다.

그리고 트랜잭션을 외부 API 호출보다 좁게 잡아야 한다. DB를 읽고 외부 API를 기다리는 동안 같은 커넥션을 계속 들고 있을 이유가 있는지 요청 경로를 다시 보고 있다. QueuePool의 크기와 timeout도 단순히 늘리는 방향이 아니라, 얼마나 오래 점유되는지가 먼저다.

이번 장애에서 아직 확실한 것은 SIGKILL 뒤에 커넥션과 트랜잭션의 정리가 즉시 일어난다고 기대하면 안 된다는 점이다. 4분의 정확한 원인은 연결 로그, PostgreSQL 세션 상태, 노드 네트워크 설정을 더 모아봐야 한다. 그 다음에야 timeout 값을 근거 있게 정할 수 있을 것 같다.
