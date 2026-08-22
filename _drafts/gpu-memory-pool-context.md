# 작업 컨텍스트 — GPU 메모리 풀 글 (집 GPU에서 이어서)

작성 2026-08-22. 회사 노트북에서 여기까지 하고 끊음.

## 지금 상태

| 파일 | 상태 |
|---|---|
| `_posts/2026-08-10-gpu-memory-reserved-allocated-caching-allocator.md` | 6절 끝 `*(작성 중)*` 에서 멈춤. 8262 바이트 |
| `assets/notebooks/gpu-memory-pool-sharing.ipynb` | 완성. 32셀 / 코드 13개. **아직 실행 안 함(출력 비어 있음)** |
| `_drafts/gpu-memory-pool-context.md` | 이 파일 |

## 할 일 (집에서)

1. 노트북을 GPU 머신에서 **두 번** 돌린다 (`USE_RMM=False` → 커널 재시작 → `True`)
2. 판정표 실측값을 채운다. 특히 STEP 8 — 회사에서 못 돌린 유일한 단계
3. 그 숫자로 글을 마무리한다

## 노트북 돌리기

### 코랩

배지 링크는 이 브랜치가 머지된 뒤에 동작한다. 그 전에는 코랩에서 `파일 > 노트북 업로드`.
GPU 런타임 확인 (`런타임 > 런타임 유형 변경 > T4 GPU`).

### 집 GPU 로컬

```
pip install rmm-cu12 --extra-index-url=https://pypi.nvidia.com
pip install cupy-cuda12x jupyterlab     # torch 는 이미 있다고 가정
jupyter lab
```

`rmm-cu12` 는 CUDA 12 계열이다. 드라이버가 CUDA 13 이면 `rmm-cu13` 으로 바꿔야 한다.

### 두 번 돌리는 이유

`torch.cuda.memory.change_current_allocator()` 는 **첫 CUDA 할당 이전에만** 먹는다.
한 커널에서 두 모드를 볼 수 없다. 결과는 `results_rmm_off.json` / `results_rmm_on.json`
으로 저장되고, 맨 아래 셀이 둘을 읽어 판정표를 자동으로 채운다.

### 파라미터

기본값은 T4(15 GB) 기준이다. 카드가 크면 그대로 둬도 되고, `SIZE_MIB` 를 키우면 STEP 8
채우는 시간이 줄어든다.

- `SIZE_MIB = 512` — 한 덩어리
- `RETAIN_MIB = 1024` — release threshold
- `HEADROOM_MIB = 256` — **`SIZE_MIB` 보다 작아야 한다.** 크면 드라이버에 여유가 남아서
  STEP 8 의 cupy/생 malloc 이 그냥 성공해버리고 실험이 성립하지 않는다
- `RUN_FILL_TEST = True` — 카드를 거의 꽉 채운다. 세션이 죽으면 재시작하고 False

## 회사에서 이미 측정한 값

H100 / worker 이미지 (torch 2.8.0+cu126, cupy 13.6.0, rmm 26.02.00).
집에서 나온 숫자와 대조용. **STEP 8 만 빠져 있다** — GPU 를 74 GB 까지 채우는 단계라
살아 있는 dev 워커를 굶길 수 있어서 안 돌렸다.

| 항목 | 기대 off | 실측 off | 기대 on | 실측 on |
|---|---|---|---|---|
| STEP 3 cupy 가 추가로 쓴 양 | ≈512 | 512 | ≈0 | **0** |
| STEP 4 torch 카운터 | 읽힘 | 읽힘 | 예외 | RuntimeError |
| STEP 5 cupy 기본 풀이 할당을 담는가 | True | True | False | False |
| STEP 5 `free_all_blocks()` 회수량 | > 0 | 512 | 0 | 0 |
| STEP 6 임계값의 2배 요청 시 peak | ≈2048 | 2048 | ≈2048 | 2048 |
| STEP 6 `synchronize()` 뒤 쥐고 있는 양 | 그대로 | 2560 | ≈1024 | **1024** |
| STEP 6 `empty_cache()` 회수량 | > 0 | 2560 | 0 | 0 |
| STEP 7 생 `cudaMalloc` 이 가져간 양 | ≈512 | 512 | ≈512 | 512 |
| STEP 8 꽉 찬 상태에서 cupy | 실패 | — | 성공 | — |
| STEP 8 꽉 찬 상태에서 생 `cudaMalloc` | 실패 | — | 실패 | — |
| STEP 8 꽉 찬 상태에서 torch | 성공 | — | 성공 | — |

