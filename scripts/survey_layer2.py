#!/usr/bin/env python3
"""Survey enumerators inside layer-1 body sections (REASONS, FACTS_REASONS, FACTS) to design layer 2.

Reports: which enumerator styles occur, the order in which styles first appear in a document (the implied
hierarchy), and the commonest phrases right after the enumerator at the first and second level.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate import doc_id  # noqa: E402

ENUMS = [  # (style, regex at line start after optional spaces); order = check order
    ("壹", r"[壹貳參叁肆伍陸柒捌玖拾]+[、．.]"),
    ("甲", r"[甲乙丙丁戊己庚辛壬癸][、．.]"),
    ("一", r"[一二三四五六七八九十]+[、．.]"),
    ("㈠", r"[㈠㈡㈢㈣㈤㈥㈦㈧㈨㈩]、?|[（(][一二三四五六七八九十]+[）)]"),
    ("⑴", r"[⑴⑵⑶⑷⑸⑹⑺⑻⑼⑽⑾⑿]|[（(][0-9０-９]+[）)]"),
    ("1.", r"[0-9０-９]+[、．.](?![0-9０-９])"),
    ("①", r"[①②③④⑤⑥⑦⑧⑨⑩]"),
    ("A", r"[A-ZＡ-Ｚa-z][、．.]"),
]
RE_ENUM = [(st, re.compile(rf"^[\s　]*({p})[\s　]*(.{{0,14}})")) for st, p in ENUMS]
BODY = {"REASONS", "FACTS_REASONS", "FACTS"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    segs = {json.loads(l)["id"]: json.loads(l) for l in open(a.segments)}
    style_docs = Counter()
    order = Counter()
    after = defaultdict(Counter)            # (type_group, depth, style) -> phrase after enumerator
    n = 0
    for line in open(a.texts):
        r = json.loads(line)
        s = segs.get(doc_id(r))
        if not s or s["status"] != "ok":
            continue
        n += 1
        seen = []
        for sec in s["sections"]:
            if sec["label"] not in BODY:
                continue
            for ln in r["text"][sec["start"]:sec["end"]].split("\n"):
                for st, rx in RE_ENUM:
                    m = rx.match(ln)
                    if m:
                        if st not in seen:
                            seen.append(st)
                        depth = seen.index(st)
                        head = re.sub(r"[\s　]+", "", m.group(2))[:8]
                        after[(r.get("type_group", ""), depth, st)][head] += 1
                        break
        style_docs.update(set(seen))
        order[">".join(seen[:4])] += 1
    out = {"n_docs": n, "style_docs": style_docs.most_common(), "first_appearance_order": order.most_common(25),
           "after_enumerator": {f"{k[0]}|d{k[1]}|{k[2]}": v.most_common(25)
                                for k, v in sorted(after.items()) if k[1] <= 1 and sum(v.values()) >= 200}}
    a.out.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: out[k] for k in ("n_docs", "style_docs", "first_appearance_order")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
