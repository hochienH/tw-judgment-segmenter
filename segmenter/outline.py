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
    ("壹", r"([壹貳參叁肆伍陸柒捌玖拾]+)[、．.](?![0-9０-９○〇零])"),
    # an amount is not an enumerator: 一、０００、０００元, 一九八、○○○股
    ("一", r"([一二三四五六七八九十]+)(?:[、．.](?![0-9０-９○〇零])|(?=[㈠-㈩⑴-⒇⒈-⒛]|[（(][一二三四五六七八九十0-9０-９]))"),
    ("㈠", r"([㈠-㈩])、?|[（(]([一二三四五六七八九十]+)[）)]、?"),
    ("⑴", r"([⑴-⒇])|[（(]([0-9０-９]{1,2})[）)]"),
    ("1.", r"([0-9０-９]{1,2})[、．.](?![0-9０-９])|([⒈-⒛])"),   # ⒈ U+2488 = 1. as one glyph
    ("①", r"([①-⑳])"),
    ("A", r"([A-Z])[、．.]"),
]
RE_ENUMS = [(st, re.compile(rf"^[\s　]*(?:{p})")) for st, p in ENUM_PATTERNS]
BODY_LABELS = ("FACTS", "REASONS", "FACTS_REASONS", "BODY_OTHER")
RE_HEADING_LINE = re.compile(r"^[\s　]*(?:理[\s　]*由|事[\s　]*實|事[\s　]*實[\s　]*及[\s　]*理[\s　]*由|犯[\s　]*罪[\s　]*事[\s　]*實)[\s　]*[：:]?[\s　]*$")


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
        return ord(token) - 0x2487 if "\u2488" <= token <= "\u249b" else int(token)
    if style == "A":
        return ord(token) - 64
    return None


# Big5 custom glyphs (造字) in the Private Use Area, used as enumerators. Inferred from runs in the 200k
# training sample: after the last Unicode glyph of a style (㈩, ⑳ ...) the k-th consecutive PUA item at the
# same indentation is ordinal 10+k (or 20+k). Codes descend as ordinals rise. F6B0.. are 一、 二、 … with the
# 、 built in: they follow headings such as 理由 / 事實及理由 as the FIRST item.
PUA_BLOCKS = [  # (first code, last code, style, ordinal of first code)
    (0xF6B0, 0xF6A2, "一", 1),     # F6B0 = 一、 … F6A6 = 十一、 … F6A2 = 十五、
    (0xF674, 0xF65B, "㈠", 11),    # F674 = (十一) … F65B = (三十六)
    (0xF4DA, 0xF4D7, "⑴", 21),     # F4DA = (21) … F4D7 = (24)
]
PUA_SINGLE = {0xE7CB: ("一", 11)}


def pua_enum(ch: str) -> tuple[str, int] | None:
    c = ord(ch)
    if c in PUA_SINGLE:
        return PUA_SINGLE[c]
    for hi, lo, style, first in PUA_BLOCKS:
        if lo <= c <= hi:
            return style, first + (hi - c)
    return None


def match_enum(line: str) -> list[tuple[str, int]]:
    """Enumerators at the start of a line, in order. Usually one; 六㈠ or 一、㈠ give two."""
    out: list[tuple[str, int]] = []
    rest = line
    while True:
        head = rest.lstrip(" 　\t")
        hit = pua_enum(head[0]) if head else None
        if hit:
            out.append(hit)
            rest = head[1:].lstrip("、．.")
            continue
        for style, rx in RE_ENUMS:
            m = rx.match(rest)
            if m and rest[m.end():m.end() + 1] in ("＋", "+"):
                m = None                            # ㈠＋㈡為… refers to earlier items
            if m:
                token = next(g for g in m.groups() if g)
                n = ordinal(style, token)
                if n:
                    out.append((style, n))
                    rest = rest[m.end():]
                    break
        else:
            break
        if len(out) >= 3 or not rest:
            break
    return out


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
    duplicate: bool = False        # accepted although the court repeated the number (三、 twice)


