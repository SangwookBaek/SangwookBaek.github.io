import mmap

from reader import read

with open("direct.bin", "rb") as file:
    with mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ) as mapped:
        index, binary = read(mapped)
        print(index["a"]["count"], index["d"]["count"])
        binary.release()
