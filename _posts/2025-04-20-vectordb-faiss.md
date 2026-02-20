---
title: Vector DB와 Faiss 사용기
date: 2025-04-20 15:51:00 +0900
author: oogie
categories: [VectorDB,recsys,search]
tags: [vectordb,recsys]     # TAG names should always be lowercase]
img_base: /assets/img/2025-04-20-vectordb-faiss
---

## TL;DR

의류 아이템 검색 서비스를 위해 VectorDB를 도입했다. VectorDB는 대규모 벡터 검색에서 메모리 안정화와 ANN 기반 연산 가속을 제공한다. 로컬 환경의 유연성과 알고리즘 실험 목적으로 FAISS를 선택했고, 내부 C++ 코드(IndexFlat, IndexFlatCodes 등)의 핸들러 기반 모듈 구조를 분석했다. 다만 실서비스에서는 분산처리를 지원하는 Milvus/Qdrant가 더 적합하다는 결론을 내렸다.

---

# Intro

PPicker 프로젝트에서 의류 아이템을 retrieval 하는 서비스(Vibe Searching)를 만들기 위해서  Vector DB를 적용하고 있다. 사실 VectorDB의 목적, 원리, 구현 모두 이번에 처음 알아봤고 그 내용을 정리하려고 합니다.

![etl_struct]({{ page.img_base }}/etl_struct.png)

# VectorDB 등장 배경과 목적

## 1. 유사성 기반 아이템 추출의 필요성

추천 및 검색 시스템에서는 특정 아이템이나 쿼리와 **유사한 아이템을 추출**하려는 수요가 점점 더 많아지고 있습니다.

- 비슷한 의미를 가진 문장
- 비슷한 스타일의 옷
- 비슷한 분위기의 장소

위와 같이 "비슷한 것"을 찾아 사용자에게 제공하는 것이 높은 사용자 경험과 가치를 만들어내는 핵심 요소로 자리잡고 있습니다.

---

## 2. Embedding 기술의 발전

1번과 같은 유사성 기반 시스템을 구현하기 위해서는, 아이템의 "의미"를 어떻게 **정량적으로 표현하고 저장할 것인가**가 중요합니다.

최근 딥러닝, 특히 LLM의 급속한 발전과 함께, **비정형/정형 데이터를 고차원 벡터로 변환하는 Embedding 기술** 역시 빠르게 진화해왔습니다. 이 기술의 발전은 유사성 기반 추천과 검색 시스템 구현에 있어 결정적인 전환점을 마련했습니다.

적절한 방식으로 임베딩이 수행되었다면, **유사한 아이템은 유사한 벡터를 가지며**, **서로 다른 아이템은 더 먼 벡터 거리를 가지는** 특성을 띠게 됩니다.

즉, "유사성"이라는 개념을 **Embedding → Vector Distance**라는 방식으로 구현할 수 있게 된 것입니다.

---

## 3. 엔지니어링적 한계

2번에서 설명한 것처럼, 유사도 계산을 위해 아이템 간 **벡터 간 거리**를 계산하는 방식을 채택하게 됩니다. 예를 들어, 하나의 아이템이 있을 때 이의 임베딩을 구하고, 나머지 모든 아이템의 임베딩과의 거리를 계산하여 **Top-K 유사 아이템**을 추출하는 방식입니다.

이론적으로는 간단하지만, 이를 **엔지니어링 관점**에서 보면 문제가 발생합니다.

만약 전체 아이템이 수백만~수억 개에 이른다면, **모든 벡터 간의 거리를 일일이 계산하는 작업은 연산 비용과 메모리 측면에서 매우 비효율적이며 비현실적**입니다.

특히 **실시간 응답성**이 중요한 추천 및 검색 시스템에서는 이러한 방식은 병목이 발생하기 쉽고, 시스템의 안정성에도 부정적인 영향을 줄 수 있습니다.

결국, **이러한 대규모 벡터 검색을 더 효율적이고 안정적으로 수행**하기 위해 등장한 것이 바로 **Vector DB**입니다.

## 꼭 써야하나?

실제로, 서비스에 포함된 아이템 수가 수백 개에서 수천 개 수준이라면 굳이 Vector DB를 도입할 필요는 없을 수도 있습니다.

예를 들어, **3,000개의 아이템에 대해 512차원 Embedding**을 사용하는 경우를 가정해봅시다.

512차원 벡터 하나는 `512 * 32bit = 2048Byte (약 2KB)`이므로, 전체 벡터의 메모리 크기는

`3,000 * 2KB = 6MB` 수준에 불과합니다.

이는 메모리에 충분히 올릴 수 있는 크기이며,

심지어 **NumPy의 행렬 내적 기능**을 활용하면 `3000 x 512` 형태의 배열을 이용해 한 번의 연산으로 전체 유사도를 계산할 수 있습니다.

또한, 모든 아이템 간의 유사도를 구하는 경우라도,

`512 x 6MB ≈ 3GB 메모리`만으로 계산이 가능하며, 이 경우 **오히려 Vector DB보다 빠르고 효율적으로 검색**을 수행할 수 있습니다.

즉, **Vector DB는 만능 도구가 아닙니다.**

