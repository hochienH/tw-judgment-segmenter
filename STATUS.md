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

## Held-out v3: second official layer-1 accuracy (2026-10-01)

- 50 docs, disjoint from v2, same sampling, pre-labelled by v8. 5 Opus agents reviewed them FIRST (user's
  choice); the user decided on the 4 flagged points. No full human pass, so gold quality rests on agent recall.
- Convention (a), decided by the user: any statute text appended after the judgment is APPENDIX_LAW, whether
  criminal 論罪科刑法條 or civil/administrative notice statutes (民訴 466-1, 行訴 235 ...). It covers 【附註】/附記
  that quote articles. If the two ever need to be told apart, add a `kind` attribute (sentencing vs notice)
  rather than a new label. Boundaries do not change.
- **Score with v8, BEFORE fixes: P = 1.000 (208/208), R = 0.9905 (208/210); 2/50 docs with an error.** Both misses
  were APPENDIX_LAW: a heading with the statute on the same line (042) and 【附註】 (011).
  (`annotation/layer1-v3-heldout-score-v8.json`)
- Across v2 (v7 rules) and v3 (v8 rules), 4 of 80 held-out docs had an error. All 4 were in the tail (closing
  date / appendix), none in HEADER/MAIN/body.
- Fixes (v9c): appendix heading inline with content; bracketed headings (【附註】 〔附錄〕); 附註/附記/附錄 whose
  text has a quoted-article heading line (the article reference ends the line, apart from 項/款, a paren note and a
  colon) are relabelled APPENDIX_LAW. Two over-eager versions were caught by spot checks (instruction notes
  mentioning a law) before the final rule. v1/v2/v3 all score P = R = 1.0 with v9c. 200k: 4,651 docs changed,
  3,421 relabelled; a spot check of 10 was all correct.

## Gold set v1 files

`/nfs/turing/data1/hochien894011/tw-judgment-segmenter/annotation/layer1-v1/`: 51 pre-labelled files
(statuses oversampled away from `ok`). The user corrects the ⟪LABEL⟫ marker lines; see README.md there.
Score with `python scripts/annotation.py score --input <texts.jsonl> --segments <segments.jsonl> --out <dir>`.
The round trip on unedited files gives P = R = 1.0.

## Layer 2, step 1: enumeration outline (`segmenter/outline.py`, 2026-10-01)

- Decision: the functional labels for layer 2 (原告主張, 論罪, 科刑 …) are postponed until masking is done. Only
  the numbering hierarchy is built now.
- Survey (public, body sections of ok docs): 一 87% of docs, ㈠ 31%, 壹 7.5%, 1. 5%, ⑴ 5%, 甲 3.5%. Patterns:
  一 only 54%, 一>㈠ 18%, no enumerator 11.5%. The rank 甲>壹>一>㈠>1./⑴>① fits about 90%, but levels are
  document-specific, so nesting follows the order of first appearance.
- Text after the top-level enumerators is mostly a sentence opening (依刑事訴訟法…, 核被告所為…, 據上論斷…),
  not a heading. Explicit headings (程序方面, 實體方面, 原告方面, 本院之判斷) sit mostly at the 壹/甲 levels. For the
  later functional step: classify by opening phrases, not by headings alone.
- Algorithm: each level keeps (style, last ordinal, indentation). A line continues a level when its ordinal is
  the next one and its indentation is within ±1 (full-width space = 2). A restart at 1 in a style already in use
  becomes a nested child list (nested_restart, e.g. quoted statute items). One skipped number is tolerated at the
  same indentation after a finished sentence. Anything else is rejected as text.
- Key evidence: depth-0 items are at column 0 in 30,552 of 30,639 cases. Continuation lines are indented 4. Deeper
  levels have no fixed indentation.
- Public results: v1 (ordinals only) rejected 45 per 1,000 nodes; v2 (indentation-aware) rejects 14.6 per 1,000,
  with 6.4% of docs having any rejection. nested_restart covers 1.0% of nodes and skipped 98 nodes. Rejected
  samples are mostly correct rejections (amounts 一一九、０００元, wrapped ㈣第55頁, cross references 丙、肆、四、㈠, 釋字
  numbers), plus a few court numbering errors (三 written twice).
