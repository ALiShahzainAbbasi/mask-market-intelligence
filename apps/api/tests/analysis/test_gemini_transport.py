from __future__ import annotations

from dataclasses import dataclass

import pytest
from mask_api.modules.analysis.gemini import GeminiError, UrllibGeminiTransport
from pydantic import SecretStr

KEY = SecretStr("fixture-not-a-real-key")


class FakeResponse:
    """Simulates a real stream: each read() call advances a cursor and
    returns b"" at EOF, matching http.client.HTTPResponse's contract."""

    status = 200
    headers = {"Content-Type": "application/json; charset=UTF-8"}

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._position = 0

    def read(self, limit: int) -> bytes:
        chunk = self._body[self._position : self._position + limit]
        self._position += len(chunk)
        return chunk

    def close(self) -> None:
        return None


@dataclass
class FakeOpener:
    response: object

    def open(self, request: object, timeout: float) -> object:
        self.last_request = request
        self.last_timeout = timeout
        return self.response


def transport(response: object) -> tuple[UrllibGeminiTransport, FakeOpener]:
    edge = UrllibGeminiTransport()
    opener = FakeOpener(response)
    edge._opener = opener  # type: ignore[assignment]
    return edge, opener


def test_generate_content_posts_to_the_exact_model_endpoint_with_the_key_as_a_query_param() -> None:
    body = b'{"candidates": []}'
    edge, opener = transport(FakeResponse(body))

    result = edge.generate_content(
        {"contents": []},
        model="gemini-flash-lite-latest",
        api_key=KEY,
        timeout_seconds=10,
        max_bytes=1_000_000,
    )

    assert result.status_code == 200
    assert result.body == body
    sent = opener.last_request
    assert sent.get_method() == "POST"  # type: ignore[attr-defined]
    assert sent.full_url.startswith(  # type: ignore[attr-defined]
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key="
    )
    assert "fixture-not-a-real-key" in sent.full_url  # type: ignore[attr-defined]


def test_generate_content_never_puts_the_key_in_the_request_body() -> None:
    edge, opener = transport(FakeResponse(b"{}"))

    edge.generate_content(
        {"contents": [{"role": "user", "parts": [{"text": "hello"}]}]},
        model="gemini-flash-lite-latest",
        api_key=KEY,
        timeout_seconds=10,
        max_bytes=1_000_000,
    )

    sent_body = opener.last_request.data  # type: ignore[attr-defined]
    assert b"fixture-not-a-real-key" not in sent_body


def test_generate_content_reassembles_a_body_delivered_across_many_small_reads() -> None:
    body = b'{"candidates": [{"content": {"parts": [{"text": "x"}]}}]}' * 2000
    edge, _ = transport(FakeResponse(body))

    result = edge.generate_content(
        {"contents": []},
        model="gemini-flash-lite-latest",
        api_key=KEY,
        timeout_seconds=10,
        max_bytes=len(body) + 1,
    )

    assert result.body == body


def test_generate_content_rejects_a_body_larger_than_the_byte_cap() -> None:
    edge, _ = transport(FakeResponse(b"x" * 20))

    with pytest.raises(GeminiError) as captured:
        edge.generate_content(
            {"contents": []},
            model="gemini-flash-lite-latest",
            api_key=KEY,
            timeout_seconds=10,
            max_bytes=10,
        )

    assert captured.value.code == "gemini.response_too_large"