데이터의 **규모**, **요구되는 검색 성능**, **운영 환경** 등에 따라 도입 여부를 신중하게 판단해야 하며,

소규모 데이터셋에서는 일반적인 in-memory 연산이 더 나은 선택이 될 수 있습니다.

# VectorDB의 목적과 기능

VectorDB의 주요 목적은 크게 **두 가지 측면**으로 나눌 수 있으며, 이와 관련된 기능 역시 이 두 가지 문제를 해결하는 데 중점을 두고 있습니다.

1. **메모리 사용의 안정화**
2. **유사도 계산 연산의 가속**

---

### 1. 메모리 안정화

예를 들어, 아이템이 **1,000만 개**이고 각각 **512차원 임베딩**을 갖는다고 가정해보겠습니다.

이 경우 전체 벡터 데이터만으로도 다음과 같은 메모리 용량이 필요합니다:

- `10,000,000 * 512 * 4 Byte = 약 20GB`

하지만 실제 시스템에서는 단순 벡터 외에도 **인덱스 구조, 메타데이터, ID 매핑 등**이 함께 저장되기 때문에, 보수적으로 잡으면 **25~30GB 이상**의 메모리가 필요합니다.

이 정도 수준의 메모리를 **단일 프로세스 또는 스레드에서 관리**하는 것은 시스템적으로 매우 부담이 크며, 이 상태에서 실시간 연산이 발생하게 되면 **page fault**나 **메모리 캐시 미스**로 인한 성능 저하가 필연적으로 발생할 수 있습니다.

따라서, 대규모 벡터 데이터를 안정적으로 다루기 위해 필요한 것이 **Vector DB의 메모리 관리 기능**입니다.

이를 해결하기 위한 주요 기능으로는 다음과 같은 것들이 있습니다:

- **디스크 기반 페이징 (on-disk index paging)**: 메모리에 전부 올리지 않고 필요한 부분만 로딩
- **Sharding 및 분산 처리 (distributed indexing & storage)**: 노드 간 분산 저장 및 검색 처리
- **압축 및 양자화 (Quantization)**: 벡터를 더 작은 메모리 footprint로 변환

대표적으로 **Milvus**, **Qdrant**, **Weaviate** 등의 Vector DB는 이와 같은 메모리 안정화 기능을 제공합니다.

### 2. 연산의 가속

벡터 기반 검색은 기본적으로 **쿼리 벡터와 전체 벡터들 간의 거리 계산**을 통해 이루어집니다. 하지만, 예를 들어 1,000만 개의 아이템이 있다고 가정했을 때, 단순하게 모두와의 거리를 계산하는 방식은 **시간 복잡도 O(N)이라고 하더라도** 매우 비효율적이며, 실시간 응답이 필요한 환경에서는 사용하기 어렵습니다.

이를 해결하기 위해 VectorDB는 일반적으로 **근사 최근접 이웃(Approximate Nearest Neighbor, ANN)** 알고리즘을 활용합니다. ANN은 정확한 최근접 이웃을 찾는 대신, **"충분히 유사한" 결과를 훨씬 빠르게 찾는 것**을 목표로 하며, 성능과 정확도 사이의 트레이드오프를 제공합니다.

대표적인 ANN 알고리즘으로는 다음과 같은 것들이 있습니다:

| 알고리즘 | 설명 | 사용 예 |
| --- | --- | --- |
| **HNSW (Hierarchical Navigable Small World)** | 그래프 기반 구조로, 높은 정확도와 빠른 검색 속도를 제공 | FAISS, Qdrant, Weaviate 등 |
| **IVF (Inverted File Index)** | 벡터들을 클러스터링하고, 클러스터 내부에서만 검색 | FAISS |
| **PQ (Product Quantization)** | 벡터를 압축하여 메모리 사용량을 줄이고, 빠른 검색 가능 | FAISS |
| **ScaNN** | Google이 개발한 고성능 ANN 알고리즘, recall과 latency의 밸런스가 우수 | TensorFlow ecosystem |

이러한 알고리즘들은 다음과 같은 가속 효과를 제공합니다:

- **검색 대상 축소**: 전체 벡터 중 일부만 대상으로 삼아 거리 계산
- **인덱싱 최적화**: 공간 구조를 활용하여 빠르게 근접 후보군 탐색
- **하드웨어 활용 최적화**: SIMD, AVX, GPU 등의 병렬처리를 적극 활용

결과적으로, Vector DB는 단순히 벡터 데이터를 저장하는 것이 아니라, **고속 검색을 위한 인덱싱 구조와 검색 알고리즘을 함께 제공**함으로써, 대규모 데이터셋에서도 **실시간 검색 성능을 보장**할 수 있도록 설계되어 있습니다.

### Vector DB 비교

장점과 단점은 제가 직접 경험해본건 아니고 여러 자료를 참고했습니다.

