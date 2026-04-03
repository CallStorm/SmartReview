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
