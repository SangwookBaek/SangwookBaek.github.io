---
title: "컨테이너의 CUDA 초기화 실패를 CDI로 해결하기"
date: 2026-09-09 00:00:00 +0900
author: oogie
categories: [infra]
tags: [cdi, docker, containerd, gpu, cuda, linux]
use_math: false
---

추론 서버에서 **컨테이너의 CUDA 초기화가 실패하는 문제**가 있었다. 호스트에서는 GPU를 정상적으로 인식했지만 컨테이너 안에서는 CUDA를 사용할 수 없었다. 컨테이너와 프로세스는 살아 있었고, 재시작하면 GPU 접근이 회복됐다.

재시작으로 당장의 문제는 풀렸지만, 왜 잘 쓰던 GPU에 접근하지 못하게 됐는지가 궁금했다. 그래서 NVIDIA Container Toolkit의 troubleshooting 문서를 찾아봤다. 우리가 겪은 증상과 비슷하게, 컨테이너가 실행 중인 상태에서 GPU 접근을 잃는 알려진 문제가 있었고 해결 방법 중 하나로 CDI가 제시되어 있었다.

그런데 곧바로 CDI를 적용하는 것만으로는 왜 문제가 해결되는지 알 수 없었다. 기존 GPU 연결이 어떻게 만들어졌고, 실행 중인 컨테이너가 왜 그 연결만 잃었는지부터 확인해봤다.

## 실행 중인 컨테이너는 왜 GPU만 잃었나

먼저 기존 Compose를 보면 GPU 1을 요청하던 부분은 이랬다.

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          device_ids: ["1"]
          capabilities: [gpu]
```

이 설정이 실제 컨테이너가 되기까지는 여러 단계가 있다. Docker Engine은 컨테이너의 생명주기를 containerd에 맡기고, 기본적으로 `runc`를 하위 런타임으로 사용한다. `runc`는 OCI 설정에 적힌 namespace, cgroup, mount 등을 Linux 커널에 적용해 실제 프로세스를 만든다. [Docker의 런타임 구조](https://docs.docker.com/engine/daemon/alternative-runtimes/) · [`runc` 소개](https://github.com/opencontainers/runc#introduction)

```text
Compose 설정
    │
    ▼
Docker가 OCI 실행 설정을 구성
    │
    ▼
containerd가 컨테이너 생명주기를 관리
    │
    ▼
runc가 격리된 Linux 프로세스를 생성
```

컨테이너는 결국 호스트 커널에서 실행되는 프로세스다. `runc`가 OCI 설정을 실제 실행 환경으로 만든다는 점이 이번 문제를 이해하는 출발점이었다.

기존 NVIDIA 연결은 이 생성 과정에 `prestart` hook을 끼워 넣는 방식이었다. `nvidia-container-runtime`이 OCI 설정에 NVIDIA hook을 등록한 뒤 native `runc`를 호출한다. `runc`가 컨테이너를 만들고 애플리케이션을 시작하기 직전에 hook을 한 번 실행하면, hook이 `nvidia-container-cli`를 통해 GPU 장치와 라이브러리, cgroup 접근 권한을 준비한다. [NVIDIA Container Runtime 구조](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/arch-overview.html)

![NVIDIA Container Toolkit의 legacy runtime 구조](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/_images/runtime-architecture.png)

_출처: [NVIDIA Container Toolkit Architecture Overview](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/arch-overview.html)_

그림의 왼쪽 경로가 우리가 사용하던 구조다. Docker가 `nvidia-container-runtime`을 거쳐 `runc`를 호출하고, `runc`가 컨테이너 프로세스를 시작하기 전에 오른쪽의 NVIDIA hook을 실행한다.

hook 자체는 OCI 설정에 등록된다. 문제는 **hook이 실행되면서 추가한 GPU 접근 권한을 `runc`가 관리하는 OCI 장치 설정이 모를 수 있다는 것**이다. 처음 컨테이너를 만들 때는 hook이 실행되므로 CUDA가 정상적으로 동작한다.

차이는 실행 중인 컨테이너의 cgroup이 다시 적용될 때 드러난다. `docker update`로 CPU나 메모리 제한을 바꾸는 작업은 컨테이너를 새로 만들지 않는다. systemd가 cgroup을 관리하는 일부 환경에서는 `systemctl daemon-reload`만으로도 기존 컨테이너의 cgroup 설정이 다시 적용될 수 있다. 어느 경우든 `runc create` 경로를 다시 지나지 않으므로 `prestart` hook도 재실행되지 않는다. [NVIDIA의 GPU 접근 소실 설명](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html#containers-losing-access-to-gpus-with-error-failed-to-initialize-nvml-unknown-error)

```text
처음 컨테이너 생성
    └─ NVIDIA hook 실행 → GPU 접근 가능

