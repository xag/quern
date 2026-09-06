"""quern.expr — the rule grammar as an object: compile it, run it, ask what it reads.

A rule's `expr` used to be a string a caller could only run, and only by handing it
to `run_rules`. Everything else an adopter wanted to know about one had to be
recovered from the source text or from this parser while it was private, and four
of them did exactly that (#44): one imported the private `_tokenize`/`_parse_or`
and froze them by pin, one recovered an expression's `ctx()` keys by regex, one
read a numeric bound back out with another regex, and two fabricated a staged copy
of a tree with a one-rule rule list just to evaluate an expression that was sitting
in a payload. So the grammar is its own module now, and it does three things in
public:

- `compile_expr(src)` parses once into an immutable `Expr`. It is cached by source
  text, so a rule bound to a thousand nodes is parsed once rather than a thousand
  times — the same call that used to reparse per node.
- `Expr.evaluate(env, variables)` runs it against an environment (build a tree's
  with `quern.tree.rule_env`) and a variable binding. `Expr.trace(...)` runs it and
  also hands back every call it made — the function, the arguments, the value it
  returned (#52). A red is only actionable with the values behind it, and those
  come from the evaluator that produced the answer, never from a second pass over
  the same grammar by whoever is reporting it.
- `Expr.reads` says what the source names before anything runs at all: the
  functions it calls, the free identifiers it expects bound, the literal `ctx()`
  keys it will ask for, and the numbers and strings it carries. A daemon staging a
  context knows what to put in it; a checker reading a limit rule reads the limit.

Two things every adopter patched back in are here rather than there: `true` and
`false` are literals instead of names that must be bound in every environment, and
an integer literal stays an integer instead of arriving as a float.

`and` and `or` evaluate BOTH sides, as this grammar always has. Short-circuiting
would change what existing rules answer — an expression whose right half raises
today goes red, and would silently go green — so it is a change to make on its own
evidence, not a side effect of moving the parser into a module.

Safety is unchanged, and is the point of a grammar this small: no eval, no attribute
access, no indexing, and no way to name anything the environment was not handed.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Iterator, NamedTuple

from pydantic import BaseModel, Field

# --- the parsed form ----------------------------------------------------------
#
# Five term kinds, immutable, and public: a consumer that wants something this
# module's own inspection does not offer walks them rather than re-parsing.


class Lit(NamedTuple):
    """A literal: a number, a string, or a boolean."""
    value: Any


class Var(NamedTuple):
    """A free identifier — a name the evaluation's `variables` must bind."""
    name: str


class Call(NamedTuple):
    """A call to one of the environment's functions, with its argument terms."""
    fn: str
    args: tuple[Any, ...]


class Unary(NamedTuple):
    """`not x` or `-x`."""
    op: str
    operand: Any


class Binary(NamedTuple):
    """Two operands and an operator: arithmetic, comparison, `and`, `or`."""
    op: str
    left: Any
    right: Any


Term = Lit | Var | Call | Unary | Binary


class Read(BaseModel):
    """One call an evaluation made, as data: the function, the arguments it was
    given, and the value it returned.

    This is what turns a red into a finding somebody can act on. `ok=False` says a
    rule did not hold; a list of these says what it saw — which param, at which
    path, holding what — so a report names values instead of asking its reader to
    re-run the sub-expressions and hope they read them the same way."""

    call: str
    args: list[Any] = Field(default_factory=list)
    value: Any = None


class Reads(NamedTuple):
    """What an expression names, read off the source without running it.

    `functions` and `names` are sorted and deduplicated — they are sets of what must
    be available. `ctx_keys` is the literal string argument of every `ctx(...)`
    call, which is what a caller must stage in the evaluation context before a tick
    can be attempted at all; a `ctx()` called on a computed name contributes nothing
    here, because there is nothing to state. `numbers` and `strings` stay in source
    order, because the interesting thing about a literal is usually where it sits:
    the bound in `said_words(self) <= 300` is the number, and it is data now instead
    of something to regex back out."""

    functions: tuple[str, ...]
    names: tuple[str, ...]
    ctx_keys: tuple[str, ...]
    numbers: tuple[float, ...]
    strings: tuple[str, ...]


