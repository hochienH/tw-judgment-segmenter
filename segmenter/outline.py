"""Layer-2 step 1: rebuild the enumeration outline (編號層級) inside layer-1 body sections.

Enumerator styles (one style = one family of glyphs):
  甲  甲、乙、         壹  壹、貳、        一  一、二、
  ㈠  ㈠㈡ / (一)(二)   1.  1. 2. / 1、    ⑴  ⑴⑵ / (1)(2)    ①  ①②    A  A. B.

Nesting is decided per document, not by a fixed rank: a style seen for the first time opens a level
under the current item; a style already on the stack returns to that level. So 一>⑴ and 一>1.>⑴ both
work. Each level remembers the indentation of its first item. An enumerator continues a level only if
its ordinal is the next one AND its indentation matches that level (±1 column; full-width space = 2).
That rejects wrapped lines such as "    二、三條…" (continuation lines are indented 4) and stops a quoted
statute's 二、 from stealing the outer list's next number.
A list that restarts at 1 in a style already in use (quoted statute items 一、二、…) becomes a nested
child list, flagged nested_restart. A court that skips one number (三 then 五) is tolerated when the
indentation matches exactly and the previous line ends a sentence.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

CN = {c: i for i, c in enumerate("零一二三四五六七八九", 0)}
CAPS = {c: i + 1 for i, c in enumerate("壹貳參肆伍陸柒捌玖")} | {"叁": 3, "拾": 10}
STEMS = {c: i + 1 for i, c in enumerate("甲乙丙丁戊己庚辛壬癸")}
FW = str.maketrans("０１２３４５６７８９", "0123456789")

ENUM_PATTERNS = [  # (style, pattern); the first capture group holds the ordinal token
    ("甲", r"([甲乙丙丁戊己庚辛壬癸])[、．.]"),
    ("壹", r"([壹貳參叁肆伍陸柒捌玖拾]+)[、．.]"),
    ("一", r"([一二三四五六七八九十]+)[、．.]"),
    ("㈠", r"([㈠-㈩])、?|[（(]([一二三四五六七八九十]+)[）)]、?"),
    ("⑴", r"([⑴-⒇])|[（(]([0-9０-９]{1,2})[）)]"),
    ("1.", r"([0-9０-９]{1,2})[、．.](?![0-9０-９])"),
    ("①", r"([①-⑳])"),
    ("A", r"([A-Z])[、．.]"),
]
RE_ENUMS = [(st, re.compile(rf"^[\s　]*(?:{p})")) for st, p in ENUM_PATTERNS]
BODY_LABELS = ("FACTS", "REASONS", "FACTS_REASONS", "BODY_OTHER")


def _cn_number(s: str, digits: dict) -> int | None:
    """一 / 十一 / 二十三 (or the 壹 variants) -> int."""
    total, cur = 0, 0
    for ch in s:
        if ch in ("十", "拾"):
            total += (cur or 1) * 10
            cur = 0
        elif ch in digits:
            cur = digits[ch]
        else:
            return None
    return total + cur


def ordinal(style: str, token: str) -> int | None:
    token = token.translate(FW)
    if style == "一" or (style == "㈠" and not "㈠" <= token <= "㈩"):
        return _cn_number(token, CN)
    if style == "壹":
        return _cn_number(token, CAPS | {"十": 10})
    if style == "甲":
        return STEMS.get(token)
    if style == "㈠":
        return ord(token) - 0x321F                 # ㈠ U+3220 -> 1
    if style == "⑴":
        return ord(token) - 0x2473 if "⑴" <= token <= "⒇" else int(token)
    if style == "①":
        return ord(token) - 0x245F                 # ① U+2460 -> 1
    if style == "1.":
        return int(token)
    if style == "A":
        return ord(token) - 64
    return None


def match_enum(line: str) -> tuple[str, int] | None:
    for style, rx in RE_ENUMS:
        m = rx.match(line)
        if m:
            token = next(g for g in m.groups() if g)
            n = ordinal(style, token)
            if n:
                return style, n
    return None


def indent_of(line: str) -> int:
    n = 0
    for ch in line:
        if ch == " ":
            n += 1
        elif ch == "　":
            n += 2
        elif ch == "\t":
            n += 4
        else:
            break
    return n


SENTENCE_END = set("。：:；;」』）)！？")


@dataclass
class Node:
    id: int
    parent: int            # -1 = top level of the section
    depth: int
    style: str
    ordinal: int
    start: int             # offset of the enumerator line in the original text
    end: int               # start of the next node at the same or a shallower depth, or the section end
    section: str
    head: str              # first characters after the enumerator, for inspection
    indent: int = 0
    nested_restart: bool = False   # a list restarting at 1 in a style already in use (quoted items)
    skipped: bool = False          # accepted although one ordinal was skipped (三 -> 五)


@dataclass
class Level:
    style: str
    last: int
    node: int
    indent: int


def outline(text: str, sections: list[dict]) -> dict:
    """Outline nodes for every body section, plus rejected enumerator-like lines."""
    nodes: list[Node] = []
    rejected: list[dict] = []
    for sec in sections:
        if sec["label"] not in BODY_LABELS:
            continue
        stack: list[Level] = []
        pos, prev_last = sec["start"], ""
        for raw in text[sec["start"]:sec["end"]].splitlines(keepends=True):
            line, start = raw.rstrip("\r\n"), pos
            pos += len(raw)
            hit = match_enum(line)
            stripped = line.rstrip(" 　")
            if not hit:
                prev_last = stripped[-1:] or prev_last
                continue
            style, n = hit
            ind = indent_of(line)
            nested = skipped = False
            # 1. continue an existing level of this style (innermost first) whose indentation matches
            k = next((i for i in range(len(stack) - 1, -1, -1)
                      if stack[i].style == style and n == stack[i].last + 1 and abs(stack[i].indent - ind) <= 1), None)
            # 2. tolerate one skipped number at exactly the same indentation after a finished sentence
            if k is None and prev_last in SENTENCE_END:
                k = next((i for i in range(len(stack) - 1, -1, -1)
                          if stack[i].style == style and n == stack[i].last + 2 and stack[i].indent == ind), None)
                skipped = k is not None
            if k is not None:
                stack = stack[:k]
            elif n == 1 or not stack:
                # 3. a new list: a fresh style, or a restart of a style in use (quoted items) -> nested child
                nested = any(lv.style == style for lv in stack)
            else:
                expected = [lv.last + 1 for lv in stack if lv.style == style]
                rejected.append({"start": start, "style": style, "ordinal": n, "indent": ind,
                                 "reason": f"expected {expected[-1]}" if expected else "new level not starting at 1",
                                 "line": line.strip()[:30]})
                prev_last = stripped[-1:] or prev_last
                continue
            parent = stack[-1].node if stack else -1
            node = Node(len(nodes), parent, len(stack), style, n, start, sec["end"], sec["label"],
                        re.sub(r"[\s　]+", "", line)[:20], ind, nested, skipped)
            nodes.append(node)
            stack.append(Level(style, n, node.id, ind))
            prev_last = stripped[-1:] or prev_last
        # close each node at the next node of the same or shallower depth within this section
        sec_nodes = [nd for nd in nodes if nd.section == sec["label"] and sec["start"] <= nd.start < sec["end"]]
        for i, nd in enumerate(sec_nodes):
            nd.end = next((m.start for m in sec_nodes[i + 1:] if m.depth <= nd.depth), sec["end"])
    return {"nodes": [asdict(nd) for nd in nodes], "rejected": rejected}
