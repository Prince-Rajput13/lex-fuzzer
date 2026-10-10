%option noyywrap nounput noinput 8bit
%{
#include <stdio.h>
#include <stdlib.h>

static void emit(const char *kind)
{
    fputs(kind, stdout);
    fputc('\t', stdout);
    for (int i = 0; i < yyleng; i++) {
        unsigned char c = (unsigned char)yytext[i];
        if (c == '\\')
            fputs("\\\\", stdout);
        else if (c < 0x20 || c > 0x7e)
            printf("\\x%02x", c);
        else
            fputc(c, stdout);
    }
    fputc('\n', stdout);
}
%}

ID      [A-Za-z_$][A-Za-z0-9_$]*
SPFX    (u8|u|U|L)
CPFX    (u|U|L)
PUNCT   "["|"]"|"("|")"|"{"|"}"|"."|"->"|"++"|"--"|"&"|"*"|"+"|"-"|"~"|"!"|"/"|"%"|"<<"|">>"|"<"|">"|"<="|">="|"=="|"!="|"^"|"|"|"&&"|"||"|"?"|":"|";"|"..."|"="|"*="|"/="|"%="|"+="|"-="|"<<="|">>="|"&="|"^="|"|="|","|"#"|"##"|"<:"|":>"|"<%"|"%>"|"%:"|"%:%:"|"::"

%%

[ \t\r\n\f\v]+                                   { /* whitespace */ }
\\(\r\n|\n\r|\r|\n)                               { /* line splice between tokens */ }

"//"([^\n\r\\]|\\(\r\n|\n\r|\r|\n)|\\.|\\)*                    { /* line comment (continued by backslash-newline) */ }
"/*"([^*]|\*+[^*/])*\*+"/"                       { /* block comment */ }
"/*"([^*]|\*+[^*/])*\**                          { emit("ERROR"); /* unterminated block comment */ }

{SPFX}?\"([^"\\\n\r]|\\.|\\\n)*\"                  { emit("STR"); }
{SPFX}?\"([^"\\\n\r]|\\.|\\\n)*\\?                 { emit("ERROR"); /* unterminated string */ }

{CPFX}?\'\'                                       { emit("ERROR"); /* empty char constant */ }
{CPFX}?\'([^'\\\n\r]|\\.|\\\n)+\'                  { emit("CHR"); }
{CPFX}?\'([^'\\\n\r]|\\.|\\\n)*\\?                 { emit("ERROR"); /* unterminated char constant */ }

\.?[0-9]([eEpP][+-]|[0-9A-Za-z_.])*             { emit("NUM"); }
{ID}                                             { emit("ID"); }
{PUNCT}                                          { emit("PUNCT"); }

.|\n                                             { emit("ERROR"); /* stray byte */ }

%%

int main(int argc, char **argv)
{
    if (argc > 1) {
        yyin = fopen(argv[1], "rb");
        if (!yyin) {
            perror(argv[1]);
            return 2;
        }
    }
    yylex();
    if (argc > 1)
        fclose(yyin);
    return 0;
}
