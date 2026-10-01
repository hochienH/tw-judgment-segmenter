# STATUS: tw-judgment-segmenter

Shared by TJCAS, LegalDistBench (masked-citation task) and statute-contest. It splits 司法院 open-data JFULL
text into labelled sections with offsets into the original text; the text is never rewritten.

## Decisions (2026-10-01)

- Scope: 判決 and reasoned 裁定. Formulaic documents (支付命令) only get a doc kind and status, no fine split.
- Separate repo. Layer 1 (top-level sections) first. Layer 2 (inside the body: 原告主張 / 被告抗辯 / 爭點 /
  本院之判斷; 程序 / 實體 / 論罪科刑 / 沒收) comes after layer 1 is validated.
- Rule-based state machine, in the TJCAS style: loose matching, classification afterwards, and a miss list
  (`misses.tsv`) for heading variants the rules do not catch yet.

## Layer 1 labels and status

Labels: HEADER, MAIN, FACTS, REASONS, FACTS_REASONS, BODY_OTHER, CLOSING, APPENDIX_LAW, ATTACHMENT (an attached
indictment gets kind=indictment).

Status classes:
- `ok`: 主文 + body + closing.
- `main_only`: 主文 + closing. Legitimate for 小額判決 (民訴 436-18) and 更正裁定.
- `unstructured`: no headings, closing found, e.g. one-paragraph 命補繳裁判費 orders.
- `formulaic`: 支付命令.
- `partial`: everything else, i.e. failures.

## Results on statute-contest public 10,032 (stratified), `runs/*_eval-public-v7`

| status | share |
|---|---|
| ok | 79.6% |
| formulaic | 11.2% |
| unstructured | 5.1% |
| main_only | 3.4% |
| partial | 0.61% |

By doc kind: 判決 ok 94.8% / main_only 4.6% (98% of them 小額); 裁定 ok 84.8% / unstructured 13.0%;
宣示判決筆錄 ok 78.3%.

These rates measure internal consistency, not accuracy. A heading found inside the reasons would still count
as `ok`. Accuracy comes from the gold set below.

## Gold set v1 result (2026-10-01, annotated by the user, 51 docs, about 210 boundaries)

- Before the fixes (v5): P = 1.000, R = 0.952. The 10 misses were all in 4 documents: 044/046 (憲法法庭, no line
  breaks at all), 047 (date numerals with spaces: 九　十　年), and 051 (2025 judgment whose line breaks were partly
  replaced by full-width spaces, so headings and the date sit mid-line).
- After the fixes (v7): P = R = 1.000. The last FP (048 CLOSING) was an annotation omission, fixed by the user on 2026-10-01. The annotator had not
  added ⟪CLOSING⟫ there, because v4 had not pre-labelled it.
- Caveat: this set was used to write the fixes, so it is now development data, not a test set. A fresh
  held-out set is needed for an honest accuracy number. Pre-labels also anchor the annotator (see 048).
- Fixes: inline repair pass, which runs only when the line pass misses MAIN/BODY/CLOSING. Inline headings must
  follow 。/：/line start and be followed by an enumerator or colon (in flat documents: anything except
  如/為/是/在/係/何/之). An inline closing date must open a sentence and be followed by a court or judge.
  Spaced numerals are allowed in dates.
- Documents without line breaks: 0.21% of public and 0.25% of the 200k sample, almost all 憲法法庭 2021+.

## Held-out v2: official layer-1 accuracy (2026-10-01)

- 30 docs drawn at random from the 200k training sample, in scope (no 支付命令). Half are 2021-2026; the other
  half is split evenly over 1996-2005, 2006-2015 and 2016-2020. Sampling is NOT by status. 138 boundaries.
- Checked by the user and then by 3 Opus agents (10 files each, read-only). The agents found 2 real errors that
  the user confirmed (019: 「所犯法條：」 statute appendix without 附錄; 029: first closing date 六月廿一日 mis-placed,
  pre-label anchoring) and 1 ambiguous case (007: a cheque table inside the closing block). Decision on 007:
  tables inside the closing stay CLOSING (convention (a)).
- **Score with the v7 rules, BEFORE any fix: boundary P = 0.9927 (136/137), R = 0.9855 (136/138); 2/30 docs
  with an error.** This is the number to report. With n = 30 the doc-level error rate has a 95% upper bound of
  about 21%. (`annotation/layer1-v2-heldout-score-v7.json`)
- After the fixes (v8: 廿/卅 in dates, 右為正本/右正本 closing, standalone 所犯法條/論罪科刑法條 after the closing
  → APPENDIX_LAW), v1 and v2 both score P = R = 1.0. v2 is now development data.
- v8 changed 1,609 of the 200k docs: 1,384 gained an APPENDIX_LAW (所犯法條 without 附錄 is common in 簡易判決) and
  225 had their CLOSING moved. A spot check of 8 was all correct. partial: public 0.55%, 200k 0.64%.
- Lesson: pre-labels anchor the annotator. Both v2 errors were pre-label errors that the annotator accepted.
  An independent second reader (agents) caught them.

## Gold set v1 files

`/nfs/turing/data1/hochien894011/tw-judgment-segmenter/annotation/layer1-v1/`: 51 pre-labelled files
(statuses oversampled away from `ok`). The user corrects the ⟪LABEL⟫ marker lines; see README.md there.
Score with `python scripts/annotation.py score --input <texts.jsonl> --segments <segments.jsonl> --out <dir>`.
The round trip on unedited files gives P = R = 1.0.

## Open

- Convention (2026-10-01, from held-out file 004): layer 1 marks top-level headings only. Sub-headings inside 理由
  (壹、貳、一、二…) stay REASONS even when they are about facts, e.g. 貳、犯罪事實之認定 (刑訴 310①: evidence and
  reasons for the facts found belong to 理由). Layer 2 splits REASONS into procedure/admissibility, fact-finding,
  legal analysis (論罪), sentencing (科刑) and confiscation (沒收), and splits civil FACTS_REASONS into 原告主張 /
  被告抗辯 / 不爭執事項 / 爭點 / 本院之判斷. Facts-only queries: use FACTS when present, otherwise the layer-2 fact parts.

- ~~判決 `main_only` 4.7% suspicious~~ Resolved on 2026-10-01 (the user's hypothesis): 187 of 190 (98%) are
  小額判決. 民訴 436-18 lets the judgment record only 主文, so `main_only` is correct for them. The other 3 had
  reasons with no heading, starting with 壹、程序方面. They are now handled by an implicit-REASONS rule:
  right after MAIN, before any body heading, a line starting with 壹、 opens REASONS with heading "(implicit)".
- Appendix placed BEFORE the closing date line: the closing is then not detected (most of the remaining partial, 59 docs).
- Held-out gold set v2 (fresh documents, ideally from the 200k training sample) for an honest accuracy number.
- Run on the 200k training sample to check that rates hold outside the public set.

## Pitfalls

- Fixed-width wrapping creates fake headings: "主文。", "附件檢察官聲請簡易判決處刑". Headings must be standalone
  lines without 。, and 附件/附表 must be followed only by a number, a colon or nothing.
- The title often shares its line with the case number: "…刑事判決110年度訴字第123號".
- A rare colon variant appears: ︰ (U+FE30), as in 理由要領︰.
- Numbered headings (一、犯罪事實) are top level only before any body heading. Inside the reasons they are sub-items.
- Annotation files: write and read with newline="" (JFULL uses \r\n), and split lines on \n only.
- The account is limited to 2 CPU cores per server. The full public set runs in about 5 s, so this does not matter yet.
