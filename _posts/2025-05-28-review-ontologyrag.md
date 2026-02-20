---
title: Ontology-based RAG 프로젝트 후기
date: 2025-05-28 15:50:00 +0900
author: oogie
categories: [review,project]
tags: [RAG,GraphRAG]     # TAG names should always be lowercase]
img_base: /assets/img/2025-05-28-review-ontologyrag
use_math: true
---

## TL;DR

OSSCA에서 Ontology 기반 GraphRAG 프로젝트에 참여했다. USTR 보도자료에서 Lexical Graph를 구축하고, 공급망 데이터 기반의 Domain Graph와 결합하여 정책 변화에 따른 리스크 영향도를 분석할 수 있는 RAG 시스템을 구축했다. LightRAG를 베이스로 온톨로지 기반 도메인 그래프 통합, 검색 파이프라인 설계, 평가 체계 구축 과정을 정리했다.

---


# Intro

이번에 OSSCA(오픈소스 컨트리뷰션 아카데미)에서 주관한 참여형 프로그램에서 Ontology based RAG 프로젝트에 참가했다. 참가한 이유는 다음과 같다.

1. 추천/검색 시스템에 지식 그래프를 도입해보고싶은 동기가 있었기 때문에 온톨로지 구축의 경험을 해보면 간접적인 도움이 될 수 있을 것 같았다.
2. 이전 회사(SolverX)에서 GNN 기술을 많이 다뤘고 이때 graph를 다룰 때 발생하는 자원과 오버헤드에 대해서 경험했는데 이를 딥러닝 관점에서가 아니라 데이터 엔지니어링 관점에서 다뤄보고 싶었다.
3. 퇴사후 LLM을 많이 다루다보니 RAG 기술에도 관심을 가지고 있었는데 RAG의 단점을 보완한다는 GraphRAG 기술의 내용과 적용에 대해서 알아보고싶었다.

# 목표와 팀 구성 및 진행 방식

## 프로젝트 목표

이번 프로젝트의 목표는 미국 무역대표부(USTR)의 보도자료를 활용하여 외부 지식 데이터 기반의 GraphRAG 시스템을 구축하는 것이다. 특히 일반적인 문서에서 추출한 Lexical Graph뿐 아니라 공개된 공급망 데이터(Supply Chain Graph Data)를 활용한 Domain Graph를 연결하여, 보다 심층적인 추론과 분석이 가능한 시스템을 목표로 했다.

즉, 단순히 문서를 기반으로 Lexical Graph를 구성해 정보를 검색하는 기존 RAG 시스템에서 더 나아가, 특정 도메인의 전문적인 지식(Domain Graph)을 결합하여 추가적인 분석 및 추론 능력을 갖춘 시스템을 만드는 것을 목표로 했다. 
예를 들어,

```
“미국의 정책 변화로 인해 영향을 받는 공급사를 계열사, 공장, 제품 단위로 연결하여 리스크 영향도를 분석해줘.”
```

와 같은 질문이 주어졌을 때, 실제 리스크가 공급망 내에서 어떻게 전파되는지, 그리고 해당 정책 변화가 공급망의 특정 요소(기업, 제품 등)에 어떤 영향을 미치는지까지 심층적으로 분석하는 것을 목표로 했다.

## 팀 구성

내부적으로 4가지 단계로 쪼개고 3개의 팀을 나눠서 진행했다.

![image.png]({{ page.img_base }}/1.png)

### 데이터 전처리

데이터가 선정되었을 때 데이터를 구축,  분석 및 전처리를 수행한다.

---

### 지식 시스템 구축 + prompt 튜닝

앞서 수집한 Raw 데이터를 기반으로 GraphRAG에 적합한 형태로 지식 시스템을 구축한다. 특히 LightRAG에서는 RDF(Resource Description Framework)가 아닌 PLG(Property Labeled Graph) 형식을 사용하므로, 해당 형식에 맞춰 데이터를 구성해야 한다.

이를 위해 먼저 Entity Set을 정의하고, PLG 형식의 트리플을 생성할 수 있도록 Prompt를 설계 및 튜닝한다. 해당 프롬프트는 문서 내에서 의미 있는 관계를 추출하고, 이를 Neo4j에 적재하는 데 사용된다. 동시에 벡터 기반 질의를 위한 임베딩도 생성하여 Vector DB에 함께 저장한다.

LightRAG는 Graph 기반의 구조화 질의와 Vector 기반의 유사도 검색을 병렬적으로 수행하므로, 두 저장소(Neo4j와 Vector DB)에 모두 데이터를 적재하는 것이 핵심이다.

---

### LightRAG + 도메인 그래프 연동

Neo4j에 적재된 지식 그래프를 기반으로 LightRAG를 수행하며, 필요 시 추가적인 알고리즘을 구축하여 성능을 향상시킨다. 이후, 이 결과를 도메인 그래프와 연결함으로써 보다 정교한 Inference가 가능하도록 추가 구현을 진행한다. 이를 통해 구조화된 지식과 도메인 전문 정보가 결합된 고차원의 추론이 가능해진다.

---

### Query 설계 및 평가

GraphRAG 시스템을 실제 서비스에 도입한다고 가정했을 때, 가장 중요한 단계 중 하나는 예상 사용자(페르소나)를 정의하고 이에 기반한 쿼리와 기대 응답을 설계하는 것이다.