| 항목 | FAISS | Milvus | Qdrant | Weaviate | Pinecone |
| --- | --- | --- | --- | --- | --- |
| **배포 형태** | 라이브러리 (Python/C++) | 서버 기반 (Docker/K8s) | 서버 기반 (Docker/K8s) | 서버 기반 (REST/gRPC) | 완전 관리형 SaaS |
| **검색 알고리즘 (ANN)** | IVF, HNSW, PQ 등 | IVF, HNSW, PQ 등 | HNSW (기본), IVFFlat | HNSW (기본), Flat | HNSW 기반 (내부 구현 비공개) |
| **Disk paging** | ❌ (모두 RAM에 로드) | ✅ | ✅ | ✅ | ✅ |
| **분산 처리 지원** | ❌ (직접 구현 필요) | ✅ | ✅ (built-in) | ✅ | ✅ |
| **메타데이터 검색** | ❌ | 제한적 | ✅ (filter 지원) | ✅ (schema + vector) | ✅ (metadata filter) |
| **장점 요약** | 최고 성능의 라이브러리, 유연한 커스터마이징 | 산업용 스케일링에 강함, 다양한 인덱스 지원 | 경량 + 빠른 시작, 실무 친화적 | AI/semantic 통합 최적화, GraphQL 등 지원 | 설치 필요 없음, 완전 관리형, 손쉬운 사용 |
| **단점 요약** | 자체 배포 어려움, 실시간성 약함 | 리소스 요구 높음, 운영 부담 | 커스터마이징 한계 | 시스템 무거움, 초기 학습곡선 | 벤더 종속, 고비용 가능성 |

# 그래서 왜 FAISS?

기본적으로 **클라우드 기반 제품**, 특히 **유료 SaaS 형태의 VectorDB**는 이번 프로젝트의 초기 단계에서는 선택지에서 제외했습니다. 그 이유는 다음과 같습니다:

1. **현재는 고성능 인프라가 필요하지 않으며**, 추후 필요해질 경우에도 도입은 늦지 않다.
2. **직접 구축하고 내부 동작 방식을 이해해보고 싶은 목적**이 있다.

이러한 이유로, **로컬 환경에서 구동이 가능한 VectorDB**를 기준으로 선택지를 좁혔고, 최종적으로 고려한 후보는 아래와 같았습니다:

- **Milvus**
- **Qdrant**
- **FAISS**

하지만 실제 프로젝트에서 다뤄야 할 아이템의 수가 **수십억 단위의 초대형 스케일**이 아니기 때문에,

**페이징, 분산처리, 복잡한 인프라 구성** 등의 기능은 당장 필요하지 않았습니다.

그렇기 때문에,

- 다양한 ANN 알고리즘을 직접 선택하고 실험할 수 있고
- 상대적으로 **가볍고 유연하게 사용할 수 있으며**
- **구현 난이도 또한 비교적 낮은**

**FAISS**를 최종적으로 선택하게 되었습니다.

→ 즉, FAISS는 로컬 환경, 개발 난이도, 유연성, 성능의 균형 면을 고려한 선택이었습니다

## FAISS의 내부 구조 및 설계

FAISS를 사용할 때의 큰 장점 중 하나는, **복잡한 시스템 수준의 분산 처리나 페이징 기능 없이도** 다양한 검색 알고리즘을 직접 실험하고 학습할 수 있다는 점입니다.

즉, 시스템 인프라보다는 **자료구조와 알고리즘 자체에 집중하기에 좋은 구조**를 가지고 있습니다.

### FAISS의 인덱스 구조

FAISS의 핵심은 `faiss::Index`라는 **추상 기반 클래스(Abstract Base Class)**로부터 파생되는 다양한 인덱스 클래스들입니다.

FAISS는 이들을 조합하여 다양한 검색 시나리오에 맞는 VectorDB를 구성할 수 있도록 설계되어 있습니다.

FAISS의 인덱스 클래스 계층 구조를 간단히 정리하면 다음과 같습니다:

```txt
faiss::Index  ←  abstract base class
├── Brute‑force (Flat)                  ← 정확한 검색; 벡터 원본 그대로 저장 :contentReference[oaicite:0]{index=0}
│     ├── IndexFlatL2
│     ├── IndexFlatIP
│     └── IndexRefineFlat               ← 근사 인덱스 결과를 Flat으로 재정렬
│
├── Quantization‑only                   ← 벡터 압축/양자화만 수행 :contentReference[oaicite:1]{index=1}
│     ├── IndexPQ                       ← Product Quantizer (flat) :contentReference[oaicite:2]{index=2}
│     ├── IndexResidual                 ← Additive/Residual Quantizer
│     └── IndexScalarQuantizer          ← 4/6/8‑bit 또는 FP16 압축
│
├── Inverted‑file (IVF*)                ← 클러스터→셀 프로브 방식 :contentReference[oaicite:3]{index=3}
│     ├── IndexIVFFlat                  ← Flat으로 후처리
│     ├── IndexIVFPQ                    ← IVF + PQ (ncentroids, M, nbits) :contentReference[oaicite:4]{index=4}
│     ├── IndexIVFPQR                   ← IVF+PQ + 재정렬(refine)
│     ├── IndexIVFScalarQuantizer       ← IVF + SQ (`IVFSQ8`, `IVFSQ8H`, `IVFSQ8Plus`)
│     ├── IndexIVFAdditiveQuantizer     ← IVF + AQ
│     ├── IndexIVFHNSW                  ← IVF + HNSW 기반 할당
│     ├── MultiIndexQuantizer           ← 복합 코얼스 양자화기
│     └── ResidualCoarseQuantizer       ← IVF용 잔차 양자화
│
├── Graph‑based (HNSW)                  ← 근사 그래프 탐색 방식 :contentReference[oaicite:5]{index=5}
│     ├── IndexHNSWFlat                 ← HNSW + Flat
│     ├── IndexHNSWSQ                   ← HNSW + SQ
│     ├── IndexHNSWPQ                   ← HNSW + PQ
│     └── IndexHNSW2Level               ← 2‑단계 인코딩
│
├── Composite/ID mapping                 ← 메타·조합 인덱스
│     ├── IndexIDMap                     ← `add_with_ids` 미지원 인덱스 래핑 :contentReference[oaicite:8]{index=8}
│     ├── IndexIDMap2                    ← 삭제 시 id 고정
│     ├── IndexPreTransform              ← PCA/OPQ 등 전처리 + 래핑
│     ├── IndexShards                    ← 병렬 샤딩
│     ├── IndexReplicas                  ← 복제 인덱스
│     └── IndexRefineFlat                ← 근사 결과 재정렬
└── … 그 외 GPU 전용(`IndexIVFFlatGPU` 등), 실험적/특수용 인덱스 다수
```

