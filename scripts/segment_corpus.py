#!/usr/bin/env python3
"""Layer-1 segmentation of the whole JRAR corpus (all monthly RAR archives), streamed without unpacking.

  segment_corpus.py --jrar DIR --out DIR --shard K --nshards N

Archives are assigned to shards by index modulo N. Each archive becomes <out>/<archive>.jsonl.gz with one line per
judgment JSON; a <archive>.done marker makes the run resumable. Streaming follows TJCAS: `rar l` gives entry
sizes, `rar p` writes the entries back to back in listing order, and the stream is cut by those sizes.
"""

from __future__ import annotations

import argparse
import gzip
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from segmenter import segment  # noqa: E402

RAR_BIN = "rar"
SEP = "-----------"


def entries(archive: Path) -> list[tuple[str, int]]:
    out = subprocess.run([RAR_BIN, "l", str(archive)], capture_output=True, check=True).stdout
    rows, in_table = [], False
    for line in out.decode("utf-8", errors="replace").splitlines():
        if line.startswith(SEP):
            if in_table:
                break
            in_table = True
            continue
        if not in_table:
            continue
        parts = line.split(maxsplit=4)
        if len(parts) == 5 and "D" not in parts[0] and parts[1].isdigit():
            rows.append((parts[4], int(parts[1])))
    return rows


def stream(archive: Path):
    listing = entries(archive)
    proc = subprocess.Popen([RAR_BIN, "p", "-inul", str(archive)], stdout=subprocess.PIPE)
    try:
        for name, size in listing:
            payload = proc.stdout.read(size)
            if len(payload) != size:
                raise RuntimeError(f"{archive.name}: stream ended inside {name}")
            yield name, payload
    finally:
        proc.stdout.close()
        if proc.poll() is None:
            proc.terminate()
        proc.wait()


def case_key(name: str) -> list[str]:
    """'202001/臺灣臺北地方法院刑事/TPDM,108,訴,123,20200102,1.json' -> [court, jyear, jcase, jno]."""
    parts = Path(name).stem.split(",")
    return parts[:4] if len(parts) >= 4 else [Path(name).stem, "", "", ""]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jrar", type=Path, default=Path("/data/hostD/data1/user/JRAR"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--nshards", type=int, default=1)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    archives = sorted(a.jrar.glob("*.rar"))[a.shard::a.nshards]
    t_all = time.time()
    for k, arc in enumerate(archives, 1):
        done = a.out / f"{arc.stem}.done"
        if done.exists():
            continue
        t0, n, bad = time.time(), 0, 0
        tmp = a.out / f"{arc.stem}.jsonl.gz.part"
        with gzip.open(tmp, "wt", encoding="utf-8") as fo:
            for name, payload in stream(arc):
                if not name.endswith(".json"):
                    continue
                try:
                    text = json.loads(payload.decode("utf-8-sig")).get("JFULL") or ""
                except (ValueError, UnicodeDecodeError):
                    bad += 1
                    continue
                s = segment(text)
                fo.write(json.dumps({"file": name, "key": case_key(name), "len": len(text),
                                     "doc_kind": s["doc_kind"], "status": s["status"],
                                     "sections": [[x["label"], x["start"], x["end"]] for x in s["sections"]]},
                                    ensure_ascii=False) + "\n")
                n += 1
        tmp.rename(a.out / f"{arc.stem}.jsonl.gz")
        done.write_text(json.dumps({"docs": n, "bad_json": bad, "secs": round(time.time() - t0, 1)}))
        print(f"[{time.strftime('%H:%M:%S')}] shard {a.shard}: {k}/{len(archives)} {arc.name} docs={n} "
              f"bad={bad} {time.time() - t0:.0f}s (elapsed {(time.time() - t_all) / 60:.0f} min)", flush=True)


if __name__ == "__main__":
    main()
