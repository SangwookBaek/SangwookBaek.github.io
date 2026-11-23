# binary-write-lab

헤더, JSON 청크, 바이너리 청크로 이루어진 파일을 쓰고 읽을 때 프로세스의 최대 메모리를 비교한 실험이다.

## 준비

```console
$ python -m venv .venv
$ .venv/bin/pip install numpy
```

측정 환경은 Python 3.12.13, NumPy 2.5.5, macOS 26.5.1 (Apple M5)였다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `reader.py` | 헤더·청크 구조체와, 버퍼 전체를 받아 해석하는 reader |
| `data.py` | 크기가 다른 배열 네 개(합계 416MB)와 JSON 청크 |
| `baseline.py` | 배열만 만든다 |
| `naive.py` | `bytearray`를 채운 뒤 `bytes`로 바꿔 쓴다 |
| `fill_only.py` | `bytearray`를 채우는 단계만 실행한다 |
| `fill_view.py` | `bytearray`의 `memoryview`에 채운다 |
| `join.py` | 조각 목록을 `b"".join`으로 합쳐 쓴다 |
| `direct.py` | 조각을 파일에 순서대로 쓴다 |
| `read_all.py` | 파일 전체를 읽어 reader에 넘긴다 |
| `read_mmap.py` | `mmap`으로 열어 reader에 넘긴다 |
| `read_mmap_part.py` | `mmap`으로 연 뒤 200MB 구간을 4KB 간격으로 읽는다 |
| `read_mmap_close.py` | 원소 개수를 읽고 view를 해제한 뒤 `mmap`을 닫는다 |

## 측정

macOS에서는 `/usr/bin/time -l`이 프로세스의 최대 RSS를 바이트 단위로 출력한다.

```console
$ /usr/bin/time -l .venv/bin/python naive.py 2>&1 | grep -E 'real|maximum resident'
```

Linux에서는 `/usr/bin/time -v`의 `Maximum resident set size`를 보면 되고, 단위는 KB다.

읽기 스크립트는 `direct.py`가 만든 `direct.bin`을 읽으므로 `direct.py`를 먼저 실행해야 한다. 스크립트 하나가 416MB 파일을 만든다.