예를 들어, 정책 분석가, 공급망 관리자, 기업 전략 기획자 등의 다양한 페르소나에 맞춰 쿼리를 구성하고, 각각이 어떤 방식으로 시스템을 활용할 수 있을지를 시나리오 형태로 구체화한다.

이러한 시스템에서 특히 Vector RAG와의 비교를 통해 Graph 기반 추론의 장점이 실제로 성능 향상이나 응답의 정합성에 기여하는지를 정량적으로 평가할 수 있어야 하며, 이 과정을 통해 GraphRAG의 실질적인 효과성을 검증하고자 했다.

### 나의 역할

나는 일단 1팀에 지원했다. 1팀을 선택한 이유는

1. ontology 구축 자체에 관심이 있기 때문이다.
2. neo4j를 직접 다뤄볼 수 있는 기회가 제일 많아 보였기 때문이다.
3. 1팀을 진행했을 때 1팀에서 추출한 결과가 2팀에게 전달이 되는 것이고 3팀의 결과를 반영하여서 1팀에서 지식 그래프를 구축해야하기 때문에 2팀, 3팀과 협업을 할 수 있어보이는 부분이 많이 보이고 전체적인 시스템을 이해하고 다루기 좋아보였다. 

## 데이터 & 데이터 선정 이유

`Lexical Graph`

https://ustr.gov/about-us/policy-offices/press-office/press-releases

![image.png]({{ page.img_base }}/2.png)

미국 무역대표부(USTR)의 보도자료를 Lexical Graph 데이터로 선정한 이유는 다음과 같다.

1. 공급망 데이터셋의 시점과의 일치성: 공급망 데이터셋이 2023년 데이터이기 때문에 같은 시점의 최신 데이터를 활용하여 시의적절한 연결고리를 만들 수 있다.
2. 공신력과 파급력: 미국 무역대표부는 국제적으로 공신력이 높고, 그들이 제공하는 데이터는 시장과 비즈니스 환경에 직접적인 영향을 미칠 수 있는 공식적인 정보이다.
3. 데이터의 명확한 구조: Press releases, Fact sheets, Speeches and remarks 등의 다양한 카테고리로 나뉘어져 있으며, 사건 발생 시점 전후의 명확한 사실과 정책적 방향성을 동시에 파악할 수 있다.

이를 통해, 공급망 데이터와 함께 복잡한 도메인 간의 관계성을 심층적으로 추론하고 분석할 수 있는 기반을 마련할 수 있을 것이라는 가설을 세웠다.

`Domain Graph`

