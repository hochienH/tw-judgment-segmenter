#!/usr/bin/env python3
"""Run the layer-2 functional labels over a sample and report coverage.

  label_layer2.py --texts T --segments S --outline O --out DIR [--limit N]

Inputs are the texts (``texts_labels.jsonl``: court, jyear, jcase, jno, type_group, text), the layer-1 segments
(``segments.jsonl``) and the outline (``outline.jsonl``), keyed by ``court,jyear,jcase,jno``. Only 判決 with
status ok are labelled. Writes ``labels.jsonl`` (one row per document: id, type_group, nodes with label/source,
coverage in characters), ``coverage.json`` and ``coverage.md`` (per type_group: share of body characters by label,
share of documents that have each label, label sources), and ``unlabelled.tsv`` (the commonest stripped openings
of depth-0/1 nodes that got no label, per type_group, to extend the rules).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmenter.functional import LABELS, SCHEMES, coverage, label_nodes  # noqa: E402


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parents[1]).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def load_jsonl(path: Path, keep: set[str] | None = None) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with open(path, encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            if keep is None or r["id"] in keep:
                out[r["id"]] = r
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--outline", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, help="stop after N labelled documents (smoke test)")
    ap.add_argument("--top", type=int, default=80)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "config.json").write_text(json.dumps(
        {"texts": str(a.texts), "segments": str(a.segments), "outline": str(a.outline), "limit": a.limit,
         "git_commit": git_commit(), "started": datetime.now().isoformat(timespec="seconds")}, indent=2))

    log("reading segments")
    segments = load_jsonl(a.segments)
    keep = {i for i, s in segments.items() if s["doc_kind"] == "判決" and s["status"] == "ok"}
    log(f"{len(segments):,} docs, {len(keep):,} 判決/ok")
    log("reading outline")
    outline = load_jsonl(a.outline, keep)
    log(f"{len(outline):,} outlines")

    chars: dict[str, Counter] = defaultdict(Counter)          # group -> label -> chars
    doc_has: dict[str, Counter] = defaultdict(Counter)        # group -> label -> docs with it
    sources: dict[str, Counter] = defaultdict(Counter)        # group -> source -> nodes
    unlabelled: dict[str, Counter] = defaultdict(Counter)     # group -> phrase[:8] -> nodes (depth <= 1)
    docs: Counter = Counter()
    n_nodes = 0
    log("labelling")
    with open(a.out / "labels.jsonl", "w", encoding="utf-8") as out, open(a.texts, encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            doc_id = f"{r['court']},{r['jyear']},{r['jcase']},{r['jno']}"
            if doc_id not in keep or doc_id not in outline:
                continue
            group = r.get("type_group", "")
            labelled = label_nodes(r["text"], outline[doc_id]["nodes"], group)
            cov = coverage(segments[doc_id]["sections"], labelled)
            docs[group] += 1
            n_nodes += len(labelled)
            chars[group].update(cov)
            for lab in {x["label"] for x in labelled if x["label"]}:
                doc_has[group][lab] += 1
            for x in labelled:
                sources[group][x["source"]] += 1
                if x["label"] is None and x["depth"] <= 1:
                    unlabelled[group][x["phrase"][:8]] += 1
            out.write(json.dumps({"id": doc_id, "type_group": group, "coverage": cov,
                                  "nodes": [{k: x[k] for k in ("id", "depth", "label", "source")} for x in labelled]},
                                 ensure_ascii=False) + "\n")
            if sum(docs.values()) % 10_000 == 0:
                log(f"{sum(docs.values()):,} docs")
            if a.limit and sum(docs.values()) >= a.limit:
                break
    log(f"{sum(docs.values()):,} docs, {n_nodes:,} nodes")

    report = {}
    lines = ["# Layer-2 functional labels: coverage", ""]
    for group in sorted(docs):
        total = sum(chars[group].values()) or 1
        order = LABELS[SCHEMES.get(group, "civil")] + ["FACTS", "PREAMBLE", "UNLABELLED"]
        report[group] = {
            "docs": docs[group],
            "chars_share": {lab: chars[group][lab] / total for lab in order if chars[group][lab]},
            "docs_with_label": {lab: doc_has[group][lab] / docs[group] for lab in order if doc_has[group][lab]},
            "node_sources": dict(sources[group]),
            "unlabelled_top": unlabelled[group].most_common(a.top),
        }
        lines.append(f"## {group}: {docs[group]:,} docs")
        lines.append("| label | share of body chars | docs with it |")
        lines.append("|---|---|---|")
        for lab in order:
            if chars[group][lab] or doc_has[group][lab]:
                lines.append(f"| {lab} | {chars[group][lab] / total:.1%} | {doc_has[group][lab] / docs[group]:.1%} |")
        ns = sources[group]; tot = sum(ns.values()) or 1
        lines.append("node sources: " + ", ".join(f"{k} {v / tot:.1%}" for k, v in ns.most_common()))
        lines.append("unlabelled depth<=1 openings: " + "、".join(f"{p}({n})" for p, n in unlabelled[group].most_common(40)))
        lines.append("")
    (a.out / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (a.out / "coverage.md").write_text("\n".join(lines), encoding="utf-8")
    with open(a.out / "unlabelled.tsv", "w", encoding="utf-8") as h:
        h.write("type_group\tphrase\tnodes\n")
        for group in sorted(unlabelled):
            for p, n in unlabelled[group].most_common(a.top * 3):
                h.write(f"{group}\t{p}\t{n}\n")
    log(f"wrote {a.out}/coverage.md")


if __name__ == "__main__":
    main()
