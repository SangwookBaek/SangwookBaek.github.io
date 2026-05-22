---
title: "Pod이 SIGKILL되면 PostgreSQL 커넥션은 어떻게 될까"
date: 2026-05-22 00:00:00 +0900
author: oogie
categories: [backend]
tags: [postgresql,tcp,socket,connection-pool]     # TAG names should always be lowercase]
use_math: false
---

## TL;DR

Spot 회수로 Pod 하나가 죽고, 살아남은 Pod에 트래픽이 몰리며 풀이 터졌다. 여기까진 흔한 그림이다. 그런데 그 와중에 4분짜리 트랜잭션이 박혀있었다. 우리 코드에는 4분짜리 쿼리 같은 거 없다. 범인은 SQL이 아니라 TCP였다. SIGKILL 당한 Pod이 FIN도 못 보내고 죽으면, PG는 그게 죽은 줄 모르고 트랜잭션을 계속 열어둔다. 정황상 그 4분은 Linux 커널의 TCP keepalive가 dead peer를 판정해 소켓을 닫은 구간으로 추정된다.

---

## 1. 평범하게 시작한 장애

순서는 단순했다.

- Spot 회수로 Pod 하나가 사라짐
- 살아남은 Pod로 트래픽이 쏠림
- CPU·메모리가 같이 100%까지 차오름
- `QueuePool limit of size N overflow M reached, connection timed out` 이 박히기 시작
- 결국 그 Pod까지 사망

풀 고갈과 리소스 한계가 겹친 흔한 패턴이다. 풀 사이즈, graceful drain, HPA 임계로 대응 가능한 영역이다.

진짜 이상한 건 따로 있었다. 사태가 정리된 뒤 모니터링을 다시 봤더니, **같은 시간대에 약 4분 동안 열려있던 트랜잭션**이 박혀 있었다. 우리 쿼리 중에 4분이나 걸리는 건 없다. 그럼 그 4분 동안 그 트랜잭션을 누가 잡고 있었던 걸까.

---

## 2. 닫혀야 할 소켓이 닫히지 않았다

답은 쿼리에 있지 않고 그 아래 TCP에 있다. 소켓이 어떻게 열리고 닫히는지부터 다시 보자.

```text
socket()   -> 파일 디스크립터 하나 받음
bind()     -> 포트에 묶음
listen()   -> 연결 받기 시작
accept()   -> 들어온 연결 가져옴
read/write -> 데이터 주고받음
close()    -> 양쪽이 다 호출해야 깔끔하게 끝남
```

마지막 `close()`가 핵심이다. 양쪽이 종료를 알리려면 TCP FIN이 오가야 한다.

```text
Client                  Server
  | close()             |
  | -------FIN-------->  |
  |                     | 닫을 준비
  | <------FIN/ACK----- |
  | close() 완료        | close() 완료
```

문제는 **`close()` 호출 자체가 일어나지 않고 프로세스가 사라지는 경우**다.

---

## 3. 정황상 SIGKILL로 본다

정상 종료(SIGTERM + grace period)였다면 shutdown 핸들러가 돌면서 FIN까지 갔을 거고, PG는 그 시점에 트랜잭션을 정리했을 것이다. 4분 동안 좀비가 남았다는 사실 자체가 정상 종료가 아니었다는 신호다. 정황상 그 Pod은 SIGKILL로 끊긴 것으로 본다.

SIGTERM과 SIGKILL은 같은 종료처럼 보여도 결과가 다르다.

SIGTERM은 "정리할 시간 줄게" 정도의 신호다. shutdown 핸들러가 돌면서 진행 중인 트랜잭션 마무리하고, 커넥션에 `close()` 호출해서 FIN까지 보낸 뒤에 프로세스가 빠진다.

SIGKILL은 그런 게 없다. 커널이 그냥 프로세스를 끊는다. 신호를 잡을 수도, 핸들러를 돌릴 수도 없다. 파일 디스크립터 정리는 커널이 시작하지만, TCP FIN이 상대까지 닿는다는 보장도 없다. 특히 컨테이너나 노드 자체가 사라지는 경로(Spot 회수, OOMKill 등)에서는 FIN이 PG까지 도달하지 못하는 일이 흔하다.

PG 서버 입장에서는 그냥 "어느 순간부터 패킷이 안 오는 커넥션"이 하나 남은 상태가 된다. 클라이언트가 죽었는지, 네트워크가 잠깐 멍한 건지 알 방법이 없다.

---

## 4. SIGKILL의 방아쇠는 무엇이었을까

짚어둘 게 하나 있다. `QueuePool limit ... reached`는 Pod을 죽이지 않는다. SQLAlchemy가 던지는 Python 예외라 그 요청만 500을 뱉을 뿐, 프로세스는 멀쩡하다. 그러니 SIGKILL은 다른 요인이 당겼다는 뜻이 된다.

정황상 가장 그럴듯한 흐름은 이렇다.

