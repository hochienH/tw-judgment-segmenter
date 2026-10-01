from segmenter import segment


def labels(text):
    return [s["label"] for s in segment(text)["sections"]]


CRIMINAL = """臺灣臺北地方法院刑事判決
110年度訴字第123號
公　訴　人　臺灣臺北地方檢察署檢察官
被　　　告　王小明
上列被告因詐欺案件，經檢察官提起公訴，本院判決如下：
　　主　文
王小明犯三人以上共同詐欺取財罪，處有期徒刑壹年。
　　事　實
一、王小明於民國110年1月1日……
　　理　由
一、上開事實，業據被告坦承不諱……
據上論斷，應依刑事訴訟法第299條第1項前段，判決如
主文。
中　　華　　民　　國　　110　　年　　5　　月　　3　　日
　　　　　　　　　刑事第一庭　法　官　李大華
以上正本證明與原本無異。
　　　　　　　　　　　　　　　書記官　陳美
中　　華　　民　　國　　110　　年　　5　　月　　4　　日
附錄本案論罪科刑法條全文：
中華民國刑法第339條之4
"""

CIVIL_MERGED = """臺灣新北地方法院民事判決
111年度訴字第45號
原　　　告　甲
被　　　告　乙
上列當事人間請求損害賠償事件，本院判決如下：
主  文
被告應給付原告新臺幣10萬元。
事實及理由
一、原告主張：……
二、被告則以：……
中華民國一百十一年十月三日
民事第二庭　法　官　某
"""

SIMPLE_WITH_INDICTMENT = """臺灣士林地方法院刑事簡易判決
112年度士簡字第9號
主　　文
甲犯不能安全駕駛致交通危險罪，處有期徒刑貳月。
事實及理由
一、本件犯罪事實及證據，除補充外，均引用如附件檢察官聲請簡易判決處刑
    書之記載。
中　華　民　國　112　年　3　月　1　日
附件：
臺灣士林地方檢察署檢察官聲請簡易判決處刑書
    犯罪事實
一、甲於……
    證據並所犯法條
一、上揭犯罪事實……
"""

PAYMENT_ORDER = """臺灣高雄地方法院支付命令
108年度司促字第671號
債　權　人　王上元
一、債務人應向債權人給付新台幣壹拾萬元……
中　　華　　民　　國　　108　　年　　1　　月　　31　　日
"""


def test_criminal_full_structure():
    r = segment(CRIMINAL)
    assert labels(CRIMINAL) == ["HEADER", "MAIN", "FACTS", "REASONS", "CLOSING", "APPENDIX_LAW"]
    assert r["status"] == "ok" and r["doc_kind"] == "判決"


def test_wrapped_main_line_is_not_a_heading():
    # "主文。" ends the 據上論斷 sentence; it must not open a new MAIN section
    assert labels(CRIMINAL).count("MAIN") == 1


def test_only_first_date_line_opens_closing():
    assert labels(CRIMINAL).count("CLOSING") == 1


def test_civil_merged_facts_and_reasons_with_chinese_date():
    assert labels(CIVIL_MERGED) == ["HEADER", "MAIN", "FACTS_REASONS", "CLOSING"]


def test_attached_indictment_headings_stay_inside_attachment():
    r = segment(SIMPLE_WITH_INDICTMENT)
    assert labels(SIMPLE_WITH_INDICTMENT) == ["HEADER", "MAIN", "FACTS_REASONS", "CLOSING", "ATTACHMENT"]
    att = r["sections"][-1]
    assert att["kind"] == "indictment" and att["subheadings"] == ["犯罪事實", "證據並所犯法條"]


def test_wrapped_attachment_reference_is_not_a_heading():
    # "附件檢察官聲請簡易判決處刑" starts a wrapped body line, not an attachment
    assert labels(SIMPLE_WITH_INDICTMENT).count("ATTACHMENT") == 1


def test_payment_order_is_formulaic():
    r = segment(PAYMENT_ORDER)
    assert r["doc_kind"] == "支付命令" and r["status"] == "formulaic"


def test_offsets_cover_text_without_gaps():
    for doc in (CRIMINAL, CIVIL_MERGED, SIMPLE_WITH_INDICTMENT):
        secs = segment(doc)["sections"]
        assert secs[0]["start"] == 0 and secs[-1]["end"] == len(doc)
        assert all(a["end"] == b["start"] for a, b in zip(secs, secs[1:]))


TRANSCRIPT = """臺灣臺中地方法院刑事簡易庭宣示判決筆錄
被　　　告　甲
法官當庭宣示主文如下
一、主　文
甲犯竊盜罪，處拘役參拾日。
二、犯罪事實要旨
甲於……竊取……
三、處罰條文
刑法第320條第1項
中　華　民　國　112　年　4　月　6　日
"""

TITLE_WITH_CASE_NO = "臺灣臺北地方法院刑事判決　　110年度訴字第123號\n主　文\n無罪。\n理　由\n……\n中華民國110年5月3日\n"

NO_DATE_ORDER = """臺灣臺北地方法院民事裁定
主　　文
本票准予強制執行。
理　　由
一、聲請意旨略以……
以上正本證明與原本無異。
司法事務官　某
"""


def test_transcript_numbered_headings():
    assert labels(TRANSCRIPT) == ["HEADER", "MAIN", "FACTS", "BODY_OTHER", "CLOSING"]
    assert segment(TRANSCRIPT)["doc_kind"] == "宣示判決筆錄"


def test_title_followed_by_case_number():
    assert segment(TITLE_WITH_CASE_NO)["doc_kind"] == "判決"


def test_closing_falls_back_to_certified_copy_line():
    r = segment(NO_DATE_ORDER)
    assert labels(NO_DATE_ORDER) == ["HEADER", "MAIN", "REASONS", "CLOSING"] and r["status"] == "ok"


ONE_PARAGRAPH_ORDER = """臺灣臺北地方法院民事裁定
112年度北補字第2052號
原　　告　甲
上列當事人間請求確認本票債權不存在事件，原告起訴未繳納裁判費……特此裁定。
中　華　民　國　112　年　10　月　30　日
　　　　　　臺北簡易庭　法　官　某
"""


def test_one_paragraph_order_is_unstructured_with_closing():
    r = segment(ONE_PARAGRAPH_ORDER)
    assert r["status"] == "unstructured" and labels(ONE_PARAGRAPH_ORDER) == ["HEADER", "CLOSING"]
