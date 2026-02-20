---
title: LightRAG 논문 리뷰
date: 2025-05-28 15:50:00 +0900
author: oogie
categories: [review,article]
tags: [RAG,GraphRAG]     # TAG names should always be lowercase]
img_base: /assets/img/2025-05-28-review-lightrag
use_math: true
---

## TL;DR

LightRAG는 기존 RAG의 flat한 벡터 검색 한계를 knowledge graph 구조로 보완한 프레임워크다. entity/relation 기반의 dual-level retrieval(low-level: 특정 엔티티, high-level: 넓은 토픽)로 복잡한 쿼리에 대응하며, GraphRAG 대비 retrieval 비용을 대폭 절감(61만 토큰 → 100 토큰 미만)하면서도 생성 품질에서 우위를 보였다.

---

# Introduction

RAG가 외부 지식 시스템을 통합합으로서 LLM의 단점을 극복하여 정확도와 contextually relavant한 응답을 뱉을 수 있게 됨

그런데 이런 RAG 시스템은 몇가지 한계점이 있는데

1. flat data representation에 의존함 : entity간의 관계성을 무시하고 vector로 압축해서 사용했다는 점
2. entity들의 상호 관계를 반영하지 못한다는 점
전기차, 대기질, 대중 교통이라는 키워드를 가진 문서를 추출할 수 있어도 이 topic간의 inter dependency를 잡지 못함

→ entity 간의 interdependency를 반영할 수 있는 graph structures를 결합

여기까지는 이론상 좋은데 실제 문제는 query volume을 efficiently handling하는 빠르고 scalable한 RAG system을 만드는게 필수임 

> 기존 microsoft의 GraphRAG의 경우 너무 비쌌음
그리고 query에 따라서 연결된 entity의 개수에 다라서 volume이 바뀌는데 이부분을 핸들링해야함
> 

이를 3가지 문제로 나눠서 접근함

1. Comprehensive Information Retreival 
: 모든 문서에서 inter dependent한 entities를 뽑아내야함
2. Enhanced Retrieval Efficiency 
: graph based knowledge strucutres에 대해서 응답 시간을 낮춰야함
3. Rapid Adaptation to New Data
: 새로운 데이터 업데이트가 있을 때 빠른 adaptation이 이루어져야함 / LightRAG에서는 새로운 문서에 대해서 모든 index를 새로 계산해야할 필요가 없음 특정 인덱스들만 업데이트하면 되고 노드 엣지 삽입만하면 되므로 일반 RAG보다 더 가볍다

이 3가지 문제를 해결하기 위해서 dual - level retrieval framework를 제안함 

- low level : 특정 entity와 relation에 대한 정확한 정보에 집중
- high level : 더 넓은 토픽과 주제를 통함함

---
# Retrieval - Augmented Generation

RAG에 대해서 잘 모르니 정리해보자 

RAG는 Retrieval Component와 Generation Component로 구성되어있음

`Retrieval Component`

Query에 대해서 relavant한 documents를 외부 지식 데이터베이스에서 뽑아오는 파트

`Generation Component`

retrived된 information에서 coherent하고 문맥상 relevant한 응답을 생성함

RAG는 다음 수식으로 표현됨

$$
\mathcal{M}
  = \bigl( \mathcal{G},\, \mathcal{R} = (\varphi, \psi) \bigr), \\
\mathcal{M}(q;\mathcal{D})
  = \mathcal{G}\bigl(q,\, \psi\!\bigl(q;\,\hat{\mathcal{D}}\bigr)\bigr),
\hat{\mathcal{D}} = \varphi(\mathcal{D})
$$

`M` : RAG framework

`q` : query

`D` : External Database

`g` : generator

query와 Data Retrieval에를 통해 나온 relevant documents를 이용해서 텍스트 생성

`R` : retrieval

1. $\varphi$(Data Indexer) : external database D를  가지고 specific data structure $\hat D$를 생성
2. $\psi$(Data Retrieval) : indexer에서 생성된 data와 query를 비교해 relevant documents 추출 