FAISS는 다양한 목적과 조건에 맞게 아래와 같은 **구성 요소들의 조합**으로 인덱스를 설계할 수 있습니다:

- **탐색 방식**: 정확한 검색(Flat), 근사 검색(HNSW, IVF 등)
- **저장 방식**: 원본 벡터 저장, 양자화/압축 기반 저장
- **후처리 방식**: RefineFlat 등으로 재정렬
- **메타 구조**: ID 맵핑, 샤딩, 복제, 전처리(PCA, OPQ 등)

이러한 조합 덕분에 FAISS는 실험적 탐색, 최적화, 성능 측정 등 다양한 벡터 검색 시나리오를 빠르게 구성해볼 수 있는 **고성능 저수준 툴킷**으로 매우 적합합니다.

### `예시코드`

아래는 HNSW + 양자화 + ID Mapping구조를 엮은 VectorDB를 만드는 코드입니다.

```python
import faiss
import numpy as np

# 1) 데이터 생성
d  = 128
nb = 10000
xb = np.random.random((nb, d)).astype('float32')

# 2) HNSW + PQ 설정
pq_m     = 8      # Product Quantizer 서브벡터 개수
pq_nbits = 8      # 각 서브벡터당 비트 수 (2^8 = 256 centroids)
hnsw_m   = 32     # HNSW 그래프의 M (각 노드 연결도)

# 3) Base index 생성 (IndexHNSWPQ)
# 시그니처: IndexHNSWPQ(int d, int pq_m, int hnsw_m, int pq_nbits=8, MetricType metric=METRIC_L2)
base_index = faiss.IndexHNSWPQ(
    d,        # 벡터 차원
    pq_m,     # PQ 서브벡터 개수
    hnsw_m,   # HNSW 연결도 M
    pq_nbits  # 각 서브벡터 비트 수
)

# 4) ID 매핑을 위해 IndexIDMap 래핑
#   - add_with_ids() 를 쓰려면 IndexIDMap 또는 IndexIDMap2로 감싸야 함
index = faiss.IndexIDMap(base_index)

# 5) PQ 코드북 학습: 충분한 학습용 샘플 제공
index.train(xb)

# 6) ID 배열 생성 (외부 상품 ID 등 원하는 식별자 사용 가능)
vector_ids = np.arange(nb, dtype='int64')  # 0,1,2,...,9999

# 7) 벡터 + ID 한꺼번에 추가
index.add_with_ids(xb, vector_ids)

# 8) 검색 테스트
xq = np.random.random((5, d)).astype('float32')
k  = 5
D, I = index.search(xq, k)

print("검색 결과 IDs:\n", I)       # 각 쿼리에 대한 상품 ID 배열
print("검색 결과 거리:\n", D)     # 유클리드 거리
```

가능한 조합이 알고리즘과 자료구조마다 정해져있어 Faiss 깃헙 내용을 참고하시면 좋을 것 같습니다.

