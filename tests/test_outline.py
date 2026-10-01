from segmenter import segment
from segmenter.outline import ordinal, outline


def tree(text):
    r = outline(text, segment(text)["sections"])
    return [(n["depth"], n["style"], n["ordinal"]) for n in r["nodes"]], r["rejected"]


def test_ordinals():
    assert ordinal("一", "十一") == 11 and ordinal("一", "二十三") == 23
    assert ordinal("壹", "拾壹") == 11 and ordinal("壹", "叁") == 3
    assert ordinal("㈠", "㈢") == 3 and ordinal("㈠", "十二") == 12
    assert ordinal("⑴", "⑶") == 3 and ordinal("⑴", "１２") == 12
    assert ordinal("①", "④") == 4 and ordinal("甲", "丙") == 3


DOC = """臺灣臺北地方法院民事判決
主　文
原告之訴駁回。
事實及理由
壹、程序方面：
一、本件被告經合法通知未到場。
貳、實體方面：
一、原告主張：
㈠被告於民國110年借款。
㈡迄未清償。
二、被告則以：
⑴否認借款。
⑵縱有借款亦已清償。
三、本院之判斷：
中華民國111年1月1日
"""


def test_nesting_follows_first_appearance_and_restarts_under_new_parent():
    nodes, rejected = tree(DOC)
    assert nodes == [(0, "壹", 1), (1, "一", 1), (0, "壹", 2), (1, "一", 1), (2, "㈠", 1), (2, "㈠", 2),
                     (1, "一", 2), (2, "⑴", 1), (2, "⑴", 2), (1, "一", 3)]
    assert rejected == []


def test_node_spans_end_at_next_sibling_or_shallower():
    r = outline(DOC, segment(DOC)["sections"])
    n = r["nodes"]
    shi = n[2]                                       # 貳、實體方面 covers everything to the section end
    assert DOC[shi["start"]:shi["end"]].lstrip().startswith("貳、實體方面") and shi["end"] == n[2]["end"]
    claim = n[3]                                     # 一、原告主張 ends where 二、被告則以 starts
    assert claim["end"] == n[6]["start"]


def test_wrapped_line_with_enumerator_shape_is_rejected():
    doc = ("臺灣臺北地方法院刑事判決\n主　文\n無罪。\n理　由\n一、按刑事訴訟法第一、\n"
           "三、五條規定……\n二、經查……\n中華民國111年1月1日\n")
    nodes, rejected = tree(doc)
    assert nodes == [(0, "一", 1), (0, "一", 2)]
    assert rejected and rejected[0]["ordinal"] == 3


def test_skip_level_styles_are_document_specific():
    doc = "臺灣臺北地方法院刑事判決\n主　文\n無罪。\n理　由\n一、經查\n⑴甲\n⑵乙\n二、結論\n中華民國111年1月1日\n"
    nodes, _ = tree(doc)
    assert nodes == [(0, "一", 1), (1, "⑴", 1), (1, "⑴", 2), (0, "一", 2)]


def test_quoted_statute_items_nest_and_do_not_steal_outer_numbers():
    doc = ("臺灣臺北地方法院刑事判決\n主　文\n緩刑。\n理　由\n一、按刑法第75條規定：\n"
           "    一、其處分書或裁定書定有……\n    二、緩刑期內因故意犯他罪……\n二、經查……\n中華民國111年1月1日\n")
    r = outline(doc, segment(doc)["sections"])
    got = [(n["depth"], n["ordinal"], n["nested_restart"]) for n in r["nodes"]]
    assert got == [(0, 1, False), (1, 1, True), (1, 2, False), (0, 2, False)]


def test_one_skipped_number_is_tolerated():
    doc = "臺灣臺北地方法院刑事判決\n主　文\n無罪。\n理　由\n一、甲。\n二、乙。\n四、丙。\n五、丁。\n中華民國111年1月1日\n"
    nodes, rejected = tree(doc)
    assert [o for _, _, o in nodes] == [1, 2, 4, 5] and rejected == []


def test_indented_wrapped_line_cannot_continue_top_level():
    doc = ("臺灣臺北地方法院刑事判決\n主　文\n無罪。\n理　由\n一、依刑事訴訟法第一、\n"
           "    二、三條規定……\n二、經查……\n中華民國111年1月1日\n")
    nodes, rejected = tree(doc)
    assert nodes == [(0, "一", 1), (0, "一", 2)] and len(rejected) == 1


