"""최소 S-expression 파서/직렬화기 (KiCad 파일용).

- Sym: 따옴표 없이 쓰는 토큰 (kicad_sch, xy, yes ...)
- str: 따옴표로 감싸는 문자열
- int/float: 숫자 (소수점 4자리, 불필요한 0 제거)
파서는 따옴표 문자열을 QStr로 돌려주어 Sym과 구분할 수 있다.
"""
from __future__ import annotations


class Sym(str):
    pass


class QStr(str):
    pass


def _fmt_num(v) -> str:
    if isinstance(v, bool):
        raise TypeError("bool은 S-expr 숫자가 아님")
    if isinstance(v, int):
        return str(v)
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dumps(node, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(node, list):
        if not node:
            return "()"
        simple = all(not isinstance(x, list) for x in node)
        if simple:
            return "(" + " ".join(dumps(x) for x in node) + ")"
        head = []
        rest = list(node)
        while rest and not isinstance(rest[0], list):
            head.append(dumps(rest.pop(0)))
        inner = "\n".join(pad + "  " + dumps(x, indent + 1) for x in rest)
        return "(" + " ".join(head) + "\n" + inner + "\n" + pad + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, str):
        return _quote(node)
    if isinstance(node, (int, float)):
        return _fmt_num(node)
    raise TypeError(f"직렬화 불가 타입 {type(node)}")


class ParseError(Exception):
    pass


def loads(text: str):
    pos, n = 0, len(text)
    stack, root = [], None

    while pos < n:
        ch = text[pos]
        if ch.isspace():
            pos += 1
        elif ch == "(":
            stack.append([])
            pos += 1
        elif ch == ")":
            if not stack:
                raise ParseError(f"짝 없는 ')' @ {pos}")
            done = stack.pop()
            if stack:
                stack[-1].append(done)
            elif root is None:
                root = done
            else:
                raise ParseError("최상위 표현식이 여러 개")
            pos += 1
        elif ch == '"':
            pos += 1
            buf = []
            while True:
                if pos >= n:
                    raise ParseError("닫히지 않은 문자열")
                c = text[pos]
                if c == "\\":
                    nxt = text[pos + 1] if pos + 1 < n else ""
                    buf.append("\n" if nxt == "n" else nxt)
                    pos += 2
                elif c == '"':
                    pos += 1
                    break
                else:
                    buf.append(c)
                    pos += 1
            if not stack:
                raise ParseError("괄호 밖 문자열")
            stack[-1].append(QStr("".join(buf)))
        else:
            start = pos
            while pos < n and not text[pos].isspace() and text[pos] not in '()"':
                pos += 1
            tok = text[start:pos]
            if not stack:
                raise ParseError("괄호 밖 토큰")
            try:
                val = int(tok) if tok.lstrip("-").isdigit() else float(tok)
            except ValueError:
                val = Sym(tok)
            stack[-1].append(val)
    if stack:
        raise ParseError("닫히지 않은 괄호")
    if root is None:
        raise ParseError("빈 입력")
    return root


def find(node, tag):
    """node의 직계 자식 중 첫 (tag ...) 리스트."""
    for x in node:
        if isinstance(x, list) and x and x[0] == tag:
            return x
    return None


def find_all(node, tag):
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]