- index_factory
    
    https://github.com/facebookresearch/faiss/wiki/Faiss-indexes
    
    | **Method** | **Class name** | **`index_factory`** | **Main parameters** | **Bytes/vector** | **Exhaustive** | **Comments** |
    | --- | --- | --- | --- | --- | --- | --- |
    | Exact Search for L2 | `IndexFlatL2` | `"Flat"` | `d` | `4*d` | yes | brute-force |
    | Exact Search for Inner Product | `IndexFlatIP` | `"Flat"` | `d` | `4*d` | yes | also for cosine (normalize vectors beforehand) |
    | Hierarchical Navigable Small World graph exploration | `IndexHNSWFlat` | `"HNSW,Flat"` | `d`, `M` | `4*d + x * M * 2 * 4` | no |  |
    | Inverted file with exact post-verification | `IndexIVFFlat` | `"IVFx,Flat"` | `quantizer`, `d`, `nlists`, `metric` | `4*d  + 8` | no | Takes another index to assign vectors to inverted lists. The 8 additional bytes are the vector id that needs to be stored. |
    | Locality-Sensitive Hashing (binary flat index) | `IndexLSH` | - | `d`, `nbits` | `ceil(nbits/8)` | yes | optimized by using random rotation instead of random projections |
    | Scalar quantizer (SQ) in flat mode | `IndexScalarQuantizer` | `"SQ8"` | `d` | `d` | yes | 4 and 6 bits per component are also implemented. |
    | Product quantizer (PQ) in flat mode | `IndexPQ` | `"PQx"`, `"PQ"M"x"nbits` | `d`, `M`, `nbits` | `ceil(M * nbits / 8)` | yes |  |
    | IVF and scalar quantizer | `IndexIVFScalarQuantizer` | "IVFx,SQ4" "IVFx,SQ8" | `quantizer`, `d`, `nlists`, `qtype` | SQfp16: 2 * `d` + 8, SQ8: `d` + 8 or SQ4: `d/2` + 8 | no | Same as the `IndexScalarQuantizer` |
    | IVFADC (coarse quantizer+PQ on residuals) | `IndexIVFPQ` | `"IVFx,PQ"y"x"nbits` | `quantizer`, `d`, `nlists`, `M`, `nbits` | `ceil(M * nbits/8)+8` | no |  |
    | IVFADC+R (same as IVFADC with re-ranking based on codes) | `IndexIVFPQR` | `"IVFx,PQy+z"` | `quantizer`, `d`, `nlists`, `M`, `nbits`, `M_refine`, `nbits_refine` | `M+M_refine+8` | no |  |

# Low Level 코드 뜯어보기 (c++)

실제 low level 코드를 뜯어보는 부분인데, 관심없는 분들은 넘어가도 좋습니다.

주로 다룰 내용은 다음과 같습니다

- Index Base Class
- IndexFlat
- IndexHNSWFlat
- IndexIDMap
- IndexIVFPQ/IndexHNSWPQ → 양자화는 ..잘 다룰 수 있을지 모르겠네요

---

GPU 관련 부분, 양자화 디테일, Bindary Encoding 등은 역량 부족 + 사용하지 않을 것 같아서 넘어갈 것 같고 다음에 시간되면 다뤄보겠습니다.

> 그리고 코드를 뜯어보고 남기는 후기인데.. 진짜 복잡해서 모든걸 하나하나 보지는 못했습니다 쉽지않네요
> 

---

# Index Base Class

모든 객체들의 기초이자 시작이 되는 Index 객체입니다.

```cpp
namespace faiss {

struct Index {
    int d;              // 벡터 차원 수
    size_t ntotal;      // 저장된 벡터 개수
    MetricType metric_type;  // 거리 기준 (예: L2, Inner Product)

    Index(int d, MetricType metric = METRIC_L2);

    virtual void add(idx_t n, const float* x) = 0;

    virtual void search(idx_t n, const float* x, idx_t k,
                        float* distances, idx_t* labels) const = 0;

    virtual ~Index(); // 소멸자를 가상으로 선언
};
```

`파라미터`

- d : 벡터차원,  c++답게, ntotal을 미리 선언받습니다.
- ntotal : 이 벡터수는 해당 객체에 벡터가 추가되거나 없어질 때마다 동적으로 변하는 것 같습니다
- metric_type : metric은 추후 자세하게 다룹니다. 어쨋든 해당 인덱스에서 중요한 값입니다

`메소드`

- add : 인덱스에 Vector를 추가합니다. Vector를 DB에 저장하는 Load함수라고 보면 됩니다.
- search : neighbor를 찾는 메소드입니다.
    - n : 쿼리벡터 개수
    - x : 쿼리벡터 (n * d)
    - k : 검색 이웃 개수
    - distances : 출력용 배열로, 검색된 이웃들에 대한 거리를 저장
    - labels : 출력용 배열, 검색된 이웃들의 index를 저장

메소드는 모두 상속받은 클래스에서 구현하도록 되어있습니다.

# IndexFlat - BrutForce

BrutForce를 이용해 모든 벡터간의 거리를 계산하는 IndexFlat(양자화 X) 방법을 살펴보겠습니다.

코드를 보기전에는 구조가 당연히 Index → IndexFlat → IndexFlatL2,IndexFlatIP로 구조가 잡혀있을 줄 알았는데 코드를 보니까 IndexFlatCodes라는게 존재하고 구조가 아래와 같이 되어있습니다.

```
                   +----------------+
                   |     Index      |  ← abstract base class
                   +----------------+
                           ▲
                           │
                   +-----------------+
                   |  IndexFlatCodes |  ← 코드 저장·공통 로직
                   +-----------------+
                           ▲
                           │
                   +----------------+
                   |   IndexFlat    |  ← Flat 전용 설정(L2/IP 등)
                   +----------------+
                    ▲             ▲
                    │             │
         +----------------+ +----------------+
         | IndexFlatL2    | | IndexFlatIP    |
         +----------------+ +----------------+

```

그래서 IndexFlatCodes부터 쭈루룩 살펴보겠습니다.

## IndexFlatCodes

IndexFlatCode의 핵심 역할은 다음 2가지 입니다.

