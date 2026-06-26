import sys

if len(sys.argv) != 3:
    print("Usage: calculate.py <previous_price> <current_price>", file=sys.stderr)
    sys.exit(2)

p, c = map(float, sys.argv[1:3])
if p <= 0:
    print("previous_price must be greater than 0", file=sys.stderr)
    sys.exit(2)

print(f"{max(0, (c - p) / p * 100):.1f}%")
