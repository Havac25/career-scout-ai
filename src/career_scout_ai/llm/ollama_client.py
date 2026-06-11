import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ScoringResult:
    score: float
    summary: str


class OllamaClient:
    """HTTP client for local Ollama instance."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        timeout: int = 120,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def score_offer(self, system_prompt: str, user_prompt: str) -> ScoringResult | None:
        """Call Ollama to score an offer. Returns None if all retries fail."""
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._call(system_prompt, user_prompt)
                if result is not None:
                    return result
                logger.warning(
                    "Attempt %d/%d: invalid response format",
                    attempt,
                    self.max_retries,
                )
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                logger.warning("Attempt %d/%d failed: %s", attempt, self.max_retries, e)

            if attempt < self.max_retries:
                backoff = 2**attempt
                time.sleep(backoff)

        logger.error("All %d attempts failed, skipping offer", self.max_retries)
        return None

    def _call(self, system_prompt: str, user_prompt: str) -> ScoringResult | None:
        """Make a single request to Ollama /api/chat with structured output."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "format": {
                "type": "object",
                "properties": {
                    "score": {"type": "number"},
                    "summary": {"type": "string"},
                },
                "required": ["score", "summary"],
            },
            "stream": False,
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()

        data = response.json()
        content = data.get("message", {}).get("content", "")

        return self._parse_response(content)

    def _parse_response(self, content: str) -> ScoringResult | None:
        """Parse JSON response into ScoringResult."""
        import json

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON: %s", content[:200])
            return None

        score = parsed.get("score")
        summary = parsed.get("summary")

        if score is None or summary is None:
            logger.warning("Missing fields in response: %s", parsed)
            return None

        # Clamp score to valid range
        score = max(0.0, min(1.0, float(score)))

        return ScoringResult(score=score, summary=summary)

    def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return bool(resp.status_code == 200)
        except (httpx.HTTPError, httpx.TimeoutException):
            return False