- 벡터 데이터를 **byte 코드**(`codes` 버퍼)에 저장하고
- `add`, `search`, `reconstruct` 등 Flat계열 공통 로직 구현

정리해보자면 Vector를 Index안에 저장하는 기능을 구현해놓았다고 보면 됩니다.

그리고 IndexFlat에서는 메트릭 지정 및 최적화를 지원하도록 쪼갠 것으로 보입니다.

> 더 나아가
> 

### 생성 & add

```cpp
// — IndexFlatCodes 생성자들
IndexFlatCodes::IndexFlatCodes(size_t code_size, idx_t d, MetricType metric)
    : Index(d, metric),       // 1) 부모 클래스 Index(d, metric) 생성자 호출
      code_size(code_size)    // 2) 1벡터당 바이트 크기(code_size) 초기화
{}

IndexFlatCodes::IndexFlatCodes()
    : code_size(0)           // 디폴트 생성자: code_size만 0으로 초기화
{}

// — 벡터 추가
void IndexFlatCodes::add(idx_t n, const float* x) {
    FAISS_THROW_IF_NOT(is_trained);      // 인덱스가 학습된 상태인지 확인
    if (n == 0) {
        return;                          // 추가할 벡터가 없으면 바로 종료
    }
    // 1) codes 버퍼 크기 확장: (기존 ntotal + 새로 추가할 n) × code_size
    codes.resize((ntotal + n) * code_size);
    // 2) sa_encode 호출: x 포인터의 벡터 n개를
    //    codes.data() + (ntotal * code_size) 위치부터 바이트 단위로 인코딩
    sa_encode(n, x, codes.data() + (ntotal * code_size));
    // 3) 전체 벡터 수 갱신
    ntotal += n;
}

void IndexFlat::sa_encode(idx_t n, const float* x, uint8_t* bytes) const {
  if (n > 0) {
    memcpy(bytes, x, sizeof(float) * d * n);
  }
}
```

Flat 형태는 기본적으로 Vector를 쭉 연결한 Array로 저장합니다.

3개의 512 차원 벡터가 있다면 3*512*4byte에 일렬로 쭉 저장하는 것입니다.

그래서 벡터를 추가하는 코드도, code_size * 새로운 크기로 naive하게 업데이트 해준 뒤, memcopy를 이용해서 새로운 벡터집합인 x를 기존 메모리로부터 추가된 부분까지 복사해줍니다.

![add]({{ page.img_base }}/add.png)

### search

`IndexFlatCodes`는 압축된 벡터(예: PQ 코드)를 검색할 수 있도록 설계된 FAISS의 인덱스 중 하나입니다. 이 인덱스의 핵심은 압축된 벡터를 **디코딩하고**, 쿼리 벡터와의 **거리를 계산**, 그 결과를 **heap(top-k)** 에 넣어주는 **핸들러 기반 구조**입니다.

---

<aside>


***전체 흐름 요약***

</aside>

1. 검색 함수 호출

```cpp
IndexFlatCodes::search(n, x, k, distances, labels, params)
```

1. 내부 주요 로직
    1. `Run_search_with_decompress_res r` 생성
        
        → 쿼리별로 디코딩 + 거리 계산 + 결과 저장까지 처리할 핸들러
        
    2. `dispatch_knn_ResultHandler()` 호출
        
        → 검색 루프를 돌며 `r`(result handler)을 실행
        

---

<aside>


***구성 요소별 설명***

</aside>

1. `Run_search_with_decompress_res` (외부 Result Handler)
- `dispatch_knn_ResultHandler()`에 넘겨지는 **핸들러 객체**
- 쿼리당 루프를 돌며 거리 계산 및 결과 저장까지 수행
- 내부에서 `Run_search_with_decompress<ResultHandler>`를 생성해 사용
1. `Run_search_with_decompress` (Unpacker + 거리 계산자)
- **쿼리와 모든 데이터 벡터 쌍**에 대해 loop
- `sa_decode()`를 통해 압축 코드 → float 벡터로 복원
- `vd()`를 통해 거리 계산 수행
- 결과는 내부 `SingleResultHandler`의 `add_result()`로 전달됨
1. `GenericFlatCodesDistanceComputer`
- 내부에서 사용하는 거리 계산 유틸리티
- `operator()(i)`를 통해
    - 압축 코드 복원 (decode)
    - 거리 계산
    - 결과 반환
- 복원 시 `codec.sa_decode(...)` 호출
1. `dispatch_VectorDistance()`
- 블록 단위로 전체 벡터를 순회하며
- 각 쿼리에 대해 unpacker 호출 (`unpacker.f()`)
- 거리 계산 후 result handler의 `add_result()` 호출
- 마지막에 `res.finalize()`로 heap 정리

---

<aside>


***Result Handler의 역할***

</aside>

핵심은 FAISS 내부가 **거리 계산과 결과 저장을 모듈화**하기 위해 **핸들러 기반 구조**를 쓴다는 점입니다.

### 두 종류의 핸들러

| 핸들러 역할 | 주요 클래스 | 기능 |
| --- | --- | --- |
| 거리 계산 + 복호화 (Unpacker) | `Run_search_with_decompress` | 압축 코드 → 벡터 복원 → 거리 계산 |
| 거리 저장 + Top-K 유지 (Result) | `Run_search_with_decompress_res` / `HeapResultHandler` | 거리/ID 저장, heap 유지 |

