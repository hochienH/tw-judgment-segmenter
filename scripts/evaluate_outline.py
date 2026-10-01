#!/usr/bin/env python3
"""Run the outline parser over a jsonl + layer-1 segments and report how well enumerators fit.

Outputs in --run-dir: outline.jsonl (nodes per doc), metrics.json, rejected.tsv (rejected enumerator-like lines,
most common shapes first) and a random sample of accepted items for spot checks.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate import doc_id  # noqa: E402
from segmenter.outline import outline  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    a = ap.parse_args()
    a.run_dir.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            cwd=Path(__file__).parent).stdout.strip()
    (a.run_dir / "config.json").write_text(json.dumps({"texts": str(a.texts), "segments": str(a.segments),
                                                        "git_commit": commit}, indent=2))
    t0 = time.time()
    segs = {json.loads(l)["id"]: json.loads(l) for l in open(a.segments)}
    n_docs = n_nodes = n_rej = docs_with_rej = 0
    depth = Counter()
    reasons = Counter()
    shapes = Counter()
    accepted_sample, rng = [], random.Random(0)
    with open(a.run_dir / "outline.jsonl", "w") as fo:
        for line in open(a.texts):
            r = json.loads(line)
            s = segs.get(doc_id(r))
            if not s or s["status"] not in ("ok", "main_only"):
                continue
            o = outline(r["text"], s["sections"])
            n_docs += 1
            n_nodes += len(o["nodes"])
            n_rej += len(o["rejected"])
            docs_with_rej += bool(o["rejected"])
            depth[max((nd["depth"] for nd in o["nodes"]), default=-1) + 1] += 1
            for rj in o["rejected"]:
                reasons[rj["reason"].split(" ")[0]] += 1
                shapes[f"{rj['style']}{rj['ordinal']}|{rj['reason']}|{rj['line'][:12]}"] += 1
            for nd in o["nodes"]:
                if rng.random() < 0.0005:
                    accepted_sample.append((doc_id(r), nd["depth"], nd["style"], nd["ordinal"], nd["head"]))
            fo.write(json.dumps({"id": doc_id(r), **o}, ensure_ascii=False) + "\n")
    m = {"n_docs": n_docs, "n_nodes": n_nodes, "n_rejected": n_rej,
         "rejected_per_1000_nodes": round(1000 * n_rej / max(1, n_nodes), 2),
         "docs_with_rejections": round(docs_with_rej / max(1, n_docs), 4),
         "max_depth_dist": dict(sorted(depth.items())), "reject_reasons": dict(reasons),
         "elapsed_s": round(time.time() - t0, 1)}
    (a.run_dir / "metrics.json").write_text(json.dumps(m, indent=2, ensure_ascii=False))
    with open(a.run_dir / "rejected.tsv", "w") as f:
        for k, v in shapes.most_common(300):
            f.write(f"{v}\t{k}\n")
    with open(a.run_dir / "accepted_sample.tsv", "w") as f:
        for row in accepted_sample:
            f.write("\t".join(map(str, row)) + "\n")
    print(json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