class Expr:
    """One compiled expression: its source, its parsed term, and what it reads.

    Immutable and safe to share — `compile_expr` caches by source text and hands the
    same object to every caller, so nothing here may be mutated."""

    __slots__ = ("source", "term", "_reads")

    def __init__(self, source: str, term: Term) -> None:
        self.source = source
        self.term = term
        self._reads: Reads | None = None

    def __repr__(self) -> str:
        return f"Expr({self.source!r})"

    @property
    def reads(self) -> Reads:
        """What the source names, computed once and kept."""
        if self._reads is None:
            self._reads = _static_reads(self.term)
        return self._reads

    def evaluate(self, env: dict[str, Any], variables: dict[str, Any] | None = None,
                 reads: list[Read] | None = None) -> Any:
        """Run against `env` (name -> callable) and `variables` (name -> value).

        `reads` is a list this appends a `Read` to for every call made, in the order
        they were made. Pass one when the trace must survive an exception — what was
        read before a rule blew up is most of the diagnosis — and use `trace()` when
        only the trace of an evaluation that finished is wanted."""
        return _run(self.term, env, variables or {}, reads)

    def trace(self, env: dict[str, Any], variables: dict[str, Any] | None = None,
              ) -> tuple[Any, list[Read]]:
        """`(value, reads)` — the answer, and every call that produced it."""
        reads: list[Read] = []
        return _run(self.term, env, variables or {}, reads), reads


@lru_cache(maxsize=1024)
def compile_expr(src: str) -> Expr:
    """Parse `src` into an `Expr`. Raises ValueError on a malformed expression.

    Cached by source text: the same string compiles once per process. That is what
    makes a rule bound to every node of a kind cost one parse instead of one per
    node, and it is safe because an `Expr` is immutable."""
    tokens = _tokenize(src)
    term, pos = _parse_or(tokens, 0)
    if pos != len(tokens):
        raise ValueError(f"unexpected '{tokens[pos][1]}'")
    return Expr(src, term)


def evaluate_expr(src: str, env: dict[str, Any],
                  variables: dict[str, Any] | None = None,
                  reads: list[Read] | None = None) -> Any:
    """Compile and run in one call — the shape the checker itself uses."""
    return compile_expr(src).evaluate(env, variables, reads)


# --- evaluation ---------------------------------------------------------------

_COMPARE = {"<": lambda a, b: a < b, "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b, ">=": lambda a, b: a >= b,
            "==": lambda a, b: a == b, "!=": lambda a, b: a != b}


def _run(term: Term, env: dict[str, Any], variables: dict[str, Any],
         reads: list[Read] | None) -> Any:
    if isinstance(term, Lit):
        return term.value
    if isinstance(term, Var):
        if term.name in variables:
            return variables[term.name]
        raise ValueError(f"unknown name '{term.name}'")
    if isinstance(term, Call):
        fn = env.get(term.fn)
        if fn is None:
            raise ValueError(f"unknown function '{term.fn}'")
        args = [_run(a, env, variables, reads) for a in term.args]
        value = fn(*args)
        if reads is not None:
            reads.append(Read(call=term.fn, args=args, value=value))
        return value
    if isinstance(term, Unary):
        operand = _run(term.operand, env, variables, reads)
        return (not bool(operand)) if term.op == "not" else -operand
    left = _run(term.left, env, variables, reads)
    right = _run(term.right, env, variables, reads)
    op = term.op
    if op in _COMPARE:
        return _COMPARE[op](left, right)
    if op == "and":
        return bool(left) and bool(right)
    if op == "or":
        return bool(left) or bool(right)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    return left / right


# --- inspection ---------------------------------------------------------------

def _walk(term: Term) -> Iterator[Term]:
    yield term
    if isinstance(term, Call):
        for a in term.args:
            yield from _walk(a)
    elif isinstance(term, Unary):
        yield from _walk(term.operand)
    elif isinstance(term, Binary):
        yield from _walk(term.left)
        yield from _walk(term.right)


def _static_reads(term: Term) -> Reads:
    functions: set[str] = set()
    names: set[str] = set()
    ctx_keys: list[str] = []
    numbers: list[float] = []
    strings: list[str] = []
    for t in _walk(term):
        if isinstance(t, Call):
            functions.add(t.fn)
            if (t.fn == "ctx" and t.args and isinstance(t.args[0], Lit)
                    and isinstance(t.args[0].value, str)):
                ctx_keys.append(t.args[0].value)
        elif isinstance(t, Var):
            names.add(t.name)
        elif isinstance(t, Lit):
            if isinstance(t.value, str):
                strings.append(t.value)
            elif isinstance(t.value, (int, float)) and not isinstance(t.value, bool):
                numbers.append(t.value)
    return Reads(functions=tuple(sorted(functions)), names=tuple(sorted(names)),
                 ctx_keys=tuple(dict.fromkeys(ctx_keys)),
                 numbers=tuple(numbers), strings=tuple(strings))


