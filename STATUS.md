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
- `main_only`: 主文 + closing, e.g. 更正裁定.
- `unstructured`: no headings, closing found, e.g. one-paragraph 命補繳裁判費 orders.
- `formulaic`: 支付命令.
- `partial`: everything else, i.e. failures.

## Results on statute-contest public 10,032 (stratified), `runs/*_eval-public-v4`

| status | share |
|---|---|
| ok | 79.3% |
| formulaic | 11.2% |
| unstructured | 5.1% |
| main_only | 3.5% |
| partial | 0.95% |

By doc kind: 判決 ok 94.6% / main_only 4.7%; 裁定 ok 84.8% / unstructured 13.0%; 宣示判決筆錄 ok 78.3%.

These rates measure internal consistency, not accuracy. A heading found inside the reasons would still count
as `ok`. Accuracy comes from the gold set below.

## Gold set (in progress)

`/nfs/turing/data1/hochien894011/tw-judgment-segmenter/annotation/layer1-v1/`: 51 pre-labelled files
(statuses oversampled away from `ok`). The user corrects the ⟪LABEL⟫ marker lines; see README.md there.
Score with `python scripts/annotation.py score --input <texts.jsonl> --segments <segments.jsonl> --out <dir>`.
The round trip on unedited files gives P = R = 1.0.

## Open

- 判決 `main_only` 4.7% is suspicious, because judgments must state reasons. Likely body headings written
  inline or missing; check against the gold set.
- Appendix placed BEFORE the closing date line: the closing is then not detected (part of `partial`, 93 docs).
- Run on the 200k training sample to check that rates hold outside the public set.

## Pitfalls

- Fixed-width wrapping creates fake headings: "主文。", "附件檢察官聲請簡易判決處刑". Headings must be standalone
  lines without 。, and 附件/附表 must be followed only by a number, a colon or nothing.
- The title often shares its line with the case number: "…刑事判決110年度訴字第123號".
- A rare colon variant appears: ︰ (U+FE30), as in 理由要領︰.
- Numbered headings (一、犯罪事實) are top level only before any body heading. Inside the reasons they are sub-items.
- Annotation files: write and read with newline="" (JFULL uses \r\n), and split lines on \n only.
- The account is limited to 2 CPU cores per server. The full public set runs in about 5 s, so this does not matter yet.
