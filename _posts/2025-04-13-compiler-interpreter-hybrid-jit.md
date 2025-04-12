---
title: 프로그래밍 언어 구동 방식 - 컴파일러,인터프리터, 하이브리드,JIT
date: 2025-04-13 01:22:00 +0900
author: oogie
categories: [Compter_System]
tags: [computer_system]     # TAG names should always be lowercase]
---
# Intro

하드웨어는 개발할 때 사용하는 high level language(e.g. C, Python, Java, JavaScript)를 직접적으로 이해하지 못한다. 하드웨어가 직접 이해하고 실행할 수 있는 언어는 기계어 밖에 없다. 

그러면 어떤 방식으로 우리가 고안한 프로그램을 실행시킬 수 있을까?

이와 관련된 4가지 방식 컴파일러, 인터프리터, 하이브리드, JIT에 대해서 정리해본다.

# 컴파일러(Compiler)

하드웨어는 기계어만 실행할 수 있고, 우리가 쓴 언어는 high level language라는 것이 문제 상황이다.

이럴 때 생각할 수 있는 가장 직관적이고 효과적인 방법은 high level language를 기계어로 변환하는 것이다.

결국 모든 high level language는 기계어에서 시작된 것들이고 기계어로 변환/구현할 수 있다.

```c
int main() {
    int a, b, c;
    a = 0;
    b = 0;
    c = a + b;
    return 0;
}
```

```nasm
main:
    push    rbp
    mov     rbp, rsp
    sub     rsp, 16         
    mov     DWORD PTR [rbp-4], 0     
    mov     DWORD PTR [rbp-8], 0     
    mov     eax, DWORD PTR [rbp-4] 
    add     eax, DWORD PTR [rbp-8]  
    mov     DWORD PTR [rbp-12], eax  
    mov     eax, 0
    leave
    ret
```

위에서 보인 + 같은 사칙연산 외에 array indexing, 행렬곱 등의 연산도 모두 기계어로 변환할 수 있다.

그리고 이러한 과정(high level code → machine instruction code)를 compile이라 한다.

그리고 이러한 역할을 수행하는 것이 컴파일러다.

대표적으로 C,C++가 이방법으로 실행된다.

## 정리

```text
[소스코드]
    ↓ (파싱)
[AST 생성]
    ↓ (컴파일)
[기계어(.exe, .out) 생성]
    ↓
[운영체제 또는 CPU가 직접 실행]
```

실행 전에 모든 코드가 기계어로 컴파일됨

## 장점

압도적으로 빠르다. 한번 컴파일하면 하드웨어가 해당 코드를 바로 실행하기 때문에 속도가 굉장히 빠르다.

## 단점

- flexibility 가 낮다
→ type binding이 컴파일때 이루어지기 때문에 코드 상에서 type을 정의해야하고 그래서 dynamic feature에 대응이 어려워서 flexibility가 낮다.
- 개발 시간이 느리다
    
    → 개발자의 역량이긴한데, 기본적으로 코드를 테스트하는데 빌드 과정이 계속 포함되어야하므로 개발 속도가 느릴 수 있다.
    

# 인터프리터

인터프리터는 코드를 실행하는 소프트웨어인데, 인터프리터를 사용하는 언어는 코드를 기계어로 번역하지 않는다.

하지만 인터프리터는 일종의 하드웨어 simulation 이기 때문에 high level 코드를 읽고 실행할 수 있다.

근데 그러면 한가지 의문이 든다. “실행”이라는건 하드웨어가 한다. 그런데 어떻게 소프트웨어가 high level 코드를 읽고 “실행”이라는걸 할 수 있을까?? 

이건 인터프리터의 내부 구현을 살펴봐야한다.

## 인터프리터의 내부 구현

위 질문의 답은 인터프리터의 대부분이 C언어로 작성되어있다는데 있다.

인터프리터는 C언어로 작성되고 C언어를 컴파일한 소프트웨어이다.

그래서 인터프리터 안에는 C언어로 구현하고 기계어로 작성된 함수들이 준비되어있다.

