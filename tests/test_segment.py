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