LightRAG에서 RAG 구조를 개선하는 부분은 3가지임

- Comprehensive Information Retrieval : global information을 retrieve할 수 있어야함
- Efficient and Low Cost Retrieval : $\hat D$를 통해 빠르고 효율적인 retrieve를 할 수있어야함
- Fast Adaptation to Data Changes : 새로운 데이터가 추가 되었을 때 기존 data structure에 빠르고 잘 조정이 되어야함

---

# LightRAG Architecture

![image.png]({{ page.img_base }}/overall.png)



## 1. Graph Based Text Indexing

### Graph-Enhanced Entity and Relationship Extraction

document를 더 작은 단위로 쪼갬으로 써 전체 document 분석 없이 빠르게 relevant information을 접근할 수 있도록 함

→ LLM을 이용해서 document에서 entity를 추출하고 이 entity 간에 relationship을 만들어 줌 → 결과적으로 전체 document에서 발견되는 connections과 insights를 knowledge graph 형태로 표현하게됨

$$
\hat{\mathcal{D}} = (\hat{\mathcal{V}}, \hat{\mathcal{E}}) = \mathrm{Dedupe} \circ \mathrm{Prof}(\mathcal{V}, \mathcal{E}), \\ \quad \mathcal{V}, \mathcal{E} = \bigcup_{\mathcal{D}_i \in \mathcal{D}} \mathrm{Recog}(\mathcal{D}_i)
$$

$\hat{\mathcal{D}}$ : 최종 지식 그래프

$D_i$: raw text document

3가지 스텝으로 $D_i$에서 $\hat{\mathcal{D}}$를 추출함

`Extracting Entities and Relationships. R()` 

Prompt를 통해서 Document에서 entity(nodes)를 추출하고 이 entity들의 relation(edges)을 추출함.

효율성을 높이기 위해서 Document를 chunk 단위로 쪼개서 수행한다고 함

`LLM Profiling for Key-Value Pair Generation. P`

LLM으로 작동하는 entity node와 relation edge에 대해서 text key-value pair(K,V)를 생성하는 profiling function을 사용함

Index Key는 efficient retrieval을 위한 word or short phrase

Value는 external data를 기반으로 한 relevant snippets를 요약한 text paragraph

Entity들은 name을 유일한 index key로 가지고 있는 반면 relation들은 연결된 엔티티들마다 뽑힌 global theme에 따르기 때문에 index key가 여러개 존재함

`Deduplication of Optimize Graph Operations. D`

서로 다른 raw text $D_i$에서 뽑힌 중복된 entity와 relation을 제거함 → graph의 크기 자체가 줄어들어서 $\hat{\mathcal{D}}$에 대한 graph operation 비용을 굉장히 효과적으로 줄여줌

---

위에서 소개한 D,P,R이 아래와 같이 적용되고 결과적으로 Index Graph가 생성됨

![image.png]({{ page.img_base }}/arch_1.png)

---

> **Graph Based Text Indexing의 장점?**
> 
1. multihop subgraph가 만들어지게 되면 global information을 추출할 수 있고 결과적으로 multiple document chunk를 봐야하는 복잡한 쿼리를 잘 다룰 수 있게 됨
2. less accurate한 embedding matching 보다 정확하고 inefficient한 chunk traversal보다 빠르게 retrieval가능

### Fast Adaptation to Incremental Knowledge Base

새로운 데이터를 빠르게 적용하기 위해서  전체 external database를 가공할 필요없이 새로운 데이터를 기존 knowledge base에 효율적으로 업데이트하는 구조를 가짐

목표는 다음 2가지임

- Seamless Integration of New Data 
consistent한 방법론으로 새로운 정보를 바로 적용할 수 있게하여 기존 그래프 구조를 disrupt하지 않고 new external database를 통합할 수 있음
- Reducing Computational Overhead
entire index를 다시 만들어야하는 필요성 자체를 날려서 계산 비용을 줄이고 빠르게 새로운 데이터를 적용 가능

`update 구조`

