---
title: Apache Arrow를 이용해서 데이터 빨리 읽기
date: 2025-04-03 13:59:00 +0900
author: oogie
categories: [Data_engineering]
tags: [apache_arrow]     # TAG names should always be lowercase]
---

## Intro
movie lens 데이터에 대해서 추천시스템 예제 코드를 보고 재구현 하던 중 데이터를 읽어오는 부분이 너무 느려서 답답함을 느꼈고  
pandas로 써져있는걸 보고 일단 이것부터 수정해야겠다는 생각을 했고 수정하는 과정과 수정환 결과를 공유하려고 합니다.


## Dask 와 Apache Arrow
pandas의 대안으로 **Dask** 와 **Apache Arrow** 2가지를 고려했습니다.
  
Dask는 병렬 분산 데이터 처리를 지원하는 모듈로 알고 있고 대규모 데이터를 처리할 때 안정적이고 빠르게 수행할 수 있는 것이 장점입니다.
  
Apache Arrow는 column wise 메모리 접근을 한다는 것이 특징이고 데이터 직렬화/역직렬화 없이 빠른 IO를 수행하는 것이 장점입니다.

이는 어디까지나 이론으로 알고있던거고 실제 코드로 전환하면서 생긴 시행착오랑 장단점을 정리해보려고 합니다.   

