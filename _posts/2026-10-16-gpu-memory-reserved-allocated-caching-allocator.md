---
title: "GPU 메모리를 비우려다, RMM으로 풀을 합치게 된 이유"
date: 2026-10-16 00:00:00 +0900
author: oogie
categories: [infra]
tags: [cuda,pytorch,gpu,memory,rmm]
use_math: false
---

GPU 추론 워커에서 OOM이 나서 상태를 봤는데, GPU 사용률은 0%였다. 계산은 안 하고 있는데 메모리는 16 GB쯤 잡혀 있었다. 태스크가 끝나도 그대로였고, 프로세스를 재시작하면 내려갔다.

처음에는 텐서 참조가 어딘가에 남아 있다고 생각했다. 워커가 한 프로세스에서 태스크를 계속 받으니까, 이전 태스크의 메모리가 쌓이는 게 아닐까.

그런데 안쪽을 보니 PyTorch가 붙들고 있는 메모리와 텐서가 쓰는 메모리가 달랐다. 이 차이를 따라가다가 메모리 풀을 보게 됐고, 나중에는 RMM으로 PyTorch와 CuPy의 풀을 공유하는 실험까지 하게 됐다.

메모리를 내려놓게 하려던 건데, 왜 다시 쥐고 있는 방법을 찾게 됐는지 적어보려고 한다.

## 16 GB를 누가 쓰고 있었나

`nvidia-smi`만으로는 프로세스 안에서 누가 메모리를 쓰는지 구분할 수 없었다. 그래서 PyTorch의 카운터를 같이 봤다.

```python
MIB = 1024 * 1024
print(torch.cuda.memory_allocated() / MIB)
print(torch.cuda.memory_reserved() / MIB)
```

