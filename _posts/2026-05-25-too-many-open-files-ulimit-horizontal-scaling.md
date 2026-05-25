---
title: "too many open files 원인 찾기"
date: 2026-05-25 00:00:00 +0900
author: oogie
categories: [infra]
tags: [docker,ulimit,file-descriptor]
use_math: false
---

## TL;DR

시험 이벤트로 동접이 몰리면서 Janus Gateway 기반 WebRTC 서버에 `too many open files`가 떴다. 처음에는 인스턴스를 더 띄워서 버티려고 했지만, 컨테이너마다 `nofile`이 1024로 잡혀 있어서 금방 같은 한계에 닿았다.

수평확장을 계속하면 에러 빈도는 줄일 수 있다. 다만 이건 근본 원인을 고치는 방법이 아니었다. 서버 리소스가 부족했던 게 아니라 프로세스가 동시에 열 수 있는 FD 수가 너무 낮게 잡혀 있었기 때문이다. 컨테이너 안에서 `cat /proc/1/limits`로 확인했고, Docker 29 패키징 업데이트에서 컨테이너 기본 `nofile`이 1,048,576에서 1,024로 줄어든 것도 release note에서 확인했다. 결국 `--ulimit nofile=...`을 명시해서 해결했다.

---

## 1. 원인 찾기

처음에는 단순히 사용자가 많이 몰려서 생긴 문제라고 봤다. 시험 이벤트 시간에 동접이 평소보다 크게 늘었고, Janus Gateway 기반 WebRTC 서버에서 `too many open files`가 반복해서 나왔다. 그래서 우선 인스턴스를 늘려서 트래픽을 나누는 방식으로 대응했다.

그런데 에러가 완전히 사라지지는 않았다. 서버 리소스가 부족했다면 인스턴스를 늘리는 것만으로도 어느 정도 정리가 됐어야 하는데, 같은 유형의 에러가 계속 보였다. 그래서 `too many open files`를 기준으로 원인을 다시 찾아봤고, file descriptor 제한 때문에 발생할 수 있다는 내용을 확인했다.

그다음 컨테이너 안에서 실제 제한값을 확인했다.

```bash
cat /proc/1/limits
```

여기서 `Max open files`가 1024로 잡혀 있었다. WebSocket 연결과 WebRTC media 소켓을 같이 쓰는 서버 입장에서는 너무 낮은 숫자였다.

우리는 컨테이너 ulimit을 따로 설정하지 않고 Docker 기본값을 그대로 사용하고 있었다. 그래서 왜 기본값이 1024인지 확인하려고 Docker 업데이트 내역을 찾아봤고, Docker 29 패키징 업데이트 이후 컨테이너 기본 `nofile` 값이 1,048,576에서 1,024로 바뀐 것을 확인했다.

결국 배포 설정에 `nofile` 값을 명시해서 다시 배포했고, 이후 같은 에러는 사라졌다.

---

## 2. file descriptor와 ulimit

Linux는 프로세스가 무언가를 열 때마다 정수 하나(file descriptor, FD)를 발급한다. 디스크 파일이든 TCP/UDP 소켓이든 파이프든 epoll 인스턴스든 전부 FD로 다룬다. `read()`/`write()`/`close()` 같은 시스템 콜도 이 FD를 기준으로 동작한다.

ulimit `nofile`(커널 이름 `RLIMIT_NOFILE`)은 한 프로세스가 동시에 열 수 있는 FD 개수의 상한이다. `accept()`나 `open()`이 이 상한에 닿으면 `EMFILE`로 실패하고, 애플리케이션에서는 보통 `too many open files`로 보인다. 컨테이너 안에서도 이 제한은 그대로 적용된다.

---

## 3. WebSocket + Janus는 사용자당 FD가 누적된다

HTTP REST는 요청-응답이 끝나면 커넥션이 비교적 빠르게 회수된다. 그래서 동시에 점유하는 FD 수가 동접자 수보다 훨씬 적은 경우가 많다. WebSocket은 다르다. 핸드셰이크 이후 같은 TCP 커넥션을 계속 유지하므로 동접자 수가 곧 점유 소켓 FD 수에 가깝다.

여기에 Janus Gateway 위에서 WebRTC를 처리하고 있었다. 사용자 한 명이 시그널링 WebSocket 외에도 media UDP 소켓 등 여러 FD를 같이 잡는 구조였다. 동접이 천 명 가까이 가는 상황에서는 `nofile` 1024에 금방 닿을 수밖에 없었다.

---

## 4. 수평확장보다 ulimit을 봐야 했던 이유

처음에는 사용자가 많아졌으니 인스턴스를 더 늘리는 쪽으로 대응했다. 방향이 완전히 틀린 건 아니다. 수평확장을 충분히 하면 인스턴스 하나가 맡는 연결 수가 줄어들고, 그만큼 `too many open files`도 줄어들 수 있다.

문제는 이 상황이 CPU나 메모리 같은 일반적인 리소스 부족이 아니었다는 점이다. 컨테이너에 적용된 `nofile`이 1024였고, 새로 띄우는 컨테이너도 같은 제한을 그대로 물려받았다. 결국 인스턴스를 늘리는 방식은 낮은 FD 제한을 우회해서 버티는 방법에 가까웠다.

사용자당 FD를 여러 개 잡는 워크로드에서는 인스턴스 하나가 받을 수 있는 동접 수가 생각보다 빨리 막힌다. 그래서 이 경우에는 인스턴스를 계속 늘리는 것보다, 컨테이너의 `nofile` 값을 명시적으로 올리는 게 훨씬 직접적이고 효율적인 해결이었다.

---

## 5. 원인 — Docker 29 패키징 업데이트

컨테이너에서 1024를 본 시점에 ulimit이 원인이라는 건 알았다. 그런데 왜 1024인지는 바로 이해가 안 됐다. 우리는 컨테이너 ulimit을 따로 지정하지 않고 Docker 기본값을 그대로 쓰고 있었고, 내가 알고 있던 기본값은 1,048,576이었기 때문이다.

release note를 뒤져보니 Docker 29 패키징 업데이트에 답이 있었다. containerd v2.1.5로 올라가면서 컨테이너 기본 `nofile`이 1,048,576에서 1,024로 줄어 있었다.

| 위치 | 설정 |
|---|---|
| `docker run` | `--ulimit nofile=1048576:1048576` |
| docker-compose | 서비스 아래 `ulimits.nofile.soft / hard` |
| 데몬 전역 | `/etc/docker/daemon.json`의 `default-ulimits.nofile` |
| Kubernetes | 노드의 containerd `default_ulimits` |

---

## 6. 정리

- `too many open files`는 CPU나 메모리가 부족해서 나는 에러가 아니라, 프로세스가 열 수 있는 FD 상한에 닿았다는 신호다.
- 수평확장으로 에러를 줄일 수는 있지만, 낮은 `nofile` 값이 그대로라면 비효율적인 우회에 가깝다.
- Docker 기본값은 런타임 업데이트만으로도 바뀔 수 있다. 중요한 값이면 기본값에 기대지 말고 컨테이너 ulimit을 명시해두는 게 안전하다.
