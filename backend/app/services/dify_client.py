"""Call Dify HTTP API using configured base URL and API key."""

from __future__ import annotations

from typing import Any

import httpx


def list_dataset_catalog(base_url: str, api_key: str, *, page: int = 1, limit: int = 100) -> list[dict[str, Any]]:
    """GET /datasets — knowledge base list (requires Dataset API key in Dify)."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Dify 服务地址未配置")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Dify API 密钥未配置")
    url = f"{base}/datasets"
    headers = {"Authorization": f"Bearer {key}"}
    with httpx.Client(timeout=45.0) as client:
        resp = client.get(url, headers=headers, params={"page": page, "limit": limit})
        resp.raise_for_status()
        body = resp.json()
    rows = body.get("data")
    if not isinstance(rows, list):
        return []
    out: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        did = item.get("id")
        if did is None:
            continue
        name = item.get("name")
        out.append({"id": str(did), "name": str(name) if name is not None else ""})
    return out


def retrieve_dataset_chunks(
    base_url: str,
    api_key: str,
    dataset_id: str,
    query: str,
    *,
    top_k: int = 5,
    timeout: float = 45.0,
) -> str:
    """POST /datasets/{id}/retrieve — returns concatenated segment texts for prompting."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Dify 服务地址未配置")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Dify API 密钥未配置")
    q = (query or "").strip()
    if not q:
        return ""
    url = f"{base}/datasets/{dataset_id}/retrieve"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload: dict[str, Any] = {
        "query": q[:250],
        "retrieval_model": {
            "search_method": "semantic_search",
            "reranking_enable": False,
            "top_k": top_k,
            "score_threshold_enabled": False,
        },
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            payload_min: dict[str, Any] = {"query": q[:250]}
            resp = client.post(url, headers=headers, json=payload_min)
        resp.raise_for_status()
        body = resp.json()
    parts: list[str] = []
    records = body.get("records")
    if not isinstance(records, list):
        return ""
    for rec in records:
        if not isinstance(rec, dict):
            continue
        seg = rec.get("segment")
        if isinstance(seg, dict):
            content = seg.get("content")
            if isinstance(content, str) and content.strip():
                parts.append(content.strip())
    return "\n\n---\n\n".join(parts)