`예시`

python, 그리고 python 인터프리터 중 Cpython을 예시로 들어보자

python에서 print를 작성해놓고 호출한다.

```python
print("hello world")
```

CPython안에는 이 print라는 함수와 매치되는 C언어 기반의 함수 PyObject_Print라는 것을 작성되어 있다.

```c

int PyObject_Print(PyObject *obj, FILE *fp, int flags) {
    // 객체를 문자열로 변환하고 출력
}
```

그러면 Cpython기반의 인터프리터가 print(”hello world”)를 읽고 PyObject_Print라는 함수를 실행한다.

이때 작성은 C로 되어있지만 이를 빌드하여 기계어로 작성된 함수를 실행하게 된다.

---

즉, python의 각 기능에 매치되도록 C언어로 파일을 작성하고, 이를 컴파일하면 → 인터프리터가 만들어진다.

```bash
gcc -o python main.c ceval.c ...
```

인터프리터(위에서는 python)를 이용하여 코드를 실행시키는 것이 우리가 사용하던 python명령의 의미이다.

```bash
python(인터프리터를 실행시키는 명령어) hello.py(대상 파일)
```

## 정리

```text
[소스코드]
    ↓ (줄 단위 해석)
[인터프리터가 직접 해석]
    ↓
[구문 단위로 실행 (eval)]
    ↓
[C 함수 호출 / 시스템 호출]
    ↓
[기계어 실행 by OS/CPU]
```

요약해보자면 인터프리터는 

1. C언어로 작성된, 그리고 기계어로 컴파일된 다양한 기능(함수)들을 가지고 있는 소프트웨어다.
2. 이 소프트웨어가 high level 코드를 한줄 한줄 읽고
3. 읽은 코드와 매치되는 기능(함수)를 찾아 실행한다.

대표적으로 python,JavaScript, Ruby,Bash 가 이방법으로 실행된다.

## 장점

- 컴파일 없이 바로 실행이 가능하고 그래서 디버깅이 쉽다. 그리고 개발속도가 빠르다
- 동적 실행을 잘 대처한다

## 단점

- 실행속도가 너무 느리다 : 결국 한줄한줄 eval을 해야하기 때문에 굉장히 느리다.
- 최적화가 불가능 : 정적 분석을 할 수 없으므로 최적화가 불가능함
- 런타임 오류가 많다 : 컴파일단계가 없기때문에 런타임에서 에러가 발생하기 쉽다

# 하이브리드

이름부터 유추할 수 있듯이 하이브리드는 컴파일과 인터프리터를 섞어놓은 방법이다.

대표적으로 Java가 있다. 그런데 현대의 python을 포함한 인터프리터 언어들이 대부분의 인터프리터 언어들은 하이브리드 방식으로 구현되고 있다.

그럼 어떤 점이 interpreter언어와 다른지 확인해보자

## 한줄 한줄 읽어 실행한다?? - AST,ByteCode

인터프리터 언어를 얘기할 때 모두가 하는 얘기가 코드를 한줄 한줄 읽는다는 것이다.

근데 당장 정말 단순한 if / for loop / function을 실행시켜도 한줄 한줄 읽어서 실행한다는 것은 어색하다.

대부분의 프로그램들이 필요로하는 control flow가 그렇게 단순하지 않기 때문이다.

그러면 한줄 한줄 읽고 실행한다는 것의 실체는 무엇일까?

### `AST(Abstract Syntax Tree)`

AST란 소스코드를 **구문 분석**해서 복잡한 flow를 표현한 만든 **트리 구조이다.**

이때 각 노드는 변수, 연산자, 함수 호출 등 코드의 구문 요소를 의미한다. 이들의 관계를 기계가 이해할 수 있는 트리형태로 표현하는 것이다.

```python
x = 3 + 4
```

```text
Assignment
 ├── Variable(x)
 └── BinaryOperation(+)
     ├── Constant(3)
     └── Constant(4)
```

```python
if x > 10:
    print("hi")
else:
    print("bye")
```

