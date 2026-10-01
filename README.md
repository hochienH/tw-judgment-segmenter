# tw-judgment-segmenter

Rule-based segmentation of Taiwanese court documents (司法院裁判書開放資料, field `JFULL`) into labelled
sections — HEADER, MAIN (主文), FACTS, REASONS, FACTS_REASONS, CLOSING, APPENDIX_LAW, ATTACHMENT — with
character offsets into the original text.

```python
from segmenter import segment
seg = segment(jfull_text)   # {"doc_kind", "status", "missing", "sections": [{"label", "start", "end", ...}]}
```

- `scripts/evaluate.py`: run over a jsonl and report parse rates and missed heading candidates
- `scripts/annotation.py`: export pre-labelled files for manual correction and score them as gold
- `tests/`: `venv/bin/python -m pytest -q tests`

See `STATUS.md` for decisions, results and known issues.
