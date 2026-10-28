"""Layer 2, step 2: functional labels for the outline nodes.

The outline (``outline.py``) gives the numbering tree of a body section; this module says what each node does.
A node is labelled from its first line: the heading when the line is one (a short own line, or text before a
colon), otherwise the sentence opening. A node with no match inherits its parent's label; a node with nothing
to inherit is unlabelled (None). Two rule sets: ``criminal`` for 刑事 and ``civil`` for 民事, 行政 and the rest
(行政 reads like 民事 with 事實概要 up front).

Rules are (label, heading pattern, opening pattern). Heading patterns match the whole normalised heading
(spaces removed, trailing colon dropped); opening patterns match at the start of the stripped line. The first
matching rule wins, so the order inside a rule set matters (PROCEDURE before COURT_FINDING: 按民事訴訟法第385條
is procedure, 按民法第184條 is the court's reasoning).

Design notes from the 200k survey (STATUS, 2026-10-28): headings cover only 37% (刑事) to 45% (民事) of depth-0
nodes, so the opening patterns do most of the work; 刑事 openings are formulaic, 民事 has a long tail that stays
unlabelled. 實體方面 / 實體部分 is a container (MERITS): its children carry the real labels.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from .outline import RE_ENUMS, ordinal, pua_enum

SCHEMES = {"刑事": "criminal", "民事": "civil", "行政": "civil", "其他": "civil"}
HEADING_MAX = 12          # a heading before a colon is at most this long
SHORT_LINE = 12           # a line this short with no sentence punctuation is a heading on its own line
_WS = re.compile(r"[\s　]+")
_COLON = re.compile(r"^([^，。；：:、（）()「」]{1,%d})[：:︰﹕]" % HEADING_MAX)
_SENTENCE = re.compile(r"[，。；]")

# --- rule sets -------------------------------------------------------------------------------------------------
# v2 (2026-10-28): after the first 200k run (UNLABELLED 刑事 17.8% / 民事 11.6% / 行政 13.8%) the commonest unlabelled
# openings were added, and generic law-citation openings (按…, 刑法第…, 依民事訴訟法第…) became WEAK: they only
# label a node whose parent has no label, so a party quoting a statute under 原告主張 stays CLAIM.

CRIMINAL = [
    ("FACT_FINDING",      # evidence law and the acquittal standard come before the generic 刑事訴訟法 rule
     r"$^",
     r"按刑事訴訟法第(15[4-9]|16[01]|30[01])條|按犯罪事實應依證據|按刑事訴訟諭知無罪|按認定不利於被告|按被告之自白"),
    ("PROCEDURE",
     r"程序(部分|方面|事項)?|證據能力.*|本院審理範圍|審理範圍|管轄",
     r"按刑事訴訟法第|按告訴乃論|按被告以外之人|被告經合法傳喚|本件被告經合法|本案經檢察官|本案經本院|本件經|本院審理範圍"
     r"|本件被告.{0,8}所犯.{0,14}(死刑|無期徒刑|簡式|簡易)|按提起附帶民事訴訟|附帶民事訴訟"
     r"|按被告死亡者|按案件曾經判決確定|按檢察官聲請以簡|按因犯罪而受損害|本件被告因.{0,24}(經|由)檢察官"),
    ("ACCUSATION",
     r"(公訴|起訴|聲請簡易判決處刑|.*上訴|檢察官|被告|自訴)意旨(另|略)?以|公訴意旨另以|公訴意旨|.*上訴意旨略以",
     r"公訴意旨|本件公訴(人|意旨)|公訴人認|聲請簡易判決處刑意旨|檢察官(上訴|起訴)意旨|被告上訴意旨|起訴(意旨)?(略|係)以|自訴意旨"),
    ("CLOSING",
     r"應適用之?法(條|律)|適用之法(條|律)|據上論斷|據上論結|附記事項|附記",
     r"據上論(斷|結)|應依刑事訴訟法|依刑事訴訟法第|如不服本|如對本判決|本判決除有|本件如有前述|本案(經|由)檢察官.{0,20}(聲請|提起)|協商判決除有|刑事訴訟法第"),
    ("CONFISCATION",
     r".*沒收.*|犯罪所得(部分)?|追徵",
     r"扣案(如附表|之)|未扣案|按[，,]?犯罪所得|按[，,]?供犯罪所用|沒收部分|關於沒收"),
    ("SENTENCING",
     r"科刑(部分)?|量刑(部分|審酌|因素)?|刑之(減輕|加重)(事由)?|刑罰減輕事由|累犯(部分)?|緩刑|酌減其刑|爰審酌(被告)?|主刑",
     r"爰審酌|爰以行為人(之)?責任|審酌被告|本院審酌|爰(依|就|併)|被告前因|量刑|被告(前)?未曾因故意"),
    ("APPEAL",
     r"駁回上訴之理由|撤銷改判之理由|撤銷原判決之理由|有罪部分|無罪部分|不另為無罪諭知部分|上訴駁回(部分|之理由)?|撤銷部分",
     r"本件原判決|本件原審|原審(以|認|判決|審理|斟酌)|原判決(駁回|撤銷|以)|上訴人(上訴|之上訴)|檢察官上訴|被告上訴|經本院審理結果"
     r"|按不服地方法院|按除被告所犯為死刑|上訴意旨|依上所述，本件上訴|本件上訴人|撤銷原判決"),
    ("CONVICTION",
     r"論罪(及|、)?科刑(部分|之理由|之依據)?|論罪(部分|之理由)?|罪名|罪數|新舊法比較|所犯(罪名|法條)|共同正犯|想像競合犯?|接續犯|數罪併罰|處罰條文",
     r"核被告.{0,6}所為|核(上訴人|被告等|被告二人|被告2人)所為|本件被告.{0,6}所犯|按刑法第|按刑法上|被告行為後|按行為後法律|被告以一行為"
     r"|被告所犯|刑法第\d|刑法施行法|修正前|按毒品危害防制條例|毒品危害防制條例|按甲基安非他命|按.{1,12}(條例|法)第"),
    ("FACT_FINDING",
     r"犯罪事實(要旨|部分)?|本件犯罪事實|本案事實|證據(名稱|部分|部分補充)?|下列證據.*|認定(犯罪)?事實所憑之證據(及理由)?|事實(認定)?部分"
     r"|經查|惟查|本院查|本院之判斷|得心證之理由|被告(雖)?辯稱|實體(部分|方面|事項)",
     r"訊據(被告|上訴人)|認定犯罪事實|上[揭開]犯罪事實|上[揭開]事實|右揭(犯罪)?事實|前揭(犯罪)?事實|本件犯罪事實|本案犯罪事實|前開犯罪事實"
     r"|犯罪事實(及證據)?(引用|除)|本(件|院)認定(之)?(被告之)?犯罪事實|證人即|被告於(警詢|偵查|審理|本院)|經查|惟查|本院查"
     r"|被告(雖|固)(辯稱|以|不否認|坦承)|被告(甲|乙|丙|[一-鿿]{2,3})(固|雖|於)|綜上所述|綜上|查"
     r"|本案之犯罪事實|本件除犯罪事實欄|犯罪事實應依證據|不另為無罪(之)?諭知"),
]

CIVIL = [
    ("PROCEDURE",
     r"程序(方面|部分|事項)?|管轄|一造辯論|本件訴訟程序",
     r"被告(.{0,8})?(經合法通知|經受合法通知|未於言詞辯論|均未於言詞辯論)|本件(係|為)(就|依|適用|小額|涉外|因|屬)|按訴狀送達後"
     r"|本院依(職權|聲請|原告之聲請|被告之聲請)|按當事人(得|不得)|依民事訴訟法第(385|386|255|256|24|28)|按民事訴訟法第(385|386|255|256|24|28)"
     r"|本件被告(經|未於)|本件原告(起訴|聲請)後|本件原告經合法|按(訴之|原告於)|本院(就|有)管轄權|依行政訴訟法第|本件兩造合意"
     r"|本件係刑事附帶民事|本件(係|為)民事訴訟法|本件據兩造所簽訂|本件依兩造間|被告未於最後|兩造合意以本院|本判決係就|參加人未於言詞辯論"
     r"|(被告|被上訴人|原告)之?代表人|本件法官依"),
    ("FACTS_SUMMARY",
     r"事實(概要|摘要)|爭訟概要|本件事實概要|案件事實",
     r"緣(原告|上訴人|被告|被上訴人|聲請人)|本件如事實概要"),
    ("COURT_FINDING",     # "原告主張上開事實，業據其提出…" is the court weighing the claim, not the claim
     r"$^",
     r"(原告|上訴人|被上訴人|聲請人|再審原告)(.{0,8})?主張(上開|前揭|上揭|前開|系爭|之|.{0,16}等)事實.{0,8}(業據|有|固|為|並|堪)"
     r"|原告主張.{0,14}(為真|可採|洵屬|固非|不足|無理由|有理由)|本件原告之訴為"),
    ("CLAIM",
     r"(本件)?(原告|上訴人|再審原告|反訴原告|聲請人|抗告人|原審原告)(等)?(.{0,8})?(起訴)?(主張|聲明|之聲明|方面|起訴主張及聲明|主張略以|起訴主張略以|主張及聲明|請求)"
     r"|兩造聲明|兩造之聲明|兩造陳述|上訴聲明|先位聲明|備位聲明|訴之聲明|原告起訴主張.*|.*起訴意旨略(謂|以)|(上訴人)?上訴意旨略(以|謂)|聲請意旨略以",
     r"(本件)?(原告|上訴人|再審原告|反訴原告|聲請人|抗告人)(等)?(.{0,8})?(起訴)?(主張|請求|聲明)|原告起訴"
     r"|(本件)?原告起訴略以|起訴(意旨)?略(以|謂)|(上訴人)?上訴意旨略(以|謂)|聲請意旨略以|聲請人(主張|聲請)"),
    ("DEFENCE",
     r"(本件)?(被告|被上訴人|上訴人|再審被告|反訴被告|相對人|參加人)(等)?(.{0,8})?(則以|則略以|則答辯以|答辯(及聲明|略以|則以|聲明|意旨)?|抗辯(略以)?|方面|辯稱|則辯以|則抗辯|聲明求為判決|聲明請求.*)"
     r"|(本件)?(被告|被上訴人|再審被告|相對人|參加人)(等)?(之)?(主張|陳述)(略以)?"
     r"|答辯聲明|被告(等)?則以",
     r"(被告|被上訴人|上訴人|再審被告|反訴被告|相對人|參加人)(等)?(.{0,10})?(則以|則略以|則抗辯|則辯以|抗辯稱|抗辯略以|答辯|辯稱|則辯稱|雖辯稱|雖抗辯|雖主張|聲明求為判決|聲明請求)|(本件)?(被上訴人|被告)(等)?(之)?主張"),
    ("UNDISPUTED",
     r"(兩造)?不爭執(之)?(事項|事實)?|兩造不爭(執)?.*|不爭執事項|前提事實",
     r"兩造不爭(執)?|查(下列|以下)事實|兩造對於.{0,12}不爭執|(上開|本件|前揭|上揭|如)?事實概要欄?所(載|述|示|記)|本件無爭執"),
    ("ISSUES",
     r"(兩造|本件)?(之)?爭(點|執事項|執要點|執之點)(.*)?|本件爭點|爭執事項|爭點",
     r"(本件|兩造)(之)?爭點|本件兩造(之)?爭(點|執要點)|兩造爭執|本件之爭(點|執)|歸納兩造"),
    ("MERITS",
     r"實體(方面|部分|事項)?|實體上|本訴部分|反訴部分|先位之訴部分|備位之訴部分",
     r"$^"),
    ("CLOSING",
     r"訴訟費用(負擔)?(之依據)?|結論|據上論結|假執行(之宣告|部分)?|本件事證已臻明確|附記|結論︰.*|結論：.*",
     r"據上論結|本件事證(已臻|業已|已經|已)(明確|明)|訴訟費用|本件訴訟費用|兩造其餘(攻擊防禦|之攻擊|主張|陳述|之)|本件判決(之)?基礎|本件為判決(之)?基礎"
     r"|因本案事證已臻明|依民事訴訟法第(78|79|85|87|389|390|392)|本判決(原告勝訴部分|依民事訴訟法)|本件原告勝訴部分|本件(經)?依民事訴訟法"
     r"|原告陳明願供擔保|兩造均陳明願供擔保|原告願供擔保|被告願供擔保|本件(第一|第二)審訴訟費用|本件第一審|本件訴訟標的金額|如不服本判決|依行政訴訟法第(98|104|195|236)"
     r"|至(於)?兩造其餘|末按下列各款之判決|按下列各款之判決|確定訴訟費用額|本案事證|據上結論|(又|另)?本件事證[，,]?(已|業)"),
    ("COURT_FINDING",
     r"(本院|法院)(之|的)?判斷(如下)?|(本院)?得心證(之)?理由|本院(查|按|之判斷|判斷|經核)|經查|惟查|法院之判斷|原審斟酌|理由|本件應適用之法(律|令)|應適用之法(律|令)",
     r"經查|惟查|按當事人主張有利於己|按因故意|所定申報(權利)?期間|上開證券|原審(斟酌|以|認|為上訴人|判決|維持)|原判決(駁回|以|認)|從而|綜上所述|綜上|依上所述|依上(開)?說明"
     r"|本院(查|按|審酌|經核|認)|(又|次|再|復|末)(按|依|查)|本件應適用之法(律|令)|原判決撤銷|原審駁回|原告主張.{0,12}(為真|為可採|洵屬|固非|雖據|縱|不足|無理由)|原告(請求|依).{0,20}(有無理由|是否有理由|為有理由|為無理由)"
     r"|查|按|依民事訴訟法第|民事訴訟法第"),
]

# Openings that only say "here comes a statute": they label a node only when its parent is unlabelled.
WEAK_OPENINGS = {
    "criminal": re.compile(r"^(按|次按|又按|刑法第|刑事訴訟法第|毒品危害防制條例|修正前)"),
    "civil": re.compile(r"^(按|次按|又按|再按|末按|復按|依民事訴訟法第|民事訴訟法第|又依|次依|查|又查)"),
}

RULES = {
    "criminal": [(lab, re.compile(f"^(?:{h})$"), re.compile(f"^(?:{o})")) for lab, h, o in CRIMINAL],
    "civil": [(lab, re.compile(f"^(?:{h})$"), re.compile(f"^(?:{o})")) for lab, h, o in CIVIL],
}
LABELS = {
    "criminal": [lab for lab, _, _ in CRIMINAL],
    "civil": [lab for lab, _, _ in CIVIL],
}


# --- line reading --------------------------------------------------------------------------------------------

def first_line(text: str, start: int) -> str:
    end = text.find("\n", start)
    return text[start:] if end < 0 else text[start:end]


def strip_enum(line: str) -> str:
    """Drop whitespace and up to three leading enumerators (六㈠ gives two), the way outline.match_enum reads them."""
    rest = _WS.sub("", line)
    for _ in range(3):
        if not rest:
            break
        if pua_enum(rest[0]):
            rest = rest[1:].lstrip("、．.")
            continue
        for style, rx in RE_ENUMS:
            m = rx.match(rest)
            if m:
                token = next((g for g in m.groups() if g), None)
                if token and ordinal(style, token):
                    rest = rest[m.end():]
                    break
        else:
            break
    return rest


def read_heading(phrase: str) -> str | None:
    """The heading a stripped line carries: before a colon, or the whole line when it is a short label."""
    m = _COLON.match(phrase)
    if m:
        return m.group(1)
    if len(phrase) <= SHORT_LINE and not _SENTENCE.search(phrase):
        return phrase.rstrip("：:︰﹕")
    return None


@dataclass
class Labelled:
    id: int
    parent: int
    depth: int
    section: str
    start: int
    end: int
    label: str | None
    source: str            # heading | opening | inherit | none
    phrase: str            # stripped first line, for inspection


def label_node(phrase: str, scheme: str) -> tuple[str | None, str]:
    heading = read_heading(phrase)
    rules = RULES[scheme]
    if heading is not None:
        for lab, rx_h, _ in rules:
            if rx_h.match(heading):
                return lab, "heading"
    for lab, _, rx_o in rules:
        if rx_o.match(phrase):
            return lab, "opening"
    return None, "none"


def label_nodes(text: str, nodes: list[dict], type_group: str) -> list[dict]:
    """Functional label for every outline node (``outline()['nodes']``), parents before children."""
    scheme = SCHEMES.get(type_group, "civil")
    by_id: dict[int, Labelled] = {}
    out: list[Labelled] = []
    for nd in nodes:
        phrase = strip_enum(first_line(text, nd["start"]))[:40]
        label, source = label_node(phrase, scheme)
        parent = by_id.get(nd["parent"]) if nd["parent"] >= 0 else None
        inherited = parent.label if parent is not None else None
        weak = source == "opening" and WEAK_OPENINGS[scheme].match(phrase) is not None
        if inherited is not None and (label is None or weak):
            label, source = inherited, "inherit"
        if label is None and nd["section"] == "FACTS":
            label, source = "FACTS", "section"      # a layer-1 事實 section is facts unless a rule says otherwise
        item = Labelled(nd["id"], nd["parent"], nd["depth"], nd["section"], nd["start"], nd["end"], label, source, phrase)
        by_id[nd["id"]] = item
        out.append(item)
    return [asdict(x) for x in out]


def coverage(sections: list[dict], labelled: list[dict], body=("REASONS", "FACTS_REASONS", "FACTS")) -> dict[str, int]:
    """Characters of each body section by the label of the deepest node covering them.

    Text before the first node of a section is PREAMBLE; a node's own span excludes its children."""
    chars: dict[str, int] = {}
    children: dict[int, int] = {}
    for x in labelled:
        if x["parent"] >= 0:
            children[x["parent"]] = children.get(x["parent"], 0) + (x["end"] - x["start"])
    for sec in sections:
        if sec["label"] not in body:
            continue
        in_sec = [x for x in labelled if x["section"] == sec["label"] and sec["start"] <= x["start"] < sec["end"]]
        first = min((x["start"] for x in in_sec if x["depth"] == 0), default=sec["end"])
        chars["PREAMBLE"] = chars.get("PREAMBLE", 0) + max(0, first - sec["start"])
        for x in in_sec:
            own = (x["end"] - x["start"]) - children.get(x["id"], 0)
            key = x["label"] or "UNLABELLED"
            chars[key] = chars.get(key, 0) + max(0, own)
    return chars