### 핵심 메서드

- `add_result(distance, id)` → 거리 결과를 힙에 삽입
- `begin(q)` / `end()` → 쿼리 단위 루프 시작/종료 처리
- `finalize()` → 최종 거리/ID 배열로 정리

---

### 정리 및 요약


![search]({{ page.img_base }}/search.png)

초록색 화살표 : handler호출

```
IndexFlatCodes::search
  └── dispatch_knn_ResultHandler
        └── consumer.f() (Run_search_with_decompress_res)
              └── dispatch_VectorDistance
                    ├── query 루프 (outer)
                    └── embedding 루프 (inner)
                          └── operator()(i): sa_decode → 거리 계산 → add_result()
                                └── 힙(heap)에 top-K 삽입

```

- FAISS는 검색 로직을 **핸들러 기반 모듈 구조**로 설계
- `IndexFlatCodes`에서는 압축 코드를 복원(decode)해서 거리 계산
- `dispatch_VectorDistance()`는 쿼리-데이터 쌍 loop 실행기
- **핸들러(consumer)**는 거리 계산과 저장을 분리하여 유연성 제공
- **heap 기반 top-K 유지**로 효율적인 결과 추출 가능

## 다시, IndexFlat

앞서 살펴본 `IndexFlatCodes`는 PQ 등의 **양자화된 코드 기반** 벡터 검색을 처리하는 인덱스였다면,

`IndexFlat`은 그 기반이 되는 부모 클래스를 상속하여 **양자화 없이 원본 벡터에 대해 직접 거리 계산을 수행하는 인덱스**입니다.

가장 기본적이며 단순한 **Brute-force 방식의 벡터 검색**을 구현하고 있습니다.

---

### search

```cpp
void IndexFlat::search(
    idx_t n,
    const float* x,
    idx_t k,
    float* distances,
    idx_t* labels,
    const SearchParameters* params
) const {
    IDSelector* sel = params ? params->sel : nullptr;
    FAISS_THROW_IF_NOT(k > 0);

    if (metric_type == METRIC_INNER_PRODUCT) {
        float_minheap_array_t res = {size_t(n), size_t(k), labels, distances};
        knn_inner_product(x, get_xb(), d, n, ntotal, &res, sel);
    } else if (metric_type == METRIC_L2) {
        float_maxheap_array_t res = {size_t(n), size_t(k), labels, distances};
        knn_L2sqr(x, get_xb(), d, n, ntotal, &res, nullptr, sel);
    } else {
        FAISS_THROW_IF_NOT(!sel); // TODO implement with selector
        knn_extra_metrics(...);
    }
}
```

- 거리 계산 메서드는 **metric_type**에 따라 다르게 호출됩니다:
    - `knn_inner_product`: 내적 기반 유사도
    - `knn_L2sqr`: L2 거리
    - `knn_extra_metrics`: 기타 사용자 정의 metric

---

위의 코드만 보면  IndexFlatCodes와 다른 구조처럼 보일 수 있지만, 사실은 유사한 구조를 따릅니다.

```cpp
void knn_inner_product(...) {
    ...
    Run_search_inner_product r;
    dispatch_knn_ResultHandler(
        nx, vals, ids, k,
        METRIC_INNER_PRODUCT,
        sel,
        r,       // unpacker (distance computer)
        x, y, d, nx, ny
    );
    ...
}
```

1. 거리 계산을 담당하는 **핸들러 (unpacker)** 생성
    
    → `Run_search_inner_product`
    
2. 검색 루프를 담당하는 **엔진** 호출
    
    → `dispatch_knn_ResultHandler(...)`
    
3. 내부에서는 `dispatch_VectorDistance()`가 실행되어,
    
    쿼리/데이터 간 거리 계산 및 힙 정리까지 진행
    

---

### 메타 구조 설계의 인사이트

> “그러면 왜 이렇게 구조를 나눴을까?”
> 

이 질문의 답은 FAISS의 굉장히 잘 설계된 **핸들러 기반 모듈화 구조**에 있습니다.

- `dispatch_knn_ResultHandler()`는 일종의 **검색 루프 엔진** 역할을 수행
- 이 루프 안에 들어가는 핸들러(`Run_search_inner_product`, `Run_search_with_decompress`, ...)만 다르게 제공하면,
- **데이터 타입(flat, PQ, scalar quantized)**
    
    **거리 메트릭(L2, IP, L1 등)**
    
    **결과 저장 방식(heap, array 등)**
    
    이 전부 유연하게 커스터마이징
    

---

### 정리 및 요약

- `IndexFlat`은 가장 단순한 형태의 Brute-force 벡터 검색 인덱스
- 별도의 인덱싱 구조 없이 원본 벡터와 거리 계산을 수행
- **핸들러 구조는 `IndexFlatCodes`와 동일하게 재사용**
    - 거리 계산용 unpacker 핸들러
    - 결과 저장용 result 핸들러
- 핵심 검색 루프는 `dispatch_knn_ResultHandler`에 의해 수행됨
- FAISS는 이 구조 덕분에 다양한 인덱스/거리 계산을 유연하게 지원