[https://oogie.notion.site/Supply-Graph-1e84b8a2fb218059bb03e0819d59af6b?pvs=4](https://oogie.notion.site/Supply-Graph-1e84b8a2fb218059bb03e0819d59af6b?pvs=4)

도메인 그래프는 Nodes, Edges , Temporal 데이터 3개 섹션으로 이루어져있음
Nodes는 product의 feature로 id, index(integer id) group, subgroup, plant, storage로 구성됨
Edges는 node간의 연결인데 같은 group, subgorup, plant, storage를 공유하는 경우를 edge로 보고 저장해놓음
Temporal data 는 시간대별로 Product(Node)의 주문량, 배송량, 생산량, 출고 물량을 개수와 무게 단위로 저장해놓음

이들을 그래프로 묶기 위해서 다음과 같은 relation type을 정의해서 domain graph 생성

- **CONNECTED_STORAGELOCATION(product - plant)**: 특정 제품이 어떤 공장에서 생산되어 어떤 창고에 저장되었는지를 나타내는 관계.
- **CONNECTED_PRODUCTGROUP**: 동일한 제품 그룹에 속한 제품들 간의 연결을 나타내는 관계.
- **CONNECTED_PRODUCTSUBGROUP**: 동일한 제품 서브그룹에 속한 제품들 간의 연결을 나타내는 관계.
- **DELIVERYTODISTRIBUTOR**: 유통업체로 실제 배송된 제품 수량 및 무게를 나타내며, 이는 회사의 수익에 직접적인 영향을 미친다.
- **PRODUCTION**: 주문, 고객 수요, 차량 적재율, 배송 긴급도를 고려하여 실제 생산된 제품 수량과 무게를 나타낸다.
- **FACTORYISSUE**: 공장에서 출고된 전체 제품 수량 및 무게로, 유통업체로 배송되거나 창고에 저장되는 물량을 나타낸다.
- **SALESORDER**: 유통업체가 요청한 제품 수량을 나타내며, 이는 제품의 총 수요를 반영한다.

***<생성된 도메인 그래프>***

노란색 : product, 회색 : plant

![image.png]({{ page.img_base }}/3.png)

# 지식 그래프 구축

### entity set 정의

LightRAG의 프롬프트는 기본적으로 다음과 같이 생겼다.

- prompt
    
    ```python
    ROMPTS["entity_extraction"] = """---Goal---
    Given a text document that is potentially relevant to this activity and a list of entity types, identify all entities of those types from the text and all relationships among the identified entities.
    Use {language} as output language.
    
    ---Steps---
    1. Identify all entities. For each identified entity, extract the following information:
    - entity_name: Name of the entity, use same language as input text. If English, capitalized the name.
    - entity_type: One of the following types: [{entity_types}]
    - entity_description: Comprehensive description of the entity's attributes and activities
    Format each entity as ("entity"{tuple_delimiter}<entity_name>{tuple_delimiter}<entity_type>{tuple_delimiter}<entity_description>)
    
    2. From the entities identified in step 1, identify all pairs of (source_entity, target_entity) that are *clearly related* to each other.
    For each pair of related entities, extract the following information:
    - source_entity: name of the source entity, as identified in step 1
    - target_entity: name of the target entity, as identified in step 1
    - relationship_description: explanation as to why you think the source entity and the target entity are related to each other
    - relationship_strength: a numeric score indicating strength of the relationship between the source entity and target entity
    - relationship_keywords: one or more high-level key words that summarize the overarching nature of the relationship, focusing on concepts or themes rather than specific details
    Format each relationship as ("relationship"{tuple_delimiter}<source_entity>{tuple_delimiter}<target_entity>{tuple_delimiter}<relationship_description>{tuple_delimiter}<relationship_keywords>{tuple_delimiter}<relationship_strength>)
    
    3. Identify high-level key words that summarize the main concepts, themes, or topics of the entire text. These should capture the overarching ideas present in the document.
    Format the content-level key words as ("content_keywords"{tuple_delimiter}<high_level_keywords>)
    
    4. Return output in {language} as a single list of all the entities and relationships identified in steps 1 and 2. Use **{record_delimiter}** as the list delimiter.
    
    5. When finished, output {completion_delimiter}
    
    ######################
    ---Examples---
    ######################
    {examples}
    
    #############################
    ---Real Data---
    ######################
    Entity_types: [{entity_types}]
    Text:
    {input_text}
    ######################
    Output:"""
    ```
    

LightRAG 논문(https://sangwookbaek.github.io/posts/review-lightrag/)과 실제 프롬프트 구조를 참고하면, 관계 유형(relation type)은 LLM을 통해 생성하고, 명확하게 지정된 엔터티를 입력으로 넘겨주는 방식이 필요하다는 점을 확인할 수 있다. 따라서 본 프로젝트에서는 지식 추출 이전에 먼저 Entity Set을 정의하는 작업이 선행되었다.

이상적으로는 3팀의 페르소나와 예상 쿼리를 바탕으로 엔터티를 정의하는 것이 바람직했지만, 시간 제약으로 인해 병렬적으로 작업을 진행해야 했기 때문에 우선 Entity를 정의한 후 이를 기반으로 프롬프트를 구성하였다.

Entity 정의 과정에서는 World Bank의 *Supply Chain Management Guidance* 문서를 참고하고, 실제 USTR 보도자료를 분석하여 자주 등장하고 중요하다고 판단되는 개념들을 수집하였다. 또한 기존 LightRAG 프롬프트나 다른 온톨로지 관련 논문 사례들을 참고했을 때, Entity 개수는 10개 내외가 적절하다고 판단하여 이에 맞춰 선정하였다.

이와 같은 방식으로 정의된 Entity Set을 바탕으로 PLG(Property Labeled Graph) 형식의 관계 트리플을 생성할 수 있도록 프롬프트를 구성하고 튜닝하였으며, 생성된 데이터는 Neo4j에 적재된다. 동시에 문서 임베딩을 생성하여 Vector DB에도 함께 저장한다.

LightRAG는 구조화된 그래프 검색과 비구조화된 벡터 검색을 병행하므로, 이 두 형태의 지식 저장 방식은 모두 필수적이다.

- entity types
    
    ```yaml
    entity_types:
        - AGREEMENT
        - TRADE_POLICY
        - ORG
        - ADJUDICATOR
        - EVENT / CASE
        - POSITION
        - PERSON
        - ECONOMIC_TERM / RIGHT
        - ECONOMIC_POLICY
        - ACTION
        - ECONOMIC_CONCEPT
        - TRADE_BARRIER
        - DISPUTE_RESOLUTION
        - GOVERNMENT / ADMINISTRATION
    
      entity_descriptions:
      AGREEMENT: Inter-governmental agreements or treaties between countries (e.g., USMCA, FTA, WTO agreements).
      TRADE_POLICY: Trade policies or measures defined within a country or agreement (e.g., TRQ policy, import allocation, subsidies).
      ORG: Organizations such as governments, international bodies, industry associations, committees (e.g., USTR, USDEC).
      ADJUDICATOR: Panels or bodies that hand down legal/administrative judgments; a subtype of ORG.
      EVENT: Discrete events or cases at a point in time (e.g., maize-ban dispute filing, first RRM case).
      POSITION: Roles or titles held by individuals (e.g., U.S. Trade Representative, President).
      PERSON: Specific individuals (e.g., Katherine Tai, Joe Biden).
      ECONOMIC_TERM: Economic terms/rights (e.g., market access, import rights).
      ECONOMIC_POLICY: National or agreement-level economic doctrines (e.g., protectionism, free trade).
      ACTION: Concrete acts or procedural steps (e.g., request panel, impose tariff, notify).
      ECONOMIC_CONCEPT: General economic concepts (e.g., fair competition, efficiency).
      TRADE_BARRIER: Measures that restrict trade (e.g., GM-maize import ban, tariffs, NTBs).
      DISPUTE_RESOLUTION: Formal procedures for resolving disputes within an agreement (e.g., USMCA Chapter 31 process).
      GOVERNMENT: Specific governments/administrations (e.g., Biden Administration, Trudeau Government).
    
    ```
    

## neo4j 적재

prompt를 통해 생성되는 결과는 다음과 같다.

- 예시 결과
    
    ```python
     """
        ("entity"<|>United States<|>Actor<|>The United States is a country that issues proclamations and regulations regarding trade and international relations, including actions under the African Growth and Opportunity Act (AGOA).)##
        ("entity"<|>Islamic Republic of Mauritania<|>Actor<|>Mauritania is a country in sub-Saharan Africa that has been designated as a beneficiary country under the AGOA, subject to eligibility criteria set by the Trade Act.)##
        ("entity"<|>Proclamation 9834<|>Regulation<|>Proclamation 9834 is a formal declaration issued by the President of the United States regarding trade actions under the AGOA, specifically addressing Mauritania's eligibility.)##
        ("entity"<|>African Growth and Opportunity Act<|>Regulation<|>The AGOA is a United States trade act that enhances trade and economic relations with sub-Saharan African countries by providing them with duty-free access to the U.S. market.)##
        ("entity"<|>Trade Act of 1974<|>Regulation<|>The Trade Act of 1974 is a U.S. law that allows the President to designate countries as beneficiaries for trade benefits based on their compliance with certain eligibility criteria.)##
        ("entity"<|>section 506A<|>Regulation<|>Section 506A of the Trade Act outlines the criteria and processes for designating beneficiary sub-Saharan African countries under the AGOA.)##
        ("entity"<|>section 112(c)<|>Regulation<|>Section 112(c) of the AGOA provides special rules for certain apparel articles imported from lesser developed beneficiary sub-Saharan African countries.)##
        ("entity"<|>Africa Investment Incentive Act of 2006<|>Regulation<|>This act amended certain provisions of the AGOA, including special rules for apparel imports from lesser developed beneficiary countries.)##
        ("entity"<|>lesser developed beneficiary sub-Saharan African countries<|>Region<|>This term refers to a classification of sub-Saharan African countries that are eligible for special trade treatment under the AGOA.)##
        ("entity"<|>eligibility requirements<|>Policy<|>Eligibility requirements are the criteria set forth in the AGOA and the Trade Act that determine whether a country can be designated as a beneficiary.)##
        ("entity"<|>beneficiary sub-Saharan African country<|>Policy<|>A beneficiary sub-Saharan African country is one that meets specific eligibility criteria to receive trade benefits under the AGOA.)##
        ("relationship"<|>United States<|>Islamic Republic of Mauritania<|>The United States issued a proclamation affecting Mauritania's status as a beneficiary country under the AGOA based on its compliance with eligibility requirements.<|>trade regulation, beneficiary designation<|>8)##
        ("relationship"<|>Proclamation 9834<|>Islamic Republic of Mauritania<|>Proclamation 9834 determined Mauritania's lack of compliance with the AGOA eligibility requirements, leading to the termination of its beneficiary status.<|>regulatory action, compliance<|>7)##
        ("relationship"<|>Proclamation 9834<|>African Growth and Opportunity Act<|>Proclamation 9834 is issued under the authority of the AGOA, which governs the eligibility of countries for trade benefits.<|>regulatory framework, trade benefits<|>9)##
        ("relationship"<|>Trade Act of 1974<|>African Growth and Opportunity Act<|>The Trade Act of 1974 provides the legal foundation for the AGOA, allowing the designation of beneficiary countries.<|>legal framework, trade policy<|>9)##
        ("relationship"<|>section 506A<|>Islamic Republic of Mauritania<|>Section 506A outlines the criteria for determining Mauritania's eligibility as a beneficiary country under the AGOA.<|>eligibility criteria, regulatory compliance<|>8)##
        ("relationship"<|>section 112(c)<|>lesser developed beneficiary sub-Saharan African countries<|>Section 112(c) provides special trade rules for apparel imports from lesser developed beneficiary sub-Saharan African countries.<|>trade rules, special treatment<|>7)##
        ("relationship"<|>Africa Investment Incentive Act of 2006<|>African Growth and Opportunity Act<|>The Africa Investment Incentive Act of 2006 amended provisions of the AGOA, impacting trade rules for beneficiary countries.<|>legislative amendment, trade policy<|>8)##
        ("content_keywords"<|>trade, regulation, eligibility, AGOA, Mauritania, proclamation, compliance, beneficiary<|>trade, regulation, eligibility, AGOA, Mauritania)##("content_keywords"<|>high_level_keywords<|>trade policy, international relations, compliance, legislative framework)##<|COMPLETE|>
        """
    ```
    

이를 Neo4j에 적재하기 위해서 일단 node의 이름을 id로 잡는다. 그리고 나머지 항목은 Property로 둔다.

그리고 relation으로 정의된 Node들을 연결하는 relation을 삽입한다.

- 적재 코드
    
    ```python
    def to_kg_in_chunk(output, gid):
    """
    output을 neo4j에서 필요로하는 kg형태로 정제
    """
        TUPLE_DELEMITER = "<|>"
        RECORD_DELEMITER = "##"
        WRAPPER = "()"
        ENTITY_PREFIX, RELATIONSHIP_PREFIX, CONTENT_KEYWORDS_PREFIX = (
            '"entity"',
            '"relationship"',
            '"content_keywords"',
        )
    
        kg = {
            "entities": [],
            "relationships": [],
            "content_keywords": [],
        }
        source_id = f"Source{gid+1}"
        output_list = output.strip().split(RECORD_DELEMITER)
        for tmp_output in output_list:
            tmp_list = tmp_output.strip("\n").strip(WRAPPER).split(TUPLE_DELEMITER)
            if tmp_list[0] == ENTITY_PREFIX:
                tmp = {
                    "entity_name": tmp_list[1],
                    "entity_type": tmp_list[2],
                    "description": tmp_list[3],
                    "source_id": source_id,
                }
                kg["entities"].append(tmp)
            elif tmp_list[0] == RELATIONSHIP_PREFIX:
                tmp = {
                    "src_id": tmp_list[1],
                    "tgt_id": tmp_list[2],
                    "description": tmp_list[3],
                    "keywords": tmp_list[4],
                    "weight": float(tmp_list[5]),
                    "source_id": source_id,
                }
                kg["relationships"].append(tmp)
            elif tmp_list[0] == CONTENT_KEYWORDS_PREFIX:
                tmp = {
                    "high_level_keywords": tmp_list[-1].strip().split(","),
                    "source_id": source_id,
                }
                kg["content_keywords"].append(tmp)
            else:
                continue
        return kg
    
    def insert_entity_node(tx, chunk_number, doc_id, entity_name, entity_type, description):
    """
    entity를 node로 삽입.
    해당 Node가 속한 chunk가 적재되어있지 않다면 error 발생
    """
        check_chunk(tx, chunk_number, doc_id)
        # create
        tx.run(
            f"""
            MATCH (c:Chunk {{chunk_number: $chunk_number, doc_id: $doc_id}})
            CREATE (e:{entity_type} {{name: $entity_name, description: $description}})
            CREATE (c)-[:CONTAINS_ENTITY]->(e)
            """,
            chunk_number=chunk_number,
            doc_id=doc_id,
            entity_name=entity_name,
            description=description,
        )
    
    def insert_entity_relationship(
        tx,
        chunk_number,
        doc_id,
        source_entity,
        target_entity,
        description,
        keywords,
        strength,
    ):
    """
    relation을 적재하는 코드
    entity가 적재되어있지 않을때 error 발생
    """
        check_chunk_to_entity(tx, chunk_number, doc_id, source_entity, target_entity)
        tx.run(
            """
            MATCH (c:Chunk {chunk_number: $chunk_number, doc_id: $doc_id})
            MATCH (c)-[:CONTAINS_ENTITY]->(e1 {name: $source_entity})
            MATCH (c)-[:CONTAINS_ENTITY]->(e2 {name: $target_entity})
            MERGE (e1)-[:RELATED_TO {
                source_entity: $source_entity,
                target_entity: $target_entity,
                description: $description,
                keywords: $keywords,
                strength: $strength
            }]->(e2)
            """,
            chunk_number=chunk_number,
            doc_id=doc_id,
            source_entity=source_entity,
            target_entity=target_entity,
            description=description,
            keywords=keywords,
            strength=strength,
        )
    ```
    

### 그래프 구조

최종적으로 구성되는 그래프는 다음과 같은 구조를 갖는다:

- **중심 노드**: 보라색 노드는 보도자료 전체 문서를 나타내며, 그래프의 중심이 된다.
- **청크 노드**: 갈색으로 표시된 1, 2, 3번 노드들은 보도자료를 의미 단위로 분할한 chunk들을 나타낸다. 각 chunk는 문서 내 하나의 단락 또는 문맥 단위다.
- **엔터티 노드**: 각 chunk 내에서 추출된 개별 엔터티들이 노드로 추가된다. 이 엔터티들은 사람, 조직, 국가, 제품 등 특정 개념에 해당한다.
- **관계 엣지(Relations)**: 추출된 엔터티 간에는 LLM 기반 프롬프트를 통해 정의된 다양한 관계들이 엣지 형태로 연결된다. 이 관계들은 정책 영향, 공급망 연결, 역할, 소속 등의 의미를 가진다.

이러한 구조는 각 보도자료의 문맥을 유지한 채, 문서 내외의 개념들을 다층적으로 연결할 수 있도록 설계되어 있다.

![image.png]({{ page.img_base }}/4.png)

## 버저닝 및 협업 방식 : hydra + notion

프롬프트의 경우 hydra를 이용해서 버전별로 파일을 만들어 관리했다.

그런데 이는 인스턴스에서 entity 추출을 버전 관리할 때 유용하지만 팀원 분들과 협업을 하기에는 아쉬움이 있었다. 우리는 노션을 통해서 협업했기 때문에 구조화되어있는 prompt를 notion에 table에 삽입하는 방식을 취했다.

- notion table
    
    ![image.png]({{ page.img_base }}/5.png)

    
- notion sdk 코드 → hydra config를 notion으로 업로드, notion의 table에서 yaml파일로 저장
    
    ```python
    def config2notion(cfg):
        load_dotenv()
        # ─── 1) 설정 ───
        NOTION_TOKEN = os.getenv("NOTION_TOKEN")  # Integration 토큰
        NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # 대상 데이터베이스 ID
        for key in cfg:
            if isinstance(cfg[key], list):
                for idx in range(len(cfg[key])):
                    cfg[key][idx] = str(cfg[key][idx])
    
        # ─── 2) Notion 클라이언트 초기화 ───
        notion = Client(auth=NOTION_TOKEN)
        db_info = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
    
        notion_schema = db_info["properties"]
        props = dict_to_props(cfg, notion_schema)
        notion.pages.create(parent={"database_id": NOTION_DATABASE_ID}, properties=props)
    
    def notion2config(target_id, cfg_path, model_cfg_path="./config/base.yaml"):
        load_dotenv()
        # ─── 1) 설정 ───
        NOTION_TOKEN = os.getenv("NOTION_TOKEN")  # Integration 토큰
        NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")  # 대상 데이터베이스 ID
    
        # ─── 2) Notion 클라이언트 초기화 ───
        notion = Client(auth=NOTION_TOKEN)
        db_info = notion.databases.retrieve(database_id=NOTION_DATABASE_ID)
        notion_schema = db_info["properties"]
        response = notion.databases.query(
            **{
                "database_id": NOTION_DATABASE_ID,
                "filter": {"property": "id", "title": {"equals": target_id}},
                "sorts": [{"property": "last_updated", "direction": "descending"}],
                "page_size": 1,  # 가장 최신 한 건만
            }
        )
    
        # 3) 결과 확인
        results = response.get("results", [])
        if not results:
            print("해당 id의 페이지가 없습니다.")
            return None
        else:
            page = results[0]
            cfg = props_to_dict(page["properties"], notion_schema)
            prompt_cfg = {}
            for key in cfg:
                tmp = cfg[key]
                tmp_object = parse_string_to_python_object(tmp)
    
                prompt_cfg[key] = tmp_object  # 새로 저장
    
            with open(model_cfg_path, "r", encoding="utf-8") as f:
                model_cfg = yaml.safe_load(f)
            save_to_yaml_file(prompt_cfg, model_cfg, cfg_path)
            
    ```
    

### 2 & 3팀과 협업

- 2팀과의 협업은 새롭게 entity를 추출해 knowledge graph를 만들었을 때 업데이트된 database를 2팀에게 전달하는 식으로 수행했다
- 3팀과의 협업은 3팀이 정리한 페르소나, 쿼리를 보고 거기서 추가하거나 고려해볼만한 entity를 수정하거나 프롬프트를 수정하는 식으로 진행했다.

# 인스턴스 구조 (Docker Compose & Dockerfile)

이 부분은 내가 진행한 내용이 아니라 멘토님께서 진행해주신 내용이다.

- docker-compose.yml
    
    ```yaml
    services:
      lightrag:
        container_name: lightrag
        build: .
        ports:
          - "${PORT:-9621}:9621"
          - "8888:8888"
          - "2727:2727"
        volumes:
          - ./data/rag_storage:/app/data/rag_storage
          - ./data/inputs:/app/data/inputs
          - ./config.ini:/app/config.ini
          - ./.env:/app/.env
          - ./monitoring:/app/monitoring/
          - ./notebook:/app/notebook
          - ./tests:/app/tests
        env_file:
          - .env
        restart: unless-stopped
        extra_hosts:
          - "host.docker.internal:host-gateway"
        depends_on:
          - dozerdb
        networks:
          - lightrag_net
    
      dozerdb:
        image: graphstack/dozerdb:5.26.3.0
        container_name: dozerdb
        ports:
          - "7474:7474"
          - "7687:7687"
        environment:
          - NEO4J_AUTH=neo4j/ossca2727
          - NEO4J_PLUGINS=["apoc"]
          - NEO4J_apoc_export_file_enabled=true
          - NEO4J_apoc_import_file_enabled=true
          - NEO4J_dbms_security_procedures_unrestricted=*
        volumes:
          - ./lightrag/dbinterface/lightrag_neo4j_data:/data
          - ./lightrag/dbinterface/lightrag_neo4j_logs:/logs
          - ./lightrag/dbinterface/lightrag_neo4j_import:/var/lib/neo4j/import
          - ./lightrag/dbinterface/plugins:/plugins
        extra_hosts:
          - "host.docker.internal:host-gateway"
        networks:
          - lightrag_net
    
      prometheus:
        image: prom/prometheus
        container_name: prometheus
        ports:
          - "9090:9090"
        volumes:
          - ./monitoring/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
        networks:
          - lightrag_net
    
      grafana:
        image: grafana/grafana
        container_name: grafana
        ports:
          - "3000:3000"
        depends_on:
          - prometheus
        volumes:
          - ./monitoring/grafana:/var/lib/grafana
        networks:
          - lightrag_net
    
    volumes:
      lightrag_neo4j_data:
      lightrag_neo4j_logs:
      lightrag_neo4j_import:
    
    networks:
      lightrag_net:
        driver: bridge
    
    ```
    
- Dockerfile
    
    ```docker
    # Build stage
    FROM python:3.11-slim AS builder
    
    WORKDIR /app
    
    # Install Rust and required build dependencies
    RUN apt-get update && apt-get install -y \
        curl \
        build-essential \
        pkg-config \
        && rm -rf /var/lib/apt/lists/* \
        && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
        && . $HOME/.cargo/env
    
    # Copy only requirements files first to leverage Docker cache
    COPY requirements.txt .
    COPY lightrag/api/requirements.txt ./lightrag/api/
    
    # Install dependencies
    ENV PATH="/root/.cargo/bin:${PATH}"
    RUN pip install --user --no-cache-dir -r requirements.txt
    RUN pip install --user --no-cache-dir -r lightrag/api/requirements.txt
    
    # Final stage
    FROM python:3.11-slim
    
    WORKDIR /app
    
    # Copy only necessary files from builder
    COPY --from=builder /root/.local /root/.local
    COPY ./lightrag ./lightrag
    COPY setup.py .
    COPY ./monitoring ./monitoring
    COPY ./monitoring/query_api.py ./monitoring/query_api.py
    
    RUN pip install .
    # Make sure scripts in .local are usable
    ENV PATH=/root/.local/bin:$PATH
    
    # Create necessary directories
    RUN mkdir -p /app/data/rag_storage /app/data/inputs
    
    # Docker data directories
    ENV WORKING_DIR=/app/data/rag_storage
    ENV INPUT_DIR=/app/data/inputs
    
    # Expose the default port
    EXPOSE 9621 8888 2727 9090 3000
    
    # Set entrypoint
    # ENTRYPOINT ["python", "-m", "lightrag.api.lightrag_server"]
    CMD ["uvicorn", "monitoring.query_api:app", "--host", "0.0.0.0", "--port", "2727"]
    ```
    

### 서비스 레이어

| Service | 역할 | 주요 포트 |
| --- | --- | --- |
| `lightrag` | GraphRAG API 서버, Jupyter 노트북, 모니터링 엔드포인트 | 9621(API), 8888(Jupyter), 2727(Monitoring API) |
| `dozerdb` | **Neo4j** 기반 그래프 DB(APOC 플러그인 포함) | 7474(HTTP), 7687(Bolt) |
| `prometheus` | 컨테이너 메트릭 수집 | 9090 |
| `grafana` | 프로메테우스 결과 대시보드로 시각화 | 3000 |

# 추가 구현 → 개인적으로 구현한 내용

여기까지가 진행한 멘토링 기간 동안 진행한 프로젝트의 내용이다.

이 내용을 보면 아직 부족한 부분이 많다. 정리해보면 다음과 같다.

1. 그래서 lightrag랑 어떻게 연결되나?
2. 그래서 domain graph와 연결 해야하지?
3. 평가는 어떤식으로 진행할까?

멘토링이 끝난 뒤 개인적으로 위 3가지에 대해서 고민하고 추가 구현한 내용을 정리하려고 한다.

## LightRAG와의 연결

기존 내용에서 특히 궁금한 점이 2가지 있었는데

1. chunk안에서만 entity - relation을 만들게되면 multi hop question을 어떻게 대답할 수 있는가
: 결국 한 chunk안에서 만들어지게 되는데 이 경우 vectordb만으로 충분하게 결과를 뽑을 수 있을 것 같고 결국 chunk - chunk를 넘어가는 multi hop question을 수행해야할 것 같은데 이를 어떻게 구현하나?
2.  기존에 진행한 방법으로 knowledge graph를 만들게되면 서로 다른 chunk에서 뽑아진 동일한 이름을 가진 node가 많이 생겨나게 되는데 이걸 어떻게 다룰 것인가??

이는 모두 lightrag에서 다뤄진다는 것을 lighrag 구조를 뜯어봄으로써 확인했다.

1. 일단 lightrag에서는 chunk에서 만들어진 subgraph를 global graph 로 병합한다.
    - **청크별 추출 → 최종 병합**
        
        각 청크에서 `maybe_nodes`, `maybe_edges`로 추출된 엔티티와 관계를 `all_nodes`, `all_edges`에 통합·그룹화한다. 이 과정에서 동일 키(엔티티 이름, 관계 쌍)를 기준으로 결합하며, 결과적으로 하나의 글로벌 지식 그래프가 완성된다.
        
    - **네오4J에 Upsert(MERGE)**
        
        병합된 엔티티와 관계를 Neo4j에 `MERGE` 쿼리로 삽입/업데이트하여, 중복 없는 단일 노드·단일 관계 구조를 유지하게 된다.
        
    - **벡터 검색 + 그래프 탐색의 하이브리드**
        
        질의 시에는 먼저 청크 수준의 벡터 검색으로 **seed 노드**를 찾고, 이어서 지식 그래프 상에서 Cypher 패스를 수행해 필요한 다중 홉(multi-hop) 연결 경로를 탐색합니다. 이때 각 관계에 부여된 `weight`(관계 강도)나 `degree`(노드 중요도)를 기반으로 탐색 우선순위를 조절할 수 있다.
        
2. LightRAG은 deduplication 과정을 거친다.
    - **해시 기반 식별자 생성**
        
        각 엔티티 이름에 대해 `compute_mdhash_id(entity_name, prefix="ent-")`로 고유 ID를 생성하고, 관계도 `(src_id + tgt_id)` 조합을 동일한 방식으로 해싱하여 `rel-` 접두사 ID를 만든다.
        
    - **최종 병합 단계에서 그룹화**
        
        `all_nodes["Alex"]`처럼 엔티티 이름을 키로 모든 추출 조각을 한데 모으고, 관계도 `(Alex, Taylor)`를 정렬한 후 동일 키로 묶어 중복 관계를 통합한다.
        
    - **Cypher MERGE로 단일화**
        
        Neo4j에 Upsert 시 `MERGE (n:base {entity_id: $entity_id})`를 사용해, 이미 존재하는 노드·관계는 갱신만 하고 신규 생성은 막아 중복 생성을 방지한다.
        

→ 결과적으로 프로젝트동안 만든 prompt 내용을 코드 내부로 삽입하면 문제없이 lightrag가 작동한다

## 인프라 이식 및 구성

프로젝트 초기에는 AWS 인프라에서 코드를 배포·운영했으나, 멘토링 종료 후 제공 서버가 사라져 개인 오라클 서버로 환경을 이식하며 다음과 같이 주요 설정을 수정·최적화했습니다.

### KV 스토어: JSON → PostgreSQL

- 대용량 JSON 파일 기반 저장소의 안정성 이슈를 해소하기 위해 PostgreSQL로 전환했습니다.
- 관계형 DB의 트랜잭션 보장, 인덱싱, 확장성 기능을 활용해 데이터 안정성을 확보했습니다.

### 벡터 스토어: FAISS → pgvector

- 벡터 검색도 PostgreSQL 내장 확장인 pgvector로 통합 관리하도록 마이그레이션했습니다.
- FAISS 설치·운영 복잡도를 제거하고, KV 스토어와 일원화된 환경에서 편리하게 관리합니다.

### Query API 최적화

- **인스턴스 초기화 최적화**
    - FastAPI의 `startup` 이벤트 훅에서 LightRAG 인스턴스와 Neo4j 드라이버를 한 번만 초기화하도록 변경했습니다.
    - 이후 모든 요청에 동일 인스턴스를 재사용해 불필요한 리소스 낭비를 줄였습니다.
- **메모리 경량화**
    - 사용하지 않는 전역 변수 및 리스트를 제거해 메모리 사용량을 최소화했습니다.
    - 핵심 로직에 필요한 데이터만 메모리에 유지하도록 구조를 재정비했습니다.

### Gemini LLM 통합

- OpenAI API 호출 비용을 줄이기 위해 Google Gemini LLM 및 임베딩 함수 연동 코드를 추가했습니다.
- LightRAG 코드베이스에 Gemini 전용 LLM 호출·임베딩 모듈을 구현해, 대다수 LLM 요청을 Gemini로 처리하도록 확장했습니다.

아직 밑의 2가지 질문에 대해서 구현을 마무리 하지 못했고 현재 구현을 진행하고 있다. 

1. 그래서 domain graph와 연결 해야하지?
2. 평가는 어떤식으로 진행할까?

추후 구현이 될때마다 내용을 업데이트할 예정이다.

# Outro

Intro에서 아래 3가지 목적을 가지고 프로젝트에 지원했다고 얘기했다.

1. 추천/검색 시스템에 지식 그래프를 도입해보고싶은 동기가 있었기 때문에 온톨로지 구축의 경험을 해보면 간접적인 도움이 될 수 있을 것 같았다.
→ 전통적인 의미의 온톨로지가 아닌 PLG형태로 구현을 한것이라 살짝 다르긴하지만 온톨로지라는 시스템 자체를 어떻게 접근할지에 대해서 감을 얻을 수 있어 도움이 되었다.
2. 이전 회사(SolverX)에서 GNN 기술을 많이 다뤘고 이때 graph를 다룰 때 발생하는 자원과 오버헤드에 대해서 경험했는데 이를 딥러닝 관점에서가 아니라 데이터 엔지니어링 관점에서 다뤄보고 싶었다.
→ neo4j를 직접 많이 만지면서 발생하는 오버헤드나 neo4j의 로우레벨 인터널까지 다뤄볼 수 있어서 유익했다.
3. 퇴사후 LLM을 많이 다루다보니 RAG 기술에도 관심을 가지고 있었는데 RAG의 단점을 보완한다는 GraphRAG 기술의 내용과 적용에 대해서 알아보고싶었다.
→ GraphRAG 기술, 특히 Lightrag 알고리즘과 그 구현에 대해서 뜯어볼 수 있었다.

## Outro

이번 프로젝트는 처음에 가졌던 세 가지 목적을 돌아보는 데 의미 있는 시간이 되었다.

1. **추천/검색 시스템에 지식 그래프를 도입해보고 싶다**
    
    전통적인 온톨로지 시스템은 아니었지만, PLG(Product-Led Graph) 형태의 구현을 경험하면서 온톨로지를 어떤 방식으로 접근하고 구조화할 수 있는지에 대한 감을 얻을 수 있었다. 
    
2. **Graph 연산의 자원/오버헤드를 데이터 엔지니어링 관점에서 다뤄보고 싶다**
    
    Neo4j를 직접 운영하며 쿼리 성능 튜닝, 병합(MERGE) 연산의 비용, 데이터 모델링 방식에 따라 발생하는 성능 차이 등을 체험했다. 특히 대규모 데이터를 대상으로 했을 때 시스템이 감당해야 하는 부하를 실감했고, 이는 기존 딥러닝 모델과는 또 다른 차원의 고민을 안겨주었다.
    
3. **GraphRAG, 특히 LightRAG에 대해 깊이 이해하고 싶었다**
    
    알고리즘 구조와 코드 구현을 직접 뜯어보며, 단순 벡터 검색 기반 RAG가 아닌, 지식 그래프 기반의 추론이 어떻게 이루어지는지 구체적으로 이해할 수 있었다. 멀티홉 질문 대응, 엔티티 병합, 그래프 탐색 기반 추론 등 GraphRAG의 강점을 확인했다.
    

하지만 이 과정에서 현실적인 한계 또한 분명히 보였다.

GraphRAG 구조는 생각보다 고려할 요소가 많았고, 특히 Neo4j와 같은 외부 그래프 시스템을 연동할 경우, 성능과 비용 측면에서 **엔터프라이즈 환경에서의 도입은 상당한 오버헤드**가 발생할 수 있음을 체감했다.

아직 Vector RAG와의 직접적인 성능 비교는 진행하지 못했지만, 두 방식의 **속도, 정확도, 비용 효율성** 등을 정량적으로 비교해가며 GraphRAG만의 장점을 찾아보고자 하고 실제 비즈니스 환경에 적합한 구조가 무엇인지 판단할 수 있는 기술적 기준을 세우는 데까지 확장해보고 싶다.