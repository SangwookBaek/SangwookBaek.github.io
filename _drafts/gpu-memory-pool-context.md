# 작업 컨텍스트 — GPU 메모리 풀 글 (집 GPU에서 이어서)

최초 작성 2026-08-22. 본문 재구성 2026-10-16.

## 2026-10-16 재작성

1부와 2부로 나누려던 내용을 기존 post 한 편으로 연결했다. 출발점은 원래 초안의
워커 OOM과 메모리 카운터이고, 질문의 흐름은 다음과 같다.

누수 의심 → 왜 캐시를 보관하나 → 다음 요청이 CuPy라면 → 같은 resource로 연결 →
재사용을 뒷받침하는 측정 → 관측과 반납 책임의 이동 → 메모리 압박 상황의 미검증 동작.

재작성 후 2026-10-16 H100 PCIe GPU 1에서 소규모 실험을 재실행했다.
PyTorch 2.8.0+cu126 / CuPy 13.6.0 / RMM 26.02.00 / Python 3.10.20.
기존 dev 이미지로 네트워크 없는 별도 read-only 컨테이너를 사용했다. 워커 설정은 바꾸지 않았다.

- `assets/experiments/rmm-memory-pool/measure.py`: 재사용 512 MiB, 반납 2048 MiB 시나리오.
- 각 시나리오 × default/RMM × 3회, 모두 새 프로세스. 총 12회.
- 실측 원본과 실행 로그는 로컬에만 보관하고 블로그에는 올리지 않는다.
- `assets/img/posts/rmm-memory-pool/`: 실제 주피터 코드와 출력만 자른 PNG 9장.
- segment/block 및 RMM 재사용·반납 노트북은 실행한 뒤 저장 출력을 비워 코드만 첨부했다.
- 게시일과 글 파일명을 2026-10-16으로 변경했다.
- 모든 반복에서 CuPy 추가 할당 default 512 / RMM 0 MiB.
- 반납 실험 RMM은 해제 후 2048, 동기화 후 1024, empty_cache 후 1024 MiB.
- 반납 실험 default는 해제 후 2048, 동기화 후 2048, empty_cache 후 0 MiB.
- STEP 7 직접 cudaMalloc과 STEP 8 OOM은 이번에 실행하지 않았다.

기존 노트북에는 여전히 실행 출력이 없다. 아래 8월 수치와 새 실측 자료를 구분한다.

기존 해석 중 다음은 수정했다.

- `reserved - allocated` 전체를 즉시 재사용·반납할 수 있다고 단정하지 않는다.
- 한 번의 카운터 관찰로 누수 부재나 원래 OOM 원인을 확정하지 않는다.
- PyTorch 카운터 예외와 반납 함수의 회수량은 당시 버전·연결 방식의 결과로 한정한다.
- `release_threshold`는 할당 상한도, 유휴 시 보유량 보장도 아니다.
- STEP 7의 추가 할당은 메모리 압박 상태에서의 실패를 증명하지 않는다. NVIDIA 문서에는
  같은 프로세스의 `cudaMalloc` 요청을 위해 CUDA 풀이 가진 미사용 메모리를 회수할 수
  있다고 명시돼 있다. STEP 8의 raw malloc 실패 예상은 재검토해야 한다.

근거: [NVIDIA stream-ordered allocator 설명](https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/).
본문에도 관련 공식 문서를 문단별로 연결했다. 아래 기대값 표와 노트북은 8월 실험 설계를
보존한 것이며, 특히 STEP 8 예상은 검증된 결과가 아니다.

## 지금 상태

| 파일 | 상태 |
|---|---|
| `_posts/2026-10-16-gpu-memory-reserved-allocated-caching-allocator.md` | RMM 실험까지 이어지는 한 편으로 재작성. STEP 8과 실제 워커 적용 효과는 미검증 |
| `assets/notebooks/gpu-memory-pool-sharing.ipynb` | 완성. 32셀 / 코드 13개. **아직 실행 안 함(출력 비어 있음)** |
| `_drafts/gpu-memory-pool-context.md` | 이 파일 |

## 남은 실험

1. STEP 8의 실패 예상을 다시 검토한다. 풀을 직접 재사용하는 경로와 CUDA가 회수하는
   경로를 구분하고, 각 요청 직전의 실제 드라이버 여유와 동기화 상태를 기록해야 한다.
2. 실험 코드와 판정표를 검토한 뒤 독점 사용 가능한 GPU에서 두 회차를 실행한다
   (`USE_RMM=False` → 커널 재시작 → `True`).
3. 출력과 실행 환경을 함께 저장하고 본문에 검증 범위를 갱신한다.

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

## 8월에 기록한 측정값과 당시 예상

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

## 원래 구상과 현재 구성

8월에는 캐싱 할당자 설명을 1부로 끝내고, RMM 실험을 2부로 쓰려 했다.
현재 본문은 세그먼트 크기 등 질문에 직접 필요하지 않은 세부를 덜어내고,
왜 반납을 고민하다 공유 풀을 실험하게 됐는지 한 편으로 이어지게 했다.

실제 워크로드에는 PyTorch와 CuPy 외의 할당 경로도 있다. 노트북은 둘로 줄여 비교하고
직접 `cudaMalloc`을 호출하는 경로를 대조군으로 둔 것이다. 실제 워커의 OOM 해결이나
성능 개선은 이 실험만으로 확인한 것이 아니다.

## Segment / block 노트북 실측 추가

- `assets/notebooks/pytorch-segment-blocks.ipynb`: H100 GPU 1의 독립 컨테이너에서
  nbclient + ipykernel로 실제 실행. 출력과 실행 시각 metadata 보존.
- PyTorch 2.8.0+cu126, native, expandable_segments=False. 텐서 최대 10 MiB,
  segment 20 MiB. 원본 snapshot은 `segment-snapshots-20261016.json`.
- 4+6 MiB → 20 MiB segment의 4 active / 6 active / 10 inactive.
- a 삭제 → 4 inactive / 6 active / 10 inactive.
- 3 MiB c → a의 주소 재사용, block은 4 MiB 전체 사용. requested_size는 3 MiB.
  should_split의 큰 block 경로는 remaining > 1 MiB이므로 남는 1 MiB는 분할하지 않음.
- b,c 삭제 → 20 MiB inactive 하나로 병합. empty_cache 뒤 snapshot 빈 목록.
- 실제 실행 노트북 HTML 화면을 CUA screenshot으로 PNG 두 장 저장해 본문 삽입.
- 첫 컨테이너는 tmpfs noexec로 Jupyter 확장 모듈 로딩 실패. 임시 mount에 exec를
  지정한 별도 컨테이너에서 실행했고, tensor_mib 출력 추가 후 전체 재실행함.