## IndexFlatL2 & IndexFlatIP

각각 l2 distance, inner product를 vector distance로 잡는 Index입니다. 이들은 한번 더 최적화를 해놓은 버전입니다.

### IndexFlatIP 최적화

음..사실 얘는 최적화가 없더라구요 그냥 metric을 명시해버리는게 전부입니다.

```cpp
struct IndexFlatIP : IndexFlat {
    explicit IndexFlatIP(idx_t d) : IndexFlat(d, METRIC_INNER_PRODUCT) {}
    IndexFlatIP() {}
};
```

### IndexFlatL2 최적화

```cpp
struct IndexFlatL2 : IndexFlat {
    // Special cache for L2 norms.
    // If this cache is set, then get_distance_computer() returns
    // a special version that computes the distance using dot products
    // and l2 norms.
    std::vector<float> cached_l2norms;

    /**
     * @param d dimensionality of the input vectors
     */
    explicit IndexFlatL2(idx_t d) : IndexFlat(d, METRIC_L2) {}
    IndexFlatL2() {}

    // override for l2 norms cache.
    FlatCodesDistanceComputer* get_FlatCodesDistanceComputer() const override;

    // compute L2 norms
    void sync_l2norms();
    // clear L2 norms
    void clear_l2norms();
};
```

L2에서는 caching을 했습니다. 정확히 caching을 하는 부분은 , norm을 미리 계산하는 것입니다.

$$
∥x−y∥^2=∥x∥^2+∥y∥^2−2(x⋅y)
$$

와 같이 L2거리를 계산하는데, multi query에 대해서 $∥y∥^2$를 매번 계산하는 것이 낭비이기 때문에 미리 sync_l2norms로 이를 계산하여 저장해두는 것으로 보입니다. 그리고 l2 norm 연산도 캐시된 것에 맞도록 미리 오버라이드를 시켜놓는 식으로 최적화를 진행합니다.

# 실제 사용 후기

저는 Vibe Searching의 프로토타입단계에서 VectorDB로 Faiss를 사용했습니다. 앞서 얘기한 것처럼 되게 직관적이고 처음 도입을 할때 VectorDB의 원리와 알고리즘을 이해하기에는 굉장히 직관적이고 도움도 많이 됩니다.

그런데 실제로 사용하면서 느낀 점은 실제 서비스 단계를 고려한다면 Faiss는 사용하지 않을 것 같다입니다.

이유는 2가지가 있습니다

1. `.index` 파일 기반 로컬 의존성
FAISS는 `.index`라는 **인덱스 파일을 로컬에 보관**하고, 이를 **라이브러리를 통해 메모리에 로딩**한 후에야 검색이 가능합니다. 
그런데 저희의 경우, **ETL 파이프라인과 Vibe Searching 시스템이 서로 다른 인스턴스**에서 작동하고 있었습니다. 즉, ETL 인스턴스에서 생성한 인덱스를 **다른 인스턴스로 전달**해야 하는 구조가 필요했고, 이는 설계적으로나 운영적으로 꽤 번거로운 작업이었습니다.
물론 인덱스를 공유하는 방법은 다양하겠지만, **데이터가 많아질수록 `.index` 파일의 용량이 커지고, 인스턴스 간 전송 자체가 부담**으로 작용하게 됩니다.
2. 모든 벡터가 메모리에 상주해야 하는 구조
Faiss는 앞서 얘기한 것 처럼 Index라는 객체가 벡터를 모두 저장하고 있고 모든 기능을 담당합니다.
이는 **굉장히 직관적이고 빠른 구조이지만**, 동시에 **모든 데이터를 메모리에 올려야만 검색이 가능하다는 단점**도 내포하고 있습니다.
데이터가 적을 때는 매우 빠르고 가볍게 동작합니다.
하지만 데이터가 많아지면:
    - **캐시 미스**
    - **페이지 폴트**
    - 심한 경우 **메모리 부족으로 전체 시스템에 영향**을 줄 수 있습니다.
    게다가 FAISS는 **라이브러리 형태**이기 때문에,
    
    **Microservice 구조로 쉽게 분리되도록 설계된 툴은 아닙니다.**
    
    정리하자면, 데이터 양이 작고, 메모리에 안정적으로 적재 가능한 수준이면 FAISS는 좋은 선택입니다.
    그렇지 않다면, Milvus나 Qdrant 같은 페이징/분산처리를 지원하는 벡터 DB가 적합하다는게 제 생각입니다.
    또한 Milvus, Qdrant는 **클라우드 기반 SaaS로도 운영 가능**하여,
    
    서비스 전체의 안정성을 높이기 위해 Microservice 형태로 분리 운영하기에 더 적합하다고 판단했습니다.
    

# Outro

원래 이번 포스팅에서는 Faiss의 HNSW 구현, IndexMap, 양자화(Product Quantization), IVF(Inverted File)까지 모두 정리하려고 했습니다.

하지만, 예상보다 구현 구조가 복잡하고 분량도 많아져서, 이번에는 여기까지만 정리하고 다음 포스팅에서 나머지를 이어서 다루도록 하겠습니다.