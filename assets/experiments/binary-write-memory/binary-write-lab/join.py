from data import binary_length, json_chunk, total, views
from reader import BINARY, CHUNK, HEADER, JSON

pieces = [
    HEADER.pack(b"DEMO", 1, total),
    CHUNK.pack(JSON, len(json_chunk)),
    json_chunk,
    CHUNK.pack(BINARY, binary_length),
    *views,
]
result = b"".join(pieces)

with open("join.bin", "wb") as file:
    file.write(result)
