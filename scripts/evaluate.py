#!/usr/bin/env python3
"""Run the layer-1 segmenter over a jsonl of judgments and report how well it parses.

Input lines need "id" and "text"; "type_group", "court_level", "period" are used for strata if present.
Outputs in --run-dir:
  segments.jsonl   per-document segmentation (offsets into the original text)
  metrics.json     status rates overall, by doc kind, by stratum; most common section sequences
  misses.tsv       short standalone lines in non-ok documents that were NOT recognised as headings,
                   most common first: the list to read when hunting for missed heading variants
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmenter import segment  # noqa: E402
from segmenter.segment import RE_APPENDIX_LAW, RE_ATTACH, RE_BODY, RE_DATE_LINE  # noqa: E402

def doc_id(r: dict) -> str:
    return r.get("id") or ",".join(str(r[k]) for k in ("court", "jyear", "jcase", "jno"))


RE_SHORT = re.compile(r"^[一-鿿、：:（）()0-9０-９]{1,14}$")


def candidate_misses(text: str) -> list[str]:
    """Short standalone lines that look like headings but matched no pattern."""
    out = []
    for line in text.split("\n"):
        s = re.sub(r"[\s　]+", "", line)
        if not s or not RE_SHORT.match(s) or s.endswith(("。", "，")):
            continue
        if RE_BODY.match(line) or RE_ATTACH.match(line) or RE_APPENDIX_LAW.match(line) or RE_DATE_LINE.match(line):
            continue
        out.append(s.rstrip("：:"))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--run-dir", type=Path, required=True)
    args = ap.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                            cwd=Path(__file__).parent).stdout.strip()
    (args.run_dir / "config.json").write_text(json.dumps({"input": str(args.input), "git_commit": commit}, indent=2))
    t0 = time.time()

    status = Counter()
    by_kind = defaultdict(Counter)
    by_stratum = defaultdict(Counter)
    seqs = defaultdict(Counter)
    missing = Counter()
    misses = Counter()
    n = 0
    with open(args.input) as fin, open(args.run_dir / "segments.jsonl", "w") as fout:
        for line in fin:
            r = json.loads(line)
            seg = segment(r["text"])
            n += 1
            st = seg["status"]
            status[st] += 1
            by_kind[seg["doc_kind"] or "(unknown)"][st] += 1
            by_stratum[f"{r.get('type_group', '')}|{r.get('period', '')}"][st] += 1
            seqs[seg["doc_kind"] or "(unknown)"][">".join(s["label"] for s in seg["sections"])] += 1
            if st == "partial":
                missing.update(seg["missing"])
                if not seg["order_ok"]:
                    missing["ORDER"] += 1
                misses.update(set(candidate_misses(r["text"])))
            fout.write(json.dumps({"id": doc_id(r), **seg}, ensure_ascii=False) + "\n")

    def rates(c: Counter) -> dict:
        tot = sum(c.values())
        return {"n": tot, **{k: round(v / tot, 4) for k, v in sorted(c.items())}}

    metrics = {
        "n": n,
        "status": rates(status),
        "partial_missing": dict(missing.most_common()),
        "by_kind": {k: rates(v) for k, v in sorted(by_kind.items(), key=lambda x: -sum(x[1].values()))},
        "by_stratum": {k: rates(v) for k, v in sorted(by_stratum.items())},
        "top_sequences": {k: v.most_common(8) for k, v in seqs.items() if sum(v.values()) >= 30},
        "elapsed_s": round(time.time() - t0, 1),
    }
    (args.run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    with open(args.run_dir / "misses.tsv", "w") as f:
        for s, c in misses.most_common(300):
            f.write(f"{c}\t{s}\n")
    print(json.dumps({k: metrics[k] for k in ("n", "status", "partial_missing", "elapsed_s")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