```text
If
 ├── Test: Compare(>)
 │     ├── Name(x)
 │     └── Const(10)
 ├── Body:
 │     └── Expr(Call(print, Const("hi")))
 └── Orelse:
       └── Expr(Call(print, Const("bye")))
```

```python
for i in range(3):
    print(i)
```

```text
For
 ├── Target: Name(i)
 ├── Iter: Call(Name(range), Const(3))
 └── Body:
      └── Expr(Call(print, Name(i)))

```

정리해보자면 high level language를 미리 모두 읽어 문법/구문 분석을 진행하며 AST라고 하는 구문 단위의 트리로 변환 시킨다. 

그리고 이렇게 만들어진 구문 단위의 트리가 인터프리터 실행의 최소 단위이다.

즉, 이 트리가 “한줄한줄 실행시킨다”의 한줄이 된다.

### ByteCode

AST의 정보는 구조 중심이지 실행 중심이 아니다.

이말을 쉽게 이해하려면 우리가 실행하는 코드는 반드시 위에서 아래로 sequential하게 흐른다는 것을  생각하면 된다.

Tree는 인간의 눈으로 보기에는 이미 충분한 정보가 있지만 기계가 이해하기에는 복잡하고 실행 불가능한 구조이다. 이를 명령어 줄 단위의 sequence로 바꾸는 과정이 필요한데, 이 명령어 줄 단위가 ByteCode이다.

```text
Assignment
 ├── Variable(x)
 └── BinaryOperation(+)
     ├── Constant(3)
     └── Constant(4)
```

```text
LOAD_CONST 3
LOAD_CONST 4
BINARY_ADD
STORE_NAME x
```

위 예시를 보면 AST를 명령어 중심으로 풀어서 sequence of codes로 바꿔줬는데 , 이 과정이 컴파일이고, 이 과정이 있기 때문에 이 방식을 하이브리드 방식이라 부른다.

참고로 python에서 ByteCode를 직접 확인할 수 있는데 아래 코드를 실행하면 된다.

```python
code = compile("x = 3 + 4", "<string>", "exec")
print(code.co_code)  # bytecode 출력 가능
'''
b'\x97\x00d\x00Z\x00d\x01S\x00' -> opcode인데 이거 번역하면 아래와 같이 나옵니다
  0           0 RESUME                   0
  1           2 LOAD_CONST               0 (7)
              4 STORE_NAME               0 (x)
              6 LOAD_CONST               1 (None)
              8 RETURN_VALUE
code = compile("x = 3 + 4", "<string>", "exec")
dis.dis(code)
이렇게 하면 디코딩도 해주는것 같네요
'''
```

참고로 ByteCode는 Opcode로 작성되어있다.

`Opcode(Operation Code)` 

Opcode는 간단히 말해, 특정 연산을 수행하라는 명령어 코드이다.

처음 Opcode를 배우면, 대개 이게 **CPU에서 직접 실행되는 하드웨어 명령어**라고 이해하게 된다.

그렇다면 이런 의문이 생긴다:

> “어? 하드웨어 명령어라면 굳이 인터프리터를 거칠 필요 없이, 그냥 바로 실행하면 되는 거 아닌가?”
> 

하지만 실제로 우리가 Python이나 Java 같은 언어에서 말하는 **Opcode는 CPU용 명령어가 아니다.**

이것은 **가상 머신(Virtual Machine)** 전용의 Opcode이며,

실제 하드웨어(CPU)가 직접 이해할 수 있는 **기계어와는 전혀 다른 계층**에 속한다.

---

그렇다면 왜 굳이 이런 별도의 Opcode(바이트코드)를 만들었을까?

그 이유는 바로 **플랫폼 독립성과 유연성 확보**에 있다.

즉, 소스코드를 하드웨어에 종속된 기계어로 변환하지 않고, 중간 단계인 바이트코드(opcode)로 변환함으로써,

어떤 플랫폼에서도 해당 플랫폼에 맞는 인터프리터(혹은 가상 머신)만 존재하면 동일한 코드를 실행할 수 있다.