def _doc(body):
    return "臺灣臺中地方法院刑事判決\n主　文\n無罪。\n理　由\n" + body + "中華民國111年1月1日\n"


def test_digit_full_stop_glyphs_and_mixed_ascii():
    doc = _doc("一、經查：\n㈠甲。\n⒈子一。\n⒉子二。\n㈡乙。\n")
    assert tree(doc)[0] == [(0, "一", 1), (1, "㈠", 1), (2, "1.", 1), (2, "1.", 2), (1, "㈠", 2)]
    items = "".join(f"{k}.第{k}項。\n" for k in range(1, 10))                   # 1. … 9. then ⒑ (one glyph)
    doc = _doc("一、經查：\n" + items + "⒑第十項。\n")
    nodes = tree(doc)[0]
    assert [o for _, _, o in nodes] == [1] + list(range(1, 11)) and nodes[-1] == (1, "1.", 10)


def test_pua_glyphs_continue_after_unicode_limit():
    items = "".join(f"{chr(0x321F + k)}第{k}項。\n" for k in range(1, 11))       # ㈠..㈩
    doc = _doc("一、證據：\n" + items + "第十一項。\n第十二項。\n")
    nodes = tree(doc)[0]
    assert nodes[-2:] == [(1, "㈠", 11), (1, "㈠", 12)]


def test_pua_yi_block_is_first_level_items():
    doc = _doc("第一項。\n第二項。\n")
    assert tree(doc)[0] == [(0, "一", 1), (0, "一", 2)]


def test_chained_enumerators_without_comma():
    doc = _doc("五、甲。\n六㈠鄧某因發現上情。\n㈡又…。\n七、乙。\n")
    assert tree(doc)[0] == [(0, "一", 5), (0, "一", 6), (1, "㈠", 1), (1, "㈠", 2), (0, "一", 7)]


def test_court_repeated_number_is_accepted_as_sibling():
    doc = _doc("一、甲。\n二、乙。\n三、丙。\n三、丁。\n四、戊。\n")
    r = outline(doc, segment(doc)["sections"])
    assert [n["ordinal"] for n in r["nodes"]] == [1, 2, 3, 3, 4] and r["nodes"][3]["duplicate"]


def test_wrapped_cross_reference_restart_is_rejected():
    doc = _doc("一、經查：\n㈠甲。\n㈡乙，即犯罪事實欄\n    三㈠即如附表所示。\n㈢丙。\n")
    nodes, rejected = tree(doc)
    assert nodes == [(0, "一", 1), (1, "㈠", 1), (1, "㈠", 2), (1, "㈠", 3)]


def test_chained_child_takes_indentation_from_its_first_sibling():
    doc = _doc("五、甲。\n六㈠鄧某因發現上情。\n  ㈡而張某另於同月領取。\n  ㈢張某又於6月領取。\n七、乙。\n")
    assert tree(doc)[0] == [(0, "一", 5), (0, "一", 6), (1, "㈠", 1), (1, "㈠", 2), (1, "㈠", 3), (0, "一", 7)]


def test_inconsistent_sibling_indentation_after_a_finished_sentence():
    doc = _doc("一、甲。\n二、乙。\n三、丙：\n　　㈠子一。\n　㈡子二。\n　　㈢子三。\n　四、綜上。\n")
    assert tree(doc)[0] == [(0, "一", 1), (0, "一", 2), (0, "一", 3), (1, "㈠", 1), (1, "㈠", 2), (1, "㈠", 3), (0, "一", 4)]


def test_amounts_and_sums_are_not_enumerators():
    doc = _doc("一、經查：\n㈠甲。\n㈡乙：\n    一、０００、０００元。\n㈢㈠＋㈡為：二、００八元。\n")
    nodes, _ = tree(doc)
    assert nodes == [(0, "一", 1), (1, "㈠", 1), (1, "㈠", 2), (1, "㈠", 3)]


def test_wrapped_number_cannot_open_a_section_outline():
    doc = _doc("經查曾某各一九\n八、○○○股，以贈與論。\n")
    assert tree(doc)[0] == []


def test_second_heading_restarts_outline():
    doc = _doc("甲、原告方面：\n乙、被告方面：未到場。\n    理    由\n一、程序方面：\n㈠依約定。\n二、實體方面。\n")
    assert tree(doc)[0] == [(0, "甲", 1), (0, "甲", 2), (0, "一", 1), (1, "㈠", 1), (0, "一", 2)]