- No gold for the outline yet.

### Outline gold v1 (2026-10-01): 50 docs, stratified by max depth (0:5, 1:20, 2:15, ≥3:10)

- Population strata sizes (ok docs in 200k): 0: 17,855 / 1: 88,108 / 2: 33,167 / ≥3: 20,488.
- Review: 5 Opus agents (10 docs each). 132 findings in 8 docs, all accepted by the user. Later, 19 more
  gold corrections were approved by the user: invisible PUA enumerators that both the agents and the
  annotator missed (040: seven items 一–六、 written as U+F6B0…F6AB plus the depth shift beneath them;
  005 L2691 = (十一)).
- **Official score, v2 rules vs corrected gold: item P = 0.997, R = 0.862, depth accuracy 0.933; 42/50 docs
  exact (1-level docs 20/20; 2-level 11/15; ≥3-level 6/10). Population-weighted docs exact ≈ 89%.**
  (`annotation/outline-v1-score-v2-corrected.json`)
- Root causes found (all fixed in v3b):
  1. ⒈–⒛ glyphs (U+2488–249B) were missing from the "1." style, the biggest cause. A whole level vanished,
     so children were shifted up. Courts also mix 1.–9. with ⒑ ⒒ in one list.
  2. Chained enumerators without 、: 六㈠…. The missing 六 cascaded into 七–十.
  3. Numbers repeated by the court (三、 twice, ㈥ twice) are now accepted as a sibling at the same
     indentation after a finished sentence (flag `duplicate`).
  4. Big5 custom glyphs (PUA). The mapping was inferred from consecutive runs after a style's last Unicode glyph
     (㈩, ⑳) in 200k docs: F6B0–F6A2 = 一、…十五、 (、 built in; F6B0 follows headings as the first item),
     F674–F65B = (十一)…(三十六), F4DA–F4D7 = (21)…(24), E7CB = 十一、. Codes descend as ordinals rise.
     Unclear: F511–F513 (possibly 壹/貳/參), E01D (an indentation glyph before ⑴). See
     `runs/pua_unmapped_linestart.tsv`.
  5. A restart of a style in use must follow a finished sentence, which rejects wrapped cross-references.
     The level opened by a chained child takes its indentation from its first sibling.
- Dev score with v3b: P = 0.9986, R = 1.0, depth 1.0, 49/50 docs exact. The one FP is ① inside a verbatim
  quoted meeting record (005), which the rules cannot detect yet.
- Scorer fix: items are counted per offset, because a chained line (六㈠) holds two. The v1 gold was completed
  for 017 六㈠/七㈠ (⟦1⟧⟦2⟧): the old format could not carry two prefixes on one line. This moved R from 0.864
  to 0.862.
### Outline held-out v2 (2026-10-01): 100 docs (0:10, 1:40, 2:30, ≥3:20), disjoint from all earlier gold sets

- Pre-labelled by v3b. A workflow of 10 Opus agents (10 docs each; concurrency is capped, so not all 10 run at
  once) found 17 points in 6 docs. All were verified against the text and accepted by the user.
- **Official score, v3b vs gold: item P = 0.9966, R = 0.9944, depth accuracy 0.990; 94/100 docs exact
  (1-level 39/40, 2-level 27/30, ≥3-level 18/20). Population-weighted docs exact ≈ 95.2%** (v2 rules: ≈ 89%).
  (`annotation/outline-v2-heldout-score-v3b.json`; strata sizes 0: 16,787 / 1: 88,704 / 2: 30,077 / ≥3: 24,000)
