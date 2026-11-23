import mmap

from reader import read

with open("direct.bin", "rb") as file:
    data = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)

index, binary = read(data)
print(index["a"]["count"], index["d"]["count"])