새로운 document($\mathcal D'$)가 들어옴 → graph-based indexing step을 똑같이 수행함 → 해당 document에서늬 지식 그래프$\hat {\mathcal D'} = (\hat {\mathcal V'},  \hat {\mathcal E'})$가 얻어짐

기존 node set, edge set과의 union을 통해 기존 graph와 합침 

## 2.Dual Level Retrieval Paradigm

2가지 수준의 query를 가정함

`Specific Quries`

graph의 특정 entity에 대한 specific, detail oriented한 질문임

보통 particular node, edge에 대한 질문

e.g. Who wrote ‘Pride and Prejudice’?

`Abstract Quries`

broader topic를 묶어야하는 질문, 주제에 대한 전반적인 질문이나 요약과 같은 보다 개념적인 수준의 질문. entity에 대한 직접적인 질문이 아님

e.g. How does artificial intelligence influence modern education?

위의 2가지 수준의 query를 다루기 위해서 retrieval 전략도 2가지 레벨로 이루어짐

`Low Level Retrieval`

specific entity와 그들의 attributes, relationships를 retrieve하는데 집중

`High Level Retrieval`

broader topics, 중요한 주제를 뽑아내는데 집중
related entities, relationships에 엮여있는 정보를 모으는데 집중

→ higher level concepts + summary 제공

### Integrating Graph and Vectors for Efficient Retrieval

vector representations과 graph structures를 합침으로써 entity간 interrelationship에서 더 깊은 insight를 얻어낼 수 있음

이를 통해서 local & global keywords를 둘다 활용하는 retrieval algorithm이 가능해지고 search process가 간소화됨

3단계로 진행됨

1. query keyword extraction
: query q가 들어왔을 때, local query keyword ($k^l$)과 global query keyword ($k^g$)를 retrieval algorithm을 통해 추출
2. keyword matching
: efficient한 vector로 후보 entity와 local query keywords를 매치, global key와 연결된 relation과 global query keywords를 매치함
3. incorporating high order relatedness
: higher order relatedness를 필요로하는 query를 다루기 위해 retrived graph의 nodes를 꺼내 모음
결과적으로 아래 수식처럼 one-hop neighboring nodes, edges를 꺼내올 수 있게 됨 

$$
\{ 
v_i | v_i \in  \mathcal V \wedge  (v_i \in \mathcal N_e \vee v_i \in \mathcal N_e)
\}
$$

이런 dual level 접근이 결과적으로 relevant structual information을 통합하할 수 있게됨

---

![image.png]({{ page.img_base }}/arch_2.png)

query를 low level key와 high level key로 나눠서 분석하여 keyword를 추출 그리고 이에 맞는 entity, relation, 원본 텍스트 발췌를 꺼내옴. 이게 retrived 된 data가 된다.

---

## 3. Retrieval Augmented Answer Generation

### Utilization of Retrieved Information

추출된 entities, relations를 profiling function을 이용해서 가공한 결과들을 이어붙인 data를 만듦

그리고 이 data를 이용해서 LLM으로 응답 생성

여기에는 entities와 relations의 이름과 설명등, 원본 텍스트 발췌등을 포함함

![image.png]({{ page.img_base }}/arch_3.png)

위 그림에서 retrieval context가 이어붙여진 data에 해당, 이거랑 query를 묶어서 llm의 입력으로 보냄

### Context Integration and Answer Generation

위에서 생성된 multi-souce text랑 query를 합쳐서 LLM으로 생성 → 유저의 의도를 잘 파악해서 생성

context + query를 둘다 LLM에 넣음으로써 answer generation 과정을 단순화 할 수 있게된다고 함

## 4.Complexity Analysis of the LightRAG Framework

위의 framework에서 발생하는 복잡도를 분석해보는 section으로 2가지로 나눠서 분석함

1. graph-based Index phase : LLM으로 각 chunk에서 entity랑 relationship을 추출하는데, 결과적으로 $\frac{\text{total tokens}}{\text{chunk size}}$만큼 호출됨 , 새로운 데이터가 들어왔을 때 이 외에 오버헤드가 없다는게 장점이라고 함
2. graph-based retrieval phase : query에 대해서 일단 relevant keywords를 추출 → 여기서는 vector based search를 사용. 하지만 chunk retrieve에서 RAG와 다르게 entity, relationships를 retrieve하는데 집중함 → 이 접근 방법이 GraphRAG에서 사용하는 community based traversal 방법보다 오버헤드가 줄어든다고 함

