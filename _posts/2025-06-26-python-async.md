---
title: Python 비동기 프로그래밍(async)
date: 2025-6-27 00:00:00 +0900
author: oogie
categories: [backend,python]
tags: [async]     # TAG names should always be lowercase]
use_math: false
---


## Intro

python으로 백엔드 코드를 짜다보면 점점 많이 사용하게 문법이 `async,await`이다.

이는 목적만 놓고보면 python 내에서 비동기 프로그래밍을 할 수 있게한다.

비동기 프로그래밍을 구현하는 방법은 thread, multiprocess등 다양할 수 있다. 하지만 python의 async함수는 코루틴을 활용한다. 이 개념이 좀 복잡하고 중요하다보니 한번 정리해보고자 한다.

## 왜 써야하나?

목적 없는 기술은 의미가 없기 때문에, 비동기 프로그래밍을 사용하는 이유를 먼저 명확히 정리하고자 한다.

결론부터 말하면, **비동기 프로그래밍은 주로 파일(File) I/O나 네트워크(Network) I/O 등 I/O 작업이 많은(IO-intensive) 환경에서 활용된다.**

학부 운영체제 수업에서 스케줄러를 배우면, CPU-intensive한 작업과 I/O-intensive한 작업을 다루는 방법에 대해 들어본 적이 있을 것이다. 보통 I/O-intensive한 작업은 CPU를 계속 점유하지 않고 I/O 작업이 진행될 때 CPU를 다른 작업에 넘겨주는 방식으로 효율성을 높인다.

비동기 프로그래밍은 이 스케줄링 원리를 시스템 수준에서 자동으로 결정하는 것이 아니라, **프로그래머가 직접 컨트롤하여 작업이 실행될 시점을 명시적으로 정하고 CPU 점유를 효과적으로 관리할 수 있도록 해준다.**

즉, I/O-intensive한 작업을 비동기적으로 실행하면, 해당 작업이 I/O를 기다리는 동안 CPU가 다른 작업을 수행할 수 있도록 사용자가 직접 제어할 수 있다.

예를 들어 데이터베이스(DB)에서 데이터를 읽는 작업은 파일 I/O에 해당하고, API 호출이나 응답을 기다리는 작업은 네트워크 I/O에 해당하므로, 실제 프로덕션 환경에서 Python으로 백엔드를 작성하다 보면 자연스럽게 비동기 프로그래밍을 자주 활용하게 된다.

## Multiprocess & Thread

비동기 처리를 위한 기본적인 방법으로 `멀티프로세스(multiprocessing)`와 `멀티스레드(multithreading)`가 자주 언급된다.

- **멀티프로세스**는 프로세스를 여러 개 생성하여 병렬로 작업을 처리하는 방식으로, CPU-bound 작업에 적합하다.
- **멀티스레드**는 하나의 프로세스 안에서 여러 스레드를 만들어 실행하는 방식으로, 특히 I/O-bound 작업에서 유용하게 사용된다.

하지만 Python에서는 멀티스레딩이 제한적으로 동작한다. 이유는 뒤에서 설명할 GIL 때문이다.

Python에서는 여러 스레드를 만들어도 결국 한 번에 하나의 스레드만 실행되기 때문에, **진정한 병렬 처리는 멀티프로세스로 해야 한다.**

결과적으로 I/O 처리를 위한 경량 동시성 구조가 필요했고, Python에서는 이 역할을 **코루틴(coroutine)**으로 구현한다.

## Coroutine & event handler

Python에서 `async def`로 정의된 함수는 코루틴이다. 이 코루틴은 실제 함수처럼 바로 실행되는 것이 아니라, **“실행 계획서” 같은 객체**를 반환한다. 이 코루틴을 실제로 실행하려면 `await` 키워드를 통해 명시적으로 **이벤트 루프에 등록**해야 한다.

비동기 함수 내부에서 `await`를 만나면 해당 작업이 끝날 때까지 그 코루틴은 **일시 정지**되고, 이벤트 루프가 다른 코루틴으로 제어권을 넘긴다. 이를 통해 하나의 스레드에서도 여러 작업을 동시처럼 실행할 수 있다. 즉, **비동기 코드는 CPU 시간을 효율적으로 쓰기 위해, I/O 작업 동안 다른 일을 할 수 있도록 제어를 넘기는 구조**다.

코루틴은 컨텍스트 스위칭 비용이 거의 없고, 수천 개의 코루틴도 문제없이 스케줄링이 가능하다. 이런 특성 때문에 I/O 중심의 백엔드 작업에서는 멀티스레드보다 코루틴이 훨씬 적합하다.

## GIL(Global Interpreter Lock)

Python(CPython)의 GIL은 여러 스레드가 동시에 Python 바이트코드를 실행하지 못하게 막는 전역 락이다.

GIL이 존재하는 이유는 Python의 메모리 관리 방식 때문이다. Python은 모든 변수가 객체이며 heap에 할당되어 관리되고, 변수라는 것은 이러한 객체에 대한 포인터이다. 그래서 Python은 garbage collection을 통해서 이를 관리하는데 gc에서 참조 카운트 기반으로 객체를 관리하는데, 여러 스레드가 동시에 참조 카운트를 수정하면 레이스 컨디션이 발생할 수 있다는 것은 자명하다. 멀티프로세스가 아닌 스레드에서는 스택만 복사하고 힙섹션은 공유하기 때문에 레이스가 발생할 수 있다. 그래서 이를 막기 위해 GIL이 도입되었다.