이러한 구조 덕분에 인터프리터 언어는 컴파일 언어와는 달리 **높은 이식성(platform independence)**과 **런타임 유연성(runtime flexibility)**을 갖게 된다.

---

그리고 이 부분이 바로 **컴파일러 언어와 인터프리터 언어의 가장 큰 차이점**이라고 생각한다.

두 방식 모두 `AST(Abstract Syntax Tree)`까지는 동일하게 생성하지만,

컴파일러는 이후 **기계어로 번역**하고,

인터프리터 언어는 `바이트코드(opcode)`로 변환한 후,

그 바이트코드를 인터프리터가 한 줄씩 읽어가며 실행한다.

즉, 바이트코드까지만 놓고 보면 플랫폼에 독립적인 공통된 구조를 갖고 있고,

**플랫폼에 맞는 인터프리터만 있으면 실행이 가능**하다.

## 다시 인터프리터

앞서 인터프리터는 high level code를 한줄한줄 읽고 그에 매칭되는 C언어 기능을 호출하는 것이라 했다.

hybrid방식에서는 한줄 한줄 읽는 코드가 해당 언어가 아닌 bytecode이고, 이것에 매치되는 기능을 호출한다.

```c
for (;;) {
    opcode = NEXTOP();      // 다음 opcode를 가져옴
    switch (opcode) {
        case LOAD_CONST:
            PUSH(consts[oparg]);
            break;
        case BINARY_ADD:
            x = POP();
            y = POP();
            PUSH(x + y);
            break;
        ...
    }
}
```

위는 CPython의 ceval.c 파일 속 eval loop 코드를 가져온 것이다.

보면 opcde를 한줄씩 뽑고 각 명령어 별로 기능을 수행하는 것을 확인할 수 있다.

이때 opcode를 읽고 eval하는 것이 high level code를 읽고 eval하는 것보다 훨씬 빠르기에 일반 인터프리터보다 성능 면에서 장점이 있다.

## 정리

```text
[소스코드]
    ↓ (파싱)
[AST 생성]
    ↓ (컴파일)
[Bytecode 생성 (.pyc 등)]
    ↓
[Interpreter (eval loop)]
    ↓
[Opcode 하나씩 해석 실행]
    ↓
[C 함수 호출 → 기계어 실행]
```

정리해보면 hybrid 방식이란, 

1. 코드 전체를 문법/구문 분석을 해서 AST로 만듦
2. AST를 컴파일해서 ByteCode를 생성함
3. Interpreter가 이 ByteCode를 줄 단위로 읽으면서 실행

## 장점

- 인터프리터 언어의 장점인 이식성과 유연성 확보
- 컴파일처럼 전체 코드를 한 번에 파싱 → 바이트코드로 변환하기 때문에 실행 속도도 빠름
- Bytecode → Eval 실행은 줄 단위 해석보다 빠르다 → 일반적인 인터프리터보다 더 나은 성능을 가짐

## 단점

- 바이트코드 해석이 결국 느림
- 정적 분석이 어려워서  바이트코드 최적화를 결국 하지는 못함

# JIT(Just-in-Time)컴파일

현대 언어 실행 구조의 핵심 중 하나임 

대표적으로 Java 언어가 JIT 방식을 사용하고 있고 Javascript(V8), python,.NET등에서 사용하기 시작함

기본적인 컨셉은 캐싱과 비슷함

> ***프로그램을 실행하는 도중(런타임 중)에 필요한 코드만 선택적으로 기계어로 컴파일함***
> 

hybrid 방식에서의 컴파일은 기계어 컴파일이 아닌 Bytecode 컴파일이었지만, 

JIT 에서의 컴파일은 기계어 컴파일을 의미한다. 

그래서

- 컴파일 언어처럼 기계어를 활용해 실행속도가 빠름
- 인터프리터처럼 즉시 실행 가능 + 유연함

→ 어떻게 보면 진짜 하이브리드 방식

## JIT 알고리즘 전략

`Method-based JIT`

