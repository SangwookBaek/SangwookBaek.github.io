from data import binary_length, json_chunk, total, views
from reader import BINARY, CHUNK, HEADER, JSON

buffer = bytearray(total)
HEADER.pack_into(buffer, 0, b"DEMO", 1, total)
offset = HEADER.size
CHUNK.pack_into(buffer, offset, JSON, len(json_chunk))
offset += CHUNK.size
buffer[offset : offset + len(json_chunk)] = json_chunk
offset += len(json_chunk)
CHUNK.pack_into(buffer, offset, BINARY, binary_length)
offset += CHUNK.size
for view in views:
    buffer[offset : offset + view.nbytes] = view
    offset += view.nbytes
result = bytes(buffer)

with open("naive.bin", "wb") as file:
    file.write(result)
