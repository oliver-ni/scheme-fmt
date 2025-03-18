import argparse
import sys
from dataclasses import dataclass
from itertools import tee
from typing import Callable, List, TypeVar, Union

T = TypeVar("T")


class SExpr(List[T]):
    BEGIN = "("
    END = ")"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        return f"({' '.join(map(str, self))})"


class QuotedSExpr(SExpr):
    BEGIN = "'("

    def __str__(self) -> str:
        return f"'{super().__str__()}"


class QuasiQuotedSExpr(SExpr):
    BEGIN = "`("

    def __str__(self) -> str:
        return f"`{super().__str__()}"


class UnquotedSExpr(SExpr):
    BEGIN = ",("

    def __str__(self) -> str:
        return f",{super().__str__()}"


class Comment:
    BEGIN = ";"
    END = "\n"

    def __init__(self, text) -> None:
        self.text = text


class TaggedExpr:
    def __init__(self, expr: Union[str, SExpr["TaggedExpr"] | Comment], start: int, end: int):
        self.inner = expr
        self.start_pos = start
        self.end_pos = end

    def __bool__(self):
        return bool(self.inner)

    def __eq__(self, value: object):
        return self.inner == value

    def __str__(self):
        return str(self.inner)


@dataclass
class FormatOptions:
    indent_seq: str = "  "


class ParserFormatter:
    DELIMETERS = (
        SExpr.BEGIN,
        QuotedSExpr.BEGIN,
        QuasiQuotedSExpr.BEGIN,
        UnquotedSExpr.BEGIN,
        SExpr.END,
        Comment.BEGIN,
        Comment.END,
    )

    def __init__(self, code: str, options: FormatOptions = FormatOptions()):
        self.code = code
        self.options = options
        self.pos = 0

    def cursor(self, length: int = 1):
        return self.code[self.pos : self.pos + length]

    def take(self, t: str):
        if self.cursor(len(t)) == t:
            self.pos += len(t)
            return t

    def take_until(self, f: Callable[[str], bool]):
        start_pos = self.pos
        while self.cursor():
            if f(self.cursor()):
                break
            self.pos += 1
        return self.code[start_pos : self.pos]

    def take_whitespace(self):
        return self.take_until(lambda s: not s.isspace())

    def take_token(self):
        for t in self.DELIMETERS:
            if self.take(t):
                return t
        return self.take_until(lambda s: s.isspace() or any(self.cursor(len(d)) == d for d in self.DELIMETERS))

    def parse_expr(self):
        self.take_whitespace()
        start_pos = self.pos
        t = self.take_token()

        for cls in (SExpr, QuotedSExpr, QuasiQuotedSExpr, UnquotedSExpr):
            if t == cls.BEGIN:
                expr = cls()
                break
        else:
            if t == Comment.BEGIN:
                text = self.take_until(lambda s: s == Comment.END)
                self.take(Comment.END)
                return TaggedExpr(Comment(text), start_pos, self.pos)
            else:
                return TaggedExpr(t, start_pos, self.pos)

        while True:
            elem = self.parse_expr()
            if elem is None or elem == expr.END:
                break
            expr.append(elem)

        if elem != expr.END:
            raise ValueError(f"Expected ')', found {elem!r}")

        return TaggedExpr(expr, start_pos, self.pos)

    def parse(self):
        yield from iter(self.parse_expr, "")

    def _fmt_expr(self, expr: TaggedExpr, indent: int):
        if isinstance(expr.inner, str):
            yield expr.inner
            return

        yield expr.inner.BEGIN

        if isinstance(expr.inner, Comment):
            yield expr.inner.text
            yield "\n"
            yield self.options.indent_seq * indent
            return

        last = ""

        if len(expr.inner) > 0:
            for last in self._fmt_expr(expr.inner[0], indent=indent + 1):
                yield last

        for prev, elem in zip(expr.inner, expr.inner[1:]):
            if "\n" in self.code[prev.end_pos : elem.start_pos]:
                yield "\n"
                yield self.options.indent_seq * (indent + 1)
            elif not last.isspace():
                yield " "
            for last in self._fmt_expr(elem, indent=indent + 1):
                yield last

        yield expr.inner.END

    def fmt_expr(self, expr: TaggedExpr):
        return "".join(self._fmt_expr(expr, 0))

    def fmt(self):
        exprs, exprs2 = tee(self.parse())
        yield self.fmt_expr(next(exprs2))
        for prev_expr, next_expr in zip(exprs, exprs2):
            yield self.code[prev_expr.end_pos : next_expr.start_pos].count("\n") * "\n"
            yield self.fmt_expr(next_expr)


if __name__ == "__main__":
    BOLD = "\033[1m"
    RESET = "\033[0m"
    BLUE = "\033[94m"

    parser = argparse.ArgumentParser(prog="scheme-fmt", description="Formats scheme code")
    parser.add_argument("--indent-with", choices=["tabs", "spaces"], default="spaces")
    parser.add_argument("--indent-size", type=int, default=2)
    parser.add_argument("files", nargs="+", type=argparse.FileType("r+"))
    args = parser.parse_args()

    indent_seq = "\t" if args.indent_with == "tabs" else " " * args.indent_size
    options = FormatOptions(indent_seq=indent_seq)
    num_fmt = len(args.files)

    for f in args.files:
        code = f.read()
        pf = ParserFormatter(code, options=options)
        result = "".join(pf.fmt()) + "\n"

        if f is sys.stdin:
            sys.stdout.write(result)
        elif code != result:
            f.seek(0)
            f.write(result)
            f.truncate()
            f.close()

        if code == result:
            num_fmt -= 1
        else:
            print(f"{BOLD}reformatted {f.name}{RESET}", file=sys.stderr)

    if num_fmt > 0:
        print(file=sys.stderr)

    print(f"{BOLD}All done!{RESET} ✨ 🍰 ✨", file=sys.stderr)

    def file(n: int):
        return f"file" if n == 1 else f"files"

    num_nofmt = len(args.files) - num_fmt
    fmt_text = f"{BOLD}{BLUE}{num_fmt}{RESET}{BOLD} {file(num_fmt)} reformatted{RESET}"
    nofmt_text = f"{BLUE}{num_nofmt}{RESET} {file(num_nofmt)} left unchanged"

    if num_fmt == 0 and num_nofmt == 0:
        print(f"{BOLD}No files given{RESET}.", file=sys.stderr)
    elif num_fmt == 0:
        print(nofmt_text, file=sys.stderr)
    elif num_nofmt == 0:
        print(fmt_text, file=sys.stderr)
    else:
        print(f"{fmt_text}, {nofmt_text}.", file=sys.stderr)
