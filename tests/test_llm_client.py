"""LLM 客户端网络层重试单元测试。"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIStatusError, RateLimitError

from llm.llm_client import _create_completion_with_retry


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    return httpx.Response(status_code, request=request)


def _make_completion(content: str = '{"ok": true}') -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    response = MagicMock()
    response.choices = [choice]
    return response


def test_create_completion_retries_on_rate_limit(monkeypatch):
    monkeypatch.setattr("config.LLM_NETWORK_MAX_RETRIES", 3)
    monkeypatch.setattr("config.LLM_NETWORK_RETRY_BASE_DELAY", 0.01)

    client = MagicMock()
    rate_limit_exc = RateLimitError(
        "rate limited",
        response=_make_response(429),
        body=None,
    )
    success = _make_completion()
    client.chat.completions.create.side_effect = [rate_limit_exc, rate_limit_exc, success]

    with patch("llm.llm_client.time.sleep"):
        result = _create_completion_with_retry(client, model="deepseek-chat", messages=[])

    assert result is success
    assert client.chat.completions.create.call_count == 3


def test_create_completion_does_not_retry_on_4xx(monkeypatch):
    monkeypatch.setattr("config.LLM_NETWORK_MAX_RETRIES", 3)
    monkeypatch.setattr("config.LLM_NETWORK_RETRY_BASE_DELAY", 0.01)

    client = MagicMock()
    auth_exc = APIStatusError(
        "unauthorized",
        response=_make_response(401),
        body=None,
    )
    client.chat.completions.create.side_effect = auth_exc

    with patch("llm.llm_client.time.sleep") as sleep_mock:
        with pytest.raises(APIStatusError):
            _create_completion_with_retry(client, model="deepseek-chat", messages=[])

    assert client.chat.completions.create.call_count == 1
    sleep_mock.assert_not_called()
