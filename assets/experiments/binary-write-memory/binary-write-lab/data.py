import json

import numpy as np

from reader import CHUNK, HEADER

M = 1_000_000

arrays = {
    "a": np.arange(8 * M, dtype=np.uint32),
    "b": np.ones(24 * M, dtype=np.float32),
    "c": np.arange(8 * M, dtype=np.uint32),
    "d": np.ones(64 * M, dtype=np.uint32),
}

views = [memoryview(array).cast("B") for array in arrays.values()]

index = {}
offset = 0
for name, array in arrays.items():
    index[name] = {"dtype": array.dtype.name, "offset": offset, "count": len(array)}
    offset += array.nbytes
binary_length = offset

json_chunk = json.dumps(index).encode()

total = HEADER.size + CHUNK.size + len(json_chunk) + CHUNK.size + binary_length
