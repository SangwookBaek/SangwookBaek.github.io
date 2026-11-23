from reader import read

with open("direct.bin", "rb") as file:
    data = file.read()

index, binary = read(data)
print(index["a"]["count"], index["d"]["count"])
