"""检查项清单拆分（services/checklist.py）单测。

用例文本取自线上模板 12（悬挑脚手架）的真实 review_prompt。
"""

from __future__ import annotations

from app.services.checklist import (
    CHECKLIST_VERSION,
    build_checklist_block,
    checklist_signature,
    explicit_check_items,
    split_check_items,
)


def _ids(items):
    return [it["id"] for it in items]


def test_single_sentence_single_item():
    items, notes = split_check_items("n5", "核对是否描述施工地的气候特征和季节性天气。")
    assert _ids(items) == ["n5-1"]
    assert items[0]["text"].startswith("核对是否描述")
    assert notes == []


def test_multi_sentence_prose_splits_per_sentence():
    prompt = (
        "核对是否含有本项目工程概况，核对是否含有悬挑脚手架工程概况（搭设区域与范围）。"
        "核对是否含有工程及周边环境情况描述。"
        "若无工程及周边环境情况描述，则属于严重缺陷。"
        "如果判断属于严重缺陷，那么属于严重缺陷这句话一定要指出来。"
    )
    items, notes = split_check_items("n2", prompt)
    assert _ids(items) == ["n2-1", "n2-2"]
    assert len(notes) == 2  # 判级说明 + 输出要求 -> 附注


def test_circled_markers_become_separate_items():
    prompt = (
        "请检查是否含有脚手架搭设标准、剪刀撑、周边拉结等各类构造措施内容。\n"
        "① 若高度超过20米的悬挑脚手架无架体卸荷措施，属于严重缺陷\n"
        "如果判断属于严重缺陷，那么属于严重缺陷这句话一定要指出来。"
    )
    items, notes = split_check_items("n19", prompt)
    assert _ids(items) == ["n19-1", "n19-2"]
    # 带圈标记从检查项文本中剥离
    assert "①" not in items[1]["text"]
    assert "20米" in items[1]["text"]
    assert notes and notes[0].startswith("如果判断")


def test_parenthesized_circled_block_splits_and_drops_dangling_paren():
    prompt = (
        "核对是否包含安全保证措施、质量技术保证措施、文明施工保证措施、环境保护措施、"
        "季节性施工保证措施等。（①施工中若涉及高处作业、临时用电，应在安全保证措施中写明"
        "相应的安全技术保证措施；②质量技术保证措施中，应对照主要工程施工内容，制定相应质量保证措施）。"
        "如无技术保障措施，则为严重缺陷。"
    )
    items, notes = split_check_items("n23", prompt)
    assert len(items) == 3
    dangling = [it for it in items if not it["text"].strip("（）()。；;，, ")]
    assert dangling == []
    assert any("如无技术保障措施" in n for n in notes)


def test_clarify_sentences_go_to_notes():
    prompt = "核对是否含有其他人员的名单及岗位职责。只需要含有人员和岗位职责就行，不需要纠结其他人员的数量及种类。"
    items, notes = split_check_items("n29", prompt)
    assert _ids(items) == ["n29-1"]
    assert any("不需要纠结" in n for n in notes)


def test_punctuation_only_sentence_dropped():
    prompt = "核对是否含有具体验收程序，是否含有验收人员组成。。注意不需要专家论证的如写出了专家论证，请指出。"
    items, notes = split_check_items("n32", prompt)
    assert all(it["text"] for it in items)
    assert any(it["text"].startswith("核对是否含有具体验收程序") for it in items)
    assert any("注意" in n for n in notes)


def test_explicit_check_items_override():
    node = {
        "id": "n99",
        "review_prompt": "核对是否含有X。核对是否含有Y。",
        "check_items": [{"id": "n99-a", "text": "检查X"}, "检查Y"],
    }
    explicit = explicit_check_items(node)
    assert explicit == [
        {"id": "n99-a", "text": "检查X"},
        {"id": "n99-2", "text": "检查Y"},
    ]
    items, notes = split_check_items("n99", node["review_prompt"], node=node)
    assert items == explicit
    assert notes == []


def test_empty_prompt_returns_empty():
    items, notes = split_check_items("n1", "")
    assert items == []
    assert notes == []


def test_build_checklist_block_renders_ids_and_notes():
    block = build_checklist_block(
        [{"id": "n20-1", "text": "检查主材质量标准"}],
        ["注意 X"],
    )
    assert "[n20-1] 检查主材质量标准" in block
    assert "共 1 项" in block
    assert "- 注意 X" in block


def test_checklist_signature_stable_and_sensitive():
    items = [{"id": "a-1", "text": "t"}]
    notes = ["n"]
    s1 = checklist_signature(items, notes, "rules")
    s2 = checklist_signature(list(items), list(notes), "rules")
    assert s1 == s2
    assert CHECKLIST_VERSION in s1
    assert s1 != checklist_signature(items, notes, "rules2")
    assert s1 != checklist_signature([{"id": "a-1", "text": "t2"}], notes, "rules")


def test_trailing_balanced_close_paren_kept():
    """与句内开括号配对的尾括号必须保留（roundtrip 关键）。"""
    from app.services.checklist import split_check_items
    prompt = "核对是否含有风险因素辨识（如坍塌、触电等）\n核对是否含有风险分级"
    items, _ = split_check_items("n1", prompt)
    assert items[0]["text"] == "核对是否含有风险因素辨识（如坍塌、触电等）"
    assert items[1]["text"] == "核对是否含有风险分级"


def test_dangling_close_paren_stripped():
    """跨句悬空的尾括号仍应去除。"""
    from app.services.checklist import _clean_segment
    assert _clean_segment("核对内容）") == "核对内容"
    assert _clean_segment("（核对内容") == "核对内容"
    assert _clean_segment("（核对内容）") == "（核对内容）"