# Evaluation

제안한 구조를 평가하기 위해 다음 4가지 질문에 대해서 테스트

1. 기존 RAG 구조들과 비교해서 generation performance 비교(RQ1)
2. dual level retrieval과 graph based indexing가 LightRAG의 생성 퀄리티를 증가시키는가?(RQ2)
3. LightRAG가 가지는 특정한 장점이 있는가??(RQ3)
4. 데이터 변화에 대해서 발생하는 비용과 적응 능력이 어느정도인가?(RQ4)

### RQ1

`세팅`

4개 도메인 (Agriculture, CS, Legal, Mix)  코퍼스에서 125개 질문(LLM-생성)으로 평가

비교 대상 : Naive RAG, RQ-RAG, HyDE, **GraphRAG**. 

평가지표는 LLM 판정 기반 ① Comprehensiveness ② Diversity ③ Empowerment 및 종합(Overall).

`결과 정리` 

LightRAG가 모든 데이터셋·모든 지표에서 승률이 높았음
특히 대규모 Legal 코퍼스에서는 LightRAG 승률 ≈ 85 %, 베이스라인은 15 % 내외. 그래프 기반인 GraphRAG보다도 전반적으로 5 ~ 10 %p 앞섰음

![image.png]({{ page.img_base }}/result_0.png)

### RQ2

`세팅`

고수준 제거, 저수준 제거, 텍스트 chunk 미사용 세가지 모드에서 비교해서 결과 보기

`결과 정리`

두 수준을 동시에 쓸 때 가장 높음. 한 수준만 제거하면 5 ~ 10 %p 성능 하락. 원문 chunk를 빼도 성능 크게 떨어지지 않아 그래프 요약만으로도 충분한 맥락 제공됨을 확인

![image.png]({{ page.img_base }}/result_1.png)

### RQ3

`세팅`

영화 추천 지표를 묻는 질의 등에서 GraphRAG vs LightRAG 비교

`결과 정리`

LLM 평가 결과 네 지표 모두 LightRAG가 우세. 이유 : 엔티티·관계의 폭넓은 커버리지와 고·저수준 혼합이 더 다양한 관점·심층 정보 제공

### RQ4

`세팅`

토큰·API 콜 수를 Legal 셋에서 측정

`결과 정리`

- Retrieval 단계
GraphRAG 61 만 토큰 / 수백 API 콜 ↔ LightRAG < 100 토큰 / 1 콜.
- new data update
GraphRAG 전체 커뮤니티 재생성(약 1,400 × 2 × 5,000 토큰) 필요, LightRAG는 새 노드·엣지만 합집합으로 삽입 →대폭 저렴

![image.png]({{ page.img_base }}/result_2.png)

# My Summary

RAG는 LLM에서 발생하는 신뢰도 문제, 맥락을 충분히 못담는 문제를 해결하는 방법으로 많이 사용됨

그렇지만 기존 RAG는 문서를 단순히 vector로 압축하여` retrieval하는데, 이때 정보를 flat하게 표현하기 때문에 맥락을 다 못담고 multi hop relation을 못잡는 문제가 있었음 그리고 이를 해결하는 방법으로 GraphRAG 도입

LightRAG의 주요 특징은 다음과 같음

1. query의 keyword, relation의 키워드를 추출하여 dual level에서의 retrieval가 가능해짐
2. entity, relation 중심의 retrieval을 이용하여 full text를 retrieval하는 것보다 저렴해짐
3. 새로운 데이터를 추가할 때 기존 전처리 과정을 동일하게 거친 후 knowledge graph와 결합하기만 하면되는 구조로 만들어서 추가 비용이 훨씬 저렴함
4. vector + graph 를 결합한 구조를 사용해서 더 빠르고 정확한 검색이 가능해짐