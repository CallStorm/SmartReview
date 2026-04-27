"""Manual diagnostic script for Dify dataset API connectivity.

Usage examples:
  python scripts/test_dify_datasets.py --base-url http://10.73.2.13/v1 --api-key xxx
  python scripts/test_dify_datasets.py --base-url http://10.73.2.13/v1 --api-key xxx --insecure

Environment fallback:
  DIFY_BASE_URL
  DIFY_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import httpx


def _mask_key(key: str) -> str:
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _build_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/datasets"


def _print_json_preview(data: Any, limit: int) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > limit:
        print(text[:limit])
        print(f"\n... (truncated, total {len(text)} chars)")
        return
    print(text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Dify /datasets endpoint manually.")
    parser.add_argument("--base-url", default=os.getenv("DIFY_BASE_URL", "").strip())
    parser.add_argument("--api-key", default=os.getenv("DIFY_API_KEY", "").strip())
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--insecure", action="store_true", help="Disable TLS certificate verification")
    parser.add_argument(
        "--preview-chars",
        type=int,
        default=1200,
        help="Max chars to print from response body/JSON",
    )
    args = parser.parse_args()

    base_url = args.base_url.strip()
    api_key = args.api_key.strip()

    if not base_url:
        print("ERROR: missing --base-url and DIFY_BASE_URL is empty")
        return 2
    if not api_key:
        print("ERROR: missing --api-key and DIFY_API_KEY is empty")
        return 2

    url = _build_url(base_url)
    params = {"page": args.page, "limit": args.limit}
    headers = {"Authorization": f"Bearer {api_key}"}

    print("=== Dify Manual Check ===")
    print(f"URL: {url}")
    print(f"Params: {params}")
    print(f"API Key: {_mask_key(api_key)}")
    print(f"Timeout: {args.timeout}s")
    print(f"TLS Verify: {not args.insecure}")
    print("-" * 60)

    try:
        with httpx.Client(timeout=args.timeout, verify=not args.insecure) as client:
            resp = client.get(url, headers=headers, params=params)
    except httpx.ConnectError as exc:
        print(f"CONNECT ERROR: {exc}")
        return 1
    except httpx.TimeoutException as exc:
        print(f"TIMEOUT: {exc}")
        return 1
    except httpx.RequestError as exc:
        print(f"REQUEST ERROR: {exc}")
        return 1

    print(f"HTTP Status: {resp.status_code}")
    print(f"Content-Type: {resp.headers.get('content-type', '(none)')}")
    print("-" * 60)

    body_text = resp.text or ""
    try:
        data = resp.json()
        print("Response JSON preview:")
        _print_json_preview(data, args.preview_chars)
    except ValueError:
        print("Response text preview:")
        print(body_text[: args.preview_chars] or "(empty body)")
        if len(body_text) > args.preview_chars:
            print(f"\n... (truncated, total {len(body_text)} chars)")

    print("-" * 60)
    if resp.status_code == 200:
        if isinstance(resp.json(), dict) and isinstance(resp.json().get("data"), list):
            print(f"SUCCESS: dataset count in this page = {len(resp.json()['data'])}")
        else:
            print("SUCCESS: status 200, but response format is unexpected")
        return 0

    if resp.status_code in (401, 403):
        print("HINT: API Key is invalid or lacks dataset permission.")
    elif resp.status_code == 502:
        print("HINT: Dify upstream/gateway is failing (not usually a client bug).")
    elif resp.status_code >= 500:
        print("HINT: Dify server-side error.")
    else:
        print("HINT: Check request params, base URL suffix (/v1), and API key type.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
