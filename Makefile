CC      ?= gcc
CFLAGS  ?= -O1 -g -Wall -Wno-unused-function
SAN     := -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer

all: lexer lexer_asan

lex.yy.c: lexer.l
	flex -o $@ $<

lexer: lex.yy.c
	$(CC) $(CFLAGS) -o $@ $<

# Sanitizer build used by the fuzzer: ASan + UBSan, abort on first finding
lexer_asan: lex.yy.c
	$(CC) $(CFLAGS) $(SAN) -o $@ $<

# Coverage build (gcov); see `make coverage`
lexer_cov: lex.yy.c
	$(CC) -O0 -g --coverage -o $@ $<

# Quick smoke run of the whole pipeline
test: all
	python3 -m fuzz.harness --lexer ./lexer_asan --iters 2000 --seed 1

# Run the fuzzer on the coverage build and print gcov line coverage for lexer.l
coverage: lexer_cov
	rm -f *.gcda *.gcov
	python3 -m fuzz.harness --lexer ./lexer_cov --iters 3000 --seed 1 --jobs 1
	gcov -o . lexer_cov-lex.yy.gcda > /dev/null || true
	@grep -E "^ *[0-9#-]+:" lexer.l.gcov 2>/dev/null | awk -F: '{c=$$1; gsub(/ /,"",c); if (c=="#####") miss++; else if (c!="-") hit++} END {printf "lexer.l line coverage: %d/%d = %.1f%%\n", hit, hit+miss, 100*hit/(hit+miss)}'

clean:
	rm -f lexer lexer_asan lexer_cov lex.yy.c *.gcda *.gcno *.gcov

.PHONY: all test coverage clean
