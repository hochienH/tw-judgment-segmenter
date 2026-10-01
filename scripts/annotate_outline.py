#!/usr/bin/env python3
"""Gold for the enumeration outline: export pre-labelled files, then score corrections.

  export: annotate_outline.py export --texts T --segments S --outline O --out DIR [--exclude-manifest M ...]
  score : annotate_outline.py score  --texts T --outline O --out DIR

Each item line in a body section gets an inline prefix ⟦d⟧ (d = depth, 1 = top). ⟦d*⟧ marks a list the
parser thinks may be quoted (nested_restart). Layer-1 marker lines ⟪LABEL⟫ are shown for orientation only.
Annotators fix depth numbers and add or delete ⟦d⟧ prefixes, changing nothing else.
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
from scripts.annotation import load_jsonl  # noqa: E402

RE_ITEM = re.compile(r"⟦(\d+)\*?⟧")
RE_L1 = re.compile(r"⟪[A-Z_]+⟫\r?\n")
# Big5 custom glyphs (PUA) are invisible on screen; a visible hint ⟦U+F6B0⟧ goes in front of a line-initial one
RE_HINT = re.compile(r"⟦U\+[0-9A-F]{4}⟧")
RE_LINE_PUA = re.compile(r"^([ 　\t]*)([\ue000-\uf8ff])", re.M)


def add_pua_hints(chunk: str) -> str:
    return RE_LINE_PUA.sub(lambda m: f"{m.group(1)}⟦U+{ord(m.group(2)):04X}⟧{m.group(2)}", chunk)
STRATA = {0: 5, 1: 20, 2: 15, 3: 10}           # max outline depth (3 = 3 or more) -> number of docs

GUIDE = """# 大綱（編號層級）標註說明

範圍：只看第一層的內文段落（⟪FACTS⟫、⟪REASONS⟫、⟪FACTS_REASONS⟫、⟪BODY_OTHER⟫ 底下）。
⟪…⟫ 這種行只是幫你定位，不用改。

每個大綱項目的行首有前綴 ⟦d⟧，d 是層級，最外層是 1。例：⟦1⟧一、…　⟦2⟧㈠…　⟦3⟧⑴…
⟦d*⟧ 表示程式懷疑這是引用文字裡的清單（例如引用條文的一、二、），請特別確認。
⟦U+F6B0⟧ 這類提示表示後面緊跟一個「看不見」的 Big5 造字（私用區字元），常常是編號：
  U+F6B0 起依序是 一、二、三…（F6A6 = 十一、），U+F674 起是 (十一)(十二)…，U+F4DA 起是 (21)(22)…。
  提示本身不用改也不用刪，評分時會自動忽略。

什麼算大綱項目：
- 算：法院本身用來組織內文的編號，包含子清單；也包含法院整理當事人主張時用的編號
  （例如「原告主張：㈠…㈡…」）。
- 不算：逐字引用的條文或文件原文中的編號（例如「刑法第75條規定：一、…二、…」、引號內的書狀原文）、
  金額或號碼的一部分（「一一九、０００元」）、交叉引用（「如理由欄丙、肆、四、㈠所述」）、
  斷行後剛好出現在行首的數字。

