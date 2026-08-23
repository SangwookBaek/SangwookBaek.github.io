---
layout: post
title: "[홈 서버 로그 #03] 포트포워딩 대신 Tailscale VPN으로 SSH 접속"
date: 2026-02-20 10:00:00 +0900
categories: [Home Server]
tags: [Home Server, SSH, Tailscale, VPN, Network]
image:
  path: /assets/img/posts/ssh-tailscale-vpn/tailscale-network.png
  alt: Tailscale을 통한 홈 서버 접속 경로
series: homeserver
series_order: 3
---

## Intro

이전 글에서 포트포워딩으로 외부 SSH 접속을 열었다. 집 밖에서 서버에 붙는다는 목적은 달성했다.

그런데 막상 설정하고 나니 계속 신경 쓰이는 것이 있었다. 공인 IP가 바뀌면 어떻게 접속하지, 22번 포트를 외부에 열어둬도 괜찮을까, 공유기를 바꾸면 또 같은 설정을 해야 하나. DDNS와 키 인증을 붙이면 해결할 수 있는 문제들이지만, 개인 서버에 접속하려고 관리해야 할 일이 생각보다 많아 보였다.

포트포워딩을 이해한 뒤에야 “그럼 꼭 공개 포트를 열어야 하나?”라는 질문이 생겼다. 그러다 Tailscale을 알게 됐다.

## 포트포워딩과는 출발점이 조금 다르다

포트포워딩은 외부에서 집 공유기의 공인 IP로 들어온 요청을 서버로 넘긴다.

```text
내 노트북 → 인터넷 → 집 공유기:22 → 홈 서버:22
```

Tailscale은 서버와 내 노트북을 같은 가상 사설망에 넣는 방식이다. 각 기기에 Tailscale IP가 생기고, 같은 계정으로 인증된 기기끼리 그 주소로 통신한다.

```text
내 노트북 ── Tailscale 사설망 ── 홈 서버
```

처음에는 VPN이면 트래픽이 전부 어떤 중앙 서버를 거쳐 갈 거라고 생각했다. Tailscale은 가능한 경우 기기끼리 직접 연결하고, 연결이 어려운 환경에서는 릴레이를 사용한다. 중요한 건 적어도 내가 공유기에 SSH 포트를 외부로 열지 않아도 된다는 점이었다.

![Tailscale 네트워크](/assets/img/posts/ssh-tailscale-vpn/tailscale-network.png)

## 설치하고 나서 실제로 달라진 것

서버에서는 설치 후 로그인만 했다.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Mac에는 Tailscale 앱을 설치하고 같은 계정으로 로그인했다. 두 기기 모두 온라인이면 서버에서 이런 식으로 보였다.

```bash
tailscale status
```

이제 로컬 IP나 공인 IP 대신 Tailscale이 준 `100.x.x.x` 주소로 SSH 접속할 수 있다.

```bash
ssh user@100.x.x.x
```

이 주소가 인터넷에서 누구나 접근할 수 있는 주소는 아니다. 같은 tailnet에 승인된 기기여야 한다. 공유기의 포트포워딩 규칙도 더 이상 이 접속을 위해서는 필요하지 않았다.

서버를 재부팅한 뒤에도 자동으로 다시 연결됐다. 회사 VPN을 켠 상태에서는 네트워크 정책에 따라 연결이 달라질 수 있다고 생각했는데, 내 환경에서는 split tunnel처럼 같이 사용할 수 있었다. 이 부분은 회사 VPN 설정에 따라 다를 수 있으니 다른 환경까지 일반화할 수는 없다.

## 포트포워딩을 한 건 헛된 일이 아니었다

Tailscale을 쓰면 처음부터 이걸 쓰면 되지 않았을까 싶기도 했다. 그래도 포트포워딩을 먼저 해본 덕분에 사설 IP, 공인 IP, NAT가 각각 무엇을 해결하는지는 알게 됐다.

포트포워딩은 외부 요청이 집 안의 특정 기기로 들어오는 길을 직접 만드는 방식이었다. Tailscale은 그 길을 공개 인터넷에서 찾지 않도록 별도의 네트워크 관계를 만들어 주는 방식에 가깝다.

지금 내 목적에는 Tailscale 쪽이 더 자연스럽다. 다만 서버가 단순히 내가 접속하는 장비를 넘어 공개 서비스를 제공하게 되면, 그때는 다시 공인 접근과 reverse proxy, 도메인, 방화벽을 따로 고민해야 한다. 접속을 편하게 만드는 것과 서비스를 공개하는 것은 다른 문제였다.
