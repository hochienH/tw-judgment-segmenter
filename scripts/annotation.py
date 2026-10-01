#!/usr/bin/env python3
"""Export pre-labelled documents for manual correction, and read the corrections back as gold.

  export: python scripts/annotation.py export --input texts.jsonl --segments segments.jsonl --out DIR [--n 50]
  score : python scripts/annotation.py score  --input texts.jsonl --segments segments.jsonl --out DIR

Each exported file is the original text with one marker line ⟪LABEL⟫ inserted before the line where a
section starts. The annotator moves, relabels, adds or deletes marker lines and changes nothing else.
`score` strips the markers, checks that the remaining text is byte-identical to the original, and
reports boundary precision/recall (a boundary = (offset, label)) against the segmenter's prediction.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ["HEADER", "MAIN", "FACTS", "REASONS", "FACTS_REASONS", "BODY_OTHER", "CLOSING", "APPENDIX_LAW",
          "ATTACHMENT", "UNSTRUCTURED"]

GUIDE = """# 第一層分段標註說明

每個 .txt 是一篇原文，程式已在每段開頭插入一行 ⟪標籤⟫。請只做以下三件事：
1. 移動標記行到正確的段落起點（標記行要自成一行，放在該段第一行的正上方）
2. 改標籤名稱，或增刪標記行
3. 不要修改任何原文文字（包括空白與換行）；改到原文的檔案會被拒收

標籤：
  HEADER         標題、案號、當事人、案由，到第一個段落標題前
  MAIN           主文
  FACTS          事實／犯罪事實／事實概要…（與理由分開寫時）
  REASONS        理由
  FACTS_REASONS  事實及理由（合寫）／事實及理由要領…
  BODY_OTHER     其他頂層內文標題（證據並所犯法條、處罰條文…）
  CLOSING        從第一個日期行（中華民國…年…月…日）開始：法院、法官、正本證明、書記官
  APPENDIX_LAW   附錄 論罪科刑法條
  ATTACHMENT     附件／附表／附記／附註／計算書（附在後面的起訴書也是 ATTACHMENT）
  UNSTRUCTURED   沒有任何段落標題的一段式文書主體（例如命補繳裁判費裁定）

沒有換行的文件（例如憲法法庭裁判整篇只有一行）：直接把標記打在行內、該段第一個字前面，
例如「…本庭裁定如下：⟪MAIN⟫主文本件不受理。⟪REASONS⟫理由一、…」，不需要換行。

不確定的地方，在檔案最後加一行「# NOTE: …」寫下理由即可。
"""


def load_jsonl(path: Path) -> dict:
    return {r["id"]: r for r in map(json.loads, open(path))}


def _lines(text: str) -> list[str]:
    """Split on \n only, keeping it (same as the segmenter; splitlines() also breaks on rare control chars)."""
    return [m.group(0) for m in re.finditer(r"[^\n]*\n?", text) if m.group(0)]


def with_markers(text: str, sections: list[dict]) -> str:
    starts = {s["start"]: s["label"] for s in sections if s["label"] != "HEADER"}
    out, pos = ["⟪HEADER⟫\n"], 0
    for line in _lines(text):
        if pos in starts:
            out.append(f"⟪{starts[pos]}⟫\n")
        out.append(line)
        pos += len(line)
    return "".join(out)


RE_TOKEN = re.compile(r"⟪([A-Z_]+)⟫")
RE_NOTE_LINE = re.compile(r"^# NOTE:.*\n?", re.M)


def strip_markers(annotated: str) -> tuple[str, list[tuple[int, str]]]:
    """Remove markers and return (original text, [(offset, label)]).

    A marker alone on its line (as exported) is removed together with its newline. A marker typed inside
    a line (needed for documents without line breaks, e.g. 憲法法庭 decisions) is removed on its own.
    """
    annotated = RE_NOTE_LINE.sub("", annotated)
    out, bounds, last, pos = [], [], 0, 0
    for m in RE_TOKEN.finditer(annotated):
        piece = annotated[last:m.start()]
        out.append(piece)
        pos += len(piece)
        bounds.append((pos, m.group(1)))
        at_line_start = m.start() == 0 or annotated[m.start() - 1] == "\n"
        # editors may save the marker line with \r\n (matching the source's line endings)
        eol = 2 if annotated.startswith("\r\n", m.end()) else 1 if annotated.startswith("\n", m.end()) else 0
        last = m.end() + (eol if at_line_start else 0)
    out.append(annotated[last:])
    return "".join(out), bounds


def export(args) -> None:
    texts, segs = load_jsonl(args.input), load_jsonl(args.segments)
    groups = defaultdict(list)
    for i, s in segs.items():
        if s["status"] == "formulaic":
            continue
        groups[(s["doc_kind"] or "?", s["status"], texts[i].get("type_group", ""))].append(i)
    # oversample the uncertain statuses: they are where the rules are most likely wrong
    quota = {"ok": 0.6, "main_only": 0.15, "unstructured": 0.1, "partial": 0.15}
    rng = random.Random(args.seed)
    picked = []
    for st, share in quota.items():
        keys = [k for k in groups if k[1] == st]
        want = round(args.n * share)
        pool = [(k, i) for k in keys for i in groups[k]]
        rng.shuffle(pool)
        seen = Counter()
        for k, i in pool:                         # round-robin over strata
            if len([p for p in picked if segs[p]["status"] == st]) >= want:
                break
            if seen[k] <= min(seen.values(), default=0):
                picked.append(i)
                seen[k] += 1
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "README.md").write_text(GUIDE)
    with open(args.out / "manifest.tsv", "w") as f:
        f.write("file\tid\tdoc_kind\tstatus\ttype_group\tperiod\n")
        for n, i in enumerate(picked, 1):
            name = f"{n:03d}_{i}.txt"
            with open(args.out / name, "w", newline="") as fo:   # keep \r\n exactly as in the source
                fo.write(with_markers(texts[i]["text"], segs[i]["sections"]))
            s = segs[i]
            f.write(f"{name}\t{i}\t{s['doc_kind']}\t{s['status']}\t{texts[i].get('type_group', '')}\t{texts[i].get('period', '')}\n")
    print(f"exported {len(picked)} files to {args.out}")


def score(args) -> None:
    texts, segs = load_jsonl(args.input), load_jsonl(args.segments)
    tp = fp = fn = 0
    rejected, per_label = [], Counter()
    for f in sorted(args.out.glob("*.txt")):
        i = f.stem.split("_", 1)[1]
        with open(f, newline="") as fi:            # no newline translation
            text, gold = strip_markers(fi.read())
        if text != texts[i]["text"]:
            rejected.append(f.name)
            continue
        pred = {(s["start"], s["label"]) for s in segs[i]["sections"]}
        gold = set(gold)
        tp, fp, fn = tp + len(pred & gold), fp + len(pred - gold), fn + len(gold - pred)
        per_label.update(f"FN:{l}" for _, l in gold - pred)
        per_label.update(f"FP:{l}" for _, l in pred - gold)
    p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
    print(json.dumps({"boundary_precision": round(p, 4), "boundary_recall": round(r, 4),
                      "errors_by_label": dict(per_label.most_common()), "rejected_files": rejected},
                     ensure_ascii=False, indent=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["export", "score"])
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--segments", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    export(args) if args.cmd == "export" else score(args)


if __name__ == "__main__":
    main()