전체 코드는 해당 [링크](https://github.com/SangwookBaek/RecommenderSytems_Introduction/blob/main/utils/data_loader.py)에서 확인할 수 있습니다.  
데이터 로딩 중 병목이 걸리는 부분은 Dataloader._load() 이고 이 부분을 Dask와 pyarrow 기반으로 수정했습니다.   
그리고 나머지 예시 코드들과의 호환성을 위해서 Dataloader.load()함수의 return값은 기존의 pandas dataframe이 되도록 설정했습니다. 이 부분에서 병목이 발생할 수 있지만 예시 코드 호환성과 가독성을 위해서 기존 포맷을 유지했습니다.


## Dask로 전환
Dask의 장점은 분산처리가 된다는 것이고 pandas와 거의 동일한 형식을 가지고 있다는 것입니다. 그래서 기존 코드를 그대로 재활용해서 Dask로 전환하는 것은 어렵지 않을 것이라 예상했습니다. 그런데 생각보다 코드 변환에서 오류가 문제가 많았고 Dask는 적절한 선택이 아니었습니다.    
결론부터 말하자면 movie data, tag data는 pandas로, rating data만 Dask로 읽어오는 구조로 만들었습니다.

### 데이터 크기와 작업 특성에 따른 선택

평점 데이터(ratings)는 일반적으로 매우 큰 데이터셋이라 Dask의 병렬 처리 능력이 유용합니다.  
영화 정보(movies)와 태그(tags)는 상대적으로 작은 데이터셋이므로 Pandas로 처리하는 것이 더 효율적입니다.


### Dask의 제한사항

Dask는 모든 Pandas 연산을 완벽하게 지원하지 않습니다. 특히 복잡한 groupby 연산이나 rank 같은 연산은 Dask에서 정확하게 구현하기 어려울 수 있는 것 같습니다.
사용자별 최신 평가 항목을 찾는 작업 같은 경우, 각 사용자의 모든 데이터를 한 번에 볼 수 있어야 정확한 결과가 나오는데, Dask의 분산 특성 때문에 이런 작업에는 한계가 있다는걸 알았습니다



## pyarrow로 전환
pyarrow은 다음과 같은 특징을 같다.
- Columnar Format
- zero - copy IO
- 직렬화/역직렬화 없이 바로 IO 가능 


### Columnar Format
시스템의 메모리를 배우다보면 row major / column major 접근을 배울 수 있다.  메모리를 row를 기준으로 연속적일지, column을 기준으로 연속적일지에 대한 내용이다.   
그런데 보통은 row major를 사용하는데 apache arrow에서는 columnar format을 왜 이용하고 결과적으로 왜 빠를까?


100개의 row, 20개의 column으로 구성된 panda dataframe을 numpy or pytorch로 처리하는 과정을 생각해보자.  

- dataframe에서 특정 열에 접근한다.(e.g.  rating , etc)   
    -  pandas에서는 row 단위로 저장이 되어있다. age가 rating이 3번째 column이라면 100개의 rating을 접근하려면 [0][2],[1][2],...,[99][2]를 접근해야한다.
    - row major에서 메모리 access를 찍어보면 
    start +0 x 20(num_columns) x size_of_column + 2 * size_of_row  
    start +1 x 20(num_columns) x size_of_column + 2 * size_of_row  
    start +2 x 20(num_columns) x size_of_column + 2 * size_of_row  
    ...   
    start +99 x 20(num_columns) x size_of_column + 2 * size_of_row    
    와 같이 접근하는데, 이것은 일단 cache affinity가 낮기 때문에 느리다.
- 이를 ndarray나 torch.tensor로 바꾼다. 그리고 연산을 수행한다.
    - ndarray나 torch.tensor로 바꾸기 위해서는 **copy**가 발생한다.
    - ndarray와 tensor는 뽑힌 값들을 row로 가지게 됩니다. 간단히 생각하면 column단위로 저장 및 접근했던게 array로 바뀌면 row 단위로 저장 및 접근할 수 있게 되는 것이다.
    - 하나의 메모리에서 이걸 할 수 없으니까 따로 **copy**가 발생함 -> 느려짐

정리하자면 row wise 접근에서 column 단위로 데이터를 뽑아 다시 row 단위의 배열로 변환시켜 처리하는 과정이 굉장히 느릴 수 밖에 없습니다.

--- 
Apache Arrow -> numpy or torch.tensor를 봐보면 
- dataframe에서 특정 열에 접근한다.(e.g.  rating , etc)   
    -  pandas에서는 row 단위로 저장이 되어있다. age가 rating이 3번째 column이라면 100개의 rating을 접근하려면 [0][2],[1][2],...,[99][2]를 접근해야한다.
    - row major에서 메모리 access를 찍어보면 
    start + 2(column index) x size_of_row + 0 * size_of_column  
    start + 2(column index) x size_of_row + 1 * size_of_column  
    start + 2(column index) x size_of_row + 2 * size_of_column  
    ...   
    start + 2(column index) x size_of_row + 99 * size_of_column   
    와 같이 접근하는데, 보면 size_of_column만큼만 증가한다. 애초에 memory 상에서 continuous하게 존재할 것이기 때문에 cache affinity가 매우 높고 빠를 수 밖에 없다.
- 이를 ndarray나 torch.tensor로 바꾼다. 그리고 연산을 수행한다.
    - apache arrow를 통해 처리한 값을 column으로 접근하지만, 그 저장은 row로 되어있습니다. 그래서 별도의 copy없이 이 값을 바로 indexing/처리합니다.

정리하자면 columnar 접근을 하기 때문에 dataframe에서 열단위로 데이터를 뽑고 처리할 때 메모리 접근 자체 속도도 빠르고 별도의 copy가 생기지 않는게 장점입니다.



추가로 직렬화/역직렬화가 필요없다는 것은 저장할 때 python 고유 메모리 양식이 아니라 C++, Java 등에서 쓸 수 있는 공통 메모리 양식으로 저장하기 때문에 이를 변환하는 직렬화 및 역직렬화가 필요없다는 의미이다.
(python 라이브러리로만 활용하면 이 부분은 의미가 없는것으로 보임)

## 속도 비교
pandas, dask, apache arrow기반으로 코드를 작성했고 속도를 비교해봤습니다.

+ pandas : 23.2337초
+ dask : 24.2178초
+ apache arrow :**2.3696초**

이론대로 apache arrow가 미친듯이 빠른 속도를 냈습니다.

dask가 pandas보다 느린 이유에 대해서 생각해봤는데, dask는 결국 대용량 데이터를 멀티 인스턴스로 **안정적**으로 처리하는데 장점이 있는거지 속도를 빠르게 해주지는 않는게 당연하더라구요.  
분산처리 준비를 하는 과정 (task graph 생성 등)에서 오버헤드가 걸리고 lazy evaluation방식을 쓰는데 무슨 처리를 하냐에 따라 병목이 발생하면 한방에 메모리에 올려서 처리하는 pandas보다 느릴 수 밖에 없더라구요.

`요약`  
- dask : 대규모 데이터에 대한 병렬분산 처리를 제공 / 중규모에서는 오버헤드 때문에 오히려 느릴 수 있고 병렬처리 특성상 지원하지 못하는 연산도 있음
- apache arrow : columnar기반의 저장으로 cache affinity가 높고 직렬화/역직렬화가 필요없으며 zero copy라는 특징이 있음

|항목|pandas|dask|apache arrow|
|------|---|---|---|
|주요 역할|단일 머신에서 데이터 분석|병렬 분산 데이터 처리|메모리 내 데이터 포맷 (표준화된 컬럼 기반 구조)|
|속도|작고 중간 크기 데이터에 빠름|대용량 데이터에 적합 (병렬 처리)|데이터 직렬화/역직렬화 없이 빠른 I/O 가능|
|주요 사용|분석, 시각화, 전처리|대용량 데이터 전처리, ETL, ML pipeline|데이터 교환, zero-copy I/O, cross-language 처리|