`memory_allocated()`는 텐서가 차지한 양이고, `memory_reserved()`는 PyTorch의 캐싱 할당자가 관리하는 전체 양이다. 텐서가 더 이상 쓰지 않아도 할당자가 보관하는 메모리는 `nvidia-smi`에 계속 사용 중으로 나타난다. [PyTorch 메모리 관리 문서](https://docs.pytorch.org/docs/2.8/notes/cuda.html#memory-management)

당시 할당된 양은 1,534 MiB, 예약된 양은 15,458 MiB로 차이가 13,924 MiB였다. 처음에는 이걸 전부 살아 있는 텐서가 붙들고 있다고 생각했는데, 적어도 그 설명은 맞지 않았다.

다만 이 숫자 한 번으로 누수가 없다고 결론 낼 수도 없다. 남아 있는 1,534 MiB가 정상인지, 태스크를 반복하면 늘어나는지는 별도 문제다. 지금 확인한 건 **예약된 양 전체가 살아 있는 텐서의 양은 아니라는 것**이다.

그러면 PyTorch는 텐서가 놓은 메모리를 왜 계속 갖고 있을까.

## PyTorch는 다음 텐서에 다시 주려고 보관한다

PyTorch의 기본 캐싱 할당자는 **한번 확보한 메모리를 다음 텐서에 다시 주는 쪽**으로 설계돼 있다. 텐서가 없어질 때마다 CUDA에 반납하면, 다음 텐서를 만들 때 다시 할당받는 비용을 치러야 하기 때문이다. 캐시에서 재사용하면 `cudaMalloc`과 `cudaFree`를 매번 호출하지 않아도 된다. 여기서 메모리를 보관하기로 한 주체는 PyTorch다. [PyTorch 캐싱 할당자 구현](https://github.com/pytorch/pytorch/blob/v2.8.0/c10/cuda/CUDACachingAllocator.cpp)

그럼 받아온 메모리를 어떻게 나눠 쓰나. 기본 `native` 할당자에서 CUDA로부터 받은 메모리 덩어리를 **segment**, 그 안에서 나눠 관리하는 조각을 **block**이라고 부른다. 텐서의 저장 공간은 이 block에서 할당된다. [PyTorch의 segment와 block 설명](https://docs.pytorch.org/docs/2.8/torch_cuda_memory.html#snapshot-api-reference)

실제 구현에도 `Block` 구조체가 있다. [PyTorch 2.8의 `Block`](https://github.com/pytorch/pytorch/blob/v2.8.0/c10/cuda/CUDACachingAllocator.cpp#L184)에서 필요한 필드만 보면 이렇다.

```cpp
size_t size;
size_t requested_size;
void* ptr{nullptr};
bool allocated{false};
Block* prev{nullptr};
Block* next{nullptr};
```

크기와 주소, 사용 중인지 여부, 분할된 이웃 block을 가리키는 포인터를 갖고 있다. `size`와 `requested_size`가 따로 있다는 것도 눈에 들어왔다. 요청한 크기와 실제 block 크기가 꼭 같지는 않다는 뜻인가.

직접 확인하려고 H100에서 작은 텐서를 만들고 `torch.cuda.memory_snapshot()`을 찍어봤다. PyTorch 2.8.0+cu126의 `native` backend에서 `expandable_segments=False`로 실행했다. 이 API가 돌려주는 건 내부 메모리 상태를 담은 Python 딕셔너리 목록이다. 아래의 `inspect_segment()`는 그중 추적하는 segment의 `total_size`, `allocated_size`, 각 block의 `size`·`state`만 골라 MiB로 출력하는 함수다. 함수와 준비 코드는 다음과 같다.

```python
import gc
from pprint import pprint

import torch

MIB = 1024 * 1024

def inspect_segment(address):
    snapshot = torch.cuda.memory_snapshot()
    pprint([
        {
            "total_mib": segment["total_size"] // MIB,
            "allocated_mib": segment["allocated_size"] // MIB,
            "blocks": [
                (block["size"] // MIB, block["state"])
                for block in segment["blocks"]
            ],
        }
        for segment in snapshot
        if segment["address"] == address
    ], sort_dicts=False)
```

![segment와 block 실행 코드 및 결과](/assets/img/posts/rmm-memory-pool/segment-allocate.png)

텐서는 4 MiB와 6 MiB인데 `total_mib`는 20이다. 그 안이 **4 사용 중 + 6 사용 중 + 10 비어 있음**으로 나뉘어 있다. 이 버전의 기본 할당자는 맞는 캐시가 없을 때 1 MiB 초과·10 MiB 미만 요청에 20 MiB 덩어리를 받아 나눠 쓰는 경로가 있다. 모든 segment가 20 MiB로 고정된다는 뜻은 아니다. [할당 크기를 정하는 구현](https://github.com/pytorch/pytorch/blob/v2.8.0/c10/cuda/CUDACachingAllocator.cpp#L2519)

![segment와 block 실행 코드 및 결과](/assets/img/posts/rmm-memory-pool/segment-free-block.png)

`a`를 지우면 4 MiB block의 상태만 `active_allocated`에서 `inactive`로 바뀐다. 할당된 양은 10에서 6으로 줄지만 segment는 20 MiB 그대로다. **텐서가 놓은 메모리가 PyTorch의 재사용 가능한 block으로 남는 모습**을 여기서 볼 수 있었다.

![segment와 block 실행 코드 및 결과](/assets/img/posts/rmm-memory-pool/segment-reuse-block.png)

그 다음 3 MiB짜리 `c`를 만들었더니 `reused_a_address: True`가 나왔다. 그런데 block 크기는 여전히 4 MiB다. 이번 설정에서 큰 block을 나눌 때는 남는 크기가 1 MiB보다 커야 하는데, 4에서 3을 떼면 정확히 1 MiB만 남아 분할하지 않은 것이다. 그래서 텐서의 데이터는 3 MiB여도 할당자가 내준 block은 4 MiB였다. [block 분할 조건](https://github.com/pytorch/pytorch/blob/v2.8.0/c10/cuda/CUDACachingAllocator.cpp#L2510)

![segment와 block 실행 코드 및 결과](/assets/img/posts/rmm-memory-pool/segment-merge-blocks.png)

남은 텐서까지 지우자 이웃한 빈 block들이 하나의 20 MiB block으로 합쳐졌다. 할당된 양은 0이지만 segment는 여전히 PyTorch가 보유하고 있었다.

![segment와 block 실행 코드 및 결과](/assets/img/posts/rmm-memory-pool/segment-empty-cache.png)

`empty_cache()`를 호출한 뒤에야 빈 목록이 나왔다. 추적하던 segment가 snapshot에서 사라진 것이다. 앞에서 본 `allocated`와 `reserved`의 차이가 실제 객체 상태에서는 이렇게 나타나는 거였다.

이렇게 보니 안 쓰는 메모리를 무조건 반납해야 한다는 생각도 달라졌다. PyTorch 입장에서는 다음 텐서가 가져갈 수 있도록 보관한 공간이었다. 그런데 이 전략이 통하려면, 다음 요청도 그 block을 관리하는 할당자로 들어와야 한다.

## 근데 다음 요청이 CuPy라면

한 프로세스가 GPU를 쓴다고 해서, 그 안의 메모리를 한 할당자가 관리하는 건 아니었다. CuPy도 기본적으로 자기 메모리 풀을 갖는다. 배열이 사라져도 풀에 보관해 재사용한다는 목적은 같다. [CuPy 메모리 관리 문서](https://docs.cupy.dev/en/v13.6.0/user_guide/memory.html)

문제는 각자가 관리한다는 점이다.

```text
PyTorch 요청 → PyTorch 캐시 → CUDA
CuPy 요청    → CuPy 풀      → CUDA
```

PyTorch의 캐시에 빈 공간이 있어도 CuPy의 기본 풀은 그 공간을 직접 꺼내 쓸 수 없다. 같은 프로세스라는 사실만으로 두 할당자의 재사용 범위가 합쳐지지는 않는다.

`torch.cuda.empty_cache()`로 사용하지 않는 캐시를 반납하면 다른 할당자가 쓸 여지가 생긴다. 다만 이 함수도 살아 있는 텐서를 없애지는 않는다. 앞의 기본 할당자에서는 segment 안에 사용 중이거나 GPU 작업의 완료를 기다리는 block이 남아 있으면 그 segment를 통째로 반납할 수 없다. `reserved - allocated`를 그대로 “즉시 반납 가능한 양”으로 읽으면 안 되는 이유다. [PyTorch의 segment와 block 설명](https://docs.pytorch.org/docs/2.8/torch_cuda_memory.html#snapshot-api-reference)

라이브러리 사이를 넘어갈 때마다 캐시를 비우는 방법은 생각할 수 있다. 그런데 그러면 재사용하려고 만든 캐시를 매번 비우고, 다음 라이브러리는 다시 메모리를 받아야 한다.

내가 확인하고 싶었던 건 그 사이를 생략할 수 있는지였다. **PyTorch가 놓은 공간을 드라이버에 반납하지 않고 CuPy가 바로 재사용할 수 있을까.**

## RMM에서는 무엇을 합치는 건가

RMM(RAPIDS Memory Manager)은 GPU 메모리 할당 방식을 memory resource로 다루고, 다른 라이브러리가 그 resource를 사용하도록 연결하는 할당자를 제공한다. RMM을 쓴다고 무조건 풀을 쓰는 건 아니다. 기본 resource는 `cudaMalloc`을 사용하는 `CudaMemoryResource`이고, 어떤 resource를 선택하느냐에 따라 동작이 달라진다. [RMM 사용 가이드](https://docs.rapids.ai/api/rmm/stable/user_guide/guide/)

이번 실험에서는 `CudaAsyncMemoryResource`를 선택했다. 이 resource는 CUDA의 stream-ordered allocator를 사용한다. `cudaMallocAsync`와 `cudaFreeAsync` 계열로 할당·해제를 처리하고, 그 아래 CUDA 풀이 메모리를 보관한다. [RMM의 async resource 설명](https://docs.rapids.ai/api/librmm/stable/classrmm_1_1mr_1_1cuda__async__memory__resource.html)

왜 stream이 여기서 나올까. Python에서 텐서를 놓았더라도 GPU에서는 그 메모리를 쓰는 작업이 아직 진행 중일 수 있다. 따라서 재사용하려면 이전 사용이 끝났다는 순서가 필요하다. stream-ordered allocator는 할당과 해제를 GPU 작업의 실행 순서에 연결한다. 다른 stream을 걸치면 그 사이의 의존성도 맞아야 한다. [CUDA의 stream ordering 설명](https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/)

여기에 PyTorch와 CuPy의 할당 요청을 연결했다.

```text
PyTorch ─┐
         ├→ RMM의 같은 memory resource → CUDA async pool
CuPy ────┘
```

기존에 따로 있던 두 캐시의 내용을 나중에 합치는 건 아니다. 앞으로의 할당 요청이 같은 resource를 통하도록 입구를 바꾸는 것이다. 노트북에서 관측용 계층을 빼면 핵심 설정은 이 정도다.

```python
import cupy as cp
import rmm
import torch
from rmm.allocators.cupy import rmm_cupy_allocator
from rmm.allocators.torch import rmm_torch_allocator

pool = rmm.mr.CudaAsyncMemoryResource(
    initial_pool_size=0, release_threshold=1024 * 1024 * 1024
)
rmm.mr.set_current_device_resource(pool)

torch.cuda.memory.change_current_allocator(rmm_torch_allocator)
cp.cuda.set_allocator(rmm_cupy_allocator)
```

이 연결 방식은 [RMM의 PyTorch·CuPy 연동 API](https://docs.rapids.ai/api/rmm/stable/user_guide/guide/)를 사용한다. PyTorch의 현재 할당자를 교체하므로, 기존 할당자가 이미 초기화된 뒤에는 바꿀 수 없다. 실험에서는 CUDA 할당 전에 설정하고, 기본 설정과 비교할 때 커널을 재시작했다. [PyTorch의 할당자 교체 제약](https://docs.pytorch.org/docs/2.8/notes/cuda.html#using-custom-memory-allocators-for-cuda)

여기서 바뀐 건 텐서나 배열의 내용이 아니라, 새 메모리를 어디에 요청하느냐다.

## 정말 재사용했다면 어떤 숫자가 나와야 할까

풀을 공유했다는 설정만으로는 부족하다. 실제로 한쪽이 놓은 메모리를 다른 쪽이 쓰는지 봐야 한다.

그래서 순서를 단순하게 만들었다. PyTorch로 512 MiB를 할당하고 텐서를 없앤다. 그 다음 CuPy로 같은 크기를 요청한다. 이때 CuPy 요청 전후로 드라이버가 보는 여유 메모리를 비교한다.

풀이 따로라면 CuPy는 추가 메모리를 받아와야 할 것이다. 같은 풀의 빈 공간을 재사용한다면 추가로 받아오는 양은 거의 없어야 한다.

8월에 이 순서로 실험한 메모가 있었는데, 이번에는 같은 순서로 다시 측정했다. 2026년 10월 16일, H100 PCIe에서 PyTorch `2.8.0+cu126`, CuPy `13.6.0`, RMM `26.02.00`을 사용했다. 각 설정을 새 프로세스에서 3번씩 실행했고, 세 번 모두 같은 값이 나왔다.

아래 코드를 새 주피터 커널에서 실행했다. 먼저 측정에 쓸 코드를 준비했다. RMM 쪽은 앞의 할당자 연결을 마친 뒤 이 코드를 실행하고, 기본 설정은 연결 없이 실행했다.

```python
import gc

import cupy as cp
import torch

MIB = 1024 * 1024

torch.cuda.init()
cp.cuda.runtime.memGetInfo()
torch.cuda.synchronize()
baseline_free = cp.cuda.runtime.memGetInfo()[0]

def held_mib():
    return (baseline_free - cp.cuda.runtime.memGetInfo()[0]) / MIB
```

`held_mib()`는 시작점보다 드라이버 여유 메모리가 얼마나 줄었는지 MiB로 읽는다. 텐서 크기를 더한 값이 아니라 드라이버에서 직접 읽은 차이다.

먼저 각각 기본 할당자를 쓰면 이렇다.

![기본 할당자 실행 코드 및 print 결과](/assets/img/posts/rmm-memory-pool/reuse-default-print.png)

텐서를 지워도 512 MiB가 남아 있고, CuPy 배열을 만들자 1,024 MiB가 됐다. CuPy가 쓸 512 MiB를 추가로 받아온 것이다.

새 커널에서 두 라이브러리를 같은 RMM resource에 연결하고 같은 순서로 실행했다.

![RMM 재사용 코드 및 print 결과](/assets/img/posts/rmm-memory-pool/reuse-rmm-print.png)

이번에는 CuPy 배열을 만들어도 512 MiB 그대로였다. 두 번째 요청에서 드라이버로부터 추가로 받은 양은 0 MiB다.

이 결과는 두 번째 요청을 풀이 이미 갖고 있던 메모리로 처리했다는 해석을 뒷받침한다. 같은 주소가 돌아왔는지까지 확인한 건 아니다.

또 이 실험은 “새로 확보한 메모리가 줄었는가”를 본 것이다. 실제 모델이 빨라졌는지, 원래 워커의 OOM이 사라지는지까지 보여주지는 않는다. 동시에 살아 있어야 하는 데이터가 GPU 용량보다 크다면 풀을 공유해도 그 데이터가 작아지는 건 아니다.

## 할당자를 바꾸니, 보던 숫자도 달라졌다

처음 문제를 이해할 때 썼던 게 `memory_allocated()`와 `memory_reserved()`였다. 그런데 RMM으로 연결한 실험에서는 이 카운터를 읽는 단계에서 예외가 났다.

`CUDAPluggableAllocator`가 `getDeviceStats`를 지원하지 않는다는 예외였다. 당시 버전과 이 연결 방식에서 확인한 제한이다. RMM을 쓰는 모든 구성에서 관측이 불가능하다는 뜻은 아니다.

기존 카운터는 PyTorch 캐싱 할당자의 장부였는데, 이제 할당 경로가 바뀌었다. 그래서 노트북은 두 설정에서 공통으로 읽을 수 있는 `torch.cuda.mem_get_info()`의 드라이버 여유 메모리를 비교했다. 이 값은 GPU 전체의 영향을 받으므로 다른 프로세스의 사용량이 변하면 실험에도 섞일 수 있다.

RMM 쪽에는 `StatisticsResourceAdaptor`를 붙여 할당 통계를 볼 수 있다. 다만 resource를 통과한 할당량과 하위 풀이 캐시까지 포함해 보유한 양은 구분해야 한다. 기존 `reserved`를 다른 카운터 하나로 이름만 바꿔 대체할 수 있는지는 따져봐야 한다. [RMM 통계 계층 설명](https://docs.rapids.ai/api/rmm/stable/user_guide/guide/#memory-statistics-and-profiling)

반납 함수에서도 비슷한 일이 생겼다. 실험에서 CuPy 기본 풀의 `free_all_blocks()`는 RMM 설정일 때 0 MiB를 회수했다. `torch.cuda.empty_cache()`도 마찬가지였다. 요청을 RMM으로 보내놓고 예전 풀에 비우라고 한 셈이다.

그러면 이제 메모리를 돌려주는 시점은 어디서 정해야 할까.

## 1 GiB를 남기라고 했는데, 왜 2 GiB를 쥐고 있나

설정에 넣은 `release_threshold`를 처음 보면 메모리 상한처럼 읽기 쉽다. 실험에서는 1,024 MiB로 설정하고 그 두 배인 2,048 MiB를 요청했다. 할당은 됐다.

더 흥미로웠던 건 놓은 다음이었다.

기본 할당자에서는 텐서를 지우고 동기화해도 2,048 MiB가 남았다. `empty_cache()`를 호출하자 0이 됐다.

![기본 할당자 실행 코드 및 print 결과](/assets/img/posts/rmm-memory-pool/release-default-print.png)

RMM은 동기화에서 1,024 MiB로 줄었고, 그 뒤 `empty_cache()`를 호출해도 그대로였다.

![RMM 반납 코드 및 print 결과](/assets/img/posts/rmm-memory-pool/release-rmm-print.png)

이 실험은 재사용 실험과 별도의 새 프로세스에서 실행했다. 앞서 각 설정을 3번 측정한 값과 이번 측정도 일치했다. RMM은 초기 풀 크기 0, release threshold 1,024 MiB로 설정했다.

이 값은 할당을 막는 상한이 아니다. CUDA 문서에서 release threshold는 풀이 보유한 메모리가 임계값을 넘었을 때, 다음 stream·event·context 동기화에서 시스템으로 반납을 시도하는 기준이다. 아직 사용 중인 메모리나 반납할 수 없는 단위까지 강제로 줄이는 보장은 아니다. [CUDA pool 속성 설명](https://docs.nvidia.com/cuda/cuda-runtime-api/group__CUDART__MEMORY__POOLS.html)

8월 실험에서는 측정도 한 번 헷갈렸다. 앞 실험이 남긴 캐시가 있는 상태를 기준점으로 잡았더니, 보유량을 1,024 MiB가 아니라 512 MiB로 읽었다. 추가로 늘어난 양과 전체 보유량을 섞어서 보고 있었다. 풀이 비어 있던 앞 단계의 기준으로 비교하니 메모에 남긴 값과 맞았다.

처음의 워커로 돌아가면 이 구분이 필요하다. 태스크가 끝나고 폴링만 한다면 동기화가 일어나지 않을 수도 있다. 그 경우 임계값을 지정했다는 사실만으로, 쉬고 있는 동안 보유량이 그 값까지 내려갔다고 가정할 수는 없다.

이 실험에서 동기화 뒤 정확히 1,024 MiB가 남았다는 것과, 어떤 상황에서도 그 양을 보장한다는 건 다른 이야기다.

## 풀 밖의 할당자는 어떻게 되나

노트북에는 CuPy의 풀을 거치지 않고 `cudaMalloc`을 직접 호출하는 단계도 넣었다. 할당자를 연결할 수 없는 라이브러리를 생각한 대조군이다.

8월 작업 메모에서는 여유가 있는 상태에서 512 MiB를 요청하니 RMM 사용 여부와 관계없이 드라이버 여유가 512 MiB 줄었다. 이 직접 할당 단계는 이번 재측정에는 포함하지 않았다. 여기까지 보면 “공유 풀 밖에서는 그 공간을 못 쓰는구나”라고 생각하기 쉽다.

그래서 원래 메모에는 GPU를 거의 채우면 직접 `cudaMalloc`하는 쪽은 실패할 거라고 적었다. 그런데 글을 다시 쓰며 문서를 확인하니, 이 예상은 그대로 결론으로 쓸 수 없었다.

CUDA 드라이버는 **같은 프로세스**의 `cudaMalloc` 같은 별도 요청을 처리하기 위해 CUDA 메모리 풀의 미사용 메모리를 회수할 수 있다. RMM의 할당 경로를 직접 공유하는 것과, 드라이버가 풀에서 회수해 다른 요청을 처리하는 것은 다른 경로다. [NVIDIA의 pool 회수 설명](https://developer.nvidia.com/blog/using-cuda-stream-ordered-memory-allocator-part-1/)

따라서 여유가 있을 때 512 MiB를 추가로 받았다는 결과만으로, 메모리가 부족할 때도 반드시 실패한다고 말할 수 없다. 반대로 별도 프로세스의 요청까지 같은 방식으로 해결된다고 확장해서도 안 된다.

GPU를 거의 채우는 STEP 8은 당시 실행하지 않았다. 사용 중인 개발 워커와 같은 GPU였기 때문이다. 이 부분은 아직 실험해야 할 질문으로 남아 있다. 기존 노트북의 성공·실패 예상표도 확정된 결과로 읽으면 안 된다.

## 지금 다시 보면

처음에는 `nvidia-smi`의 숫자가 안 내려가는 게 문제라고 생각했다. 그런데 캐시를 보고 나니, 숫자가 남아 있다는 사실만으로는 부족했다. 그 공간을 다음 요청이 재사용할 수 있는지까지 봐야 했다.

PyTorch만 반복해서 쓰면 자체 캐시로 충분할 수 있다. PyTorch와 CuPy가 번갈아 메모리를 크게 쓰는 경우에는 재사용 범위를 라이브러리 밖으로 넓힐 이유가 생긴다. RMM은 이번 실험에서 두 할당 경로를 같은 resource로 연결하는 수단이었다.

그 연결 덕분에 512 MiB를 추가로 받지 않아도 되는 건 봤다. 대신 메모리 카운터를 읽는 방법과 반납을 제어하는 위치도 같이 바뀌었다. 실제 워커에서 이 교환이 이득인지 판단하려면 어느 라이브러리가 언제 얼마나 할당하는지, 작업이 끝난 뒤 무엇을 남기는지 더 봐야 한다.

내가 다음에 확인하고 싶은 건 메모리가 부족한 상태에서의 동작이다. 공유 풀을 직접 쓰는 요청과, 풀 밖에서 들어오는 요청을 나눠서 보면 될 것 같다. 그때는 “풀이 있으니 성공할 것”이라는 예상뿐 아니라, 예상과 다른 결과가 나왔을 때 어떤 회수 경로가 작동했는지도 같이 봐야겠다.

실험 코드는 [측정 스크립트](/assets/experiments/rmm-memory-pool/measure.py)와 노트북으로 남긴다. [segment와 block](/assets/notebooks/pytorch-segment-blocks.ipynb), [기본 재사용](/assets/notebooks/rmm-reuse-default.ipynb), [RMM 재사용](/assets/notebooks/rmm-reuse-rmm.ipynb), [기본 반납](/assets/notebooks/rmm-release-default.ipynb), [RMM 반납](/assets/notebooks/rmm-release-rmm.ipynb)에서 전체 코드를 볼 수 있다.
