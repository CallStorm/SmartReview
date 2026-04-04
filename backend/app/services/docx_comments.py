"""Inject Word comments into .docx (OOXML) at body paragraph indices."""

from __future__ import annotations

import re
import zipfile
from datetime import UTC, datetime
from io import BytesIO

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree


def _direct_body_paragraphs(body: etree.Element) -> list[etree.Element]:
    return [c for c in body if c.tag == qn("w:p")]


def _next_rel_id(rels_xml: str) -> str:
    ids = [int(m.group(1)) for m in re.finditer(r'Id="rId(\d+)"', rels_xml)]
    return f"rId{max(ids, default=0) + 1}"


def _ensure_content_type(ct: str, part: str, content_type: str) -> str:
    if part in ct:
        return ct
    insert = f'<Override PartName="{part}" ContentType="{content_type}"/>'
    return ct.replace("</Types>", insert + "</Types>")


def _ensure_comments_rel(rels: str, rel_id: str) -> str:
    if "relationships/comments" in rels:
        return rels
    line = (
        f'<Relationship Id="{rel_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments" '
        f'Target="comments.xml"/>'
    )
    return rels.replace("</Relationships>", line + "</Relationships>")


def _build_comment_element(cid: int, author: str, text: str) -> etree.Element:
    c = OxmlElement("w:comment")
    c.set(qn("w:id"), str(cid))
    c.set(qn("w:author"), author[:128])
    c.set(qn("w:date"), datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    c.set(qn("w:initials"), "SR")
    p = OxmlElement("w:p")
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    t.text = (text or "")[:12000]
    r.append(t)
    p.append(r)
    c.append(p)
    return c


def _rebuild_zip(
    zin: zipfile.ZipFile,
    document_xml: bytes,
    comments_xml: bytes,
    content_types: bytes,
    document_rels: bytes,
) -> bytes:
    out_buf = BytesIO()
    had_comments_entry = False
    with zipfile.ZipFile(out_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            name = info.filename
            if name == "word/document.xml":
                zout.writestr(name, document_xml)
            elif name == "word/comments.xml":
                zout.writestr(name, comments_xml)
                had_comments_entry = True
            elif name == "[Content_Types].xml":
                zout.writestr(name, content_types)
            elif name == "word/_rels/document.xml.rels":
                zout.writestr(name, document_rels)
            else:
                zout.writestr(info, zin.read(name))
        if not had_comments_entry:
            zout.writestr("word/comments.xml", comments_xml)
    return out_buf.getvalue()


def inject_comments_at_paragraphs(
    docx_bytes: bytes,
    annotations: list[tuple[int, str]],
    *,
    author: str = "SmartReview",
) -> bytes:
    """
    annotations: (paragraph_index_in_body, comment_plain_text).
    Only top-level w:p under w:body are counted (matches python-docx document.paragraphs).
    """
    if not annotations:
        return docx_bytes

    buf_in = BytesIO(docx_bytes)
    with zipfile.ZipFile(buf_in, "r") as zin:
        names = set(zin.namelist())
        doc_xml = zin.read("word/document.xml")
        ct = zin.read("[Content_Types].xml").decode("utf-8")
        rels_path = "word/_rels/document.xml.rels"
        rels = zin.read(rels_path).decode("utf-8") if rels_path in names else (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
        )

        root = etree.fromstring(doc_xml)
        body = root.find(qn("w:body"))
        if body is None:
            return docx_bytes
        ps = _direct_body_paragraphs(body)

        if "word/comments.xml" in names:
            comments_tree = etree.fromstring(zin.read("word/comments.xml"))
        else:
            comments_tree = etree.fromstring(
                b'<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
            )

        base_cid = 0
        for el in comments_tree.findall(qn("w:comment")):
            i = el.get(qn("w:id"))
            if i is not None and str(i).isdigit():
                base_cid = max(base_cid, int(i) + 1)

        sorted_ann = sorted(annotations, key=lambda x: x[0])
        cid = base_cid
        marks: list[tuple[int, int]] = []
        for para_idx, msg in sorted_ann:
            if para_idx < 0 or para_idx >= len(ps):
                continue
            comments_tree.append(_build_comment_element(cid, author, msg))
            marks.append((para_idx, cid))
            cid += 1

        if not marks:
            return docx_bytes

        for para_idx, comment_id in marks:
            p = ps[para_idx]
            sid = str(comment_id)
            start = OxmlElement("w:commentRangeStart")
            start.set(qn("w:id"), sid)
            p.insert(0, start)
            end = OxmlElement("w:commentRangeEnd")
            end.set(qn("w:id"), sid)
            p.append(end)
            r = OxmlElement("w:r")
            cref = OxmlElement("w:commentReference")
            cref.set(qn("w:id"), sid)
            r.append(cref)
            p.append(r)

        new_doc = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
        comments_bytes = etree.tostring(
            comments_tree, xml_declaration=True, encoding="UTF-8", standalone=True
        )
        ct_new = _ensure_content_type(
            ct,
            "/word/comments.xml",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
        )
        rels_new = _ensure_comments_rel(rels, _next_rel_id(rels))
        return _rebuild_zip(zin, new_doc, comments_bytes, ct_new.encode("utf-8"), rels_new.encode("utf-8"))
