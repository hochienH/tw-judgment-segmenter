import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from annotation import strip_markers, with_markers  # noqa: E402


def test_roundtrip_own_line_markers():
    text = "標題\r\n主　文\r\n無罪。\r\n"
    secs = [{"label": "HEADER", "start": 0}, {"label": "MAIN", "start": 4}]
    back, bounds = strip_markers(with_markers(text, secs))
    assert back == text and bounds == [(0, "HEADER"), (4, "MAIN")]


def test_inline_markers_for_flat_documents():
    ann = "⟪HEADER⟫\n憲法法庭裁定本庭裁定如下：⟪MAIN⟫主文本件不受理。⟪REASONS⟫理由一、……"
    back, bounds = strip_markers(ann)
    assert back == "憲法法庭裁定本庭裁定如下：主文本件不受理。理由一、……"
    assert bounds == [(0, "HEADER"), (13, "MAIN"), (21, "REASONS")]


def test_note_lines_are_ignored():
    back, _ = strip_markers("⟪HEADER⟫\n內文\n# NOTE: 不確定\n")
    assert back == "內文\n"


def test_marker_line_saved_with_crlf_by_editor():
    back, bounds = strip_markers("⟪HEADER⟫\r\n標題\r\n⟪MAIN⟫\r\n主　文\r\n")
    assert back == "標題\r\n主　文\r\n" and bounds == [(0, "HEADER"), (4, "MAIN")]


def test_pua_hint_roundtrip():
    text = "標題\r\n原告主張：\r\n"
    exported = with_markers(text, [{"label": "HEADER", "start": 0}])
    assert "⟦U+F6B0⟧" in exported
    assert strip_markers(exported)[0] == text