@dataclass
class Level:
    style: str
    last: int
    node: int
    indent: int | None     # None: opened by a chained enumerator (六㈠); the first sibling sets it


def outline(text: str, sections: list[dict]) -> dict:
    """Outline nodes for every body section, plus rejected enumerator-like lines."""
    nodes: list[Node] = []
    rejected: list[dict] = []
    for sec in sections:
        if sec["label"] not in BODY_LABELS:
            continue
        stack: list[Level] = []
        pos, prev_last = sec["start"], "。"            # a section start counts as a sentence boundary
        for raw in text[sec["start"]:sec["end"]].splitlines(keepends=True):
            line, start = raw.rstrip("\r\n"), pos
            pos += len(raw)
            hits = match_enum(line)
            stripped = line.rstrip(" 　")
            if not hits and RE_HEADING_LINE.match(line):
                stack, prev_last = [], "。"             # a second 理由/事實 heading restarts the outline
                continue
            if not hits:
                prev_last = stripped[-1:] or prev_last
                continue
            ind = indent_of(line)
            for j, (style, n) in enumerate(hits):
                after_sentence = j > 0 or prev_last in SENTENCE_END   # a chained 2nd enumerator opens cleanly
                nested = skipped = duplicate = False
                # 1. continue an existing level of this style (innermost first) whose indentation matches
                # (±1 column normally; up to 4 when the previous line finished a sentence, because courts
                #  indent siblings inconsistently, e.g. ㈠㈢ with two full-width spaces and ㈡ with one)
                tol = 4 if after_sentence else 1
                k = next((i for i in range(len(stack) - 1, -1, -1)
                          if stack[i].style == style and n == stack[i].last + 1
                          and (stack[i].indent is None or abs(stack[i].indent - ind) <= tol or j > 0)), None)
                # 2. tolerate one skipped number, or a number the court repeated (三、 written twice),
                #    at exactly the same indentation after a finished sentence
                if k is None and after_sentence:
                    for delta, flag in ((2, "skipped"), (0, "duplicate")):
                        k = next((i for i in range(len(stack) - 1, -1, -1)
                                  if stack[i].style == style and n == stack[i].last + delta
                                  and stack[i].indent == ind and n > 1), None)
                        if k is not None:
                            skipped, duplicate = flag == "skipped", flag == "duplicate"
                            break
                if k is not None:
                    stack = stack[:k]
                elif n == 1 or (not stack and after_sentence):
                    # 3. a new list: a fresh style, or a restart of a style in use (quoted items) -> nested child.
                    #    A restart must follow a finished sentence; a wrapped cross reference does not.
                    nested = any(lv.style == style for lv in stack)
                    if nested and not after_sentence:
                        rejected.append({"start": start, "style": style, "ordinal": n, "indent": ind,
                                         "reason": "restart inside a sentence", "line": line.strip()[:30]})
                        break
                else:
                    expected = [lv.last + 1 for lv in stack if lv.style == style]
                    rejected.append({"start": start, "style": style, "ordinal": n, "indent": ind,
                                     "reason": f"expected {expected[-1]}" if expected else "new level not starting at 1",
                                     "line": line.strip()[:30]})
                    break
                parent = stack[-1].node if stack else -1
                node = Node(len(nodes), parent, len(stack), style, n, start, sec["end"], sec["label"],
                            re.sub(r"[\s　]+", "", line)[:20], ind, nested, skipped, duplicate)
                nodes.append(node)
                stack.append(Level(style, n, node.id, None if j > 0 else ind))
            prev_last = stripped[-1:] or prev_last
        # close each node at the next node of the same or shallower depth within this section
        sec_nodes = [nd for nd in nodes if nd.section == sec["label"] and sec["start"] <= nd.start < sec["end"]]
        for i, nd in enumerate(sec_nodes):
            nd.end = next((m.start for m in sec_nodes[i + 1:] if m.depth <= nd.depth), sec["end"])
    return {"nodes": [asdict(nd) for nd in nodes], "rejected": rejected}
