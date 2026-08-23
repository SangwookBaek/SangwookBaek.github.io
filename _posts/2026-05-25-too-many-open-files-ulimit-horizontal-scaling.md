---
title: "too many open files 원인 찾기"
date: 2026-05-25 00:00:00 +0900
author: oogie
categories: [infra]
tags: [docker,ulimit,file-descriptor]
use_math: false
---

## Intro

시험 이벤트 때 동접이 몰리면서 Janus Gateway 기반 WebRTC 서버에 `too many open files`가 계속 찍혔다.

처음 생각은 단순했다. 사용자가 많아졌으니까 인스턴스를 더 띄워서 나누면 되는 거 아닌가? 그래서 우선 수평확장으로 대응했다.

근데 에러가 완전히 사라지지 않았다. 인스턴스를 늘리면 한 인스턴스가 받는 연결 수는 줄어드니까 에러 빈도는 당연히 줄 수 있다. 그런데 새로 뜬 컨테이너도 똑같은 시점에 막힌다면, 이건 CPU나 메모리처럼 인스턴스 하나의 자원이 부족한 문제만은 아닐 수 있겠다고 생각했다.

에러 메시지를 다시 보니까 이름이 너무 직접적이었다. `too many open files`.

그러면 이 "file"이 진짜 파일만 말하는 건지, 그리고 우리 WebRTC 서버에서 왜 이렇게 빨리 한도에 닿는지를 봐야했다.

## file descriptor가 뭐길래

Linux에서 프로세스가 무언가를 열면 file descriptor(FD)라는 정수 하나를 받는다. 파일을 열 때만 생기는 게 아니다. TCP/UDP 소켓, 파이프, epoll 인스턴스도 전부 FD로 다룬다.

그래서 `open()`, `accept()` 같은 동작을 하면 FD가 하나씩 늘고, `close()`를 하면 다시 반환된다. 그리고 프로세스마다 동시에 열 수 있는 FD의 상한이 있다. 이게 `ulimit nofile`, 커널 쪽 이름으로는 `RLIMIT_NOFILE`이다.

상한을 넘기면 더 이상 파일이나 소켓을 열 수 없고 `EMFILE`이 난다. 애플리케이션에서는 그게 `too many open files`로 보이는 것 같다.

그러면 WebSocket이나 WebRTC도 결국 소켓이니까, 동접자가 늘면 FD가 같이 늘어나는 구조일까?

## WebSocket + Janus에서는 왜 더 빨리 닿나

일반적인 HTTP REST 요청은 요청과 응답이 끝나면 커넥션이 비교적 빨리 회수된다. 그래서 순간 트래픽이 많아도 동시에 잡고 있는 FD 수는 동접자 수보다 작을 수 있다.

근데 WebSocket은 다르다. 연결한 뒤에도 같은 TCP 커넥션을 계속 들고 있어야 한다. 동접자 수가 곧 점유하고 있는 socket FD 수에 가까워진다.

우리는 여기에 Janus Gateway 위에서 WebRTC를 처리하고 있었다. 사용자 한 명이 시그널링 WebSocket만 쓰는 게 아니라 media UDP socket 같은 것들도 같이 잡을 수 있다. 그러면 동접이 천 명 가까이 갈 때 1024라는 숫자는 생각보다 바로 닿는 한도였던 것 같다.

이제 문제는 명확해졌다. 실제 컨테이너의 `nofile`이 얼마로 잡혀 있는지 확인해야 했다.

```bash
cat /proc/1/limits
```

여기서 `Max open files`가 1024로 잡혀 있었다. WebSocket 연결과 WebRTC media 소켓을 같이 쓰는 서버 입장에서는 너무 낮았다.

그런데 우리는 컨테이너 ulimit을 따로 설정하지 않고 Docker 기본값을 그대로 쓰고 있었다. 내가 알고 있던 기본값은 1,048,576이었는데 왜 1024가 나왔을까?

## 기본값은 왜 바뀌었지?

Docker 업데이트 내역을 찾아보니 Docker 29 패키징 업데이트에서 containerd v2.1.5로 올라가면서 컨테이너 기본 `nofile`이 1,048,576에서 1,024로 바뀐 이력이 있었다.

즉 애플리케이션 코드가 바뀌어서 생긴 문제도, 트래픽 자체가 예상보다 많아서만 생긴 문제도 아니었다. 별도로 명시하지 않은 런타임 기본값이 바뀌었고, 그 값이 WebRTC 워크로드에는 너무 낮았던 것이다.

그래서 배포 설정에 `nofile`을 명시해서 다시 배포했다.

| 위치 | 설정 |
|---|---|
| `docker run` | `--ulimit nofile=1048576:1048576` |
| docker-compose | 서비스 아래 `ulimits.nofile.soft / hard` |
| 데몬 전역 | `/etc/docker/daemon.json`의 `default-ulimits.nofile` |
| Kubernetes | 노드의 containerd `default_ulimits` |

## 다시 돌아와서, 인스턴스를 더 늘린 건 틀렸나?

완전히 틀린 대응은 아니었다. 인스턴스를 늘리면 한 컨테이너가 맡는 연결 수가 줄고, 그래서 에러도 줄어든다.

근데 새 컨테이너도 `nofile=1024`를 그대로 물려받는다. 결국 수평확장은 낮은 FD 한도를 여러 개로 나눠서 버티는 방식에 가까웠다. 지금처럼 사용자 한 명이 여러 소켓을 오래 들고 있는 구조에서는, 먼저 인스턴스 하나가 감당할 수 있는 FD 수를 맞춰주는 게 더 직접적인 해결이었다.

이번에 알게 된 건 `too many open files`를 단순히 서버 리소스 부족으로 보면 안 된다는 점이다. 파일만이 아니라 소켓도 FD고, 연결을 오래 들고 있는 서비스에서는 동접을 볼 때 CPU나 메모리만큼 FD도 같이 봐야 한다.

그리고 Docker의 기본값도 그냥 믿으면 안 될 것 같다. 다음에는 사용자 한 명당 실제로 FD를 몇 개나 잡는지, 그리고 피크 동접에서 어느 정도 `nofile`이 필요할지 먼저 계산해봐야겠다.
