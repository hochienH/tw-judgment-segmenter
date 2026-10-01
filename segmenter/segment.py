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
    "FACTS_REASONS": ["犯罪事實及理由要領", "犯罪事實及理由", "事實及理由要領", "事實理由及證據", "事實及理由",
                      "事實與理由", "事實及證據"],
    "FACTS": ["犯罪事實要旨", "犯罪事實", "事實概要", "事實要領", "事實"],
    "REASONS": ["理由要領", "理由"],
    "BODY_OTHER": ["證據並所犯法條", "證據名稱", "所犯法條", "處罰條文", "證據"],
}
# longest first, so 事實及理由 wins over 事實
_BODY = sorted(((w, lab) for lab, ws in BODY_HEADINGS.items() for w in ws), key=lambda x: -len(x[0]))
RE_BODY = re.compile(rf"^{WS}(?:{'|'.join(_spaced(w) for w, _ in _BODY)}){WS}[：:]?{WS}$")
BODY_LABEL = {w: lab for w, lab in _BODY}
# 宣示判決筆錄 writes numbered or prefixed headings: 一、主文 / 二、犯罪事實要旨 / 判決事實及理由要領
TRANSCRIPT_HEADINGS = {
    "主文": "MAIN", "法官當庭宣示主文如下": "MAIN", "宣示主文如下": "MAIN",
    "犯罪事實要旨": "FACTS", "處罰條文": "BODY_OTHER", "證據名稱": "BODY_OTHER", "附記事項": "BODY_OTHER",
    "判決事實及理由要領": "FACTS_REASONS", "事實及理由要領": "FACTS_REASONS", "訴訟標的及理由要領": "FACTS_REASONS",
    "理由要領": "REASONS",
}
RE_TRANSCRIPT = re.compile(
    rf"^{WS}(?:[一二三四五六七八九十]+{WS}、{WS})?(?:{'|'.join(_spaced(w) for w in sorted(TRANSCRIPT_HEADINGS, key=len, reverse=True))}){WS}[：:]?{WS}$")
RE_NUM_PREFIX = re.compile(r"^[一二三四五六七八九十]+、")

NUMC = r"[0-9０-９一二三四五六七八九十百零〇]"
RE_DATE_LINE = re.compile(rf"^{WS}中{WS}華{WS}民{WS}國{WS}{NUMC}+{WS}年{WS}{NUMC}+{WS}月{WS}{NUMC}+{WS}日{WS}$")

NUMLAB = r"[0-9０-９一二三四五六七八九十()（）]*"
RE_APPENDIX_LAW = re.compile(rf"^{WS}附{WS}錄{WS}[^。，\n]{{0,24}}?(?:法{WS}條|條{WS}文|法{WS}規){WS}[^。，\n]{{0,8}}?[：:]?{WS}$|^{WS}附{WS}錄{WS}[：:]?{WS}$")
RE_ATTACH = re.compile(rf"^{WS}(?:附{WS}(?:件|表){WS}{NUMLAB}{WS}(?:[：:][^\n]{{0,40}})?|附{WS}(?:記|註){WS}(?:[：:][^\n]*)?|計{WS}算{WS}書{WS}[：:]?){WS}$")
RE_CLOSING_ALT = re.compile(rf"^{WS}(?:以{WS}上|本{WS}件)?{WS}正{WS}本{WS}(?:證{WS}明{WS}與{WS}原{WS}本{WS}無{WS}異|係{WS}照{WS}原{WS}本{WS}作{WS}成)")
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
    return re.sub(r"[\s　：:]+", "", s)


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


def segment(text: str) -> dict:
    events: list[tuple[int, str, str]] = []        # (offset, label, heading)
    alt_closing = None                             # 以上正本證明與原本無異 ..., used only if no date line
    in_tail = False
    seen_body = False
    closing_done = False
    for start, _, line in _lines(text):
        if RE_APPENDIX_LAW.match(line):
            events.append((start, "APPENDIX_LAW", _squash(line)))
            in_tail = True
            continue
        if RE_ATTACH.match(line):
            events.append((start, "ATTACHMENT", _squash(line)))
            in_tail = True
            continue
        m = RE_BODY.match(line) or RE_TRANSCRIPT.match(line)
        if m:
            word = RE_NUM_PREFIX.sub("", _squash(line))
            label = BODY_LABEL.get(word) or TRANSCRIPT_HEADINGS.get(word)
            if label is None:
                continue
            if in_tail:                            # heading inside an attachment (e.g. attached indictment)
                events.append((start, "SUB", word))
            elif not closing_done:
                events.append((start, label, word))
                seen_body = True
            continue
        # the closing opens at the first date line after 主文 or a body heading
        if not in_tail and not closing_done and seen_body and RE_DATE_LINE.match(line):
            events.append((start, "CLOSING", _squash(line)))
            closing_done = True
            continue
        if not in_tail and not closing_done and seen_body and RE_CLOSING_ALT.match(line):
            alt_closing = alt_closing if alt_closing is not None else (start, "CLOSING", _squash(line)[:12])

    if not closing_done and alt_closing is not None:
        events.append(alt_closing)
        events.sort(key=lambda e: e[0])
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
        sections.append(sec)

    merged: list[Section] = []                     # 法官當庭宣示主文如下 + 一、主文 -> one MAIN
    for sec in sections:
        if merged and merged[-1].label == sec.label and sec.label not in TAIL_LABELS:
            merged[-1].end = sec.end
        else:
            merged.append(sec)
    sections = merged
    labels = [s.label for s in sections]
    kind = doc_kind(text)
    missing = [x for x, ok in (("MAIN", "MAIN" in labels),
                               ("BODY", any(l in BODY_LABELS for l in labels)),
                               ("CLOSING", "CLOSING" in labels)) if not ok]
    order_ok = "MAIN" not in labels or all(labels.index("MAIN") < i for i, l in enumerate(labels) if l in BODY_LABELS)
    if kind in FORMULAIC:
        status = "formulaic"
    elif not missing and order_ok:
        status = "ok"
    else:
        status = "partial"
    return {"doc_kind": kind, "status": status, "missing": missing, "order_ok": order_ok,
            "sections": [asdict(s) for s in sections]}
