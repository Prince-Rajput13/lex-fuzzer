"""Input generation: edge-case corpus, mutation of seed text, token soup."""
import os
import random

EDGE_CASES = [
    # maximal munch
    "a+++++b", "a---b", "x>>=1;", "x<<=1;", "a->b", "a-->b", "a<<<b", "a>>>b",
    "a&&&b", "a|||b", "a...b", "a..b", "a.b", "x=-1", "x=+1", "x=--y", "a<:1:>",
    "<%%>", "%:define X", "%:%:", "#", "##", "# define X 1", "a##b",
    "<::", "::", ".*", "->*", "?:", "a?b:c", "!=", "!==", "===",
    # numbers (pp-numbers)
    "0x1fULL", "0X1F", "0b101", "017", "08", "1e+5f", "1E-5", "1e+", "1e", "0x", "0xg",
    "1.e3", ".5", ".5e+3", "1..2", "1.2.3e+4x", "0x1p-3", "0x1p+", "123abc", "1_000",
    "1'000", "1$2", "1u", "1ull", "1.f", "1.0L", "..5", "5..", "0.", "00", "9999999999999999999999",
    # identifiers
    "_", "__", "$a", "a$b", "x1y2", "u8", "u", "U", "L", "u8x", "Lx", "defined",
    # strings and chars
    '"abc"', '""', '"a\\"b"', '"a\\\\"', '"unterminated', '"unterminated\nx', "'a'", "''",
    "'ab'", "'\\''", "'\\\\'", "'unterminated", "'unterminated\nx", "L'x'", "u'x'", "U'x'",
    'L"x"', 'u"x"', 'U"x"', 'u8"x"', 'u8\'x\'', 'u8', '"\\', '"\\"', "'\\", '"a\\\nb"', "L", 'L"',
    'u8"', "'", '"',
    # comments
    "/* c */", "/**/", "/***/", "/*/", "/* unterminated", "/* a * b */", "/* a **/ b",
    "/* nested /* x */ */", "// line", "// line \\\ncontinued\nx", "//", "// \\", "a//b", "a/ /b",
    "a/**/b", "/*\n*/", "/* \\\n */", "*/", "/", "/ *", "//\r\nx", "/*\r\n*/x",
    # preprocessor-ish
    "#include <stdio.h>\n", '#include "a.h"\n', "#define F(x) #x\n", "#define G(a,b) a##b\n",
    "#if 1\n#endif\n", "#pragma once\n", "# \n", "#\\\n define X\n",
    # stray bytes and whitespace
    "@", "`", "\\", "a\\b", "\\\n", "a \\\n b", "a \\\r\n b", "a\f\vb", "a\r\nb", "\t\t",
    "\n\n\n", " ", "", "$", "a @ b", "x = @;", "\\\\\n",
]

TOKENS = [
    "a", "b", "foo", "_x", "$d", "int", "char", "while", "L", "u8", "U", "u",
    "0", "1", "42", "0x1f", "1.5", "1e+5", ".5", "1.", "0b1", "08", "1ull", "0x1p-3",
    '"s"', '""', '"a\\"b"', "'c'", "'\\n'", "L'x'", 'u8"s"',
    "(", ")", "[", "]", "{", "}", ";", ",", ".", "...", "->", "++", "--", "+", "-", "*", "/",
    "%", "&", "|", "^", "~", "!", "<", ">", "<<", ">>", "<=", ">=", "==", "!=", "&&", "||",
    "?", ":", "=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=", "#", "##",
    "<:", ":>", "<%", "%>", "%:", "%:%:", "@", "`", "\\",
    "/* c */", "// c\n", "/*", "*/", '"', "'",
]

SEPS = ["", "", "", " ", " ", "\n", "\t", "  "]
PUNCT_CHARS = list("+-*/%&|^~!<>=?:;,.#()[]{}\"'\\@`$_")
ALLOWED = set([9, 10, 11, 12, 13] + list(range(32, 127)))
MAX_LEN = 4096