STEP 4 의 예외 메시지 원문:

```
RuntimeError: CUDAPluggableAllocator does not yet support getDeviceStats.
If you need it, please file an issue describing your use case.
```

## 돌려보고 알게 된 것 두 개 (글에 넣을 것)

### 1. `release_threshold` 는 해제 시점이 아니라 동기화 지점에서 적용된다

2048 MiB 를 잡고 해제해도 그대로 2048 을 쥐고 있었다. `torch.cuda.synchronize()` 를
부르니 정확히 1024(=임계값)로 줄었다.

```
peak taken        2048
held after free   2048
held after sync   1024
```

함의가 있다. **커널을 안 돌리고 폴링만 하는 유휴 프로세스는 동기화할 일이 없으니
임계값 초과분까지 계속 붙들고 있는다.** 같은 카드를 쓰는 옆 프로세스에게 그건 없는 메모리다.
"임계값을 정했으니 그만큼만 쥔다" 가 아니다.

### 2. 처음엔 측정 기준을 잘못 잡았다

STEP 6 시작 시점 대비 증분으로 재고 있었는데, 그때 이미 앞 단계가 남긴 캐시 512 MiB 가
쥐여 있어서 1024 가 512 로 나왔다. 풀이 비어 있던 STEP 1 기준으로 바꾸니 맞았다.
글에 쓸지는 선택 — "델타로 재면 안 된다" 는 교훈은 쓸모 있다.

## 글 구성 — 결정할 것

지금 초안(1부)은 **결말이 실제 결론과 반대 방향**이다. 6절까지 읽으면 "`empty_cache()` 를
부르면 된다" 로 끝날 흐름인데, 노트북이 보여주는 결론은 그 반대(풀을 합쳐서 **쥐고 있게**
만들기)다. 그래서 이어붙이려면 뒷부분을 손봐야 한다.

두 편 분리를 추천. 지금 8 KB 에 풀 합치기까지 넣으면 너무 길다.

### 1부 (지금 글) — 마무리만

제목 그대로 "GPU 사용률은 0%인데 메모리가 안 빠진다". 6절(파편화) 뒤에 붙일 것:

- `empty_cache()` 로 해결되는 경우와 안 되는 경우
- **안 되는 경우가 왜 생기는지**로 2부 예고 — 한 프로세스에 할당자가 하나가 아닐 때

### 2부 (새 글) — 노트북이 본론

제안 뼈대:

1. 문제 — 한 프로세스, 두 할당자. torch 가 15 GB 쥐고 14 GB 가 비어 있어도 cupy 에게는
   존재하지 않는 메모리다 (STEP 3, STEP 8)
2. 해결 — RMM 으로 풀 하나에 물리기. torch/cupy 각각 한 줄
3. 대가 세 개
   - torch 카운터가 예외를 던진다 (STEP 4) — 메모리를 진단하려고 넣은 도구가 진단 수단을 없앤다
   - `free_all_blocks()` 가 조용히 no-op (STEP 5) — 에러가 안 나서 더 위험하다
   - 반납이 임계값에 묶이고, 그마저 동기화 지점에서만 (STEP 6)
4. 한계 — 스스로 `cudaMalloc` 하는 라이브러리는 여전히 굶는다 (STEP 7, STEP 8).
   할당자 훅을 제공하는 라이브러리만 편입 가능
5. 결론 — 판단 기준은 "공유가 되는가" 가 아니라 **"내 프로세스의 할당자를 전부 편입할 수
   있는가"**. 하나라도 밖에 남으면 통합 이득은 부분만 받고 관측성과 반납은 잃는다

실제 상황에서는 할당자가 둘이 아니라 넷쯤 된다(직접 만든 커널, CUDA 솔버 라이브러리 등).
노트북은 개념만 보이게 둘로 줄였고, 생 `cudaMalloc` 이 "훅을 안 주는 라이브러리" 역할이다.

## front matter

1부 것을 그대로 쓰면 된다. 2부는 날짜만 바꾸고 `tags` 에 `rmm` 추가.

```yaml
---
title: "..."
date: 2026-08-XX 00:00:00 +0900
author: oogie
categories: [infra]
tags: [cuda,pytorch,gpu,memory,rmm]
use_math: false
---
```
