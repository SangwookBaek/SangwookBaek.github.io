import json
import struct

HEADER = struct.Struct("<4sIQ")
CHUNK = struct.Struct("<IQ")
JSON, BINARY = 0, 1


def read(data):
    magic, version, total = HEADER.unpack_from(data, 0)
    if total != len(data):
        raise ValueError("file length mismatch")
    chunks = {}
    offset = HEADER.size
    while offset < total:
        kind, length = CHUNK.unpack_from(data, offset)
        chunks[kind] = (offset + CHUNK.size, length)
        offset += CHUNK.size + length
    start, length = chunks[JSON]
    index = json.loads(data[start : start + length])
    start, length = chunks[BINARY]
    return index, memoryview(data)[start : start + length]