자주 호출되는 함수/메서드를 통째로 컴파일해버림

`Tracing JIT` 

바이트코드를 실행시킬 때, 루프나 함수가 반복 실행되면 실행 경로를 기록

그리고 그 경로만 기계어로 컴파일해서 실행

> Tracing JIT의 대표적인 예시가 pypy3이다.
백준을 풀다보면 python3가 아닌 pypy3를 써야 시간 제한을 맞추는 경우가 종종있을텐데 이제 그 이유에 대해서 알 수 있게 되었다. 
반복문이 많은 알고리즘 문제 특성 상 python3(cpython)인터프리터보다 pypy3가 많이 유리한 것이다.
> 

`Tiered JIT`

다단계 JIT 컴파일 전략으로 가장 현대적인 방식임

코드 실행을 여러 tier로 나누어서 점진적으로 빠르고 정교하게 최적화하는 방식

```
1단계: 인터프리터로 먼저 실행 (가볍고 빠른 시작)
  ↓
2단계: 자주 실행되는 코드 감지 (hot code)
  ↓
3단계: Baseline JIT → 단순한 native code로 변환
  ↓
4단계: 최적화 JIT → 인라이닝, 루프 풀기, escape analysis 등 적용
  ↓
5단계: 필요 시 deopt (되돌리기) 후 다시 컴파일
```

| 언어 | 대표 JIT 엔진 | 전략 | 특징 |
| --- | --- | --- | --- |
| Java | HotSpot JIT | Tiered JIT | 메서드 단위로 점진적 최적화 |
| JavaScript | V8 (TurboFan) | Tiered JIT | 인터프리터 → 고급 최적화기 |
| Python | PyPy | Tracing JIT | 루프 기반 최적화. trace 따라 컴파일 |
| .NET | CLR JIT (RyuJIT) | Method + Tiered JIT | AOT와 혼합 가능 |
| Ruby | YJIT / MJIT | Lazy Basic Block JIT | 실행 블록만 컴파일 (점진적) |

## 정리

```text
[소스코드]
    ↓ (파싱)
[AST]
    ↓ (컴파일)
[Bytecode]
    ↓
[Interpreter 실행 시작]
    ↓
[반복적 실행 감지 → JIT 작동!]
    ↓
[해당 코드 → 기계어로 컴파일]
    ↓
[기계어로 직접 실행 🔥 빠름!]
```

JIT는 기존 하이브리드 인터프리터 방식에서 반복적으로 인터프리팅하는 부분을 컴파일함

그리고 이 컴파일된 코드는 캐시처럼 메모리에 저장되어서 빠르게 수행됨

다만 캐시와 마찬가지로 구현 전략이 다양할 수 있음

## 장점

- 컴파일의 빠른 실행 속도
- 인터프리터의 유연함

## 단점

- JIT 컴파일시간이 좀 걸려서 초기 warm up이 있음
- 컴파일 코드가 메모리에 있기 때문에 메모리 사용량이 증가함

# Outro

사실 컴파일언어 인터프리터언어에 대해서 아주 대충만 알고 있었는데 인터프리터에 대해서 low level구현까지 알아볼 수 있어서 흥미로웠다.

이 내용을 정리하면서 생긴 새로운 궁금증은

1. python의 기본적인 연산자들이 작동하는 방법은 이해했음
numpy, pytorch 같은 외부라이브러리를 import해서 사용할때는 어떻게 작동하는가??
2. 기계어라는 것도 결국 ALU, 즉 cpu에 대한 얘기이다.
그렇다면 더 나아가 코드로 gpu를 실행시키는 것은 어떻게 하는 것일까?
3. pypy3는 아주 기본적인 tracing기반의 JIT를 사용한다. 
그런데 pypy3같은 인터프리터 레벨이 아니라 numba, pytorch의 compiler등 코드레벨에서도 compile옵션을 제공하는 경우가 늘어나고 있는에 이들의 작동 원리는 무엇일까??

시간이 나면 다음에 이 주제들에 대해서 다뤄보고싶다.