systemctl daemon-reload
    └─ 기존 cgroup 설정 재적용
       └─ 컨테이너 생성 아님 → NVIDIA hook 실행 안 됨
          └─ OCI 장치 설정에 없던 GPU 접근 권한 소실 가능
```

그래서 프로세스와 작업 polling은 계속 살아 있는데 CUDA 초기화만 실패할 수 있었다. 컨테이너를 재시작하면 생성 과정에서 hook이 다시 실행되므로 GPU 접근도 돌아온다.

우리 장애 전에도 systemd 재로딩 기록이 있었고, 다른 GPU 컨테이너에서도 NVML 오류가 발생했다. 같은 이미지와 GPU로 컨테이너를 재시작하니 CUDA 접근이 회복됐다. 다만 재시작 전의 cgroup 규칙은 확보하지 못했으므로, systemd 재로딩이 원인이었다고 확정한 것은 아니다. 관측과 맞는 가장 유력한 설명으로 남겨뒀다.

## GPU 설정을 처음부터 OCI에 포함시키기

그렇다면 GPU 장치와 접근 권한을 hook의 일회성 변경으로 두지 않고, `runc`에 전달할 OCI 설정 자체에 포함시키면 된다. NVIDIA troubleshooting에서 해결책으로 제시한 CDI가 바로 이 경로를 지원한다.

GPU 연결을 native CDI로 바꾸고 Compose를 다음과 같이 수정했다.

```yaml
runtime: runc
devices:
  - "nvidia.com/gpu=1"
environment:
  NVIDIA_VISIBLE_DEVICES: void
```

Docker는 CDI 명세에서 `nvidia.com/gpu=1`의 장치 정보를 찾아 OCI 설정에 합친다. `runc`는 처음부터 GPU 장치와 접근 권한이 포함된 설정을 받는다. 이후 설정을 재적용해도 GPU 항목이 같은 OCI 설정 안에 남는다. [NVIDIA CDI 대응 설명](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/troubleshooting.html#mitigations-and-workarounds)

CDI 명세에도 라이브러리나 링크를 준비하는 hook이 있을 수 있다. 중요한 건 hook의 유무 자체보다 **장치와 접근 권한이 런타임의 설정에 포함되는가**였다.

근데 GPU 요청을 `nvidia.com/gpu=1`로 바꾸는 것만으로 어떻게 그게 가능할까? 이 이름 뒤에서 CDI가 어떤 일을 하는지 궁금해졌다.

## CDI가 표현하는 건 무엇인가

CDI는 **Container Device Interface**다. 컨테이너가 특정 장치를 사용하려면 어떤 실행 환경이 필요한지를 표현하는 공통 명세다. Docker뿐 아니라 Podman, containerd 같은 런타임에서도 사용할 수 있다.

GPU를 사용하려면 장치 파일 하나만 보이게 하는 것으로 끝나지 않을 수 있다. 여러 장치 노드, 사용자 공간의 드라이버 라이브러리, 환경변수, 추가 초기화 작업이 필요하다. 제조사마다 필요한 것도 다를 것이다.

이걸 런타임마다 따로 구현하면 NVIDIA는 Docker용 연결 방식, 다른 런타임용 연결 방식을 각각 맞춰야 한다. CDI는 제조사가 필요한 설정을 공통 형식으로 설명하고, 런타임이 그 설명을 읽게 한다. [CDI가 필요한 이유](https://github.com/cncf-tags/container-device-interface#why-is-cdi-needed)

그 설명이 YAML이나 JSON으로 된 CDI 명세 파일이다. 여기에는 **컨테이너의 OCI 설정을 어떻게 수정할지**가 들어 있다. OCI 설정은 `runc` 같은 하위 런타임에 전달하는 컨테이너 실행 설정이라고 보면 된다. [CDI 명세](https://github.com/cncf-tags/container-device-interface/blob/main/SPEC.md#overview)

실제 파일을 보면 이 명세가 컨테이너 설정과 어떻게 연결되는지 더 잘 보인다.

## `nvidia.com/gpu=1`은 실제로 무엇과 연결되나

우리 서버의 `/var/run/cdi/nvidia.yaml`에서 GPU 1에 해당하는 부분만 추렸다. 전체 파일은 아니다.

```yaml
cdiVersion: 0.7.0
kind: nvidia.com/gpu
devices:
  - name: "1"
    containerEdits:
      deviceNodes:
        - path: /dev/nvidia1
          major: 195
          minor: 1
          permissions: rwm
