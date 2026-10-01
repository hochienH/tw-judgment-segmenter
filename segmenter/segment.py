"""Layer-1 segmentation of Taiwanese court documents (司法院 open data JFULL).

Output sections, with character offsets into the ORIGINAL text (the text itself is never rewritten):

  HEADER         title, case number, parties, 案由 ... up to the first heading
  MAIN           主文
  FACTS          事實 / 犯罪事實 / 事實概要 ...
  REASONS        理由 / 理由要領
  FACTS_REASONS  事實及理由 / 犯罪事實及理由 / 事實及理由要領 ... (facts and reasons written as one block)
  BODY_OTHER     other top-level body headings (證據並所犯法條 ...)
  CLOSING        from the first standalone date line (中華民國…年…月…日): court, judges, 以上正本證明…, clerk
  APPENDIX_LAW   附錄 (本案)論罪科刑法條: the full text of the applied statutes
  ATTACHMENT     附件 / 附表 / 附記 / 附註 / 計算書; an attached indictment (起訴書, 聲請簡易判決處刑書)
                 is flagged with kind="indictment"

Status: ok (主文 + body + closing), main_only (主文 + closing, e.g. 更正裁定), unstructured (no headings,
closing found: one-paragraph procedural orders), formulaic (支付命令), partial (anything else = failures).

Headings are detected only on standalone lines (spaces inside allowed, an optional colon, no 。),
because fixed-width line wrapping produces lines such as "主文。" or "附件檢察官聲請簡易判決處刑"
that start or end with heading words but are ordinary text.
Once the first appendix/attachment starts, later body headings belong to that attachment
(attached indictments carry their own 犯罪事實 / 證據並所犯法條).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

WS = r"[\s　]*"


def _spaced(word: str) -> str:
    """Heading pattern that tolerates spaces between characters: 主　　文, 事　實　及　理　由."""
    return WS.join(map(re.escape, word))


BODY_HEADINGS = {
    "MAIN": ["主文"],
    "FACTS_REASONS": ["犯罪事實及理由要領", "犯罪事實及理由", "事實及理由之要領", "事實及理由要領", "事實理由及證據",
                      "事實及理由", "事實與理由", "事實暨理由", "事實及證據"],
    "FACTS": ["犯罪事實及證據名稱", "犯罪事實要旨", "犯罪事實", "事實概要", "事實要領", "事實"],
    "REASONS": ["理由要領", "理由"],
    "BODY_OTHER": ["證據並所犯法條", "證據名稱", "所犯法條", "處罰條文", "證據"],
}
# longest first, so 事實及理由 wins over 事實
_BODY = sorted(((w, lab) for lab, ws in BODY_HEADINGS.items() for w in ws), key=lambda x: -len(x[0]))
RE_BODY = re.compile(rf"^{WS}(?:{'|'.join(_spaced(w) for w, _ in _BODY)}){WS}[：:︰﹕]?{WS}$")
BODY_LABEL = {w: lab for w, lab in _BODY}
# 宣示判決筆錄 writes numbered or prefixed headings: 一、主文 / 二、犯罪事實要旨 / 判決事實及理由要領
TRANSCRIPT_HEADINGS = {
    "主文": "MAIN", "法官當庭宣示主文如下": "MAIN", "宣示主文如下": "MAIN",
    "犯罪事實要旨": "FACTS", "處罰條文": "BODY_OTHER", "證據名稱": "BODY_OTHER", "附記事項": "BODY_OTHER",
    "判決事實及理由要領": "FACTS_REASONS", "事實及理由要領": "FACTS_REASONS", "訴訟標的及理由要領": "FACTS_REASONS",
    "爭執事項及理由要領": "FACTS_REASONS", "爭執事項理由要領": "FACTS_REASONS", "爭執事項、理由要領": "FACTS_REASONS",
    "理由要領": "REASONS",
    # numbered top-level headings; accepted only before any body heading (see segment())
    "犯罪事實": "FACTS", "事實": "FACTS", "理由": "REASONS", "事實及理由": "FACTS_REASONS",
}
RE_TRANSCRIPT = re.compile(
    rf"^{WS}(?:[一二三四五六七八九十]+{WS}、{WS})?(?:{'|'.join(_spaced(w) for w in sorted(TRANSCRIPT_HEADINGS, key=len, reverse=True))}){WS}[：:︰﹕]?{WS}$")
RE_NUM_PREFIX = re.compile(r"^[一二三四五六七八九十]+、")
RE_IMPLICIT_REASONS = re.compile(rf"^{WS}壹{WS}、")

NUMC = r"[0-9０-９一二三四五六七八九十百零〇廿卅]"     # 廿 = 20, 卅 = 30 (六月廿一日)
NUMS = rf"(?:{NUMC}{WS})+"                      # numerals may be spaced: 九　十　年
DATE = rf"中{WS}華{WS}民{WS}國{WS}{NUMS}年{WS}{NUMS}月{WS}{NUMS}日"
RE_DATE_LINE = re.compile(rf"^{WS}{DATE}{WS}$")

# ---- inline patterns, used only to repair documents whose line breaks were lost --------------
# (憲法法庭 decisions are one single line; some recent judgments replace breaks with spaces)
_INLINE_BODY = sorted((w for w, lab in _BODY if lab in ("FACTS", "REASONS", "FACTS_REASONS")), key=len, reverse=True)
RE_INLINE_MAIN = re.compile(rf"如{WS}下{WS}[：:︰﹕]?{WS}(主{WS}文)")
# a body heading must follow 。/：/line start and be followed by a colon or an enumerator (一、 壹、),
# so that "。理由如下" or "。事實上" never match
RE_INLINE_BODY = re.compile(
    rf"(?:^|(?<=[。：:︰﹕]))[ \t　]*({'|'.join(_spaced(w) for w in _INLINE_BODY)})"
    rf"(?={WS}(?:[：:︰﹕]|[一二三四五六七八九十壹貳參肆伍]+{WS}、))", re.M)
# a closing date opens a sentence (after 。 or at line start) and is followed by a court or judge;
# "爰於中華民國111年1月3日依司法院…" fails both: it follows 於, and 司法院 is not the signing court
RE_INLINE_DATE = re.compile(
    rf"(?:^|(?<=。))[ \t　]*({DATE})(?={WS}[\u4e00-\u9fff]{{0,14}}?(?:法院|法庭|庭|法官|大法官|審判長))", re.M)
# fully flat documents (憲法法庭): "。理由聲請意旨略以…" has no enumerator, so allow any continuation
# except connectives that make 理由 an ordinary word (理由如下 / 理由為 …)
RE_INLINE_BODY_FLAT = re.compile(
    rf"(?:^|(?<=[。：:︰﹕]))[ \t　]*({'|'.join(_spaced(w) for w in _INLINE_BODY)})(?!{WS}[如為是在係何之])", re.M)

NUMLAB = r"[0-9０-９一二三四五六七八九十()（）]*"
RE_APPENDIX_LAW = re.compile(rf"^{WS}附{WS}錄{WS}[^。，\n]{{0,24}}?(?:法{WS}條|條{WS}文|法{WS}規){WS}[^。，\n]{{0,8}}?[：:︰﹕]?{WS}$|^{WS}附{WS}錄{WS}[：:︰﹕]?{WS}$")
RE_ATTACH = re.compile(rf"^{WS}(?:附{WS}(?:件|表){WS}{NUMLAB}{WS}(?:[：:︰﹕][^\n]{{0,40}})?|附{WS}(?:記|註){WS}(?:[：:︰﹕][^\n]*)?|計{WS}算{WS}書{WS}[：:︰﹕]?){WS}$")
RE_CLOSING_ALT = re.compile(rf"^{WS}(?:以{WS}上|本{WS}件|右{WS}(?:為{WS})?)?{WS}正{WS}本{WS}(?:證{WS}明{WS}與{WS}原{WS}本{WS}無{WS}異|係{WS}照{WS}原{WS}本{WS}作{WS}成)")
# heading followed by the statutes on the same line: 附錄本案論罪科刑法條全文：刑法第二百六十六條…
RE_APPENDIX_LAW_INLINE = re.compile(
    rf"^{WS}附{WS}錄{WS}[^。，\n]{{0,24}}?(?:法{WS}條|條{WS}文|法{WS}規){WS}(?:全{WS}文)?{WS}[：:︰﹕]")
RE_BRACKETED = re.compile(r"^([\s　]*)[【〔［\[]([^】〕］\]]{1,12})[】〕］\]]")    # 【附註】 -> 附註
# convention (a): any statute text appended after the judgment is APPENDIX_LAW, including 附註/附記
# that quote 民訴 466-1 etc.; 附表/附件 are not relabelled (tables often just mention laws)
# the quoted article must head a line ("民事訴訟法第466條之1：", "一、民事訴訟法第436條之24第2項："),
# not just be mentioned inside an instruction ("★一、請聲請人…依民事訴訟法第…條…")
RE_STATUTE_HEAD_LINE = re.compile(
    r"^[\s　]*(?:[一二三四五六七八九十]+[、.]|[⑴⑵⑶]|\(\d+\))?[\s　]*(?:中華民國)?[\u4e00-\u9fff]{1,20}?(?:法|條例|通則|規則)"
    r"[\s　]*第[\s　]*[0-9０-９一二三四五六七八九十百千]+[\s　]*條", re.M)
RELABEL_HEADS = ("附註", "附記", "附錄")
# after the closing, a standalone 所犯法條 / 論罪科刑法條 heading is the statute appendix (no 附錄 in front)
RE_APPENDIX_LAW_AFTER_CLOSING = re.compile(rf"^{WS}(?:本{WS}案{WS})?(?:所{WS}犯{WS}法{WS}條|論{WS}罪{WS}科{WS}刑{WS}法{WS}條){WS}(?:全{WS}文)?{WS}[：:︰﹕]?{WS}$")
RE_INDICTMENT = re.compile(r"起訴書|聲請簡易判決處刑書|聲請簡易判決處刑|追加起訴|犯罪事實|證據並所犯法條")

RE_TITLE_KIND = re.compile(
    r"(宣示判決筆錄|支付命令|判決|裁定|決定書|處分書|命令|筆錄)(?=(?:[0-9一二三四五六七八九十百]+年度?\S{0,12}?字第?[0-9一二三四五六七八九十百]+號)?$)")
RE_PAYMENT_CASE = re.compile(r"^[0-9一二三四五六七八九十百]+年度?司?促字")
FORMULAIC = {"支付命令"}

TAIL_LABELS = {"APPENDIX_LAW", "ATTACHMENT"}
BODY_LABELS = {"FACTS", "REASONS", "FACTS_REASONS", "BODY_OTHER"}


@dataclass
class Section:
    label: str
    start: int
    end: int
    heading: str = ""
    kind: str = ""                 # ATTACHMENT only: "indictment" or ""
    subheadings: list = field(default_factory=list)


def _lines(text: str):
    """(start, end_without_newline, line) for every line of the original text."""
    pos = 0
    for m in re.finditer(r"[^\n]*\n?", text):
        if not m.group(0):
            break
        line = m.group(0).rstrip("\r\n")
        yield pos, pos + len(line), line
        pos = m.end()


def _squash(s: str) -> str:
    return re.sub(r"[\s　：:︰﹕]+", "", s)


def doc_kind(text: str) -> str:
    """Kind from the title, the first non-empty line(s): 判決, 裁定, 支付命令, ..."""
    seen = []
    for _, _, line in _lines(text):
        s = _squash(line)
        if not s:
            continue
        seen.append(s)
        m = RE_TITLE_KIND.search(s)
        if m:
            return m.group(1)
        if RE_PAYMENT_CASE.match(s):             # title missing, but 司促/促 cases are payment orders
            return "支付命令"
        if len(seen) >= 3:
            break
    return ""


def _inline_repair(text: str, events: list, closing_done: bool, seen_body: bool):
    """Fill in only what the line pass missed, from strict inline patterns."""
    tail_start = min((o for o, l, _ in events if l in TAIL_LABELS), default=len(text))
    have = {l for _, l, _ in events}
    new = []
    main_off = next((o for o, l, _ in events if l == "MAIN"), None)
    if main_off is None:
        m = RE_INLINE_MAIN.search(text, 0, tail_start)
        if m:
            main_off = m.start(1)
            new.append((main_off, "MAIN", "主文"))
    if not (have & BODY_LABELS) and main_off is not None:
        stop = min(next((o for o, l, _ in events if l == "CLOSING"), tail_start), tail_start)
        flat = text.count("\n") <= 2
        for m in (RE_INLINE_BODY_FLAT if flat else RE_INLINE_BODY).finditer(text, main_off, stop):
            word = _squash(m.group(1))
            new.append((m.start(1), BODY_LABEL[word], word))
    if not closing_done:
        after = max((o for o, l, _ in events + new if l == "MAIN" or l in BODY_LABELS), default=None)
        if after is not None:
            m = RE_INLINE_DATE.search(text, after, tail_start)
            if m:
                new.append((m.start(1), "CLOSING", _squash(m.group(1))))
                closing_done = True
    seen_body = seen_body or any(l == "MAIN" or l in BODY_LABELS for _, l, _ in new)
    return sorted(events + new, key=lambda e: e[0]), closing_done, seen_body


def segment(text: str) -> dict:
    events: list[tuple[int, str, str]] = []        # (offset, label, heading)
    alt_closing = None                             # 以上正本證明與原本無異 ..., used only if no date line
    seen_inner_body = False                        # a FACTS/REASONS/... heading has been seen
    kind = doc_kind(text)
    in_tail = False
    seen_body = False
    closing_done = False
    for start, _, line in _lines(text):
        line = RE_BRACKETED.sub(r"\1\2", line)       # same length minus brackets; offsets use `start` only
        if (RE_APPENDIX_LAW.match(line) or RE_APPENDIX_LAW_INLINE.match(line)
                or (closing_done and RE_APPENDIX_LAW_AFTER_CLOSING.match(line))):
            events.append((start, "APPENDIX_LAW", _squash(line)))
            in_tail = True
            continue
        if RE_ATTACH.match(line):
            events.append((start, "ATTACHMENT", _squash(line)))
            in_tail = True
            continue
        m = RE_BODY.match(line) or RE_TRANSCRIPT.match(line)
        if m:
            numbered = bool(RE_NUM_PREFIX.match(_squash(line)))
            if numbered and seen_inner_body and kind != "宣示判決筆錄":
                continue                           # "一、犯罪事實" inside the reasons is a sub-item, not a section
            word = RE_NUM_PREFIX.sub("", _squash(line))
            label = BODY_LABEL.get(word) or TRANSCRIPT_HEADINGS.get(word)
            if label is None:
                continue
            if in_tail:                            # heading inside an attachment (e.g. attached indictment)
                events.append((start, "SUB", word))
            elif not closing_done:
                events.append((start, label, word))
                seen_body = True
                seen_inner_body = seen_inner_body or label in BODY_LABELS
            continue
        # reasons written without a heading: 主文 is followed directly by 壹、程序方面 / 壹、實體部分 ...
        if (not in_tail and not closing_done and not seen_inner_body and events and events[-1][1] == "MAIN"
                and RE_IMPLICIT_REASONS.match(line)):
            events.append((start, "REASONS", "(implicit)"))
            seen_inner_body = True
            continue
        # the closing opens at the first date line after 主文 or a body heading
        if not in_tail and not closing_done and seen_body and RE_DATE_LINE.match(line):
            events.append((start, "CLOSING", _squash(line)))
            closing_done = True
            continue
        if not in_tail and not closing_done and seen_body and RE_CLOSING_ALT.match(line):
            alt_closing = alt_closing if alt_closing is not None else (start, "CLOSING", _squash(line)[:12])

    have = {l for _, l, _ in events}
    if "MAIN" not in have or not (have & BODY_LABELS) or not closing_done:
        events, closing_done, seen_body = _inline_repair(text, events, closing_done, seen_body)
    if not closing_done and alt_closing is not None:
        events.append(alt_closing)
        events.sort(key=lambda e: e[0])
        closing_done = True
    if not seen_body and not closing_done:
        # one-paragraph orders (命補正, 命補繳裁判費 ... 特此裁定) have no headings at all:
        # still cut the closing at the first date line
        for start, _, line in _lines(text):
            if start > 0 and RE_DATE_LINE.match(line) and not any(o <= start for o, l, _ in events if l in TAIL_LABELS):
                events.append((start, "CLOSING", _squash(line)))
                events.sort(key=lambda e: e[0])
                break
    sections: list[Section] = []
    first = next((e[0] for e in events if e[1] != "SUB"), len(text))
    if first > 0:
        sections.append(Section("HEADER", 0, first))
    top = [e for e in events if e[1] != "SUB"]
    for i, (off, lab, head) in enumerate(top):
        end = top[i + 1][0] if i + 1 < len(top) else len(text)
        sec = Section(lab, off, end, head)
        if lab in TAIL_LABELS:
            sec.subheadings = [h for o, l, h in events if l == "SUB" and off < o < end]
            if lab == "ATTACHMENT" and RE_INDICTMENT.search(_squash(text[off:end][:400]) + "".join(sec.subheadings)):
                sec.kind = "indictment"
            elif (lab == "ATTACHMENT" and head.startswith(RELABEL_HEADS)
                    and RE_STATUTE_HEAD_LINE.search(re.sub(r"^[^\n]*?[：:︰﹕]", "", text[off:end][:400], count=1))):
                sec.label = "APPENDIX_LAW"
        sections.append(sec)

    merged: list[Section] = []                     # 法官當庭宣示主文如下 + 一、主文 -> one MAIN
    for sec in sections:
        if merged and merged[-1].label == sec.label and sec.label not in TAIL_LABELS:
            merged[-1].end = sec.end
        else:
            merged.append(sec)
    sections = merged
    labels = [s.label for s in sections]
    missing = [x for x, ok in (("MAIN", "MAIN" in labels),
                               ("BODY", any(l in BODY_LABELS for l in labels)),
                               ("CLOSING", "CLOSING" in labels)) if not ok]
    order_ok = "MAIN" not in labels or all(labels.index("MAIN") < i for i, l in enumerate(labels) if l in BODY_LABELS)
    if kind in FORMULAIC:
        status = "formulaic"
    elif not missing and order_ok:
        status = "ok"
    elif missing == ["BODY"] and order_ok:
        # legitimate: 小額判決 may record only 主文 (民訴 436-18), 更正裁定 ...
        status = "main_only"
    elif missing == ["MAIN", "BODY"]:
        status = "unstructured"                    # no headings at all, closing found
    else:
        status = "partial"
    return {"doc_kind": kind, "status": status, "missing": missing, "order_ok": order_ok,
            "sections": [asdict(s) for s in sections]}
