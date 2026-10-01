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
