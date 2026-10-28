#!/usr/bin/env python3
"""Gold for the layer-2 functional labels: export pre-labelled files, then score the corrections.

  export: annotate_layer2.py export --texts T --segments S --outline O --out DIR [--per-group 刑事:15,民事:15,行政:5]
  score : annotate_layer2.py score  --texts T --segments S --outline O --dir DIR

Every outline node in a body section gets an inline prefix ⟦LABEL⟧ with the label the current rules predict
(⟦?⟧ when they predict nothing). Layer-1 marker lines ⟪LABEL⟫ are shown for orientation only. Annotators
change the word inside ⟦⟧ and nothing else; ⟦X⟧ marks a node that is not a body item at all (ignored).
Scoring recovers the original text (it must match byte for byte), reads the gold label per node and compares
it with the rules as they are now: node accuracy, character-weighted accuracy, per-label precision/recall.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmenter.functional import LABELS, SCHEMES, label_nodes  # noqa: E402

RE_MARK = re.compile(r"⟪[A-Z_]+⟫\r?\n|⟦[^⟧\n]*⟧")
BODY = ("REASONS", "FACTS_REASONS", "FACTS")
DEFAULT_GROUPS = "刑事:15,民事:15,行政:5"

GUIDE = """# 第二層功能標籤標註說明

範圍：第一層內文段落（⟪FACTS⟫、⟪REASONS⟫、⟪FACTS_REASONS⟫）底下的每個大綱項目。⟪…⟫ 行只是定位，不用改。
每個項目的行首有 ⟦標籤⟧，是程式目前的猜測；⟦?⟧ 表示程式沒猜。請把 ⟦⟧ 裡的字改成正確標籤，其他文字一律不要動
（包括空白與換行）。子項目若沒有自己的功能，就填和父項目相同的標籤。這一行不是內文項目（例如引用條文裡的編號）就填 ⟦X⟧。

刑事（REASONS／FACTS_REASONS）：
- PROCEDURE 程序：證據能力、管轄、審理範圍、簡式審判、附帶民訴等程序說明
- ACCUSATION 起訴意旨：公訴意旨、聲請簡易判決處刑意旨、上訴意旨的轉述
- FACT_FINDING 事實認定：訊據被告、證據取捨、犯罪事實之認定、被告辯解之駁斥、無罪理由
- CONVICTION 論罪：所犯法條、罪名、罪數、新舊法比較、共同正犯等
- SENTENCING 科刑：量刑審酌、刑之加減、累犯、緩刑
- CONFISCATION 沒收：沒收、追徵、犯罪所得
- APPEAL 上訴審：原判決之審查、駁回上訴或撤銷改判之理由
- CLOSING 結論：應適用之法條、據上論斷、上訴告知
- FACTS 事實：第一層 ⟪FACTS⟫ 段裡的犯罪事實敘述（程式預設）

民事、行政（FACTS_REASONS／REASONS／FACTS）：
- PROCEDURE 程序：一造辯論、管轄、訴之變更追加、簡易／小額程序之說明
- FACTS_SUMMARY 事實概要：行政判決開頭的事實概要、民事簡易判決的事實摘要
- CLAIM 原告主張：原告／上訴人／聲請人的主張與聲明（含「聲明」「陳述」子項）
- DEFENCE 被告抗辯：被告／被上訴人的答辯與聲明
- UNDISPUTED 不爭執事項
- ISSUES 爭點
- MERITS 實體方面（容器）：只用在「實體方面」這種本身沒有內容的標題行，子項另標
- COURT_FINDING 本院之判斷：法律見解、證據取捨、各項請求之認定、綜上所述
- CLOSING 結論：訴訟費用、假執行、據上論結、兩造其餘攻擊防禦方法不逐一論述

