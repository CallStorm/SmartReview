"""Extract inline images from docx paragraphs and upload to object storage."""

from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from docx import Document

from app.services import minio_storage

_DRAWING_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_CONTENT_TYPE_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/svg+xml": ".svg",
}


@dataclass
class DocxImageUploadResult:
    paragraph_image_keys: dict[int, list[str]]
    uploaded_count: int
    failed_count: int


def _object_prefix_for_docx(object_key: str) -> str:
    key = (object_key or "").strip()
    if not key:
        return "reviews/unknown"
    if "." in key.rsplit("/", maxsplit=1)[-1]:
        return key.rsplit(".", maxsplit=1)[0]
    return key


def _ext_from_content_type(content_type: str) -> str:
    return _CONTENT_TYPE_TO_EXT.get((content_type or "").lower().strip(), ".bin")


def _iter_run_image_rel_ids(run: Any) -> list[str]:
    rel_ids: list[str] = []
    for blip in run._element.findall(f".//{{{_DRAWING_NS}}}blip"):
        rid = blip.get(f"{{{_REL_NS}}}embed")
        if rid:
            rel_ids.append(str(rid))
    return rel_ids


def extract_and_store_docx_images(
    *,
    docx_bytes: bytes,
    source_object_key: str,
) -> DocxImageUploadResult:
    prefix = _object_prefix_for_docx(source_object_key)
    paragraph_image_keys: dict[int, list[str]] = defaultdict(list)
    uploaded_count = 0
    failed_count = 0
    serial = 0

    doc = Document(io.BytesIO(docx_bytes))
    for paragraph_index, paragraph in enumerate(doc.paragraphs):
        for run in paragraph.runs:
            rel_ids = _iter_run_image_rel_ids(run)
            if not rel_ids:
                continue
            for rid in rel_ids:
                part = paragraph.part.related_parts.get(rid)
                if part is None:
                    failed_count += 1
                    continue
                blob = getattr(part, "blob", None)
                if not isinstance(blob, bytes) or not blob:
                    failed_count += 1
                    continue
                serial += 1
                content_type = str(getattr(part, "content_type", "") or "application/octet-stream")
                ext = _ext_from_content_type(content_type)
                object_key = f"{prefix}/images/p{paragraph_index:04d}_{serial:04d}{ext}"
                try:
                    minio_storage.put_object(
                        object_key=object_key,
                        data=blob,
                        length=len(blob),
                        content_type=content_type,
                    )
                except Exception:
                    failed_count += 1
                    continue
                paragraph_image_keys[paragraph_index].append(object_key)
                uploaded_count += 1

    return DocxImageUploadResult(
        paragraph_image_keys=dict(paragraph_image_keys),
        uploaded_count=uploaded_count,
        failed_count=failed_count,
    )