def sanitize(b: bytes, wild: bool) -> bytes:
    if wild:
        return b[:MAX_LEN]
    return bytes(c if c in ALLOWED else 32 for c in b[:MAX_LEN])


class SeedPool:
    """Text snippets taken from real C/C++ files (any directory)."""

    EXT = (".c", ".h", ".cc", ".cpp", ".hpp", ".cxx", ".txt")

    def __init__(self, root, max_files=400, max_size=300_000):
        self.files = []  # list of lists of lines
        if root and os.path.isdir(root):
            for dp, _, fns in os.walk(root):
                for fn in sorted(fns):
                    if fn.endswith(self.EXT):
                        p = os.path.join(dp, fn)
                        try:
                            if os.path.getsize(p) <= max_size:
                                with open(p, "rb") as f:
                                    lines = f.read().split(b"\n")
                                if lines:
                                    self.files.append(lines)
                        except OSError:
                            pass
                    if len(self.files) >= max_files:
                        break
                if len(self.files) >= max_files:
                    break

    def chunk(self, rng, max_lines=20):
        if not self.files:
            return b"int main(void) { return 0; }\n"
        lines = rng.choice(self.files)
        n = rng.randint(1, max_lines)
        start = rng.randint(0, max(0, len(lines) - n))
        return b"\n".join(lines[start:start + n])


# ---- mutators --------------------------------------------------------------
def m_flip(rng, d):
    if not d:
        return d
    d = bytearray(d)
    for _ in range(rng.randint(1, 4)):
        d[rng.randrange(len(d))] = ord(rng.choice(PUNCT_CHARS))
    return bytes(d)


def m_delete(rng, d):
    if len(d) < 2:
        return d
    i = rng.randrange(len(d))
    j = min(len(d), i + rng.randint(1, 8))
    return d[:i] + d[j:]


def m_insert_tok(rng, d):
    i = rng.randint(0, len(d))
    return d[:i] + rng.choice(TOKENS).encode() + d[i:]


def m_dup(rng, d):
    if len(d) < 2:
        return d
    i = rng.randrange(len(d))
    j = min(len(d), i + rng.randint(1, 16))
    return d[:j] + d[i:j] + d[j:]


def m_swap(rng, d):
    if len(d) < 4:
        return d
    i, j = sorted(rng.sample(range(len(d)), 2))
    d = bytearray(d)
    d[i], d[j] = d[j], d[i]
    return bytes(d)


def m_truncate(rng, d):
    return d[:rng.randint(0, len(d))]


def m_edge(rng, d):
    i = rng.randint(0, len(d))
    return d[:i] + rng.choice(EDGE_CASES).encode() + d[i:]


MUTATORS = [m_flip, m_delete, m_insert_tok, m_dup, m_swap, m_truncate, m_edge]


def mutate(rng, d, rounds=None):
    for _ in range(rounds or rng.randint(1, 4)):
        d = rng.choice(MUTATORS)(rng, d)
    return d


def token_soup(rng, n=None):
    n = n or rng.randint(2, 40)
    out = []
    for _ in range(n):
        out.append(rng.choice(TOKENS))
        out.append(rng.choice(SEPS))
    return "".join(out).encode()


class Generator:
    def __init__(self, rng, pool, wild=False):
        self.rng, self.pool, self.wild = rng, pool, wild

    def edge_cases(self):
        for e in EDGE_CASES:
            yield ("edge", sanitize(e.encode("latin-1"), self.wild))

    def make(self):
        r = self.rng.random()
        if r < 0.50:
            return ("mutated", sanitize(mutate(self.rng, self.pool.chunk(self.rng)), self.wild))
        if r < 0.80:
            return ("soup", sanitize(token_soup(self.rng), self.wild))
        if r < 0.90:
            return ("seed", sanitize(self.pool.chunk(self.rng), self.wild))
        e = self.rng.choice(EDGE_CASES).encode("latin-1")
        return ("edge+mut", sanitize(mutate(self.rng, e), self.wild))
