---
title: "[홈 서버 로그 #03] 포트포워딩 대신 Tailscale VPN으로 SSH 접속"
date: 2026-02-20 00:00:00 +0900
author: oogie
categories: [infra]
tags: [tailscale,virtual-private-network,secure-shell,network]     # TAG names should always be lowercase]
use_math: false
img_base: /assets/img/2026-02-20-ssh-tailscale-vpn-setup
series: home-server-log
series_order: 3
---

## TL;DR

[이전 포스팅]({% post_url 2026-02-15-ssh-external-access-setup %})에서는 SK브로드밴드 모뎀(GNT2400)에 포트 포워딩을 설정해 외부 SSH 접속을 해결했다. 동작은 잘 됐지만 22번 포트를 외부에 열어두는 점이 계속 신경 쓰여서, Tailscale VPN으로 전환했다.

---

## 1. 포트 포워딩을 계속 쓰기 불편했던 이유

포트 포워딩은 설정 자체는 간단했지만, 운영할 때 아래 두 점이 불편했다.

- 22번 SSH 포트가 인터넷에 노출된다.
- 공인 IP가 유동이라 접속 주소를 다시 확인해야 할 때가 있다.

원리 학습에는 좋았지만, 실사용 기준에서는 더 닫힌 접근 방식이 필요했다.

---

## 2. Tailscale이 해결하는 방식

Tailscale은 기기들 사이에 가상 사설 네트워크(VPN)를 만든다. 공유기 포트를 외부에 여는 대신, 같은 계정에 등록된 기기끼리 암호화 터널로 통신한다.

```text
[포트 포워딩]
맥북 -> 인터넷 -> 공유기(포트 열림) -> 서버

[Tailscale]
맥북 <-> 암호화 터널 <-> 서버
```

핵심 차이는 아래와 같다.

- 포트 포워딩이 필요 없다.
- 공인 IP를 따로 확인하지 않아도 된다.
- CGNAT 환경에서도 동작한다.
- 각 기기에 Tailscale IP(`100.x.x.x`)가 부여되어 고정 주소처럼 쓸 수 있다.

---

## 3. 설치

### Ubuntu 서버

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

`tailscale up` 실행 후 표시되는 인증 URL로 로그인하면 서버가 등록된다.

![Ubuntu에서 Tailscale 설치 로그]({{ page.img_base }}/install_tailscale.png)

![`tailscale up` 인증 URL 출력 화면]({{ page.img_base }}/tailscale_up.png)

### 맥북

Tailscale 앱을 설치하고 같은 계정으로 로그인하면 준비가 끝난다.

---

## 4. 연결 확인

서버에서 상태를 확인한다.

```bash
tailscale status
```

![`tailscale status` 연결 상태 확인]({{ page.img_base }}/tailscale_status.png)

이후 Tailscale IP로 접속하면 된다.

```bash
ssh oogie@100.xxx.xxx.xxx
```

---

## 5. 운영하면서 좋았던 점

- 한 번 로그인하면 재부팅 후에도 자동 연결이 유지된다.
- 회사 VPN과 같이 쓸 때도 대부분 충돌 없이 동작했다. 스플릿 터널링 방식이라 Tailscale 대상 트래픽만 터널로 보낸다.

Tailscale 대시보드에서 기기 상태와 연결 여부를 한눈에 확인할 수 있는 점도 운영할 때 편했다.

![Tailscale 대시보드에서 기기 연결 상태 확인]({{ page.img_base }}/dashboard.png)

---

## 6. 포트 포워딩 vs Tailscale

| 항목 | 포트 포워딩 | Tailscale |
|------|-----------|-----------|
| 설정 난이도 | 모뎀 관리 페이지에서 직접 설정 | 설치 후 로그인 |
| 보안 노출면 | 포트가 외부에 노출 | 등록된 기기 중심 접근 |
| 공인 IP 의존 | 있음 | 거의 없음 |
| 비용 | 없음 | 무료 플랜으로 시작 가능 |

포트 포워딩으로 네트워크 원리를 이해한 뒤, 실제 운영은 Tailscale로 옮기니 관리가 훨씬 단순해졌다.
