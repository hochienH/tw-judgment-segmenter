#!/usr/bin/env python3
"""Survey what the outline nodes start with, to design the layer-2 functional labels.

Reads the layer-2 outline (``outline.jsonl``), the layer-1 segments (``segments.jsonl``, for doc_kind and status)
and the texts (``texts_labels.jsonl``, for type_group), all keyed by the judgment id. For every outline node the
enumerator is stripped from ``head`` (the first 20 characters of the line, whitespace removed) and the rest is
classified:

  heading   a short label, on its own line or before a colon: 程序方面, 原告主張：, 本院之判斷
  opening   a sentence start: 按刑法第…, 查被告…, 核被告所為…, 據上論斷…

Per (type_group, section label, depth) the script counts headings (full phrase) and sentence openings (first 2 and
first 4 characters), and per document the sequence of depth-0 headings (the document skeleton). Only
``doc_kind == 判決`` with ``status == ok`` are used.

  survey_layer2_phrases.py --outline O --segments S --texts T --out DIR [--max-depth 2]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmenter.outline import RE_ENUMS, ordinal, pua_enum  # noqa: E402

BODY = ("REASONS", "FACTS_REASONS", "FACTS")
HEADING_MAX = 12
SHORT_LINE = 10
RE_HEADING_COLON = re.compile(r"^([^，。；：:、（）()「」]{1,%d})[：:]" % HEADING_MAX)
RE_SENTENCE_PUNCT = re.compile(r"[，。；]")


def strip_enum(head: str) -> str:
    """Drop up to three leading enumerators (六㈠ gives two) the way outline.match_enum reads them."""
    rest = head
    for _ in range(3):
        if not rest:
            break
        hit = pua_enum(rest[0])
        if hit:
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


def classify(phrase: str, short_line: bool) -> tuple[str, str]:
    """('heading', label) or ('opening', text).

    ``head`` keeps only the first 20 characters of the line, so a line that was cut off is never a bare heading;
    ``short_line`` says the whole line fit (len(head) < 20)."""
    m = RE_HEADING_COLON.match(phrase)
    if m:
        return "heading", m.group(1)
    if short_line and len(phrase) <= SHORT_LINE and not RE_SENTENCE_PUNCT.search(phrase):
        return "heading", phrase
    return "opening", phrase


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parents[1]).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--outline", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--texts", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-depth", type=int, default=2)
    ap.add_argument("--top", type=int, default=60)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "config.json").write_text(json.dumps(
        {"outline": str(a.outline), "segments": str(a.segments), "texts": str(a.texts), "max_depth": a.max_depth,
         "git_commit": git_commit(), "started": datetime.now().isoformat(timespec="seconds")}, indent=2))

    log("reading segments (doc_kind, status)")
    keep: dict[str, bool] = {}
    with open(a.segments, encoding="utf-8") as h:
        for line in h:
            s = json.loads(line)
            keep[s["id"]] = s["doc_kind"] == "判決" and s["status"] == "ok"
    log(f"{len(keep):,} docs, {sum(keep.values()):,} 判決/ok")

    log("reading texts (type_group)")
    group: dict[str, str] = {}
    with open(a.texts, encoding="utf-8") as h:
        for line in h:
            r = json.loads(line)
            doc_id = f"{r['court']},{r['jyear']},{r['jcase']},{r['jno']}"
            if keep.get(doc_id):
                group[doc_id] = r.get("type_group", "")
    log(f"{len(group):,} docs with type_group")

    headings: dict[tuple, Counter] = defaultdict(Counter)   # (group, section, depth) -> heading phrase
    open2: dict[tuple, Counter] = defaultdict(Counter)      # (group, section, depth) -> first 2 chars
    open4: dict[tuple, Counter] = defaultdict(Counter)      # (group, section, depth) -> first 4 chars
    kinds: dict[tuple, Counter] = defaultdict(Counter)      # (group, section, depth) -> heading / opening
    skeletons: dict[str, Counter] = defaultdict(Counter)    # group -> tuple of depth-0 headings
    docs_with_heading0: Counter = Counter()
    docs_per_group: Counter = Counter()
    n_nodes = 0
    log("reading outline")
    with open(a.outline, encoding="utf-8") as h:
        for i, line in enumerate(h, 1):
            r = json.loads(line)
            g = group.get(r["id"])
            if g is None:
                continue
            docs_per_group[g] += 1
            skeleton: list[str] = []
            any_heading0 = False
            for nd in r["nodes"]:
                if nd["depth"] > a.max_depth or nd["section"] not in BODY:
                    continue
                n_nodes += 1
                phrase = strip_enum(nd["head"])
                kind, text = classify(phrase, short_line=len(nd["head"]) < 20)
                key = (g, nd["section"], nd["depth"])
                kinds[key][kind] += 1
                if kind == "heading":
                    headings[key][text] += 1
                    if nd["depth"] == 0:
                        skeleton.append(text)
                        any_heading0 = True
                else:
                    open2[key][text[:2]] += 1
                    open4[key][text[:4]] += 1
                    if nd["depth"] == 0:
                        skeleton.append("…")
            if any_heading0:
                docs_with_heading0[g] += 1
            skeletons[g][" > ".join(skeleton[:8])] += 1
            if i % 50_000 == 0:
                log(f"{i:,} outline rows")
    log(f"{n_nodes:,} nodes in body sections (depth <= {a.max_depth})")

    def dump(d: dict[tuple, Counter]) -> dict:
        return {"|".join(map(str, k)): v.most_common(a.top) for k, v in sorted(d.items())}

    result = {
        "docs_per_group": dict(docs_per_group),
        "docs_with_depth0_heading": dict(docs_with_heading0),
        "node_kinds": dump(kinds),
        "headings": dump(headings),
        "openings_2": dump(open2),
        "openings_4": dump(open4),
        "skeletons": {g: c.most_common(40) for g, c in sorted(skeletons.items())},
    }
    (a.out / "survey.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = ["# Layer-2 phrase survey", ""]
    for g in sorted(docs_per_group):
        lines.append(f"## {g}: {docs_per_group[g]:,} docs, {docs_with_heading0[g]:,} with a depth-0 heading")
        for key in sorted(k for k in kinds if k[0] == g):
            total = sum(kinds[key].values())
            if total < 200:
                continue
            _, section, depth = key
            lines.append(f"### {section} depth {depth}: {total:,} nodes, "
                         f"heading {kinds[key]['heading'] / total:.1%}, opening {kinds[key]['opening'] / total:.1%}")
            lines.append("headings: " + "、".join(f"{p}({n})" for p, n in headings[key].most_common(30)))
            lines.append("openings(4): " + "、".join(f"{p}({n})" for p, n in open4[key].most_common(30)))
            lines.append("")
        lines.append("skeletons (depth-0 headings in order; … = sentence item):")
        for s, n in skeletons[g].most_common(25):
            lines.append(f"  {n:>7}  {s}")
        lines.append("")
    (a.out / "survey.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"wrote {a.out / 'survey.json'} and survey.md")


if __name__ == "__main__":
    main()
