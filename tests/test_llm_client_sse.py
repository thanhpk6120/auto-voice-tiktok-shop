"""Regression: llm_client phai parse duoc body SSE cua server that.

Server that (192.168.1.68:20128) tra Content-Type: text/event-stream voi body
 dang:  {json object day du}data: [DONE]
json.loads() se vỡ ("Extra data") -> moi lô LLM rơi ve _local_fallback_items,
app chi chay duong template, khong bao gio goi duoc LLM that.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import llm_client  # noqa: E402


def test_parse_plain_json_body():
    body = {"choices": [{"message": {"content": "xin chào"}}]}
    assert llm_client._parse_response(json.dumps(body)) == body


def test_parse_sse_body_with_done_marker():
    """Body that cua server that: JSON object + 'data: [DONE]'."""
    body = {
        "choices": [{"finish_reason": "stop", "index": 0,
                     "message": {"content": "Pong", "role": "assistant"}}],
        "usage": {"completion_tokens": 12},
    }
    raw = json.dumps(body) + "data: [DONE]\n\n"
    assert llm_client._parse_response(raw) == body


def test_parse_sse_body_with_prefixed_chunks():
    """Trường hợp server bo chunk 'data: ' truoc moi JSON."""
    body = {"choices": [{"message": {"content": "Pong"}}]}
    raw = "data: " + json.dumps(body) + "\n\ndata: [DONE]\n\n"
    assert llm_client._parse_response(raw) == body


def test_parse_empty_body_raises():
    try:
        llm_client._parse_response("   ")
    except ValueError:
        return
    raise AssertionError("body rong phai raise ValueError")


def test_extract_content_from_message():
    body = {"choices": [{"message": {"content": "câu thoại"}}]}
    assert llm_client._extract_content(body) == "câu thoại"


def test_extract_content_from_stream_delta():
    body = {"choices": [{"delta": {"content": "từ delta"}}]}
    assert llm_client._extract_content(body) == "từ delta"


def test_extract_content_missing_choices_raises():
    try:
        llm_client._extract_content({"usage": {}})
    except ValueError:
        return
    raise AssertionError("response khong co choices phai raise ValueError")