- Causes, fixed in v3c–v3h:
  - Sibling indentation is inconsistent (㈠㈢ with two full-width spaces, ㈡ with one; ㈧ at column 0 after
    indented ㈠–㈦). When the previous line finished a sentence, up to 4 columns are now tolerated.
  - Amounts: 一、０００、０００元, 八、○○○股, 一、五八二、五八二─一 (Chinese-digit number lists).
  - Sums: ㈠＋㈡為…
  - A court that writes 理由 twice: the second standalone heading restarts the outline. All layer-1 heading
    regexes are reused here. A narrow version had dropped the first item after 事實及理由要領 and similar
    headings, about 20k nodes, caught by diffing against v3b.
  - New lists need a clean opening: after a finished sentence (incl. ︰﹕?), right under an item line, or after a
    short line (≤16 chars: a heading or paragraph end; wrapped lines are full). An unclean opening is still
    accepted if its sibling 2 follows (same style, similar indent, after a sentence). This stops cascades
    where one rejected 1 drops 2, 3, 4 ….
- v3h on 200k: rejected 14.7 per 1,000 nodes (v3b 15.25). v1 and v2 gold are both perfect, but both are now dev
  data. A diff of v3g against v3b showed about 9/14 removals were correct (wrapped references, case numbers,
  page and number lists) and 3/6 additions were wrong (later fixed: Chinese-digit number lists; still open:
  quoted lists in 『』, references like 「見不爭執事項㈠㈢）」).
- Diminishing returns: each rule fixes some cases and moves others. An honest v3h number needs a fresh held-out.
- Lesson: PUA glyphs are invisible, so annotators and agents cannot see them. Both exporters now insert a
  visible hint ⟦U+XXXX⟧ before a line-initial PUA char, and the scorers strip it.

## Ablation and simplified default (2026-10-02, `runs/261002-0017_ablation`)

Every special-case rule got a switch (`segment(text, off=…)`, `outline(text, sections, off=…)`). Each rule was
switched off alone, then all at once ("core"). Gold = pooled dev sets (layer 1: v1+v2+v3, 131 docs; outline: v1+v2,
150 docs). "Docs changed" = share of a ~50k sample of the 200k set whose result differs from the full rule set
(disagreement, not error).

- Layer 1 core: R 0.937, 108/131 exact, 22.4% of docs changed. Rule weights by docs changed:
  headingless_closing 16.2% (really core), closing_alt 1.4%, transcript 1.3%, statute_relabel 1.3%,
  bracketed 1.0%, appendix_after_closing 0.7%, merge_repeats 0.6%, inline_repair 0.27%, appendix_inline 0.18%,
  implicit_reasons 0.08%, date_nian 0.04%, date_spaced 0.04%.
- Outline core: R 0.886, depth 0.937, 125/150 exact, 8.8% changed. Weights: digit_stop 4.75% (really core),
  pua 1.45%, duplicate 1.1%, clean_open 1.0% (no gold effect), skip 0.9%, relaxed_indent 0.7%, indent 0.7%,
  lookahead 0.4%, chained 0.3%, restart_guard 0.2%, amount_guard 0.07%, short_line 0.07%, heading_reset 0.02%,
  numlist 0.01%, sum 0, chained_indent 0.
- **Decision (user): the simplified sets are the default.** Layer 1 drops inline_repair, implicit_reasons and
  appendix_inline: 0.53% of docs differ, gold R 0.982. The outline drops clean_open, short_line, lookahead,
  numlist_guard, sum_guard, restart_guard, heading_reset and chained_indent (amount_guard is kept): 1.6% of docs
  differ, gold 145/150. `off=FULL` gives the full sets; tests of dropped rules run with FULL.
- Known cost: flat 憲法法庭 decisions (no line breaks, 0.25% of docs) are `partial` again. public partial 0.77%,
  200k 0.9%.
- Default outputs (simplified): `runs/*_eval-public-v10`, `runs/*_eval-train200k-v10`, `runs/*_outline-train200k-v4`.
  Dev scores: layer1 v1 R 0.957 (v1 oversampled flat docs), v2 R 1.0, v3 R 0.995, all P 1.0; outline v1 48/50,
  v2 97/100 docs exact.
- For a paper: the ablation table itself justifies each kept rule.

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
