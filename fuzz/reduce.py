"""Delta-debugging reducer: shrink a failing input while it keeps failing the same way.

    python3 -m fuzz.reduce findings/MISMATCH/<id>/input.c --lexer ./lexer_asan
"""
import argparse
import os
import shutil
import sys
import tempfile

from fuzz import harness


def ddmin(items, fails, join, max_tests=5000):
    """Classic ddmin over a sequence (bytes or list of lines)."""
    tests = 0
    n = 2
    while len(items) >= 2:
        chunk = max(1, len(items) // n)
        parts = [items[i:i + chunk] for i in range(0, len(items), chunk)]
        reduced = False
        for i in range(len(parts)):
            cand = join([x for j, p in enumerate(parts) if j != i for x in p])
            tests += 1
            if tests > max_tests:
                return items
            if len(cand) and fails(cand):
                items = [x for j, p in enumerate(parts) if j != i for x in p]
                n = max(n - 1, 2)
                reduced = True
                break
        if not reduced:
            if n >= len(items):
                break
            n = min(len(items), n * 2)
    return items


def reduce_input(data, still_fails):
    cache = {}

    def f(b):
        if b not in cache:
            cache[b] = still_fails(b)
        return cache[b]

    lines = data.split(b"\n")
    lines = ddmin(lines, lambda b: f(b), lambda L: b"\n".join(L))   # pass 1: lines
    data = b"\n".join(lines)
    data = bytes(ddmin(list(data), lambda b: f(b), lambda L: bytes(L)))  # pass 2: bytes
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--lexer", default="./lexer_asan")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--out", help="where to write the reduced file (default: reduced.c next to input)")
    a = ap.parse_args()

    data = open(a.input, "rb").read()
    work = tempfile.mkdtemp(prefix="lexreduce-")
    status, detail, _, _ = harness.classify(data, a.lexer, work, a.timeout)
    if status in ("OK", "SKIP", "CLANGFAIL"):
        sys.exit("input does not fail (status %s) - nothing to reduce" % status)
    print("original: %d bytes, status %s (%s)" % (len(data), status, detail))

    def still_fails(b):
        return harness.classify(b, a.lexer, work, a.timeout)[0] == status

    small = reduce_input(data, still_fails)
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(a.input)), "reduced.c")
    with open(out, "wb") as f:
        f.write(small)
    shutil.rmtree(work, ignore_errors=True)
    print("reduced : %d bytes (%.1f%% smaller) -> %s" % (len(small), 100 * (1 - len(small) / max(1, len(data))), out))
    print("content : %r" % small)


if __name__ == "__main__":
    main()
