"""审核 pipeline 读取运行时 LLM/截断设置。"""

from __future__ import annotations

from app.services.review_pipeline import _content_prompt


def test_content_prompt_uses_runtime_text_cap():
    long_text = "章" * 500
    prompt = _content_prompt(
        long_text,
        "",
        "",
        "【检查项清单】\n- n1-1: 测试",
        content_text_cap=100,
    )
    body = prompt.split("【引用章节正文】", 1)[0]
    assert "章" * 100 in body
    assert "章" * 101 not in body
    assert "本节正文超长，已截断" in body
