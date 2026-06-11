import json

import pytest

from career_scout_ai.llm.ollama_client import OllamaClient


@pytest.fixture
def client() -> OllamaClient:
    return OllamaClient(
        base_url="http://localhost:11434",
        model="qwen3:8b",
        timeout=30,
        max_retries=2,
    )


class TestParseResponse:
    def test_valid_json(self, client: OllamaClient):
        content = json.dumps({"score": 0.85, "summary": "Great fit for ML role."})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 0.85
        assert result.summary == "Great fit for ML role."

    def test_clamps_score_above_1(self, client: OllamaClient):
        content = json.dumps({"score": 1.5, "summary": "Too high"})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 1.0

    def test_clamps_score_below_0(self, client: OllamaClient):
        content = json.dumps({"score": -0.3, "summary": "Too low"})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 0.0

    def test_invalid_json(self, client: OllamaClient):
        result = client._parse_response("not json at all")
        assert result is None

    def test_missing_score(self, client: OllamaClient):
        content = json.dumps({"summary": "No score field"})
        result = client._parse_response(content)
        assert result is None

    def test_missing_summary(self, client: OllamaClient):
        content = json.dumps({"score": 0.5})
        result = client._parse_response(content)
        assert result is None


class TestScoreOffer:
    def test_success(self, client: OllamaClient, httpx_mock):
        response_body = {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"score": 0.72, "summary": "Strong ML engineering role."}
                ),
            },
            "done": True,
        }
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            json=response_body,
        )

        result = client.score_offer("system prompt", "user prompt")
        assert result is not None
        assert result.score == 0.72
        assert result.summary == "Strong ML engineering role."

    def test_retries_on_http_error(self, client: OllamaClient, httpx_mock):
        # First call fails, second succeeds
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            status_code=500,
        )
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"score": 0.5, "summary": "OK"}),
                },
                "done": True,
            },
        )

        result = client.score_offer("system", "user")
        assert result is not None
        assert result.score == 0.5

    def test_returns_none_after_all_retries_fail(
        self, client: OllamaClient, httpx_mock
    ):
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            status_code=500,
        )
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            status_code=500,
        )

        result = client.score_offer("system", "user")
        assert result is None

    def test_retries_on_invalid_json_response(self, client: OllamaClient, httpx_mock):
        # First: invalid JSON, second: valid
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            json={
                "message": {"role": "assistant", "content": "not json"},
                "done": True,
            },
        )
        httpx_mock.add_response(
            url="http://localhost:11434/api/chat",
            method="POST",
            json={
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"score": 0.9, "summary": "Excellent"}),
                },
                "done": True,
            },
        )

        result = client.score_offer("system", "user")
        assert result is not None
        assert result.score == 0.9


class TestIsAvailable:
    def test_available(self, client: OllamaClient, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags",
            method="GET",
            json={"models": []},
        )
        assert client.is_available() is True

    def test_unavailable(self, client: OllamaClient, httpx_mock):
        httpx_mock.add_response(
            url="http://localhost:11434/api/tags",
            method="GET",
            status_code=500,
        )
        assert client.is_available() is False
