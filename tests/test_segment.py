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


def test_rare_colon_and_variant_heading():
    doc = "臺灣臺北地方法院民事簡易判決\n主　文\n駁回。\n事實暨理由︰\n一、原告主張……\n中華民國112年1月1日\n"
    assert labels(doc) == ["HEADER", "MAIN", "FACTS_REASONS", "CLOSING"]


def test_numbered_heading_inside_reasons_is_not_a_section():
    doc = "臺灣臺北地方法院刑事判決\n主　文\n無罪。\n理　由\n一、犯罪事實\n公訴意旨略以……\n中華民國112年1月1日\n"
    assert labels(doc) == ["HEADER", "MAIN", "REASONS", "CLOSING"]


def test_reasons_without_heading_start_at_first_level_enumeration():
    doc = "臺灣高等法院臺中分院民事判決\n主　文\n上訴駁回。\n壹、程序方面：\n一、按……\n貳、實體方面：\n中華民國95年1月1日\n"
    r = segment(doc)
    assert labels(doc) == ["HEADER", "MAIN", "REASONS", "CLOSING"] and r["status"] == "ok"
    assert r["sections"][2]["heading"] == "(implicit)"


def test_small_claims_judgment_with_only_main_is_main_only():
    doc = "臺灣新北地方法院小額民事判決\n111年度板小字第1號\n主　文\n被告應給付原告新臺幣1萬元。\n中華民國111年3月1日\n"
    assert segment(doc)["status"] == "main_only"


def test_flat_constitutional_court_decision():
    doc = ("憲法法庭裁定111年憲裁字第883號聲請人甲上列聲請人聲請解釋憲法，本庭裁定如下：主文本件不受理。"
           "理由一、聲請人主張略以：爰於中華民國111年1月3日依大審法聲請。二、核與要件不合，應不受理。"
           "中 華 民 國111年8月11日 憲法法庭 審判長大法官 某")
    r = segment(doc)
    assert labels(doc) == ["HEADER", "MAIN", "REASONS", "CLOSING"] and r["status"] == "ok"
    closing = r["sections"][-1]
    assert doc[closing["start"]:].startswith("中 華 民 國111年8月11日 憲法法庭")   # not the date inside the reasons


def test_semi_flat_judgment_inline_headings():
    doc = ("臺灣臺中地方法院刑事判決\r\n主　　文\r\n甲犯傷害罪，處有期徒刑陸月。\r\n"
           "壹日。　　犯罪事實一、甲於……\r\n起訴。　　理　　由壹、證據能力部分：\r\n本案……\r\n"
           "到庭執行職務。中　　華　　民　　國　　114 　年　　10　　月　　14　　日　　　刑事第三庭審判長法　官　某")
    assert labels(doc) == ["HEADER", "MAIN", "FACTS", "REASONS", "CLOSING"]


def test_spaced_numerals_in_date_line():
    doc = "臺灣板橋地方法院刑事判決\n主　文\n無罪。\n理　由\n……\n中      華      民      國      九  十      年      一      月    九    日\n"
    assert labels(doc)[-1] == "CLOSING"


def test_inline_words_in_running_text_are_not_headings():
    doc = ("臺灣臺北地方法院民事判決\n主　文\n駁回。\n理　由\n一、按……。理由如下：……。事實上，……\n"
           "中華民國112年1月1日\n")
    assert labels(doc) == ["HEADER", "MAIN", "REASONS", "CLOSING"]


def test_flat_reasons_without_enumerator_and_date_after_yu_excluded():
    doc = ("憲法法庭裁定本庭裁定如下：主文本件不受理。理由聲請意旨略以：爰於中華民國111年1月3日依司法院大法官審理案件法聲請。"
           "核與要件不合。中 華 民 國111年8月11日 憲法法庭 審判長大法官 某")
    r = segment(doc)
    assert labels(doc) == ["HEADER", "MAIN", "REASONS", "CLOSING"]
    assert doc[r["sections"][-1]["start"]:].startswith("中 華 民 國111年8月11日")


def test_nian_date_and_right_side_certified_copy():
    doc = ("臺灣臺北地方法院小額民事裁定\n主　　文\n本件應再開言詞辯論。\n"
           "中　　　華　　　民　　　國　　　　九十一　　年　　　六　　月　　廿一　　日\n"
           "　　　臺灣臺北地方法院臺北簡易庭　法官　某\n右為正本係照原本作成。\n"
           "中　　　華　　　民　　　國　　九十一　　年　　　六　　　月　　二十四　　日\n")
    r = segment(doc)
    assert labels(doc) == ["HEADER", "MAIN", "CLOSING"]
    assert doc[r["sections"][-1]["start"]:].lstrip().startswith("中　　　華　　　民　　　國　　　　九十一　　年　　　六　　月　　廿一")


def test_statute_appendix_without_fulu_after_closing():
    doc = ("臺灣臺中地方法院刑事簡易判決\n主　文\n甲犯不能安全駕駛罪。\n事實及理由\n一、……\n"
           "中　華　民　國　110　年　7　月　13　日\n　刑事第二庭　法　官　某\n以上正本證明與原本無異。\n"
           "中　華　民　國　110　年　7　月　13　日\n所犯法條：\n刑法第185條之3第1項第1款：\n駕駛動力交通工具……\n")
    assert labels(doc) == ["HEADER", "MAIN", "FACTS_REASONS", "CLOSING", "APPENDIX_LAW"]


def test_so_fan_fa_tiao_inside_body_is_not_appendix():
    # in an attached indictment or body, 所犯法條 is a body heading, not the appendix
    doc = "臺灣臺北地方法院刑事簡易判決\n主　文\n甲犯竊盜罪。\n所犯法條\n刑法第320條\n中華民國112年1月1日\n"
    assert "APPENDIX_LAW" not in labels(doc)