```

`kind`와 장치의 `name`을 합치면 Compose에서 요청한 이름이 된다.

```text
nvidia.com/gpu + = + 1
          ↓
nvidia.com/gpu=1
```

`nvidia.com`은 여기서 접속할 서버 주소가 아니다. 장치를 구분하기 위한 이름의 일부다.

Docker는 이 이름으로 명세를 찾고, `containerEdits`를 컨테이너 설정에 반영한다. 위 항목은 `/dev/nvidia1`이라는 장치 노드와 장치 번호, 접근 권한을 설명한다. 실제 파일의 공통 설정에는 `/dev/nvidiactl`, `/dev/nvidia-uvm` 및 드라이버 라이브러리 등의 마운트도 있었다.

GPU 하나를 지정했는데 명세가 길었던 이유가 이것이었다. 그 GPU를 사용하는 데 필요한 연결 정보를 함께 적어둔 파일이었음.

## Docker는 그 명세를 실제로 어떻게 쓰나

설명만 보면 중간에 CDI 전용 컨테이너 같은 게 하나 있어야 할 것 같기도 했다. Docker 쪽 코드를 보면 더 직접적이다.

우리 서버에서 사용하던 Docker 26.1.3의 `daemon/cdi.go`에는 CDI 장치 요청을 처리하는 코드가 있다. 필요한 부분만 보면 아래 호출이다.

```go
_, err := c.registry.InjectDevices(s, cdiDeviceNames...)
```

여기서 `s`는 OCI 설정이고, `cdiDeviceNames`는 요청한 장치 이름들이다. Docker가 CDI 명세 캐시를 만들고, 요청받은 장치의 설정을 OCI 설정에 주입한다. [Docker 26.1.3의 CDI 구현](https://github.com/moby/moby/blob/v26.1.3/daemon/cdi.go)

CDI 라이브러리의 `ContainerEdits.Apply`도 장치 항목을 추가하고, 해당 장치의 cgroup 접근 규칙을 추가한다. 마운트와 환경변수 등도 같은 과정에서 적용한다. “명세를 읽는다”는 게 이 설정 변경 작업이었다. [CDI의 OCI 설정 반영 코드](https://github.com/cncf-tags/container-device-interface/blob/main/pkg/cdi/container-edits.go)

containerd도 CDI 지원을 제공한다. 다만 여기서도 NVIDIA 패키지가 “CDI Docker 컨테이너”를 만들어 플러그인처럼 꽂는다는 뜻은 아니다. 예를 들어 containerd 1.7의 CRI 설정에는 `enable_cdi`, `cdi_spec_dirs`가 있다. CDI 명세를 소비하는 통합 경로가 있는 것이다. Docker를 사용할 때는 앞에서 본 Docker의 처리 경로를 구분해서 봐야 한다. [containerd 1.7 CRI 설정](https://github.com/containerd/containerd/blob/release/1.7/docs/cri/config.md)

그러면 NVIDIA 패키지는 무엇을 해주는 걸까?

## NVIDIA가 구현하는 부분

내가 이름을 혼동했던 패키지의 정확한 이름은 `nvidia-container-toolkit-base`다.

CDI라는 공통 규약에 맞춰 NVIDIA GPU의 설정을 생성하는 도구가 `nvidia-ctk`이고, 이 도구는 base 패키지에 들어 있다. base 패키지는 `nvidia-container-runtime`도 포함한다. 전체 Toolkit에는 legacy hook과 관련 라이브러리 패키지들도 함께 연결된다. [NVIDIA 패키지 구성](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/arch-overview.html#components-and-packages)

역할을 나누면 이렇다.

| 구성 요소 | 하는 일 |
| --- | --- |
| NVIDIA GPU 드라이버 | 호스트에서 실제 GPU를 제어 |
| `nvidia-ctk` 등 NVIDIA 도구 | NVIDIA 장치에 필요한 CDI 명세 생성과 보조 작업 |
| Docker의 CDI 지원 | 장치 이름으로 명세를 찾아 OCI 설정에 반영 |
| `runc` | 전달받은 설정에 따라 컨테이너 실행 환경 구성 |
| 컨테이너의 애플리케이션·라이브러리 | 준비된 장치에 접근해 CUDA 사용 |

즉, NVIDIA 쪽은 자기 장치를 어떻게 연결해야 하는지 알고, Docker 쪽은 공통 명세를 어떻게 컨테이너 설정에 적용할지 안다. 명세를 사이에 두고 두 역할이 만난다.

## 실제 세팅은 서버와 Compose로 나뉜다

이 구조를 이해하기 전에는 긴 CDI YAML을 저장소에 넣고 배포해야 하나 싶었다. 지금은 서버가 명세를 관리하고, Compose에는 사용할 장치 이름만 둔다.

우선 호스트에는 NVIDIA 드라이버와 Container Toolkit이 필요하다. CDI 전용 환경에서는 `nvidia-container-toolkit-base`만으로 필요한 도구를 설치할 수도 있다. 우리 서버에는 전체 Toolkit이 이미 설치되어 있어서 관련 패키지를 함께 1.17.7에서 1.20.0으로 올렸다. 패키지 저장소와 설치 방법은 [NVIDIA 설치 가이드](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)를 따른다.

Container Toolkit 1.18부터는 공식 `nvidia-cdi-refresh`가 명세를 자동 생성한다. 설치 후 해당 유닛이 활성화되어 있지 않다면 아래처럼 활성화할 수 있다.

```sh
sudo systemctl enable --now nvidia-cdi-refresh.path
sudo systemctl enable --now nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

