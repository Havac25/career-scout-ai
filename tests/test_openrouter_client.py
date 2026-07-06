import json

import pytest

from career_scout_ai.llm.openrouter_client import OPENROUTER_BASE_URL, OpenRouterClient

COMPLETIONS_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
AUTH_URL = f"{OPENROUTER_BASE_URL}/auth/key"


@pytest.fixture
def client() -> OpenRouterClient:
    return OpenRouterClient(
        api_key="test-api-key",
        model="google/gemini-2.5-flash-preview-05-20",
        timeout=30,
        max_retries=2,
    )


def _completion_body(score: float, summary: str) -> dict:
    return {
        "id": "gen-test",
        "object": "chat.completion",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({"score": score, "summary": summary}),
                },
                "finish_reason": "stop",
            }
        ],
    }


class TestParseResponse:
    def test_valid_json(self, client: OpenRouterClient):
        content = json.dumps({"score": 0.85, "summary": "Great fit for ML role."})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 0.85
        assert result.summary == "Great fit for ML role."

    def test_clamps_score_above_1(self, client: OpenRouterClient):
        content = json.dumps({"score": 1.5, "summary": "Too high"})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 1.0

    def test_clamps_score_below_0(self, client: OpenRouterClient):
        content = json.dumps({"score": -0.3, "summary": "Too low"})
        result = client._parse_response(content)
        assert result is not None
        assert result.score == 0.0

    def test_invalid_json(self, client: OpenRouterClient):
        result = client._parse_response("not json at all")
        assert result is None

    def test_missing_score(self, client: OpenRouterClient):
        content = json.dumps({"summary": "No score field"})
        result = client._parse_response(content)
        assert result is None

    def test_missing_summary(self, client: OpenRouterClient):
        content = json.dumps({"score": 0.5})
        result = client._parse_response(content)
        assert result is None


class TestScoreOffer:
    def test_success(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(
            url=COMPLETIONS_URL,
            method="POST",
            json=_completion_body(0.72, "Strong ML engineering role."),
        )

        result = client.score_offer("system prompt", "user prompt")
        assert result is not None
        assert result.score == 0.72
        assert result.summary == "Strong ML engineering role."

    def test_retries_on_server_error(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(url=COMPLETIONS_URL, method="POST", status_code=500)
        httpx_mock.add_response(
            url=COMPLETIONS_URL, method="POST", json=_completion_body(0.5, "OK")
        )

        result = client.score_offer("system", "user")
        assert result is not None
        assert result.score == 0.5

    def test_returns_none_after_all_retries_fail(
        self, client: OpenRouterClient, httpx_mock
    ):
        for _ in range(client.max_retries):
            httpx_mock.add_response(url=COMPLETIONS_URL, method="POST", status_code=500)

        result = client.score_offer("system", "user")
        assert result is None

    def test_no_retry_on_auth_error(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(url=COMPLETIONS_URL, method="POST", status_code=401)

        result = client.score_offer("system", "user")
        assert result is None
        assert len(httpx_mock.get_requests()) == 1

    def test_no_retry_on_forbidden(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(url=COMPLETIONS_URL, method="POST", status_code=403)

        result = client.score_offer("system", "user")
        assert result is None
        assert len(httpx_mock.get_requests()) == 1

    def test_retries_on_invalid_json_response(
        self, client: OpenRouterClient, httpx_mock
    ):
        httpx_mock.add_response(
            url=COMPLETIONS_URL,
            method="POST",
            json={
                "choices": [{"message": {"role": "assistant", "content": "not json"}}]
            },
        )
        httpx_mock.add_response(
            url=COMPLETIONS_URL,
            method="POST",
            json=_completion_body(0.9, "Excellent"),
        )

        result = client.score_offer("system", "user")
        assert result is not None
        assert result.score == 0.9


class TestIsAvailable:
    def test_available(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(
            url=AUTH_URL,
            method="GET",
            json={"data": {"label": "test-key", "usage": 0}},
        )
        assert client.is_available() is True

    def test_unavailable_on_api_error(self, client: OpenRouterClient, httpx_mock):
        httpx_mock.add_response(url=AUTH_URL, method="GET", status_code=401)
        assert client.is_available() is False

    def test_unavailable_when_no_api_key(self, httpx_mock):
        client_no_key = OpenRouterClient(api_key="")
        assert client_no_key.is_available() is False
        # Should not even attempt an HTTP call
        assert len(httpx_mock.get_requests()) == 0