請只做三件事：
1. 漏標的項目：在該行最前面加 ⟦d⟧
2. 多標或不算的項目：刪掉該行的 ⟦d⟧
3. 層級錯：改 d 的數字（星號可留可刪，不影響評分）
不要修改任何原文文字（包括空白與換行）。
"""


def export(a) -> None:
    excluded = set()
    for m in a.exclude_manifest or []:
        excluded |= {l.split("\t")[1] for l in open(m).read().splitlines()[1:]}
    segs = load_jsonl(a.segments)
    outl = {}
    for line in open(a.outline):
        r = json.loads(line)
        if r["id"] not in excluded and segs.get(r["id"], {}).get("status") == "ok":
            outl[r["id"]] = r
    by_depth = defaultdict(list)
    for i, r in outl.items():
        d = max((n["depth"] for n in r["nodes"]), default=-1) + 1
        by_depth[min(d, 3)].append(i)
    rng = random.Random(a.seed)
    picked = []
    for d, k in STRATA.items():
        picked += [(i, d) for i in rng.sample(sorted(by_depth[d]), k)]
    rng.shuffle(picked)
    texts = load_jsonl(a.texts, keep={i for i, _ in picked})
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out / "README.md").write_text(GUIDE)
    with open(a.out / "manifest.tsv", "w") as mf:
        mf.write("file\tid\tdepth_stratum\tstratum_size\n")
        for n, (i, d) in enumerate(picked, 1):
            text = texts[i]["text"]
            items = {nd["start"]: f"⟦{nd['depth'] + 1}{'*' if nd['nested_restart'] else ''}⟧" for nd in outl[i]["nodes"]}
            l1 = {s["start"]: s["label"] for s in segs[i]["sections"]}
            out, pos = [], 0
            for m in re.finditer(r"[^\n]*\n?", text):
                if not m.group(0):
                    break
                if pos in l1:
                    out.append(f"⟪{l1[pos]}⟫\n")
                out.append(items.get(pos, "") + add_pua_hints(m.group(0)))
                pos += len(m.group(0))
            name = f"{n:03d}_{i.replace('/', '_')}.txt"
            with open(a.out / name, "w", newline="") as fo:
                fo.write("".join(out))
            mf.write(f"{name}\t{i}\t{d}\t{len(by_depth[d])}\n")
    print(f"exported {len(picked)} files to {a.out}; stratum sizes: { {d: len(v) for d, v in by_depth.items()} }")


def strip(annotated: str) -> tuple[str, set]:
    annotated = RE_HINT.sub("", RE_L1.sub("", annotated))
    out, gold, pos, last = [], set(), 0, 0
    for m in RE_ITEM.finditer(annotated):
        piece = annotated[last:m.start()]
        out.append(piece)
        pos += len(piece)
        gold.add((pos, int(m.group(1))))
        last = m.end()
    out.append(annotated[last:])
    return "".join(out), gold


def score(a) -> None:
    manifest = [l.split("\t") for l in open(a.out / "manifest.tsv").read().splitlines()[1:]]
    ids = {r[1] for r in manifest}
    texts = load_jsonl(a.texts, keep=ids)
    outl = {r["id"]: r for r in map(json.loads, open(a.outline)) if r["id"] in ids}
    tot = Counter()
    per_stratum = defaultdict(Counter)
    rejected = []
    for name, i, d, size in manifest:
        with open(a.out / name, newline="") as f:
            text, gold = strip(f.read())
        if text != texts[i]["text"]:
            rejected.append(name)
            continue
        pred = {(nd["start"], nd["depth"] + 1) for nd in outl[i]["nodes"]}
        gp, pp = {o for o, _ in gold}, {o for o, _ in pred}
        c = Counter(item_tp=len(gp & pp), item_fp=len(pp - gp), item_fn=len(gp - pp),
                    exact_tp=len(gold & pred), doc=1, doc_exact=int(gold == pred))
        tot.update(c)
        per_stratum[d].update(c)

    def pr(c):
        p = c["item_tp"] / max(1, c["item_tp"] + c["item_fp"])
        r = c["item_tp"] / max(1, c["item_tp"] + c["item_fn"])
        return {"item_precision": round(p, 4), "item_recall": round(r, 4),
                "depth_acc_on_matched": round(c["exact_tp"] / max(1, c["item_tp"]), 4),
                "docs_exact": f"{c['doc_exact']}/{c['doc']}"}

    print(json.dumps({"all": pr(tot), "by_depth_stratum": {k: pr(v) for k, v in sorted(per_stratum.items())},
                      "rejected_files": rejected}, ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "score"])
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--segments", type=Path)
    ap.add_argument("--outline", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=20261003)
    ap.add_argument("--exclude-manifest", type=Path, nargs="*")
    a = ap.parse_args()
    export(a) if a.cmd == "export" else score(a)


if __name__ == "__main__":
    main()
