"""Turn both tools' output into the same comparable token list.

Comparable form: list of (kind, escaped_lexeme) where
  kind in {ID, NUM, STR, CHR, PUNCT, ERROR}
Whitespace and comments are dropped on both sides.
"""
import re

WS = " \t\n\r\f\v"

# Clang token kind -> our kind (anything not listed is punctuation)
CLANG_KIND = {
    "raw_identifier": "ID",
    "identifier": "ID",
    "numeric_constant": "NUM",
    "string_literal": "STR",
    "wide_string_literal": "STR",
    "utf8_string_literal": "STR",
    "utf16_string_literal": "STR",
    "utf32_string_literal": "STR",
    "char_constant": "CHR",
    "wide_char_constant": "CHR",
    "utf8_char_constant": "CHR",
    "utf16_char_constant": "CHR",
    "utf32_char_constant": "CHR",
    "unknown": "ERROR",
}

# one line of `-dump-raw-tokens`:  kind 'lexeme'<TAB> [flags]<TAB>Loc=<...>
CLANG_RE = re.compile(r"^(\w+) '(.*?)'\t((?: \[.*?\])*)\tLoc=<[^>\n]*>$", re.M | re.S)


def esc(raw: str) -> str:
    """Same escaping as emit() in lexer.l. `raw` is a latin-1 decoded str."""
    out = []
    for ch in raw:
        c = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif c < 0x20 or c > 0x7E:
            out.append("\\x%02x" % c)
        else:
            out.append(ch)
    return "".join(out)


def parse_ours(stdout: bytes):
    toks = []
    for line in stdout.decode("latin-1").split("\n"):
        if not line:
            continue
        kind, _, lex = line.partition("\t")
        toks.append((kind, lex))
    return toks


def parse_clang(stderr: bytes):
    """Return token list, or None if the input contains a backslash-newline
    splice *inside* a token (Clang reports the cleaned spelling there, which we
    deliberately do not model)."""
    text = stderr.decode("latin-1")
    toks = []
    for m in CLANG_RE.finditer(text):
        kind, lex, flags = m.group(1), m.group(2), m.group(3)
        if "UnClean" in flags:
            return None
        if kind in ("comment", "eof"):
            continue
        if kind == "unknown" and lex.strip(WS) == "":
            continue  # whitespace
        toks.append((CLANG_KIND.get(kind, "PUNCT"), esc(lex)))
    return toks


def fmt(tokens):
    return "".join("%s\t%s\n" % t for t in tokens)


def first_diff(a, b):
    """Index of the first differing token (or the shorter length)."""
    for i, (x, y) in enumerate(zip(a, b)):
        if x != y:
            return i
    return min(len(a), len(b))
