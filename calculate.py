import sys

p, c = map(float, sys.argv[1:3])
print(f"{max(0, (c - p) / p * 100):.1f}%")
