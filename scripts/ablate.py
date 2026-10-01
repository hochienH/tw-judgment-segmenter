#!/usr/bin/env python3
"""Ablation of the special-case rules.

For every switch (and "core" = all switches off) report:
  gold     pooled P/R over the gold sets (layer 1: v1+v2+v3; outline: v1+v2) — these sets were used to
           develop the rules, so "full" scores ~1.0 by construction; the drop when a rule is off is the point
  pop      share of documents in a ~50k sample of the 200k training set whose result changes vs. full

  ablate.py --part l1|outline --run-dir DIR
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.annotate_outline import strip as strip_outline  # noqa: E402
from scripts.annotation import ALIASES, strip_markers  # noqa: E402
from scripts.evaluate import doc_id  # noqa: E402
from segmenter.outline import OUTLINE_FEATURES, outline  # noqa: E402
from segmenter.segment import L1_FEATURES, segment  # noqa: E402

PUBLIC = Path("/nfs/leibniz/data1/hochien894011/statute-contest/datasets/v1/public/texts.jsonl")
TRAIN = Path("/nfs/leibniz/data1/hochien894011/statute-contest/datasets/v1/train/texts_labels.jsonl")
ANN = Path("/nfs/turing/data1/hochien894011/tw-judgment-segmenter/annotation")
L1_GOLD = [("layer1-v1", PUBLIC), ("layer1-v2-heldout", TRAIN), ("layer1-v3-heldout", TRAIN)]
OUTLINE_GOLD = [("outline-v1", TRAIN), ("outline-v2-heldout", TRAIN)]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def in_pop(i: str, every: int) -> bool:
    return int(hashlib.md5(i.encode()).hexdigest()[:8], 16) % every == 0


def manifest(d: Path) -> list[tuple[str, str]]:
    return [(l.split("\t")[0], l.split("\t")[1]) for l in open(d / "manifest.tsv").read().splitlines()[1:]]


def load_texts(path: Path, keep: set, every: int | None) -> dict:
    out = {}
    for line in open(path):
        r = json.loads(line)
        i = doc_id(r)
        if i in keep or (every and in_pop(i, every)):
            out[i] = r["text"]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", choices=["l1", "outline"], required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    ap.add_argument("--every", type=int, default=4, help="population = docs whose id-hash %% every == 0 (~1/every)")
    ap.add_argument("--variant", action="append", default=[],
                    help="extra combination NAME=feat1,feat2 (switched off together); with it, only full + these run")
    a = ap.parse_args()
    a.run_dir.mkdir(parents=True, exist_ok=True)

    # ---- Block 1: gold sets and texts -------------------------------------------------------
    gold_sets = L1_GOLD if a.part == "l1" else OUTLINE_GOLD
    gold = {}                                          # (set, id) -> gold boundaries
    need = {"public": set(), "train": set()}
    for name, src in gold_sets:
        for f, i in manifest(ANN / name):
            raw = open(ANN / name / f, newline="").read()
            if a.part == "l1":
                _, g = strip_markers(raw)
                gold[(name, i)] = {(o, ALIASES.get(l, l)) for o, l in g}
            else:
                gold[(name, i)] = strip_outline(raw)[1]
            need["public" if src == PUBLIC else "train"].add(i)
    texts = load_texts(PUBLIC, need["public"], None) if need["public"] else {}
    texts.update(load_texts(TRAIN, need["train"], a.every))
    pop = [i for i in texts if in_pop(i, a.every) and i in texts and not any(i == k[1] for k in gold)]
    log(f"{a.part}: gold docs {len(gold)}, population {len(pop):,}")

    features = L1_FEATURES if a.part == "l1" else OUTLINE_FEATURES
    variants = [("full", frozenset())] + [(f"-{f}", frozenset({f})) for f in features] + [("core", frozenset(features))]
    if a.variant:
        extra = [(v.split("=")[0], frozenset(x for x in v.split("=")[1].split(",") if x)) for v in a.variant]
        assert all(f in features for _, off in extra for f in off), "unknown feature"
        variants = [("full", frozenset())] + extra
    base_secs = {i: segment(texts[i])["sections"] for i in set(pop) | {k[1] for k in gold}}

    def run(off: frozenset) -> dict:
        if a.part == "l1":
            return {i: [(s["start"], s["label"]) for s in segment(texts[i], off)["sections"]] for i in base_secs}
        return {i: [(n["start"], n["depth"] + 1) for n in outline(texts[i], base_secs[i], off)["nodes"]] for i in base_secs}

    # ---- Block 2: every variant ---------------------------------------------------------------
    rows = []
    baseline = None
    for name, off in variants:
        t0 = time.time()
        res = run(off)
        if baseline is None:
            baseline = res
        tp = fp = fn = exact_tp = docs_exact = 0
        for (gs, i), g in gold.items():
            p = set(res[i])
            if a.part == "l1":
                tp, fp, fn = tp + len(p & g), fp + len(p - g), fn + len(g - p)
                docs_exact += p == g
            else:
                gc, pc = Counter(o for o, _ in g), Counter(o for o, _ in p)
                m = sum((gc & pc).values())
                tp, fp, fn = tp + m, fp + sum(pc.values()) - m, fn + sum(gc.values()) - m
                exact_tp += len(g & p)
                docs_exact += p == g
        changed = sum(res[i] != baseline[i] for i in pop)
        row = {"variant": name, "gold_P": round(tp / max(1, tp + fp), 4), "gold_R": round(tp / max(1, tp + fn), 4),
               "gold_docs_exact": f"{docs_exact}/{len(gold)}", "pop_docs_changed": changed,
               "pop_share_changed": round(changed / len(pop), 4), "secs": round(time.time() - t0, 1)}
        if a.part == "outline":
            row["gold_depth_acc"] = round(exact_tp / max(1, tp), 4)
        rows.append(row)
        log(json.dumps(row, ensure_ascii=False))
    (a.run_dir / f"ablation_{a.part}{'_combos' if a.variant else ''}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    log("done")


if __name__ == "__main__":
    main()