# --- tokenizer and parser -----------------------------------------------------

def _tokenize(src: str) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    i = 0
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
        elif c.isdigit() or (c == "." and i + 1 < len(src) and src[i + 1].isdigit()):
            j = i
            while j < len(src) and (src[j].isdigit() or src[j] == "."):
                j += 1
            text = src[i:j]
            # An integer literal stays an integer: the adopters that needed one
            # patched the float-only tokenizer, and nothing here wants the coercion.
            out.append(("num", float(text) if "." in text else int(text)))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < len(src) and (src[j].isalnum() or src[j] == "_"):
                j += 1
            out.append(("name", src[i:j]))
            i = j
        elif c in "'\"":
            j = src.find(c, i + 1)
            if j < 0:
                raise ValueError("unterminated string")
            out.append(("str", src[i + 1:j]))
            i = j + 1
        elif src[i:i + 2] in ("<=", ">=", "==", "!="):
            out.append(("op", src[i:i + 2]))
            i += 2
        elif c in "+-*/<>(),":
            out.append(("op", c))
            i += 1
        else:
            raise ValueError(f"bad character '{c}'")
    return out


def _parse_or(toks, i):
    v, i = _parse_and(toks, i)
    while i < len(toks) and toks[i] == ("name", "or"):
        r, i = _parse_and(toks, i + 1)
        v = Binary("or", v, r)
    return v, i


def _parse_and(toks, i):
    v, i = _parse_not(toks, i)
    while i < len(toks) and toks[i] == ("name", "and"):
        r, i = _parse_not(toks, i + 1)
        v = Binary("and", v, r)
    return v, i


def _parse_not(toks, i):
    if i < len(toks) and toks[i] == ("name", "not"):
        v, i = _parse_not(toks, i + 1)
        return Unary("not", v), i
    return _parse_cmp(toks, i)


def _parse_cmp(toks, i):
    v, i = _parse_sum(toks, i)
    if i < len(toks) and toks[i][0] == "op" and toks[i][1] in _COMPARE:
        op = toks[i][1]
        r, i = _parse_sum(toks, i + 1)
        v = Binary(op, v, r)
    return v, i


def _parse_sum(toks, i):
    v, i = _parse_term(toks, i)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "+-":
        op = toks[i][1]
        r, i = _parse_term(toks, i + 1)
        v = Binary(op, v, r)
    return v, i


def _parse_term(toks, i):
    v, i = _parse_unary(toks, i)
    while i < len(toks) and toks[i][0] == "op" and toks[i][1] in "*/":
        op = toks[i][1]
        r, i = _parse_unary(toks, i + 1)
        v = Binary(op, v, r)
    return v, i


def _parse_unary(toks, i):
    if i < len(toks) and toks[i] == ("op", "-"):
        v, i = _parse_unary(toks, i + 1)
        return Unary("-", v), i
    return _parse_atom(toks, i)


# `true`/`false` are literals, not names an environment has to bind. Every adopter
# bound them by hand; a grammar with comparisons and no booleans was the omission.
_BOOLEANS = {"true": True, "false": False}


def _parse_atom(toks, i):
    if i >= len(toks):
        raise ValueError("unexpected end of expression")
    kind, val = toks[i]
    if kind in ("num", "str"):
        return Lit(val), i + 1
    if kind == "op" and val == "(":
        v, i = _parse_or(toks, i + 1)
        if i >= len(toks) or toks[i] != ("op", ")"):
            raise ValueError("missing ')'")
        return v, i + 1
    if kind == "name":
        if i + 1 < len(toks) and toks[i + 1] == ("op", "("):
            args = []
            i += 2
            if toks[i] != ("op", ")"):
                while True:
                    a, i = _parse_or(toks, i)
                    args.append(a)
                    if i < len(toks) and toks[i] == ("op", ","):
                        i += 1
                        continue
                    break
            if i >= len(toks) or toks[i] != ("op", ")"):
                raise ValueError("missing ')'")
            return Call(val, tuple(args)), i + 1
        if val in _BOOLEANS:
            return Lit(_BOOLEANS[val]), i + 1
        return Var(val), i + 1
    raise ValueError(f"unexpected '{val}'")


__all__ = ["Binary", "Call", "Expr", "Lit", "Read", "Reads", "Term", "Unary", "Var",
           "compile_expr", "evaluate_expr"]