- Pod 하나에 트래픽이 몰렸다.
- 그 요청들은 DB 트랜잭션을 연 채로 외부 API 호출을 길게 기다리는 패턴이었다.
- 커넥션과 요청 컨텍스트가 메모리에 쌓이면서 컨테이너 메모리 limit을 넘었을 가능성이 높다.
- 그 순간 Linux OOM killer가 SIGTERM 없이 즉시 SIGKILL을 발사하는 흐름에 들어간다.

OOMKill은 grace period가 없다. 핸들러 돌릴 시간도, FIN 보낼 시간도 없이 프로세스가 끊긴다. CPU·메모리가 같이 100%까지 붙었던 정황으로 보면 이 경로가 가장 잘 들어맞는다.

---

## 5. PostgreSQL 입장에서 본 그림

PG는 접속 하나당 backend 프로세스 하나를 띄운다. 클라이언트 명령을 처리하고, 다음 명령이 올 때까지 기다린다.

트랜잭션 중간에 클라이언트가 갑자기 증발하면, backend 입장에선 그냥 다음 명령이 안 오는 상태일 뿐이다. 죽었는지 뜸 들이는지 알 길이 없다.

```text
[BEGIN]
[UPDATE ...]
[SELECT ...]
... (응답 보냄)
... (다음 명령 대기)
... (영원히 안 옴)
```

이게 그 유명한 `idle in transaction` 상태다. 그동안 해당 backend는

- `pg_stat_activity`에 `idle in transaction`으로 박혀있고
- 잡고 있던 row lock, advisory lock 그대로 들고 있고
- `max_connections` 슬롯 하나를 점유하고
- `xact_start`로부터 시간만 계속 흘러간다

모니터링이 트랜잭션 지속 시간을 `xact_start` 기준으로 그리고 있으면, 이 좀비가 **점점 길어지는 "느린 쿼리"** 처럼 보인다. 실제로는 무거운 쿼리가 도는 게 아니라, 죽은 클라이언트가 잡아둔 트랜잭션이 그냥 열려있을 뿐이다.

---

## 6. 그럼 PG는 영원히 모르고 있는 건가

원래는 알 수 있어야 한다. PG에는 이런 옵션들이 있다.

| 옵션 | 동작 |
|------|------|
| `idle_in_transaction_session_timeout` | 트랜잭션 안에서 N초 idle하면 세션 종료 |
| `statement_timeout` | 하나의 statement가 N초 넘으면 취소 |
| `tcp_keepalives_idle`, `tcp_keepalives_interval`, `tcp_keepalives_count` | PG가 직접 TCP keepalive를 보내는 주기 |

이 중 하나만 켜뒀어도 PG가 알아서 좀비를 끊었을 거다. 그런데 이번 환경은 셋 다 기본값(0, 즉 무제한)이었다. PG는 손도 못 쓴다.

그럼 누가 끊었나. 남는 후보는 OS다. Linux에는 시스템 전역의 TCP keepalive가 있다.

```text
net.ipv4.tcp_keepalive_time    <- 무응답 후 첫 probe까지의 idle 시간
net.ipv4.tcp_keepalive_intvl   <- probe 간 간격
net.ipv4.tcp_keepalive_probes  <- 몇 번 실패해야 끊을지
```

PG도 앱도 끊지 못한 상태에서 약 4분 뒤 트랜잭션이 풀린 정황을 보면, 이 OS 측 keepalive가 작동했을 가능성이 가장 그럴듯하다.

---

## 7. 정리

| 보이는 현상 | 진짜로 일어난 일 |
|------------|----------------|
| 분 단위 slow query | 죽은 클라이언트의 좀비 트랜잭션이 `xact_start`부터 계속 카운트 |
| 풀 고갈 후 회복 지연 | 좀비 backend가 슬롯·락을 잡고 안 놔줌 |
| 4분 뒤 갑자기 정상화 | OS TCP keepalive가 끊었을 것으로 보이는 시점 (정황 추정) |

남는 교훈은 세 가지다.

- 장애 트리거(트래픽 집중 + 풀 한도 + 리소스 한계)와 "왜 슬로우 쿼리가 분 단위였나"는 **별개의 질문**이다. 후자는 SQL이 아니라 TCP의 이야기다.
- OOMKill이든 liveness 재시작이든 Spot grace 초과든, SIGKILL이 떨어지는 모든 경로는 공통적으로 FIN을 못 보내고 끊긴다. PG는 못 알아챈다.
- `idle_in_transaction_session_timeout`이나 `statement_timeout`, 아니면 PG의 `tcp_keepalives_*` 중 뭐든 하나는 켜두자. 끊는 책임을 OS까지 떠넘기면 분 단위 좀비를 마주하게 된다.

결국 그 4분 동안 트랜잭션을 잡고 있던 건 우리 쿼리가 아니라, 인사도 없이 끊긴 소켓 하나였다.
