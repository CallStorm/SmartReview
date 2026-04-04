"""Parse .docx outline into a tree (Heading 1–9 + body lines on current section)."""

from __future__ import annotations

import io
import json
import re
from typing import Any

from docx import Document
from docx.text.paragraph import Paragraph


def _heading_level(paragraph: Paragraph) -> int | None:
    name = paragraph.style.name if paragraph.style else ""
    if not name:
        return None
    m = re.match(r"Heading\s*(\d+)\s*$", name.strip(), re.I)
    if m:
        return int(m.group(1))
    # Chinese heading styles sometimes named "标题 1"
    m = re.match(r"标题\s*(\d+)\s*$", name.strip())
    if m:
        return int(m.group(1))
    return None


def parse_docx_to_tree(file_obj: io.BytesIO) -> dict[str, Any]:
    file_obj.seek(0)
    doc = Document(file_obj)
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"n{counter}"

    nodes_out: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []

    def current_parent_children() -> list[dict[str, Any]]:
        if not stack:
            return nodes_out
        return stack[-1]["children"]

    para_index = 0
    for para in doc.paragraphs:
        text = (para.text or "").strip()
        level = _heading_level(para)
        if level is not None and text:
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            node: dict[str, Any] = {
                "id": next_id(),
                "level": level,
                "title": text,
                "heading_para_index": para_index,
                "content": [],
                "children": [],
            }
            current_parent_children().append(node)
            stack.append(node)
        elif text and stack:
            stack[-1]["content"].append(text)
        para_index += 1

    return {"nodes": nodes_out}


def tree_to_json_str(tree: dict[str, Any]) -> str:
    return json.dumps(tree, ensure_ascii=False)
