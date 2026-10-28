from segmenter import segment
from segmenter.functional import coverage, label_node, label_nodes, strip_enum
from segmenter.outline import outline

CIVIL = """臺灣臺北地方法院民事判決
主　文
原告之訴駁回。
事實及理由
壹、程序方面：
一、本件被告經合法通知，未於言詞辯論期日到場，爰依原告之聲請，由其一造辯論而為判決。
貳、實體方面：
一、原告主張：
㈠被告於民國110年向原告借款新臺幣10萬元。
㈡迄未清償。
二、被告則以：否認借款等語置辯。
三、兩造不爭執事項：
㈠被告曾收受10萬元。
四、本院之判斷：
㈠按當事人主張有利於己之事實者，就其事實有舉證之責任。
㈡經查，原告所提證據不足以證明借貸合意。
五、綜上所述，原告之請求為無理由，應予駁回。
六、訴訟費用負擔之依據：民事訴訟法第78條。
中　華　民　國　111　年　3　月　1　日
"""

CRIMINAL = """臺灣臺北地方法院刑事判決
主　文
甲○○犯竊盜罪，處拘役二十日。
事　實
一、甲○○於民國110年1月1日在臺北市竊取他人財物。
二、案經被害人訴由警方報告臺灣臺北地方檢察署檢察官偵查起訴。
理　由
一、程序部分：按被告以外之人於審判外之陳述，依刑事訴訟法第159條之5規定有證據能力。
二、訊據被告坦承不諱，核與證人證述相符，事證明確，犯行堪以認定。
三、核被告所為，係犯刑法第320條第1項之竊盜罪。
四、爰審酌被告犯罪之動機、手段，量處如主文所示之刑。
五、沒收部分：扣案如附表所示之物沒收之。
六、據上論斷，應依刑事訴訟法第299條第1項前段，判決如主文。
中　華　民　國　111　年　3　月　1　日
"""


def labels(text, group):
    sections = segment(text)["sections"]
    nodes = outline(text, sections)["nodes"]
    out = label_nodes(text, nodes, group)
    return out, sections


def test_strip_enum():
    assert strip_enum("一、程序方面：本件") == "程序方面：本件"
    assert strip_enum("　　㈠原告主張：") == "原告主張："
    assert strip_enum("六㈠被告所為") == "被告所為"


def test_label_node_rules():
    assert label_node("程序方面：本件被告", "civil") == ("PROCEDURE", "heading")
    assert label_node("按當事人主張有利於己之事實者", "civil") == ("COURT_FINDING", "opening")
    assert label_node("依民事訴訟法第385條第1項前段規定", "civil") == ("PROCEDURE", "opening")
    assert label_node("核被告所為，係犯刑法第320條", "criminal") == ("CONVICTION", "opening")
    assert label_node("爰審酌被告犯罪之動機", "criminal") == ("SENTENCING", "opening")
    assert label_node("系爭土地之界址如附圖所示", "civil") == (None, "none")


def test_civil_document():
    out, sections = labels(CIVIL, "民事")
    by_phrase = {x["phrase"][:6]: (x["label"], x["source"]) for x in out}
    assert by_phrase["程序方面："] == ("PROCEDURE", "heading")
    assert by_phrase["本件被告經合"] == ("PROCEDURE", "opening")
    assert by_phrase["實體方面："] == ("MERITS", "heading")
    assert by_phrase["原告主張："] == ("CLAIM", "heading")
    assert by_phrase["被告於民國1"] == ("CLAIM", "inherit")
    assert by_phrase["被告則以：否"] == ("DEFENCE", "heading")
    assert by_phrase["兩造不爭執事"] == ("UNDISPUTED", "heading")
    assert by_phrase["本院之判斷："] == ("COURT_FINDING", "heading")
    assert by_phrase["經查，原告所"] == ("COURT_FINDING", "opening")
    assert by_phrase["綜上所述，原"] == ("COURT_FINDING", "opening")
    assert by_phrase["訴訟費用負擔"] == ("CLOSING", "heading")
    cov = coverage(sections, out)
    assert cov.get("UNLABELLED", 0) == 0 and cov["CLAIM"] > 0 and cov["COURT_FINDING"] > 0


def test_criminal_document():
    out, sections = labels(CRIMINAL, "刑事")
    reasons = [(x["label"], x["source"]) for x in out if x["section"] == "REASONS"]
    assert [lab for lab, _ in reasons] == ["PROCEDURE", "FACT_FINDING", "CONVICTION", "SENTENCING", "CONFISCATION", "CLOSING"]
    assert reasons[0][1] == "heading" and reasons[1][1] == "opening"
    cov = coverage(sections, out)
    assert cov.get("UNLABELLED", 0) == 0
