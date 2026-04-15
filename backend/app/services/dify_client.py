"""Call Dify HTTP API using configured base URL and API key."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any

import httpx


def _normalize_base(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def _auth_headers(api_key: str) -> dict[str, str]:
    key = (api_key or "").strip()
    return {"Authorization": f"Bearer {key}"}


def list_dataset_catalog(base_url: str, api_key: str, *, page: int = 1, limit: int = 100) -> list[dict[str, Any]]:
    """GET /datasets — knowledge base list (requires Dataset API key in Dify)."""
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Dify 服务地址未配置")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Dify API 密钥未配置")
    url = f"{base}/datasets"
    headers = _auth_headers(key)
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
        try:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code >= 400:
                payload_min: dict[str, Any] = {"query": q[:250]}
                resp = client.post(url, headers=headers, json=payload_min)
            resp.raise_for_status()
            body = resp.json()
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Dify 检索超时（dataset={dataset_id}, timeout={timeout}s）") from e
        except httpx.HTTPError as e:
            raise ValueError(f"Dify 检索失败（dataset={dataset_id}, endpoint={url}）: {e!s}") from e
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


@dataclass
class DifyDatasetKbMetric:
    id: str
    name: str
    segment_count: int
    truncated: bool = False


@dataclass
class DifyKbMetrics:
    configured: bool
    dataset_count: int
    segment_total: int
    datasets: list[DifyDatasetKbMetric] = field(default_factory=list)
    error: str | None = None
    truncated: bool = False


def list_all_datasets(
    base_url: str,
    api_key: str,
    *,
    page_limit: int = 100,
    timeout: float = 45.0,
) -> list[dict[str, Any]]:
    """Paginate GET /datasets until has_more is false."""
    base = _normalize_base(base_url)
    if not base:
        raise ValueError("Dify 服务地址未配置")
    key = (api_key or "").strip()
    if not key:
        raise ValueError("Dify API 密钥未配置")
    url = f"{base}/datasets"
    headers = _auth_headers(key)
    out: list[dict[str, Any]] = []
    page = 1
    with httpx.Client(timeout=timeout) as client:
        while True:
            resp = client.get(url, headers=headers, params={"page": page, "limit": page_limit})
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data")
            if not isinstance(rows, list):
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                did = item.get("id")
                if did is None:
                    continue
                name = item.get("name")
                out.append({"id": str(did), "name": str(name) if name is not None else ""})
            has_more = body.get("has_more")
            if has_more is False:
                break
            if len(rows) < page_limit:
                break
            page += 1
            if page > 500:
                break
    return out


def list_document_ids_in_dataset(
    base_url: str,
    api_key: str,
    dataset_id: str,
    *,
    page_limit: int = 100,
    timeout: float = 45.0,
) -> list[str]:
    """Paginate GET /datasets/{id}/documents."""
    base = _normalize_base(base_url)
    key = (api_key or "").strip()
    url = f"{base}/datasets/{dataset_id}/documents"
    headers = _auth_headers(key)
    ids: list[str] = []
    page = 1
    with httpx.Client(timeout=timeout) as client:
        while True:
            resp = client.get(url, headers=headers, params={"page": page, "limit": page_limit})
            resp.raise_for_status()
            body = resp.json()
            rows = body.get("data")
            if not isinstance(rows, list):
                break
            for item in rows:
                if not isinstance(item, dict):
                    continue
                doc_id = item.get("id")
                if doc_id is not None:
                    ids.append(str(doc_id))
            has_more = body.get("has_more")
            if has_more is False:
                break
            if len(rows) < page_limit:
                break
            page += 1
            if page > 500:
                break
    return ids


def get_document_segments_total(
    base_url: str,
    api_key: str,
    dataset_id: str,
    document_id: str,
    *,
    timeout: float = 30.0,
) -> int:
    """GET .../segments with page=1&limit=1; use response total (Dify Knowledge API)."""
    base = _normalize_base(base_url)
    key = (api_key or "").strip()
    seg_url = f"{base}/datasets/{dataset_id}/documents/{document_id}/segments"
    headers = _auth_headers(key)
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(seg_url, headers=headers, params={"page": 1, "limit": 1})
        resp.raise_for_status()
        body = resp.json()
    total = body.get("total")
    if isinstance(total, int) and total >= 0:
        return total
    if isinstance(total, float):
        return int(total)
    return 0


def collect_dify_kb_metrics(
    base_url: str,
    api_key: str,
    *,
    max_documents_per_dataset: int = 400,
    max_segment_lookups_total: int = 2500,
    max_workers: int = 6,
    timeout: float = 45.0,
) -> DifyKbMetrics:
    """
    List all datasets, then per dataset sum segment counts via one segments-list call per document.
    Caps work to avoid dashboard timeouts; sets truncated when caps hit.
    """
    try:
        datasets = list_all_datasets(base_url, api_key, timeout=timeout)
    except ValueError as e:
        return DifyKbMetrics(configured=False, dataset_count=0, segment_total=0, error=str(e))
    except httpx.HTTPError as e:
        return DifyKbMetrics(
            configured=True,
            dataset_count=0,
            segment_total=0,
            error=f"Dify 请求失败: {e!s}",
        )

    metrics_list: list[DifyDatasetKbMetric] = []
    segment_total = 0
    lookups_left = max_segment_lookups_total
    any_truncated = False

    for ds in datasets:
        if lookups_left <= 0:
            any_truncated = True
            break

        ds_id = ds["id"]
        ds_name = ds.get("name") or ""
        try:
            doc_ids = list_document_ids_in_dataset(base_url, api_key, ds_id, timeout=timeout)
        except httpx.HTTPError:
            any_truncated = True
            metrics_list.append(DifyDatasetKbMetric(id=ds_id, name=ds_name, segment_count=0, truncated=True))
            continue

        doc_trunc = len(doc_ids) > max_documents_per_dataset
        if doc_trunc:
            doc_ids = doc_ids[:max_documents_per_dataset]
            any_truncated = True

        batch = doc_ids[:lookups_left]
        if len(batch) < len(doc_ids):
            any_truncated = True

        counts: list[int] = []

        def _one(doc_id: str) -> int:
            return get_document_segments_total(base_url, api_key, ds_id, doc_id, timeout=min(timeout, 30.0))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_one, did): did for did in batch}
            for fut in as_completed(futures):
                try:
                    counts.append(fut.result())
                except Exception:
                    any_truncated = True

        seg_sum = sum(counts)
        segment_total += seg_sum
        lookups_left -= len(batch)
        metrics_list.append(
            DifyDatasetKbMetric(
                id=ds_id,
                name=ds_name,
                segment_count=seg_sum,
                truncated=doc_trunc or (len(counts) < len(batch)),
            )
        )

    return DifyKbMetrics(
        configured=True,
        dataset_count=len(datasets),
        segment_total=segment_total,
        datasets=metrics_list,
        error=None,
        truncated=any_truncated,
    )