`.path`는 변경을 감시하고 `.service`가 `/var/run/cdi/nvidia.yaml`을 생성한다. Toolkit·드라이버 설치/업데이트와 부팅 시 갱신한다. MIG 재구성과 드라이버 제거는 자동 처리 대상에서 빠져 있어 별도 갱신이 필요하다. [NVIDIA CDI 자동 생성](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html#automatic-cdi-specification-generation)

우리 서버의 Docker 26.1.3에서는 CDI도 별도로 켰다. `/etc/docker/daemon.json`의 관련 설정은 다음과 같다. 기존 설정에 이 항목을 합치고, 최초 CDI 활성화 때 Docker daemon을 재시작해 적용했다.

```json
{
  "features": {
    "cdi": true
  }
}
```

Docker의 기본 명세 검색 위치는 `/etc/cdi`, `/var/run/cdi`다. 우리 환경에서는 기존 수동 생성 파일을 백업으로 옮기고, refresh 서비스가 생성하는 파일을 사용하게 했다. [Docker CDI 설정](https://docs.docker.com/reference/cli/dockerd/#configure-cdi-devices)

Compose에서 GPU와 관련해 남은 부분은 이 정도다. 실제 파일에서는 GPU 번호를 환경변수로 받지만, 여기서는 1로 펼쳐 썼다.

```yaml
runtime: runc
devices:
  - "nvidia.com/gpu=1"
environment:
  NVIDIA_VISIBLE_DEVICES: void
```

`NVIDIA_VISIBLE_DEVICES: void`는 기존 NVIDIA 방식의 중복 주입을 막기 위해 넣었다. GPU 선택은 `devices`에서 한다.

이제 앱 이미지를 배포할 때 CDI YAML을 이미지에 넣거나 CD에서 매번 생성할 필요는 없다. 앱 코드가 바뀌는 것과 서버의 장치·드라이버 구성이 바뀌는 것은 갱신 주기가 다르다. refresh는 후자를 맡는다. 명세 재생성이 이미 실행 중인 컨테이너의 드라이버 연결까지 실시간으로 교체해준다는 뜻은 아니다.

## 지금 이해한 연결 과정

적용 후 새 CDI 컨테이너에서 실제 CUDA 메모리 할당·연산·결과 읽기를 확인했다. 별도 컨테이너의 CPU 제한을 갱신해도 기존 CUDA tensor 연산이 됐고, Toolkit 설치 중 systemd 재로드를 거친 뒤에도 기존 inference의 CUDA 검사가 통과했다. 재부팅 이후와 전체 추론 경로를 모두 검증한 것은 아니다.

지금은 `nvidia.com/gpu=1`을 이렇게 이해하고 있다.

**NVIDIA 도구가 장치 연결 명세를 만들고 → Docker가 명세를 OCI 설정에 반영하고 → `runc`가 GPU에 접근할 수 있는 컨테이너 실행 환경을 구성한다.**

`nvidia.com/gpu=1`은 이 과정을 시작할 때 지정하는 장치 이름이다.
