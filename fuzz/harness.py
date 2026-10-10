"""Fuzz harness: run the lexer on generated inputs and classify every result.

Statuses
  OK         lexer output equals Clang's raw tokens, no crash, no sanitizer report
  MISMATCH   token streams differ (the interesting differential-testing result)
  CRASH      lexer killed by a signal (SIGSEGV, SIGABRT, ...)
  SANITIZER  ASan / UBSan / LSan report on stderr
  TIMEOUT    lexer did not finish in time (hang / infinite loop)
  EXITCODE   lexer exited with a non-zero status without a sanitizer report
  SKIP       input not comparable (backslash-newline splice inside a token)
  CLANGFAIL  Clang itself failed or timed out (not counted as a lexer bug)
"""
import argparse
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from fuzz import gen, normalize

SAN_MARKERS = (b"AddressSanitizer", b"LeakSanitizer", b"UndefinedBehaviorSanitizer", b"runtime error")
CLANG_CMD = ["clang", "-Xclang", "-dump-raw-tokens", "-fsyntax-only", "-x", "c"]


def sanitizer_env(leaks):
    env = dict(os.environ)
    env["ASAN_OPTIONS"] = "detect_leaks=%d:abort_on_error=0:symbolize=1" % (1 if leaks else 0)
    env["UBSAN_OPTIONS"] = "print_stacktrace=1:halt_on_error=1"
    return env


def classify(data, lexer, workdir, timeout=5, use_clang=True, leaks=False):
    """Run one input. Returns (status, detail, ours_tokens, clang_tokens)."""
    fd, path = tempfile.mkstemp(suffix=".c", dir=workdir)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        try:
            r = subprocess.run([lexer, path], capture_output=True, timeout=timeout,
                               env=sanitizer_env(leaks))
        except subprocess.TimeoutExpired:
            return "TIMEOUT", "lexer exceeded %ss" % timeout, None, None
        if r.returncode < 0:
            return "CRASH", "killed by signal %d" % -r.returncode, None, None
        if any(m in r.stderr for m in SAN_MARKERS):
            first = next((l for l in r.stderr.decode("latin-1").splitlines()
                          if "ERROR" in l or "runtime error" in l), "sanitizer report")
            return "SANITIZER", first.strip(), None, None
        if r.returncode != 0:
            return "EXITCODE", "exit status %d: %s" % (r.returncode, r.stderr[:200].decode("latin-1")), None, None
        ours = normalize.parse_ours(r.stdout)
        if not use_clang:
            return "OK", "", ours, None
        try:
            c = subprocess.run(CLANG_CMD + [path], capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            return "CLANGFAIL", "clang timeout", ours, None
        ref = normalize.parse_clang(c.stderr)
        if ref is None:
            return "SKIP", "backslash-newline splice inside a token", ours, None
        if ours == ref:
            return "OK", "", ours, ref
        i = normalize.first_diff(ours, ref)
        a = ours[i] if i < len(ours) else "<end of tokens>"
        b = ref[i] if i < len(ref) else "<end of tokens>"
        return "MISMATCH", "token #%d: ours=%s clang=%s" % (i, a, b), ours, ref
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def save_finding(outdir, status, data, detail, ours, ref):
    h = hashlib.sha1(data).hexdigest()[:10]
    d = os.path.join(outdir, status, h)
    if os.path.exists(d):
        return False
    os.makedirs(d)
    with open(os.path.join(d, "input.c"), "wb") as f:
        f.write(data)
    with open(os.path.join(d, "detail.txt"), "w") as f:
        f.write(detail + "\n")
    if ours is not None:
        with open(os.path.join(d, "ours.txt"), "w") as f:
            f.write(normalize.fmt(ours))
    if ref is not None:
        with open(os.path.join(d, "clang.txt"), "w") as f:
            f.write(normalize.fmt(ref))
    return True


def clang_version():
    try:
        return subprocess.run(["clang", "--version"], capture_output=True, text=True).stdout.splitlines()[0]
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lexer", default="./lexer_asan", help="lexer binary (use the sanitizer build)")
    ap.add_argument("--iters", type=int, default=2000, help="random inputs (edge cases are always run first)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--seed-dir", default="corpus", help="directory of C/C++ files to mutate (e.g. /usr/include)")
    ap.add_argument("--out", default="findings")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--no-clang", action="store_true", help="only crash/hang/sanitizer checks")
    ap.add_argument("--leaks", action="store_true", help="enable LeakSanitizer")
    ap.add_argument("--wild", action="store_true", help="allow arbitrary bytes (NUL, UTF-8) in inputs")
    a = ap.parse_args()

    if not os.path.exists(a.lexer):
        sys.exit("lexer binary %s not found - run `make` first" % a.lexer)

    rng = random.Random(a.seed)
    g = gen.Generator(rng, gen.SeedPool(a.seed_dir), a.wild)
    inputs = list(g.edge_cases()) + [g.make() for _ in range(a.iters)]
    os.makedirs(a.out, exist_ok=True)
    work = tempfile.mkdtemp(prefix="lexfuzz-")
    counts, by_gen, new_unique = Counter(), Counter(), Counter()
    total_tokens = 0
    t0 = time.time()

    def job(item):
        label, data = item
        st, detail, ours, ref = classify(data, a.lexer, work, a.timeout, not a.no_clang, a.leaks)
        return label, data, st, detail, ours, ref

    done = 0
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        for label, data, st, detail, ours, ref in ex.map(job, inputs):
            counts[st] += 1
            by_gen[(label, st)] += 1
            if ours:
                total_tokens += len(ours)
            if st not in ("OK", "SKIP", "CLANGFAIL"):
                if save_finding(a.out, st, data, detail, ours, ref):
                    new_unique[st] += 1
            done += 1
            if done % 500 == 0:
                print("  %d/%d ..." % (done, len(inputs)), file=sys.stderr)
    shutil.rmtree(work, ignore_errors=True)

    secs = time.time() - t0
    summary = {
        "inputs": len(inputs), "seed": a.seed, "seconds": round(secs, 1),
        "lexer": a.lexer, "clang": clang_version(),
        "tokens_compared": total_tokens, "results": dict(counts),
        "unique_findings_saved": dict(new_unique),
    }
    with open(os.path.join(a.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print("\n=== fuzz summary (%s, seed %d) ===" % (summary["clang"], a.seed))
    print("inputs: %d   tokens compared: %d   time: %.1fs" % (len(inputs), total_tokens, secs))
    for st in ("OK", "MISMATCH", "CRASH", "SANITIZER", "TIMEOUT", "EXITCODE", "SKIP", "CLANGFAIL"):
        if counts[st]:
            extra = ("   (%d unique saved in %s/%s/)" % (new_unique[st], a.out, st)) if new_unique[st] else ""
            print("  %-10s %6d%s" % (st, counts[st], extra))
    bad = sum(counts[s] for s in ("MISMATCH", "CRASH", "SANITIZER", "TIMEOUT", "EXITCODE"))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