拿不準就填 ⟦?⟧ 並在檔案最後一行以外的地方不要加字；想留話請寫在 notes.md。
"""


def load_jsonl(path: Path, keep: set | None = None) -> dict:
    out = {}
    with open(path, encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            i = r.get("id") or f"{r['court']},{r['jyear']},{r['jcase']},{r['jno']}"
            if keep is None or i in keep:
                out[i] = r
    return out


def with_markers(text: str, sections: list[dict], labels: dict[int, str]) -> str:
    """Insert ⟪LABEL⟫ lines at section starts and ⟦label⟧ prefixes at node line starts, back to front."""
    inserts: list[tuple[int, int, str]] = [(s["start"], 0, f"⟪{s['label']}⟫\n") for s in sections]
    inserts += [(start, 1, f"⟦{lab}⟧") for start, lab in labels.items()]
    out = text
    for offset, _, marker in sorted(inserts, reverse=True):
        out = out[:offset] + marker + out[offset:]
    return out


def strip_markers(annotated: str) -> tuple[str, dict[int, str]]:
    """Remove the markers; return the original text and {original offset: label} for the ⟦⟧ markers."""
    pieces, labels, removed, last = [], {}, 0, 0
    for m in RE_MARK.finditer(annotated):
        pieces.append(annotated[last:m.start()])
        if m.group(0).startswith("⟦"):
            labels[m.start() - removed] = m.group(0)[1:-1].strip()
        removed += m.end() - m.start()
        last = m.end()
    pieces.append(annotated[last:])
    return "".join(pieces), labels


def body_nodes(outline: dict, sections: list[dict]) -> list[dict]:
    return [nd for nd in outline["nodes"] if nd["section"] in BODY]


def export(a) -> None:
    segs = load_jsonl(a.segments)
    ok = {i for i, s in segs.items() if s["doc_kind"] == "判決" and s["status"] == "ok"}
    excluded = set()
    for m in a.exclude_manifest or []:
        excluded |= {l.split("\t")[1] for l in open(m, encoding="utf-8").read().splitlines()[1:]}
    outl = load_jsonl(a.outline, ok - excluded)
    outl = {i: r for i, r in outl.items() if a.min_nodes <= len(body_nodes(r, segs[i]["sections"])) <= a.max_nodes}
    groups = dict((kv.split(":")[0], int(kv.split(":")[1])) for kv in a.per_group.split(","))
    # type_group lives in the texts file: one pass to collect it for the eligible ids, a second to load the picked texts
    group_of: dict[str, str] = {}
    with open(a.texts, encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            i = f"{r['court']},{r['jyear']},{r['jcase']},{r['jno']}"
            if i in outl and r.get("type_group") in groups:
                group_of[i] = r["type_group"]
    rng = random.Random(a.seed)
    picked: list[tuple[str, str]] = []
    for g, k in groups.items():
        pool = sorted(i for i, gg in group_of.items() if gg == g)
        picked += [(i, g) for i in rng.sample(pool, min(k, len(pool)))]
    rng.shuffle(picked)
    texts = load_jsonl(a.texts, keep={i for i, _ in picked})
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / "README.md").write_text(GUIDE, encoding="utf-8")
    with open(a.out / "manifest.tsv", "w", encoding="utf-8") as mf, \
         open(a.out / "predicted.jsonl", "w", encoding="utf-8") as pf:
        mf.write("file\tid\ttype_group\tbody_nodes\n")
        for n, (i, g) in enumerate(picked, 1):
            text = texts[i]["text"]
            nodes = body_nodes(outl[i], segs[i]["sections"])
            labelled = label_nodes(text, outl[i]["nodes"], g)
            pred = {x["id"]: x["label"] for x in labelled}
            marks: dict[int, str] = {}
            for nd in sorted(nodes, key=lambda x: (x["start"], x["depth"])):
                marks.setdefault(nd["start"], pred.get(nd["id"]) or "?")      # chained 六㈠: one marker per line
            body = [s for s in segs[i]["sections"] if s["label"] in BODY]
            name = f"{n:03d}_{g}_{i.replace(',', '_')}.txt"
            with open(a.out / name, "w", encoding="utf-8", newline="") as f:
                f.write(with_markers(text, body, marks))
            mf.write(f"{name}\t{i}\t{g}\t{len(nodes)}\n")
            pf.write(json.dumps({"id": i, "type_group": g, "pred": {str(k): v for k, v in pred.items()}}, ensure_ascii=False) + "\n")
    print(f"{len(picked)} docs exported to {a.out}")


def score(a) -> None:
    manifest = [l.split("\t") for l in open(Path(a.dir) / "manifest.tsv", encoding="utf-8").read().splitlines()[1:]]
    ids = {row[1]: row for row in manifest}
    segs = load_jsonl(a.segments, set(ids))
    outl = load_jsonl(a.outline, set(ids))
    texts = load_jsonl(a.texts, set(ids))
    per_group: dict[str, Counter] = defaultdict(Counter)
    confusion: dict[str, Counter] = defaultdict(Counter)
    problems = []
    for name, i, g, _ in manifest:
        annotated = open(Path(a.dir) / name, encoding="utf-8", newline="").read()
        original, gold = strip_markers(annotated)
        if original != texts[i]["text"]:
            problems.append(f"{name}: text changed, skipped")
            continue
        labelled = label_nodes(texts[i]["text"], outl[i]["nodes"], g)
        children: Counter = Counter()
        for x in labelled:
            if x["parent"] >= 0:
                children[x["parent"]] += x["end"] - x["start"]
        for x in labelled:
            if x["section"] not in BODY or x["start"] not in gold:
                continue
            g_lab = gold[x["start"]]
            if g_lab in ("X", ""):
                continue
            own = max(0, x["end"] - x["start"] - children[x["id"]])
            p_lab = x["label"] or "?"
            per_group[g]["nodes"] += 1
            per_group[g]["chars"] += own
            if p_lab == g_lab:
                per_group[g]["nodes_ok"] += 1
                per_group[g]["chars_ok"] += own
            confusion[g][(g_lab, p_lab)] += 1
    for g, c in sorted(per_group.items()):
        print(f"## {g}: {c['nodes']} nodes, accuracy {c['nodes_ok'] / max(1, c['nodes']):.3f}, "
              f"char-weighted {c['chars_ok'] / max(1, c['chars']):.3f}")
        labels = sorted({k[0] for k in confusion[g]} | {k[1] for k in confusion[g]})
        for lab in labels:
            tp = confusion[g][(lab, lab)]
            gold_n = sum(v for (gl, _), v in confusion[g].items() if gl == lab)
            pred_n = sum(v for (_, pl), v in confusion[g].items() if pl == lab)
            print(f"  {lab:<14} gold {gold_n:>4}  pred {pred_n:>4}  P {tp / pred_n if pred_n else float('nan'):.2f}  R {tp / gold_n if gold_n else float('nan'):.2f}")
        wrong = [(k, v) for k, v in confusion[g].most_common() if k[0] != k[1]][:8]
        print("  top confusions (gold -> pred): " + ", ".join(f"{gl}->{pl} {v}" for (gl, pl), v in wrong))
    for p in problems:
        print(p)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("--texts", type=Path, required=True)
    e.add_argument("--segments", type=Path, required=True)
    e.add_argument("--outline", type=Path, required=True)
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--per-group", default=DEFAULT_GROUPS)
    e.add_argument("--min-nodes", type=int, default=5)
    e.add_argument("--max-nodes", type=int, default=60)
    e.add_argument("--seed", type=int, default=20261028)
    e.add_argument("--exclude-manifest", nargs="*")
    e.set_defaults(func=export)
    s = sub.add_parser("score")
    s.add_argument("--texts", type=Path, required=True)
    s.add_argument("--segments", type=Path, required=True)
    s.add_argument("--outline", type=Path, required=True)
    s.add_argument("--dir", type=Path, required=True)
    s.set_defaults(func=score)
    a = ap.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
