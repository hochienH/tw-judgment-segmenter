#!/usr/bin/env python3
"""Body-structure statistics over the whole-corpus segmentation output (finished archives only).

Counts documents, and distinct cases (court, jyear, jcase, jno), per type group x court level x period, by body
structure: FACTS+REASONS (separate), FACTS_REASONS (merged), REASONS only, other.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter, defaultdict
from pathlib import Path

PERIODS = [(1996, 2005), (2006, 2015), (2016, 2020), (2021, 2026)]


def type_group(folder: str) -> str:
    for t in ("刑事補償", "刑事", "民事", "行政"):
        if folder.endswith(t):
            return "其他" if t == "刑事補償" else t
    return "其他"


def court_level(folder: str) -> str:
    if folder.startswith("最高"):
        return "最高"
    if "簡易庭" in folder:
        return "簡易庭"
    if "地方庭" in folder or "地方法院" in folder or "少年及家事法院" in folder:
        return "地院"
    if "高等" in folder:
        return "高院"
    return "專業"


def period(year: int) -> str:
    return next(f"{lo}-{hi}" for lo, hi in PERIODS if lo <= year <= hi)


def structure(sections: list) -> str:
    labs = {s[0] for s in sections}
    if {"FACTS", "REASONS"} <= labs:
        return "facts+reasons"
    if "FACTS_REASONS" in labs:
        return "merged"
    if "REASONS" in labs:
        return "reasons_only"
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    a = ap.parse_args()
    docs = defaultdict(Counter)                      # (type, level, period) -> structure counts (documents)
    cases = defaultdict(set)                         # (type, structure) -> distinct case keys
    n_arch = 0
    for done in sorted(a.run.glob("*.done")):
        n_arch += 1
        year = int(done.stem[:4])
        with gzip.open(done.with_suffix(".jsonl.gz"), "rt", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                folder = r["file"].split("/")[1] if "/" in r["file"] else ""
                tg, lv, st = type_group(folder), court_level(folder), structure(r["sections"])
                docs[(tg, lv, period(year))][st] += 1
                cases[(tg, st)].add(tuple(r["key"]))
    print(f"archives: {n_arch}")
    print("\n== documents by type: structure shares")
    by_type = defaultdict(Counter)
    for (tg, _, _), c in docs.items():
        by_type[tg].update(c)
    for tg, c in sorted(by_type.items(), key=lambda x: -sum(x[1].values())):
        tot = sum(c.values())
        print(f"{tg}\t{tot:>10,}\t" + "\t".join(f"{k}={c[k]:,} ({c[k] / tot:.1%})"
                                                 for k in ("facts+reasons", "merged", "reasons_only", "other")))
    print("\n== distinct cases with facts+reasons:", {tg: f"{len(cases[(tg, 'facts+reasons')]):,}" for tg in by_type})
    print("\n== facts+reasons documents by type x level x period")
    rows = sorted(((k, c["facts+reasons"], sum(c.values())) for k, c in docs.items()), key=lambda x: x[0])
    for (tg, lv, pr), fr, tot in rows:
        if fr:
            print(f"{tg}\t{lv}\t{pr}\t{fr:>8,} / {tot:>9,} ({fr / tot:.1%})")


if __name__ == "__main__":
    main()
