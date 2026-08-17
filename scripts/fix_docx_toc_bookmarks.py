"""fix_docx_toc_bookmarks.py
=============================

扫描 docx 文件，给所有 heading 1/2/3 段落补 _Toc* bookmarkStart/End，
修复 TOC 字段里 PAGEREF / HYPERLINK 报「Error! Bookmark not defined」的问题。

用法：
    python scripts/fix_docx_toc_bookmarks.py \
        --input  <待修复 docx> \
        --output <输出 docx，不覆盖 input>

只读 input，写新文件到 output。绝不覆盖原文件。

匹配策略：
    - 解析 TOC 字段里所有 PAGEREF/HYPERLINK 指向的 _Toc* 名字，按出现顺序排
    - 扫描所有 heading 1/2/3 段落，按文档顺序排
    - 按顺序一一配对：第 N 个 heading 插入第 N 个 _Toc* bookmark
    - 数量不一致时打 warning，但仍按 min(两者) 修复

输出：报告扫描到几个 heading、命中几个 _Toc*、修了几条、还差几个。
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSMAP = {"w": W_NS}


def _q(tag: str) -> str:
    """Build qualified name like {ns}localname."""
    return f"{{{W_NS}}}{tag}"


def _load_doc_xml(docx_path: Path) -> etree._ElementTree:
    """Read word/document.xml from the docx zip."""
    with zipfile.ZipFile(docx_path) as z:
        xml_bytes = z.read("word/document.xml")
    return etree.fromstring(xml_bytes), xml_bytes


def _save_docx(src: Path, dst: Path, new_doc_xml: bytes) -> None:
    """Rewrite word/document.xml inside the zip, copy everything else as-is."""
    if dst.resolve() == src.resolve():
        raise RuntimeError("output must differ from input (refuse to overwrite source)")
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(
        dst, "w", zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(item, new_doc_xml)
            else:
                zout.writestr(item, zin.read(item.filename))


def _extract_toc_bookmark_names(doc_xml: bytes) -> list[str]:
    """从 TOC 字段内的 HYPERLINK \\l "<name>" 提取 _Toc* 名字，按出现顺序。

    Word/WPS 的 TOC 字段结构：每条目录项有
      - <w:instrText> HYPERLINK \\l "_Toc12345" </w:instrText>
      - 实际显示的文本（缓存）
      - <w:instrText> PAGEREF _Toc12345 \\h </w:instrText>
      - 实际显示的页码（缓存）
    HYPERLINK 和 PAGEREF 成对出现，所以只需取 HYPERLINK 列表即可。
    """
    text = doc_xml.decode("utf-8")
    # Match HYPERLINK \l "_Toc<digits>"
    names = re.findall(r'HYPERLINK\s+\\l\s+"(_Toc\d+)"', text)
    return names


def _existing_bookmark_ids(doc_xml: bytes) -> set[int]:
    """返回 docx 里已使用的 <w:bookmarkStart w:id="N"> 集合，避免 id 冲突。"""
    text = doc_xml.decode("utf-8")
    return {int(m) for m in re.findall(r'<w:bookmarkStart[^>]*w:id="(\d+)"', text)}


def _existing_toc_bookmark_names(doc_xml: bytes) -> set[str]:
    """返回已存在的 _Toc* bookmark 名字集合。"""
    text = doc_xml.decode("utf-8")
    return set(re.findall(r'<w:bookmarkStart[^>]*w:name="(_Toc\d+)"', text))


def _find_heading_paragraphs(root: etree._Element) -> list[etree._Element]:
    """扫描所有段落，返回 pStyle id 是 4 / 5 / 6（即 H1 / H2 / H3）的 <w:p> 元素。

    注：styleId "4"/"5"/"6" 对应 styles.xml 里的 name="heading 1"/"heading 2"/"heading 3"。
    也兼容 pStyle w:val="Heading1"/"Heading2" 写法。
    """
    heading_style_ids = {"4", "5", "6"}
    out: list[etree._Element] = []
    for p in root.iter(_q("p")):
        pStyle = p.find(f"{_q('pPr')}/{_q('pStyle')}")
        if pStyle is None:
            continue
        val = pStyle.get(_q("val")) or ""
        if val in heading_style_ids or val in {"Heading1", "Heading2", "Heading3"}:
            out.append(p)
    return out


def _make_bookmark_pair(name: str, bm_id: int) -> tuple[etree._Element, etree._Element]:
    """生成 <w:bookmarkStart> 和 <w:bookmarkEnd>。"""
    start = etree.SubElement(etree.Element(_q("dummy")), _q("bookmarkStart"))
    start.set(_q("id"), str(bm_id))
    start.set(_q("name"), name)
    end = etree.SubElement(etree.Element(_q("dummy")), _q("bookmarkEnd"))
    end.set(_q("id"), str(bm_id))
    return start, end


def _insert_bookmark_into_paragraph(p: etree._Element, name: str, bm_id: int) -> None:
    """在 heading 段落开头插入 bookmarkStart，结尾插入 bookmarkEnd。

    段落结构示例：
      <w:p>
        <w:pPr>...</w:pPr>
        <w:r>...</w:r>          ← 第一个 run
        ...
      </w:p>
    插入位置：pPr 之后（如果有），第一个 run 之前；bookmarkEnd 放在段落最后子元素之后。
    """
    start, end = _make_bookmark_pair(name, bm_id)
    # 找到 pPr 之后的位置
    pPr = p.find(_q("pPr"))
    if pPr is not None:
        # pPr 紧跟其后插入 start
        pPr.addnext(start)
    else:
        # 没有 pPr，插到最前
        p.insert(0, start)
    # end 放在段落最后
    p.append(end)


def fix_docx(src: Path, dst: Path) -> dict:
    """主流程，返回统计 dict。"""
    root, doc_xml_bytes = _load_doc_xml(src)

    expected_names = _extract_toc_bookmark_names(doc_xml_bytes)
    existing_names = _existing_toc_bookmark_names(doc_xml_bytes)
    heading_paragraphs = _find_heading_paragraphs(root)
    used_ids = _existing_bookmark_ids(doc_xml_bytes)

    # 找出需要补的：expected 但 existing 没有
    missing_names = [n for n in expected_names if n not in existing_names]

    # 按顺序配对
    n = min(len(missing_names), len(heading_paragraphs))
    next_id = max(used_ids, default=0) + 1

    added = 0
    for i in range(n):
        name = missing_names[i]
        p = heading_paragraphs[i]
        _insert_bookmark_into_paragraph(p, name, next_id)
        next_id += 1
        added += 1

    # 把修改后的 root 序列化回 bytes
    new_xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    _save_docx(src, dst, new_xml)

    return {
        "expected_toc_names": len(expected_names),
        "already_existing": len(existing_names),
        "missing_to_add": len(missing_names),
        "headings_found": len(heading_paragraphs),
        "added": added,
        "unmatched_names": len(missing_names) - added,
        "unmatched_headings": len(heading_paragraphs) - added,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Fix missing _Toc* bookmarks in a docx file")
    ap.add_argument("--input", required=True, help="input docx (read-only)")
    ap.add_argument("--output", required=True, help="output docx (written)")
    args = ap.parse_args(argv)

    src = Path(args.input).resolve()
    dst = Path(args.output).resolve()

    if not src.is_file():
        print(f"ERROR: input not found: {src}", file=sys.stderr)
        return 2
    if dst.exists() and dst.resolve() == src.resolve():
        print("ERROR: output must differ from input", file=sys.stderr)
        return 2
    dst.parent.mkdir(parents=True, exist_ok=True)

    import time

    t0 = time.perf_counter()
    stats = fix_docx(src, dst)
    elapsed = time.perf_counter() - t0

    print(f"=== fix_docx_toc_bookmarks 报告 ===")
    print(f"input : {src}")
    print(f"output: {dst}")
    print(f"size  : {dst.stat().st_size:,} bytes")
    print(f"elapsed: {elapsed:.3f}s")
    print()
    print(f"TOC 期望 _Toc* 名字数 : {stats['expected_toc_names']}")
    print(f"已存在 bookmarkStart   : {stats['already_existing']}")
    print(f"需补 bookmark 数      : {stats['missing_to_add']}")
    print(f"扫描到 heading 段落数 : {stats['headings_found']}")
    print(f"实际添加 bookmark 数  : {stats['added']}")
    if stats["unmatched_names"]:
        print(f"[WARN] unmatched TOC names  : {stats['unmatched_names']}")
    if stats["unmatched_headings"]:
        print(f"[WARN] unmatched headings    : {stats['unmatched_headings']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))