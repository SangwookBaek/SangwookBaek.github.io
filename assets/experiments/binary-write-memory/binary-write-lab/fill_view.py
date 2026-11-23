from data import json_chunk, total, views
from reader import CHUNK, HEADER

buffer = bytearray(total)
target = memoryview(buffer)
offset = HEADER.size + CHUNK.size + len(json_chunk) + CHUNK.size
for view in views:
    target[offset : offset + view.nbytes] = view
    offset += view.nbytes
