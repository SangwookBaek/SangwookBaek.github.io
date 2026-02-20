---
title: FastAPI를 왜 쓸까?
date: 2025-04-03 22:52:00 +0900
author: oogie
categories: [Backend]
tags: [web,fastapi]     # TAG names should always be lowercase]
img_base: /assets/img/2025-04-03-why-fastapi
---

## TL;DR

FastAPI가 빠른 이유는 ASGI 기반의 uvicorn 위에서 비동기 처리를 지원하기 때문이다. Django는 풀스택이지만 비동기 지원이 제한적이고, FastAPI는 API 개발에 특화되어 Node.js/Go에 견줄 만한 속도를 낸다. Gunicorn + uvicorn worker 구조와 Python GIL의 관계까지 정리했다.

---

## Intro
이전 팀에서 Python Backend를 구성했고, 이때 FastAPI를 사용했습니다.  
그래서 이번에는 FastAPI의 장점이 뭔지, 왜그런 장점이 있는지를 정리해보겠습니다.

## FastAPI에 대해서

왜 FastAPI를 선택해서 이용하는가? FastAPI는 기본적으로 python [웹 프레임워크](https://sangwookbaek.github.io/posts/whatiswebapplication/)다.


이름부터 Fast라고 붙여놓은 이 프레임워크는 직관적이게도 속도가 빠른 것이 장점이다. 

속도가 빠른 이유는 무엇이고 속도가 빠르다는게 무엇과 비교했을 때 속도가 빠른 편이라는 것일까?

그리고 Django나 Flask 가 아니라 FastAPI를 쓰는 이유가 뭘까?

## 속도

속도는 2가지 측면에서 속도를 다룰 수 있는데

![다이어그램]({{ page.img_base }}/diagram.png)

1. 코드 작성의 편의성 : 이건 Pydantic 덕분
2. 실행 속도 : Node.js, GO랑 얼추 비슷한 속도라고 함 (ㄷㄷ..)
왜 이 속도가 Node.js랑 GO에 견주는 속도가 나올 수 있는가? 이건 비동기 프로그래밍을 Starlette을 통해서 구현하는데, Starlette이 uvicorn을 쓰기 때문임



![그래프]({{ page.img_base }}/compare.png)

### FastAPI 와 uvicorn

일단 uvicorn은 [WAS(Web application Server)](https://sangwookbaek.github.io/posts/whatiswebapplication/)의 일종임

그런데 이 중에서도 uvicorn은 비동기를 지원하는 WAS, ASGI(**Asyncronous Server Gateway Interface**)의 일종임. 이러한 uvicorn을 이용해서 web framework가 구동된다는 점에서 FastAPI가 강점을 가지게 됨.

**→ FastAPI는 직접적으로 비동기 처리를 지원하는 프레임워크임**

<aside>
💡

***FastAPI vs Django : 목적과 성능 측면에서 비교***

</aside>

대표적인 Python 웹 프레임워크 Django와 FastAPI, 왜 FastAPI를 선택했는지? 두개를 비교해보자면

`Django`는 풀스택 프레임워크이고 그쪽으로 기능이 치우쳐져 있음. 그래서 ORM, 템플릿 엔진, 인증 시스템 등을 싹 내장하고 있는 형태임 다만 비동기 지원이 제한되어있다는 점이 가장 큰 단점임 → 여기서 속도차이가 크게 발생

`FastAPI`는 이름부터 티가 나듯이 api 작성에 집중되어있는 프레임워크임. orm, 템플릿 엔진 등 기능이 없고 별도 라이브러리를 사용해야함(가령 SQLAlchemy를 써서 orm기능을 구현해야함). 
대신 비동기 프로그래밍을 지원해서 속도가 정말 빠르다는게 큰 장점임

당장 Django로 의존해서 풀스택 개발을 할 필요가 없다고 생각하고 FastAPI의 속도가 빠르고 그리고 개발 방식 자체가 더 현대적이고 좋다고 생각이 들어서 해당 프레임워크를 선택. 
그리고 RestfulAPI형식으로 작성이 편하다는 것도 선택의 이유 중 하나임

정리해보자면 FastAPI가 가장 큰 장점을 다른 프레임워크와 비교해서 가지고 있는 부분은 속도고 이 속도를 높이는데 큰 역할을 하는게 비동기처리임. 그리고 이 비동기를 가능하게 해주는게 uvicorn이라는 것임

그러면 uvicorn이 뭐고 어떤식으로 FastAPI와 맞물리는지 살펴봐야함

### uvicorn & gunicorn

일단 gunicorn은 WSGI에 속함 그럼에도 불구하고 비동기가 가능한 WAS임 그 이유는 uvicorn 워커를 이용하기 때문임. uvicorn worker는 ASGI이므로 비동기를 지원함

`Gunicorn`

- 앞 단에서 요청 수신 → worker 프로세스 생성
- 워커에 요청을 전달하여 처리
- 응답 데이터를 다시 클라이언트에 반환

`uvicorn worker`

- ASGI 애플리케이션 (여기선 FastAPI, Starlette : 비동기 프레임워크)을 실행하고요청 처리
- 이때 비동기 이벤트 루프를 통해 애플리케이션에 전달이 되고 → 비동기가 가능함

uvcorn은 libuv를 기반으로 cython으로 구현된 uvloop을 이용해서 이벤트루프를 구현함 

![uvicorn]({{ page.img_base }}/uvicorn_worker.png)

### python의 비동기성

그런데 여기서 새롭게 알게된 점이 Python은 원래 multi thread환경을 지원하지 않는다는 것임

근데 그러면 어떻게 비동기 환경을 제공할 수 있을가?

일단 Python은 race condition 방지를 위해 GIL을 이용함

`GIL(Global Interpreter Lock)`

파이썬은 gc를 기반으로 메모리를 관리함. 이때 reference count 기반 방법을 사용함.

그런데 당연하게도 count 시점은 Critical section임 → 이때 문제가 생길 수 있음

그래서 thread safe를 위해서 한 쓰레드만 cpu를 받아서 동작하게 함

 그래서 멀티 스레드를 하더라도 실질적으로 한 스레드만 수행되도록 만들어버림

결과적으로 멀티 프로세스 환경으로 가야지 비동기 프로그래밍이 가능해진다.

이게 uvicorn하고 맞물리면서 이제 진짜 비동기를 할 수 있게 되는 것임

근데 어쨋든 application 레벨에서 비동기 프레임워크를 지원해야하는데, FastAPI를 ASGI 인터페이스가 구현되어있는 starlette을 추상화해놓은 프레임워크이기 때문에 이게 가능하게 됨

## 최종 구조
![final_structure]({{ page.img_base }}/final_structure.png)
# 그래서 FastAPI를 왜 쓰냐?

정리해보면

1. 기존 python 프레임워크와 다르게 비동기처리를 지원하는 웹 프레임워크가 큰 장점임 그래서 속도도 굉장히 빠름. uvicorn을 사용하는 node.js와 비슷한 속도를 가지고 있음
2. 코드 작성 측면이 편리함. api 작성에 특화되어 있기도하고 pydantic + openapi 덕분


`출처`  
https://m.blog.naver.com/pjt3591oo/222772705407   
https://breezymind.com/start-asgi-framework/

