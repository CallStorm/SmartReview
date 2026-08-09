from __future__ import annotations

import json
from typing import Any

import httpx


def _truncate(s: str, n: int = 500) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _to_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except Exception:
        return None


def _extract_usage(data: dict[str, Any]) -> dict[str, int | None]:
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {"input_tokens": None, "output_tokens": None, "total_tokens": None}
    input_tokens = _to_int(usage.get("input_tokens"))
    output_tokens = _to_int(usage.get("output_tokens"))
    total_tokens = (input_tokens or 0) + (output_tokens or 0)
    if input_tokens is None and output_tokens is None:
        total_tokens = None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _messages_url(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1"):
        return f"{root}/messages"
    return f"{root}/v1/messages"


def _normalize_block_type(block: dict[str, Any]) -> str:
    t = block.get("type")
    if isinstance(t, str):
        return t.strip().lower()
    return ""


def _text_from_text_block(block: dict[str, Any]) -> str:
    """Anthropic / MiniMax: { type: text, text: str }；兼容嵌套或别名字段。"""
    raw = block.get("text")
    if isinstance(raw, str) and raw.strip():
        return raw
    if isinstance(raw, list):
        return _collect_text_from_blocks(raw)
    alt = block.get("content")
    if isinstance(alt, str) and alt.strip():
        return alt
    if isinstance(alt, list):
        return _collect_text_from_blocks(alt)
    return ""


def _collect_text_from_blocks(blocks: Any) -> str:
    """遍历 content 块列表：跳过 thinking，拼接所有 text 块（与 SDK 遍历 message.content 一致）。"""
    if blocks is None:
        return ""
    if isinstance(blocks, str):
        return blocks.strip()
    if isinstance(blocks, dict):
        bt = _normalize_block_type(blocks)
        if bt == "thinking":
            return ""
        if bt == "text":
            return _text_from_text_block(blocks)
        if bt == "tool_use":
            return ""
        inner = blocks.get("content")
        if inner is not None:
            return _collect_text_from_blocks(inner)
        return ""
    if not isinstance(blocks, list):
        return ""
    parts: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        bt = _normalize_block_type(block)
        if bt == "thinking" or bt == "redacted_thinking":
            continue
        if bt == "text":
            s = _text_from_text_block(block)
            if s:
                parts.append(s)
        elif bt == "tool_use":
            continue
        else:
            inner = block.get("content")
            if inner is not None:
                sub = _collect_text_from_blocks(inner)
                if sub:
                    parts.append(sub)
    return "".join(parts).strip()


def _content_list_from_response(data: dict[str, Any]) -> Any:
    """兼容顶层 content、message.content、以及部分网关的 data/result 包装。"""
    if "content" in data and data["content"] is not None:
        return data["content"]
    for wrap_key in ("message", "data", "result", "response"):
        sub = data.get(wrap_key)
        if isinstance(sub, dict) and sub.get("content") is not None:
            return sub["content"]
    return None


# 结构化审核结果：强制 LLM 通过 tool_use 提交，避免自由文本解析失败。
REVIEW_TOOL_NAME = "submit_review_result"
REVIEW_TOOL_SCHEMA: dict[str, Any] = {
    "name": REVIEW_TOOL_NAME,
    "description": "Submit structured review result for one chapter/section",
    "input_schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "summary": {"type": "string"},
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {
                            "type": "string",
                            "enum": ["error", "warning", "info"],
                        },
                        "message": {"type": "string"},
                        "evidence": {"type": "string"},
                        "related": {"type": "object"},
                    },
                    "required": ["severity", "message"],
                },
            },
        },
        "required": ["passed", "summary", "issues"],
    },
}


def _find_tool_use_input(blocks: Any, tool_name: str) -> dict[str, Any] | None:
    """遍历 content 块，匹配指定 name 的 tool_use 并返回其 input 字段。

    支持嵌套结构（网关可能包了一层 data/message/result/response）。未找到返回 None。
    """
    if blocks is None:
        return None

    def _walk(node: Any) -> dict[str, Any] | None:
        if isinstance(node, list):
            for item in node:
                got = _walk(item)
                if got is not None:
                    return got
            return None
        if not isinstance(node, dict):
            return None
        # 1) 节点本身就是 tool_use 块
        if _normalize_block_type(node) == "tool_use" and node.get("name") == tool_name:
            inp = node.get("input")
            if isinstance(inp, dict):
                return inp
        # 2) Anthropic 标准 content 字段
        if "content" in node and node["content"] is not None:
            got = _walk(node["content"])
            if got is not None:
                return got
        # 3) 网关常见的包装键（data/message/result/response）
        for wrap_key in ("data", "message", "result", "response"):
            sub = node.get(wrap_key)
            if isinstance(sub, dict):
                got = _walk(sub)
                if got is not None:
                    return got
        return None

    return _walk(blocks)


def chat_anthropic_messages(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    timeout: float = 60.0,
    include_usage: bool = False,
) -> str | tuple[str, dict[str, int | None]]:
    url = _messages_url(base_url)
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_message}],
            }
        ],
    }
    if system.strip():
        payload["system"] = system.strip()
    # 结构化任务：与 OpenAI 兼容路径保持一致，固定 temperature=0 抑制采样随机性，
    # 配合 tool_use 强制 JSON 输出，最大化确定性。Anthropic / MiniMax 网关均支持。
    payload["temperature"] = 0
    # 结构化任务：强制 tool_use，模型必须通过指定 schema 提交 JSON。
    # 若 provider / MiniMax 网关不支持，会在响应里走 text 降级路径（见下方）。
    payload["tools"] = [REVIEW_TOOL_SCHEMA]
    payload["tool_choice"] = {"type": "tool", "name": REVIEW_TOOL_NAME}
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        detail = ""
        try:
            detail = _truncate(e.response.text or "")
        except Exception:
            detail = ""
        raise ValueError(f"HTTP {e.response.status_code}{': ' + detail if detail else ''}") from e

    try:
        data = r.json()
    except json.JSONDecodeError as e:
        raise ValueError("响应不是合法 JSON") from e

    if not isinstance(data, dict):
        raise ValueError("响应根节点不是 JSON 对象")

    raw_content = _content_list_from_response(data)
    # 优先：tool_use.input 是结构化 JSON，序列化后给上游 extract_json_object 解析。
    tool_input = _find_tool_use_input(raw_content, REVIEW_TOOL_NAME)
    if tool_input is not None:
        text = json.dumps(tool_input, ensure_ascii=False)
        if include_usage:
            return text, _extract_usage(data)
        return text
    # 降级：老路径（text block），网关不支持 tool_use 时仍能跑通。
    text = _collect_text_from_blocks(raw_content)
    if not text:
        raise ValueError(
            "响应中未找到文本内容（可能仅有 thinking 块或网关返回结构与 Anthropic Messages 不一致）"
        )
    if include_usage:
        return text, _extract_usage(data)
    return text
