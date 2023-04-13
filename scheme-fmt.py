import argparse
import sys
from dataclasses import dataclass
from itertools import pairwise
from typing import Callable, TypeVar

T = TypeVar("T")


class SExpr(list[T]):
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


class TaggedExpr:
    def __init__(self, expr: str | SExpr["TaggedExpr"], start_pos: int, end_pos: int):
        self.inner = expr
        self.start_pos = start_pos
        self.end_pos = end_pos

    def __bool__(self):
        return bool(self.inner)

    def __eq__(self, value: object):
        return self.inner == value


@dataclass
class FormatOptions:
    indent_seq: str = "  "


class ParserFormatter:
    DELIMETERS = SExpr.BEGIN, QuotedSExpr.BEGIN, SExpr.END

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
        return self.take_until(
            lambda s: s.isspace()
            or any(self.cursor(len(d)) == d for d in self.DELIMETERS)
        )

    def parse_expr(self):
        self.take_whitespace()
        start_pos = self.pos

        match self.take_token():
            case SExpr.BEGIN:
                expr = SExpr()
            case QuotedSExpr.BEGIN:
                expr = QuotedSExpr()
            case t:
                return TaggedExpr(t, start_pos, self.pos)

        while elem := self.parse_expr():
            if elem == expr.END:
                break
            expr.append(elem)

        if elem != expr.END:
            raise ValueError(f"Expected ')', found {elem!r}")

        return TaggedExpr(expr, start_pos, self.pos)

    def parse(self):
        while expr := self.parse_expr():
            yield expr

    def _fmt_expr(self, expr: TaggedExpr, indent: int):
        if isinstance(expr.inner, str):
            yield expr.inner
            return

        yield expr.inner.BEGIN

        if len(expr.inner) > 0:
            yield from self._fmt_expr(expr.inner[0], indent=indent + 1)

        for prev, elem in pairwise(expr.inner):
            if "\n" in self.code[prev.end_pos : elem.start_pos]:
                yield "\n"
                yield self.options.indent_seq * indent
            else:
                yield " "
            yield from self._fmt_expr(elem, indent=indent + 1)

        yield expr.inner.END

    def fmt_expr(self, expr: TaggedExpr):
        return "".join(self._fmt_expr(expr, 0))

    def fmt(self):
        for expr in self.parse():
            yield self.fmt_expr(expr)


if __name__ == "__main__":
    BOLD = "\033[1m"
    RESET = "\033[0m"
    BLUE = "\033[94m"

    parser = argparse.ArgumentParser(
        prog="scheme-fmt", description="Formats scheme code"
    )
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
        result = "\n\n".join(pf.fmt()) + "\n"

        if code == result:
            num_fmt -= 1
            continue

        out_f = sys.stdout if f is sys.stdin else f
        out_f.seek(0)
        out_f.write(result)
        out_f.truncate()

        if out_f is not sys.stdout:
            out_f.close()

        print(f"{BOLD}reformatted {f.name}{RESET}", file=sys.stderr)

    if num_fmt > 0:
        print(file=sys.stderr)

    print(f"{BOLD}All done!{RESET} ✨ 🍰 ✨", file=sys.stderr)

    def file(n: int):
        return f"file" if n == 1 else f"files"

    num_nofmt = len(args.files) - num_fmt
    fmt_text = f"{BOLD}{BLUE}{num_fmt}{RESET}{BOLD} {file(num_fmt)} reformatted{RESET}"
    nofmt_text = f"{BLUE}{num_nofmt}{RESET} {file(num_nofmt)} left unchanged"

    match num_fmt, num_nofmt:
        case 0, 0:
            print(f"{BOLD}No files given{RESET}.")
        case 0, _:
            print(nofmt_text)
        case _, 0:
            print(fmt_text)
        case _, _:
            print(f"{fmt_text}, {nofmt_text}.")