결과적으로 Python의 멀티스레딩은 **병렬 처리에 적합하지 않다**. 여러 스레드를 만들어도 결국 한 번에 하나의 스레드만 GIL을 획득해서 실행되기 때문이다.

결국 CPU-bound 작업은 멀티스레드로 처리해도 효과가 없으며, 병렬성을 확보하려면 **멀티프로세싱**을 사용해야 한다.

하지만 I/O intensive job에서는 GIL이 큰 영향을 주지 않는다. Python은 I/O 작업 시 자동으로 GIL을 해제하기 때문에, 멀티스레딩으로도 일정 수준의 동시성을 확보할 수 있다.

다만 스레드는 생성과 컨텍스트 스위칭 비용이 크고 관리가 까다롭기 때문에, Python에서는 **코루틴 + 이벤트 루프 기반의 async 모델이 더 효율적으로 IO intensive job을 처리할 수 있다.**

## FastAPI vs Django

이제 백엔드 프레임워크에 비동기 개념을 어떻게 적용하는지를 살펴보자.

### FastAPI가 Django보다 빠른 이유는?

이미 이전에 FastAPI와 Django를 비교한 내용이 있다. 이를 다시 정리해본다.

FastAPI는 처음부터 `async/await` 기반으로 설계된 비동기 프레임워크이며,

ASGI(Asynchronous Server Gateway Interface) 표준 위에서 동작한다.

이로 인해 다음과 같은 장점이 있다:

| 항목 | FastAPI |
| --- | --- |
| 요청 처리 방식 | 비동기 이벤트 루프 기반, 다수의 요청을 코루틴으로 병렬 처리 |
| DB/API 호출 | await으로 비동기 처리 가능, 대기 시간 동안 CPU는 다른 요청 처리 |
| 서버 | 기본적으로 Uvicorn(ASGI) 사용, worker마다 독립 이벤트 루프 운용 |
| 성능 | 동시 요청 처리 효율이 높고, 처리량(QPS)도 우수 |

반면 Django는 전통적인 WSGI(Web Server Gateway Interface) 기반 프레임워크로 시작됐고,

`async` 기능은 Django 3.1버전부터 일부 추가됐지만 여전히 다음과 같은 제약이 있다:

| 항목 | Django |
| --- | --- |
| 요청 처리 방식 | 기본은 동기(Sync), 일부 async view만 지원 |
| ORM/미들웨어 | 대부분 동기 방식, 내부적으로 이벤트 루프 활용 불가 |
| 서버 | 기본은 Gunicorn + WSGI, 비동기 기능을 쓰려면 Daphne/Uvicorn 따로 설정 |
| 성능 | 동시 처리에서 성능 병목 발생 가능, 특히 I/O 대기시간이 많은 작업에 불리 |

> 즉, FastAPI가 Django보다 빠른 근본적인 이유는
> 
> 
> **비동기 이벤트 루프를 네이티브로 활용할 수 있도록 프레임워크 구조가 설계되어 있기 때문**이다.
> 

### FastAPI의 비동기 vs 기본 Python의 비동기

Python에서도 기본적으로 `async/await`, `asyncio`를 통해 비동기 처리를 구현할 수 있다.

하지만 FastAPI는 이 비동기 능력을 **백엔드 서버 처리 흐름 전반에 걸쳐 일관되게 통합**한 프레임워크다.

| 항목 | 기본 Python (`asyncio`) | FastAPI |
| --- | --- | --- |
| 용도 | 로우레벨 비동기 처리 (직접 이벤트 루프 관리 필요) | API 서버 구축에 최적화된 고수준 프레임워크 |
| 서버 | 없음 (직접 `asyncio.run()`으로 루프 실행) | Uvicorn 같은 ASGI 서버 내장 |
| 요청/응답 처리 | 직접 TCP/HTTP 레이어 구성해야 함 | HTTP 요청-응답 추상화 제공 (라우팅, 바인딩 등 포함) |
| DB 연동 | 직접 `asyncpg`, `aiomysql` 등 사용 | Pydantic, SQLModel 등과 함께 자연스럽게 연동 가능 |
| 구조 | 직접 코루틴 정의 + await | 요청 핸들러를 `async def`로 작성하면 자동 스케줄링 |

즉, **FastAPI는 Python의 기본 비동기 개념을 프레임워크 수준에서 실용적으로 통합한 형태**라고 보면 된다.

직접 `asyncio`를 사용하면 세밀한 제어는 가능하지만 코드가 복잡해지고 관리가 어려워진다.

반면 FastAPI는 이 복잡함을 추상화하면서도 `async/await`의 효율은 그대로 유지한다.

## Outro

비동기 프로그래밍은 백엔드 코드의 핵심적인 내용이고,Python으로 백엔드 코드를 작성하는 입장에서는

**스레드, 멀티프로세스, 코루틴 간의 차이**, 그리고 **GIL과의 관계**를 이해하는 것이 중요하다고 생각했다. 단순히 `async/await` 문법을 사용하는 것을 넘어서, **언제 비동기를 쓰는 게 의미가 있는지**, **Python에서 왜 코루틴 기반의 비동기를 사용하는지, FastAPI와 같은 비동기 친화적인 프레임워크가 어떤 장점을 가지는지**에 대해 정리해볼 수 있었다.